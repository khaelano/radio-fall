//! Receiver heartbeat evidence for the ordered, configured sensing slots.
use crate::wire::{u16be, u32be, u64be};
use std::collections::BTreeMap;

/// Validated CGST v1 receiver status, distinct from packet validity/coverage.
#[derive(Clone, Debug)]
pub struct Status {
    pub slot: usize,
    pub run: u64,
    pub transmitter_boot: u32,
    pub boot: u32,
    pub state: u8,
    pub queue_event_loss: bool,
    pub captured: u32,
    pub dropped: u32,
    pub expired: u32,
    pub queued: u16,
    pub peak: u16,
    pub send_errors: u32,
    pub grant: u32,
    pub transition_grant: u32,
    pub departed_us: u64,
    pub returned_us: u64,
}
impl Status {
    pub fn decode(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() != 96
            || &bytes[..4] != b"CGST"
            || bytes[4] != 1
            || bytes[5] >= 4
            || crc32fast::hash(&bytes[..92]) != u32be(bytes, 92)
        {
            return Err("invalid receiver status".into());
        }
        Ok(Self {
            slot: bytes[5] as usize,
            run: u64be(bytes, 8),
            transmitter_boot: u32be(bytes, 16),
            boot: u32be(bytes, 20),
            state: bytes[6],
            queue_event_loss: bytes[7] != 0,
            captured: u32be(bytes, 72),
            dropped: u32be(bytes, 76),
            expired: u32be(bytes, 80),
            queued: u16be(bytes, 84),
            peak: u16be(bytes, 86),
            send_errors: u32be(bytes, 88),
            grant: u32be(bytes, 24),
            transition_grant: u32be(bytes, 28),
            departed_us: u64be(bytes, 56),
            returned_us: u64be(bytes, 64),
        })
    }
}

/// Boot identities are accepted only from current-run transmitter-validated events.
pub struct Ledger {
    run: u64,
    transmitter_boot: u32,
    ordered_macs: [String; 4],
    status: [Option<(Status, u64)>; 4],
    timeout_ns: u64,
    failed: bool,
}
impl Ledger {
    pub fn new(
        run: u64,
        transmitter_boot: u32,
        ordered_macs: [String; 4],
        timeout_ns: u64,
    ) -> Result<Self, String> {
        let unique: std::collections::BTreeSet<_> = ordered_macs.iter().collect();
        if run == 0
            || timeout_ns == 0
            || unique.len() != 4
            || ordered_macs.iter().any(String::is_empty)
        {
            return Err("invalid receiver ledger identities".into());
        }
        Ok(Self {
            run,
            transmitter_boot,
            ordered_macs,
            status: std::array::from_fn(|_| None),
            timeout_ns,
            failed: false,
        })
    }
    /// Ignore old runs, latch boot/transmitter changes, and retain only latest status.
    pub fn observe(&mut self, bytes: &[u8], arrival_ns: u64) -> Result<bool, String> {
        if self.failed {
            return Err("receiver ledger failed; new run required".into());
        }
        let status = Status::decode(bytes)?;
        if status.run != self.run {
            return Ok(false);
        }
        let slot = status.slot;
        if status.transmitter_boot != self.transmitter_boot
            || self.status[slot]
                .as_ref()
                .is_some_and(|(old, time)| old.boot != status.boot || arrival_ns < *time)
        {
            self.failed = true;
            return Err("receiver/transmitter boot or clock discontinuity".into());
        }
        self.status[slot] = Some((status, arrival_ns));
        Ok(true)
    }
    /// Latest status and its arrival time for each configured slot, in slot order.
    pub fn latest(&self) -> [Option<(Status, u64)>; 4] {
        self.status.clone()
    }

    /// Configured receiver MAC addresses in slot order.
    pub fn macs(&self) -> &[String; 4] {
        &self.ordered_macs
    }

    /// Require fresh evidence for every slot before constructing batch acceptance.
    pub fn verified_boots(&self, now_ns: u64) -> Result<BTreeMap<String, u32>, String> {
        if self.failed {
            return Err("receiver ledger failed".into());
        }
        let mut boots = BTreeMap::new();
        for (mac, status) in self.ordered_macs.iter().zip(&self.status) {
            let (status, arrival) = status.as_ref().ok_or("receiver status missing")?;
            if now_ns < *arrival || now_ns - *arrival > self.timeout_ns || status.queue_event_loss {
                return Err("receiver status stale or queue-event history lost".into());
            }
            boots.insert(mac.clone(), status.boot);
        }
        Ok(boots)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn status(slot: u8, boot: u32) -> Vec<u8> {
        let mut bytes = vec![0; 96];
        bytes[..4].copy_from_slice(b"CGST");
        bytes[4] = 1;
        bytes[5] = slot;
        bytes[8..16].copy_from_slice(&1u64.to_be_bytes());
        bytes[16..20].copy_from_slice(&2u32.to_be_bytes());
        bytes[20..24].copy_from_slice(&boot.to_be_bytes());
        let crc = crc32fast::hash(&bytes[..92]);
        bytes[92..].copy_from_slice(&crc.to_be_bytes());
        bytes
    }
    #[test]
    fn four_slot_freshness_and_reboot_invalidation() {
        let mut ledger =
            Ledger::new(1, 2, std::array::from_fn(|i| format!("rx-{i}")), 100).unwrap();
        assert!(ledger.verified_boots(10).is_err());
        for i in 0..4 {
            ledger.observe(&status(i, i as u32 + 10), 10).unwrap();
        }
        assert_eq!(ledger.verified_boots(110).unwrap().len(), 4);
        assert!(ledger.verified_boots(111).is_err());
        assert!(ledger.observe(&status(0, 99), 20).is_err());
        assert!(ledger.verified_boots(20).is_err());
    }
}
