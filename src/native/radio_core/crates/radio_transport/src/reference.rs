//! Continuous correlated clock and authoritative transmitter-round validation.
use crate::{
    clock::{Estimate, Estimator, Sample},
    wire::{u32be, u64be},
};

/// Native reference state. The acquisition owner sends returned CGHC payloads.
pub struct Reference {
    run: u64,
    boot: u32,
    drops: u32,
    rate_hz: u32,
    next_round: u32,
    next_sync: u32,
    pending: Option<(u32, u64)>,
    estimator: Estimator,
    estimate: Estimate,
    last_clock_ns: u64,
    last_round_ns: Option<u64>,
    interval_ns: u64,
    timeout_ns: u64,
    failed: bool,
}

/// Verified authoritative round; enqueue time is distinct from delivery time.
pub struct Round {
    pub sequence: u32,
    pub enqueue_us: u64,
    pub scheduled_us: u64,
    pub result: u32,
    pub owners: [u8; 3],
}

impl Reference {
    /// Continue a preflight estimator and require explicit freshness policy.
    pub fn new(
        run: u64,
        drops: u32,
        rate_hz: u32,
        estimator: Estimator,
        estimate: Estimate,
        now_ns: u64,
        policy: (u64, u64),
    ) -> Result<Self, String> {
        if run == 0 || rate_hz == 0 || rate_hz > 1_000_000 || policy.0 == 0 || policy.1 <= policy.0
        {
            return Err("invalid reference policy".into());
        }
        Ok(Self {
            run,
            boot: estimate.boot,
            drops,
            rate_hz,
            next_round: 0,
            next_sync: 8,
            pending: None,
            estimator,
            estimate,
            last_clock_ns: now_ns,
            last_round_ns: None,
            interval_ns: policy.0,
            timeout_ns: policy.1,
            failed: false,
        })
    }
    /// Request at most one periodic exchange; callers must immediately send it.
    pub fn request(&mut self, now_ns: u64) -> Result<Option<Vec<u8>>, String> {
        self.check(now_ns)?;
        if self.pending.is_some() || now_ns - self.last_clock_ns < self.interval_ns {
            return Ok(None);
        }
        let id = self.next_sync;
        self.next_sync = self.next_sync.wrapping_add(1);
        let t1 = now_ns / 1000;
        self.pending = Some((id, t1));
        let mut payload = b"CGHC".to_vec();
        payload.extend_from_slice(&id.to_be_bytes());
        payload.extend_from_slice(&t1.to_be_bytes());
        Ok(Some(payload))
    }
    /// Accept only the response correlated with the currently pending exchange.
    pub fn response(&mut self, bytes: &[u8], now_ns: u64) -> Result<bool, String> {
        let Some((id, t1)) = self.pending else {
            return Ok(false);
        };
        if bytes.len() != 40
            || &bytes[..4] != b"CGHC"
            || u32be(bytes, 4) != id
            || u64be(bytes, 8) != t1
        {
            return Ok(false);
        }
        self.check(now_ns)?;
        if u32be(bytes, 32) != self.boot || u32be(bytes, 36) != self.drops {
            self.failed = true;
            return Err("reference boot change or log loss".into());
        }
        self.estimate = self.estimator.add(Sample {
            boot: self.boot,
            t1,
            t2: u64be(bytes, 16),
            t3: u64be(bytes, 24),
            t4: now_ns / 1000,
        })?;
        self.pending = None;
        self.last_clock_ns = now_ns;
        Ok(true)
    }
    /// Validate the current run's contiguous round log, including explicit skips.
    pub fn round(&mut self, bytes: &[u8], now_ns: u64) -> Result<Option<Round>, String> {
        self.check(now_ns)?;
        if bytes.len() != 51 || &bytes[..4] != b"CGRD" {
            return Err("invalid round log".into());
        }
        if u64be(bytes, 4) != self.run {
            return Ok(None);
        }
        let sequence = u32be(bytes, 16);
        let result = u32be(bytes, 40);
        if u32be(bytes, 12) != self.boot
            || sequence != self.next_round
            || u32be(bytes, 44) != self.drops
            || u32be(bytes, 36) != 1_000_000 / self.rate_hz
        {
            self.failed = true;
            return Err("round sequence/boot/rate/drop mismatch".into());
        }
        let step = if result & 0x80000000 != 0 {
            result & 0x7fffffff
        } else {
            1
        };
        if step == 0 {
            self.failed = true;
            return Err("invalid skipped-round count".into());
        }
        self.next_round = sequence.wrapping_add(step);
        self.last_round_ns = Some(now_ns);
        Ok(Some(Round {
            sequence,
            enqueue_us: u64be(bytes, 20),
            scheduled_us: u64be(bytes, 28),
            result,
            owners: bytes[48..51].try_into().unwrap(),
        }))
    }
    /// Transmitter boot bound at preflight.
    pub fn boot(&self) -> u32 {
        self.boot
    }

    /// Lifetime transmitter round-log drops observed at preflight.
    pub fn drops(&self) -> u32 {
        self.drops
    }

    /// Configured sensing rate, which fixes the round period.
    pub fn rate_hz(&self) -> u32 {
        self.rate_hz
    }

    /// Current affine clock estimate.
    pub fn estimate(&self) -> &Estimate {
        &self.estimate
    }

    /// Whether capture mapping is currently valid at `now_ns`.
    pub fn ready(&self, now_ns: u64) -> bool {
        self.check(now_ns).is_ok() && self.last_round_ns.is_some()
    }

    /// Suppress capture mapping when clock or observed round evidence becomes stale.
    pub fn check(&self, now_ns: u64) -> Result<(), String> {
        if self.failed
            || now_ns < self.last_clock_ns
            || now_ns - self.last_clock_ns > self.timeout_ns
            || self
                .last_round_ns
                .is_some_and(|last| now_ns < last || now_ns - last > self.timeout_ns)
        {
            return Err("reference failed or stale".into());
        }
        Ok(())
    }
    /// Preserve Python's ties-to-even nanosecond rounding for mapped capture time.
    pub fn capture_ns(&self, enqueue_us: u64, now_ns: u64) -> Result<u64, String> {
        self.check(now_ns)?;
        if self.last_round_ns.is_none() {
            return Err("authoritative round evidence unavailable".into());
        }
        let value = (self.estimate.map(enqueue_us as f64)? * 1000.0).round_ties_even();
        if !value.is_finite() || value < 0.0 || value >= u64::MAX as f64 {
            return Err("mapped clock out of range".into());
        }
        Ok(value as u64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn reference() -> Reference {
        let mut estimator = Estimator::new(32, 10_000_000).unwrap();
        let estimate = estimator
            .add(Sample {
                boot: 7,
                t1: 0,
                t2: 150,
                t3: 160,
                t4: 110,
            })
            .unwrap();
        Reference::new(
            1,
            0,
            120,
            estimator,
            estimate,
            110000,
            (1_000_000, 10_000_000),
        )
        .unwrap()
    }
    fn round(sequence: u32, result: u32) -> Vec<u8> {
        let mut bytes = b"CGRD".to_vec();
        bytes.extend_from_slice(&1u64.to_be_bytes());
        bytes.extend_from_slice(&7u32.to_be_bytes());
        bytes.extend_from_slice(&sequence.to_be_bytes());
        bytes.extend_from_slice(&1000u64.to_be_bytes());
        bytes.extend_from_slice(&1000u64.to_be_bytes());
        bytes.extend_from_slice(&8333u32.to_be_bytes());
        bytes.extend_from_slice(&result.to_be_bytes());
        bytes.extend_from_slice(&0u32.to_be_bytes());
        bytes.extend_from_slice(&[0, 1, 2]);
        bytes
    }
    #[test]
    fn skipped_rounds_and_gaps_invalidate_mapping() {
        let mut reference = reference();
        assert!(reference.capture_ns(1000, 110000).is_err());
        reference.round(&round(0, 0x80000003), 110000).unwrap();
        reference.round(&round(3, 1), 120000).unwrap();
        assert_eq!(reference.capture_ns(1000, 120000).unwrap(), 900000);
        assert!(reference.round(&round(5, 1), 130000).is_err());
        assert!(reference.capture_ns(1000, 130000).is_err());
    }
    #[test]
    fn only_one_correlated_clock_request_is_pending() {
        let mut reference = reference();
        let request = reference.request(1110000).unwrap().unwrap();
        assert!(reference.request(1111000).unwrap().is_none());
        assert!(!reference.response(b"ok", 1120000).unwrap());
        let mut response = request;
        response.extend_from_slice(&1260u64.to_be_bytes());
        response.extend_from_slice(&1270u64.to_be_bytes());
        response.extend_from_slice(&7u32.to_be_bytes());
        response.extend_from_slice(&0u32.to_be_bytes());
        assert!(reference.response(&response, 1220000).unwrap());
        assert!(reference.request(1221000).unwrap().is_none());
        assert!(reference.check(12000000).is_err());
    }
}
