//! Reconstruct native reference state from bounded JSONL journal evidence.
use crate::{
    clock::{Estimator, Sample},
    reference::Reference,
};
use serde_json::Value;
use std::io::{BufRead, Read};

/// Read one bounded event line, rejecting truncation and oversized diagnostics.
pub fn read_event(reader: &mut impl BufRead) -> Result<Option<Value>, Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    let count = reader.take(16385).read_until(b'\n', &mut bytes)?;
    if count == 0 {
        return Ok(None);
    }
    if count > 16384 || bytes.last() != Some(&b'\n') {
        return Err("oversized or truncated event line".into());
    }
    Ok(Some(serde_json::from_slice(&bytes)?))
}
fn number(value: &Value, key: &str) -> Result<u64, String> {
    value[key]
        .as_u64()
        .ok_or_else(|| format!("missing integer event field: {key}"))
}
fn small(value: &Value, key: &str) -> Result<u32, String> {
    u32::try_from(number(value, key)?).map_err(|_| format!("event field exceeds uint32: {key}"))
}
/// Decode bounded journal hexadecimal evidence without accepting malformed bytes.
pub fn hex(value: &str) -> Result<Vec<u8>, String> {
    if value.len() > 2800 || value.len() % 2 != 0 {
        return Err("invalid frame hexadecimal length".into());
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |b: u8| {
                (b as char)
                    .to_digit(16)
                    .ok_or("invalid frame hexadecimal digit")
            };
            Ok((digit(pair[0])? * 16 + digit(pair[1])?) as u8)
        })
        .collect()
}
/// Replayed reference keeps original host-clock order and correlation rules.
pub struct ReferenceReplay {
    pub reference: Reference,
    last_ns: u64,
}
impl ReferenceReplay {
    pub fn new(initial: &Value) -> Result<Self, Box<dyn std::error::Error>> {
        if initial["kind"] != "reference_initial" {
            return Err("reference_initial event required".into());
        }
        let mut estimator = Estimator::new(32, number(initial, "minimum_drift_span_us")?)?;
        let mut estimate = None;
        for sample in initial["samples"]
            .as_array()
            .ok_or("missing initial samples")?
        {
            if small(sample, "boot")? != small(initial, "boot")? {
                return Err("initial clock boot mismatch".into());
            }
            estimate = Some(estimator.add(Sample {
                boot: small(sample, "boot")?,
                t1: number(sample, "t1")?,
                t2: number(sample, "t2")?,
                t3: number(sample, "t3")?,
                t4: number(sample, "t4")?,
            })?);
        }
        let now = number(initial, "host_monotonic_ns")?;
        let reference = Reference::new(
            initial["run"].as_str().ok_or("missing run")?.parse()?,
            small(initial, "drops")?,
            small(initial, "sample_rate_hz")?,
            estimator,
            estimate.ok_or("empty initial clock samples")?,
            now,
            (
                number(initial, "interval_ns")?,
                number(initial, "timeout_ns")?,
            ),
        )?;
        Ok(Self {
            reference,
            last_ns: now,
        })
    }
    pub fn apply(&mut self, event: &Value) -> Result<(), Box<dyn std::error::Error>> {
        let now = number(event, "host_monotonic_ns")?;
        if now < self.last_ns {
            return Err("journal event clock moved backward".into());
        }
        self.last_ns = now;
        match event["kind"].as_str().ok_or("missing event kind")? {
            "clock_request" => {
                let expected = hex(event["payload_hex"]
                    .as_str()
                    .ok_or("missing request payload")?)?;
                if self.reference.request(now)?.as_ref() != Some(&expected) {
                    return Err("replayed clock request differs from journal".into());
                }
            }
            "reference_frame" => {
                let bytes = hex(event["payload_hex"]
                    .as_str()
                    .ok_or("missing reference payload")?)?;
                match number(event, "frame_type")? {
                    21 => {
                        self.reference.response(&bytes, now)?;
                    }
                    22 => {
                        self.reference.round(&bytes, now)?;
                    }
                    _ => {}
                }
            }
            "gateway_status" | "batch_acceptance" => {}
            _ => return Err("unrecognized reference event schema".into()),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_events_and_hex_reject_corruption() {
        assert!(read_event(&mut &b"{\"kind\":\"x\"}"[..]).is_err());
        assert!(read_event(&mut &vec![b'x'; 16385][..]).is_err());
        assert!(read_event(&mut &b"\n"[..]).is_err());
        assert!(read_event(&mut &b""[..]).unwrap().is_none());
        assert!(hex("0").is_err());
        assert!(hex("gg").is_err());
        assert_eq!(hex("00aAFF").unwrap(), vec![0, 170, 255]);
        assert!(ReferenceReplay::new(&serde_json::json!({"kind":"gateway_status"})).is_err());
    }
}
