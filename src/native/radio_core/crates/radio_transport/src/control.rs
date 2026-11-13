//! Bounded synchronous startup transactions over the existing gateway relay.
use crate::{
    acquisition::FrameIo,
    framing::{Frame, encode},
};
use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};

/// Decode a single or batched wireless response without Python serial emulation.
pub fn relay_frames(payload: &[u8]) -> Result<Vec<Frame>, String> {
    let (&kind, body) = payload.split_first().ok_or("empty wireless response")?;
    if kind != 0 {
        encode(kind, body)?;
        return Ok(vec![Frame {
            kind,
            data: body.to_vec(),
        }]);
    }
    let mut offset = 0;
    let mut frames = Vec::new();
    while offset < body.len() {
        if body.len() - offset < 3 {
            return Err("truncated wireless response batch".into());
        }
        let kind = body[offset];
        let size = u16::from_be_bytes([body[offset + 1], body[offset + 2]]) as usize;
        offset += 3;
        if kind == 0 || size > body.len() - offset {
            return Err("invalid wireless response batch".into());
        }
        encode(kind, &body[offset..offset + size])?;
        frames.push(Frame {
            kind,
            data: body[offset..offset + size].to_vec(),
        });
        offset += size;
        if frames.len() > 64 {
            return Err("wireless response frame capacity exceeded".into());
        }
    }
    if frames.is_empty() {
        return Err("empty wireless response batch".into());
    }
    Ok(frames)
}

/// Serial owner during preflight. Unsolicited frames are retained with a hard bound.
pub struct Controller<T> {
    io: T,
    pending: VecDeque<(bool, Frame)>,
    failed: bool,
}

impl<T: FrameIo> Controller<T> {
    pub fn new(io: T) -> Self {
        Self {
            io,
            pending: VecDeque::new(),
            failed: false,
        }
    }

    /// Consume the controller after preflight, preserving unsolicited frames.
    pub fn into_parts(self) -> (T, VecDeque<(bool, Frame)>) {
        (self.io, self.pending)
    }

    /// Attempt both stop writes even after a failed transaction; no ACK is promised.
    pub fn stop_run(&mut self, run: u64) -> Result<(), String> {
        if run == 0 {
            return Err("invalid stop run".into());
        }
        let mut stop = b"CGSP".to_vec();
        stop.extend_from_slice(&run.to_be_bytes());
        let mut relay = vec![20];
        relay.extend_from_slice(&stop);
        let transmitter = self.io.write_frame(26, &relay);
        let gateway = self.io.write_frame(20, &stop);
        transmitter.and(gateway).map_err(|e| e.to_string())
    }

    fn transaction(
        &mut self,
        relay: bool,
        kind: u8,
        payload: &[u8],
        response_kind: u8,
        timeout: Duration,
        matches: impl Fn(&[u8]) -> bool,
    ) -> Result<Vec<u8>, String> {
        if self.failed || timeout.is_zero() {
            return Err("controller failed or invalid timeout".into());
        }
        let result = (|| {
            if relay {
                if payload.len() + 3 >= 1280 {
                    return Err("wireless command exceeds bridge limit".into());
                }
                let mut request = Vec::with_capacity(payload.len() + 1);
                request.push(kind);
                request.extend_from_slice(payload);
                self.io
                    .write_frame(26, &request)
                    .map_err(|e| e.to_string())?;
            } else {
                self.io
                    .write_frame(kind, payload)
                    .map_err(|e| e.to_string())?;
            }
            let start = Instant::now();
            loop {
                if start.elapsed() >= timeout {
                    return Err("control transaction timed out".into());
                }
                let frames = self.io.read_frames().map_err(|e| e.to_string())?;
                let mut response = None;
                for frame in frames {
                    let is_relay = frame.kind == 27;
                    let decoded = if is_relay {
                        relay_frames(&frame.data)?
                    } else {
                        vec![frame]
                    };
                    for frame in decoded {
                        if is_relay == relay
                            && frame.kind == response_kind
                            && matches(&frame.data)
                            && response.is_none()
                        {
                            response = Some(frame.data);
                        } else {
                            if self.pending.len() == 64 {
                                return Err("preflight unsolicited-frame overflow".into());
                            }
                            self.pending.push_back((is_relay, frame));
                        }
                    }
                }
                if let Some(response) = response {
                    return Ok(response);
                }
            }
        })();
        if result.is_err() {
            self.failed = true;
        }
        result
    }

    /// Discover gateway or relayed transmitter status; caller verifies identity/profile.
    pub fn discover(
        &mut self,
        relay: bool,
        timeout: Duration,
    ) -> Result<serde_json::Value, String> {
        let response = self.transaction(relay, 5, &[], 6, timeout, |_| true)?;
        serde_json::from_slice(&response).map_err(|e| e.to_string())
    }

    /// Serialize one acknowledged control command; relay receipt alone is insufficient.
    pub fn command(
        &mut self,
        relay: bool,
        payload: &[u8],
        timeout: Duration,
    ) -> Result<(), String> {
        let response = self.transaction(relay, 20, payload, 21, timeout, |r| {
            r == b"ok" || r == b"error"
        })?;
        if response != b"ok" {
            self.failed = true;
            return Err("device rejected control command".into());
        }
        Ok(())
    }

    /// Ask the gateway to restart its wireless relay epoch after a fault.
    pub fn recover_relay(&mut self, timeout: Duration) -> Result<(), String> {
        let response = self.transaction(false, 31, b"CRRC", 21, timeout, |r| {
            r == b"ok" || r == b"error"
        })?;
        if response != b"ok" {
            self.failed = true;
            return Err("gateway refused relay recovery".into());
        }
        Ok(())
    }

    /// Complete one correlated CGHC host/transmitter clock exchange via the relay.
    pub fn sync(
        &mut self,
        identity: u32,
        clock_us: impl Fn() -> u64,
    ) -> Result<(crate::clock::Sample, u32), String> {
        let t1 = clock_us();
        let mut request = Vec::with_capacity(16);
        request.extend_from_slice(b"CGHC");
        request.extend_from_slice(&identity.to_be_bytes());
        request.extend_from_slice(&t1.to_be_bytes());
        let response = self.transaction(true, 20, &request, 21, Duration::from_secs(2), |r| {
            r.len() == 40 && r[..16] == request
        })?;
        let t4 = clock_us();
        let sample = crate::clock::Sample {
            boot: crate::wire::u32be(&response, 32),
            t1,
            t2: crate::wire::u64be(&response, 16),
            t3: crate::wire::u64be(&response, 24),
            t4,
        };
        // Use the same timestamp validation as the estimator before returning.
        let mut validator = crate::clock::Estimator::new(2, 0)?;
        validator.add(sample)?;
        Ok((sample, crate::wire::u32be(&response, 36)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn relay_batch_validation_preserves_order() {
        let frames = relay_frames(&[0, 6, 0, 2, b'{', b'}', 21, 0, 2, b'o', b'k']).unwrap();
        assert_eq!(
            frames.iter().map(|f| f.kind).collect::<Vec<_>>(),
            vec![6, 21]
        );
        assert_eq!(frames[1].data, b"ok");
        for payload in [&[][..], &[0][..], &[0, 6, 0][..], &[0, 6, 0, 5, 1][..]] {
            assert!(relay_frames(payload).is_err());
        }
    }
}
