//! Per-receiver delivery quality and duplicate-capture removal for accepted batches.
//!
//! Each transmitted frame is usually captured about twice by a receiver. Only
//! the first capture of a `(run, boots, receiver, sequence, tx timestamp)`
//! identity is delivered, so a recording holds one row per sensing frame.
//! Counters are cumulative for the session; gap tracking restarts with each
//! run or receiver boot, as a new run has no sequence relationship to the last.
use crate::wire::{Batch, Record};
use serde_json::{Value, json};
use std::collections::{BTreeSet, HashSet, VecDeque};

const DEDUP_CAPACITY: usize = 2048;
const REORDER_WINDOW: u32 = 128;
const PENDING_CAPACITY: usize = 4096;

type Identity = (u64, u32, u32, u32, u64);

/// Forward-gap tracking with wraparound; returns `(missing, reordered)` deltas.
#[derive(Default)]
struct Sequence {
    last: Option<u32>,
}
impl Sequence {
    fn observe(&mut self, value: u32) -> (u64, u64) {
        let Some(last) = self.last else {
            self.last = Some(value);
            return (0, 0);
        };
        let forward = value.wrapping_sub(last);
        if 0 < forward && forward < 0x8000_0000 {
            self.last = Some(value);
            (u64::from(forward - 1), 0)
        } else if forward != 0 {
            (0, 1)
        } else {
            (0, 0)
        }
    }
}

/// Cumulative quality counters for one configured receiver slot.
#[derive(Default)]
pub struct Receiver {
    pub records: u64,
    pub batches: u64,
    pub duplicates: u64,
    pub missing_sequences: u64,
    pub transport_missing: u64,
    pub transport_reordered: u64,
    pub batch_missing: u64,
    pub batch_reordered: u64,
    pub receiver_restarts: u64,
    pub last_sequence: Option<u32>,
    pub last_record_ns: Option<u64>,
    pub boot: Option<u32>,
    pub stats: Option<[u32; 10]>,
    transport: Sequence,
    batch: Sequence,
    pending_missing: BTreeSet<u32>,
    pending_order: VecDeque<u32>,
    seen: HashSet<Identity>,
    seen_order: VecDeque<Identity>,
}

impl Receiver {
    fn reset_tracking(&mut self) {
        self.transport = Sequence::default();
        self.batch = Sequence::default();
        self.seen.clear();
        self.seen_order.clear();
    }

    fn track_record_sequence(&mut self, sequence: u32) {
        let Some(last) = self.last_sequence else {
            self.last_sequence = Some(sequence);
            return;
        };
        let forward = sequence.wrapping_sub(last);
        if 0 < forward && forward < 0x8000_0000 {
            let gap = forward - 1;
            self.missing_sequences += u64::from(gap);
            let start = gap.saturating_sub(REORDER_WINDOW - 1).max(1);
            for offset in start..=gap {
                let value = last.wrapping_add(offset);
                if self.pending_missing.insert(value) {
                    self.pending_order.push_back(value);
                }
            }
            while self.pending_order.len() > PENDING_CAPACITY {
                if let Some(old) = self.pending_order.pop_front() {
                    self.pending_missing.remove(&old);
                }
            }
            self.last_sequence = Some(sequence);
        } else if self.pending_missing.remove(&sequence) {
            self.missing_sequences = self.missing_sequences.saturating_sub(1);
        } else if forward >= 0x8000_0000 {
            // A backwards jump that is not a nearby reorder starts a new epoch.
            self.pending_missing.clear();
            self.pending_order.clear();
            self.last_sequence = Some(sequence);
        }
    }

    /// JSON counters for display and collection telemetry.
    pub fn to_json(&self, now_ns: u64) -> Value {
        json!({
            "records": self.records,
            "batches": self.batches,
            "duplicates": self.duplicates,
            "missing_sequences": self.missing_sequences,
            "transport_missing": self.transport_missing,
            "transport_reordered": self.transport_reordered,
            "batch_missing": self.batch_missing,
            "batch_reordered": self.batch_reordered,
            "receiver_restarts": self.receiver_restarts,
            "last_sequence": self.last_sequence,
            "last_record_age_ns": self.last_record_ns.map(|t| now_ns.saturating_sub(t)),
            "boot_id": self.boot,
            "stats": self.stats,
        })
    }
}

/// Quality state for the four configured receiver slots.
#[derive(Default)]
pub struct Quality {
    pub receivers: [Receiver; 4],
    run: Option<u64>,
}

impl Quality {
    /// Start gap and duplicate tracking for a new run; counters remain cumulative.
    pub fn start_run(&mut self, run: u64) {
        self.run = Some(run);
        for receiver in &mut self.receivers {
            receiver.reset_tracking();
            receiver.last_sequence = None;
            receiver.pending_missing.clear();
            receiver.pending_order.clear();
            receiver.boot = None;
        }
    }

    /// Count one accepted batch and return the indices of its first-capture records.
    pub fn accept(&mut self, slot: usize, batch: &Batch, now_ns: u64) -> Vec<usize> {
        let Some(receiver) = self.receivers.get_mut(slot) else {
            return Vec::new();
        };
        match receiver.boot {
            Some(boot) if boot != batch.rx_boot => {
                receiver.receiver_restarts += 1;
                receiver.reset_tracking();
            }
            _ => {}
        }
        receiver.boot = Some(batch.rx_boot);
        receiver.batches += 1;
        receiver.stats = Some(batch.stats);
        let (missing, reordered) = receiver.batch.observe(batch.id);
        receiver.batch_missing += missing;
        receiver.batch_reordered += reordered;
        let mut fresh = Vec::with_capacity(batch.records.len());
        for (index, record) in batch.records.iter().enumerate() {
            let (missing, reordered) = receiver.transport.observe(record.transport_sequence);
            receiver.transport_missing += missing;
            receiver.transport_reordered += reordered;
            if !first_capture(receiver, self.run.unwrap_or(batch.run), batch, record) {
                receiver.duplicates += 1;
                continue;
            }
            receiver.track_record_sequence(record.sequence);
            receiver.records += 1;
            receiver.last_record_ns = Some(now_ns);
            fresh.push(index);
        }
        fresh
    }

    /// Session totals in the shape of the collector's telemetry snapshot.
    pub fn totals(&self) -> Value {
        let sum = |f: fn(&Receiver) -> u64| self.receivers.iter().map(f).sum::<u64>();
        json!({
            "records": sum(|r| r.records),
            "batches": sum(|r| r.batches),
            "host_missing_sequences": sum(|r| r.missing_sequences),
            "transport_missing": sum(|r| r.transport_missing),
            "transport_reordered": sum(|r| r.transport_reordered),
            "batch_missing": sum(|r| r.batch_missing),
            "batch_reordered": sum(|r| r.batch_reordered),
            "duplicates": sum(|r| r.duplicates),
            "receiver_restarts": sum(|r| r.receiver_restarts),
        })
    }
}

fn first_capture(receiver: &mut Receiver, run: u64, batch: &Batch, record: &Record) -> bool {
    if record.tx_timestamp == 0 {
        return true;
    }
    let identity = (
        run,
        batch.tx_boot,
        batch.rx_boot,
        record.sequence,
        record.tx_timestamp,
    );
    if !receiver.seen.insert(identity) {
        return false;
    }
    receiver.seen_order.push_back(identity);
    if receiver.seen_order.len() > DEDUP_CAPACITY
        && let Some(old) = receiver.seen_order.pop_front()
    {
        receiver.seen.remove(&old);
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sequence_gaps_wrap_and_count_reorders() {
        let mut sequence = Sequence::default();
        assert_eq!(sequence.observe(u32::MAX - 1), (0, 0));
        assert_eq!(sequence.observe(1), (2, 0));
        assert_eq!(sequence.observe(0), (0, 1));
        assert_eq!(sequence.observe(1), (0, 0));
    }

    #[test]
    fn late_records_repair_counted_gaps_and_backward_jumps_start_epochs() {
        let mut receiver = Receiver::default();
        for value in [10, 14, 12] {
            receiver.track_record_sequence(value);
        }
        assert_eq!(receiver.missing_sequences, 2);
        assert_eq!(receiver.last_sequence, Some(14));
        receiver.track_record_sequence(3);
        assert_eq!(receiver.last_sequence, Some(3));
        receiver.track_record_sequence(12);
        assert_eq!(receiver.missing_sequences, 2 + 8);
    }
}
