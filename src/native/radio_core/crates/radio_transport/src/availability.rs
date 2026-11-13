//! Causal availability bins and round receipts, independent of CSI features.
//!
//! A bin is finalized once its delivery deadline passes; late deliveries never
//! revise it. Round receipts join authoritative transmitter rounds to receiver
//! deliveries without inventing rounds that were never logged.
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

/// Seconds of finalized bins retained for live display.
pub const HISTORY_SECONDS: u64 = 10;
const ARRIVAL_CAPACITY: usize = 2048;
const RECEIPT_CAPACITY: usize = 2048;
const FINALIZED_MEMORY: usize = 4096;

/// Capture-time bins for display; `None` denotes pre-run or expired history.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Snapshot {
    pub receivers: Vec<String>,
    pub first_bin_start_ns: i64,
    pub width_ns: u64,
    pub grace_ns: u64,
    pub packet_counts: Vec<Vec<Option<u64>>>,
}

impl Snapshot {
    /// JSON form consumed by the presentation layer.
    pub fn to_json(&self) -> Value {
        json!({
            "receivers": self.receivers,
            "first_bin_start_ns": self.first_bin_start_ns,
            "width_ns": self.width_ns,
            "grace_ns": self.grace_ns,
            "packet_counts": self.packet_counts,
        })
    }
}

/// Finalize receiver bins once; late delivery cannot revise old inputs.
pub struct Grid {
    receivers: Vec<String>,
    start_ns: u64,
    width_ns: u64,
    grace_ns: u64,
    next_bin: i64,
    counts: HashMap<(usize, i64), u64>,
    arrivals: Vec<VecDeque<(u64, u64)>>,
    latest: Vec<Option<u64>>,
    history: VecDeque<(i64, Vec<u64>)>,
    history_capacity: usize,
    pub timely: Vec<u64>,
    pub late: Vec<u64>,
}

impl Grid {
    /// Create bins of `1 / bin_hz` seconds that finalize `grace_ms` after they end.
    pub fn new(
        receivers: Vec<String>,
        start_ns: u64,
        bin_hz: u32,
        grace_ms: u64,
    ) -> Result<Self, String> {
        if receivers.is_empty() || !(1..=1000).contains(&bin_hz) {
            return Err("invalid availability receivers or bin rate".into());
        }
        let width_ns = 1_000_000_000 / bin_hz as u64;
        let count = receivers.len();
        Ok(Self {
            receivers,
            start_ns,
            width_ns,
            grace_ns: grace_ms * 1_000_000,
            next_bin: 0,
            counts: HashMap::new(),
            arrivals: vec![VecDeque::new(); count],
            latest: vec![None; count],
            history: VecDeque::new(),
            history_capacity: (HISTORY_SECONDS * 1_000_000_000).div_ceil(width_ns) as usize + 1,
            timely: vec![0; count],
            late: vec![0; count],
        })
    }

    pub fn start_ns(&self) -> u64 {
        self.start_ns
    }

    pub fn width_ns(&self) -> u64 {
        self.width_ns
    }

    pub fn grace_ns(&self) -> u64 {
        self.grace_ns
    }

    fn index(&self, time_ns: u64) -> i64 {
        (time_ns as i128 - self.start_ns as i128).div_euclid(self.width_ns as i128) as i64
    }

    fn bin_end(&self, index: i64) -> u64 {
        (self.start_ns as i128 + (index as i128 + 1) * self.width_ns as i128) as u64
    }

    /// Track packet availability without substituting or interpolating CSI.
    pub fn observe(
        &mut self,
        receiver: usize,
        captured_ns: u64,
        arrived_ns: u64,
    ) -> Result<bool, String> {
        if receiver >= self.receivers.len() {
            return Err("unknown availability receiver".into());
        }
        let index = self.index(captured_ns);
        if index < 0 {
            return Ok(false);
        }
        let timely = arrived_ns <= self.bin_end(index) + self.grace_ns && index >= self.next_bin;
        if timely {
            *self.counts.entry((receiver, index)).or_default() += 1;
            self.timely[receiver] += 1;
        } else {
            self.late[receiver] += 1;
        }
        let history = &mut self.arrivals[receiver];
        if history.len() >= ARRIVAL_CAPACITY {
            return Err("availability history exceeded bounded capacity".into());
        }
        history.push_back((captured_ns, arrived_ns));
        Ok(timely)
    }

    /// Return finalized bins through `now_ns`, preserving capture and arrival clocks.
    pub fn advance(&mut self, now_ns: u64) -> Vec<Value> {
        let mut rows = Vec::new();
        while self.bin_end(self.next_bin) + self.grace_ns <= now_ns {
            let index = self.next_bin;
            let end = self.bin_end(index);
            let deadline = end + self.grace_ns;
            let mut receivers = serde_json::Map::new();
            let mut counts = Vec::with_capacity(self.receivers.len());
            for (slot, name) in self.receivers.iter().enumerate() {
                let mut latest = self.latest[slot];
                self.arrivals[slot].retain(|&(captured, arrived)| {
                    if captured < end && arrived <= deadline {
                        latest = Some(latest.map_or(captured, |value| value.max(captured)));
                        false
                    } else {
                        true
                    }
                });
                self.latest[slot] = latest;
                let count = self.counts.remove(&(slot, index)).unwrap_or(0);
                counts.push(count);
                receivers.insert(
                    name.clone(),
                    json!({
                        "available": count > 0,
                        "packet_count": count,
                        "age_ms": latest.map(|value| end.saturating_sub(value) as f64 / 1_000_000.0),
                    }),
                );
            }
            if self.history.len() == self.history_capacity {
                self.history.pop_front();
            }
            self.history.push_back((index, counts));
            self.next_bin += 1;
            rows.push(json!({
                "schema_version": 1,
                "bin": index,
                "start_ns": end - self.width_ns,
                "end_ns": end,
                "deadline_ns": deadline,
                "receivers": receivers,
            }));
        }
        rows
    }

    /// Copy recent finalized and pending counts without advancing acquisition.
    pub fn snapshot(&self, now_ns: u64, seconds: f64) -> Result<Snapshot, String> {
        if !(seconds > 0.0 && seconds <= HISTORY_SECONDS as f64) {
            return Err("availability window must be between zero and ten seconds".into());
        }
        let last = self.index(now_ns);
        let first = (now_ns as i128 - self.start_ns as i128 - (seconds * 1e9).round() as i128)
            .div_euclid(self.width_ns as i128) as i64;
        let history: BTreeMap<i64, &Vec<u64>> = self
            .history
            .iter()
            .map(|(index, counts)| (*index, counts))
            .collect();
        let packet_counts = (0..self.receivers.len())
            .map(|slot| {
                (first..=last)
                    .map(|index| {
                        if let Some(counts) = history.get(&index) {
                            Some(counts[slot])
                        } else if index < 0 || index < self.next_bin {
                            None
                        } else {
                            Some(self.counts.get(&(slot, index)).copied().unwrap_or(0))
                        }
                    })
                    .collect()
            })
            .collect();
        Ok(Snapshot {
            receivers: self.receivers.clone(),
            first_bin_start_ns: (self.start_ns as i128 + first as i128 * self.width_ns as i128)
                as i64,
            width_ns: self.width_ns,
            grace_ns: self.grace_ns,
            packet_counts,
        })
    }
}

type RoundKey = (u32, u32);

/// Join transmitter logs to receiver deliveries, including all-stream silence.
pub struct Receipts {
    receivers: Vec<String>,
    start_ns: u64,
    width_ns: u64,
    grace_ns: u64,
    pending: BTreeMap<RoundKey, (Value, u64, BTreeMap<usize, u64>)>,
    early: HashMap<RoundKey, BTreeMap<usize, u64>>,
    early_order: VecDeque<RoundKey>,
    finalized: BTreeSet<RoundKey>,
    recent: VecDeque<RoundKey>,
}

impl Receipts {
    /// Use the grid's bin layout so round deadlines match availability bins.
    pub fn new(receivers: Vec<String>, grid: &Grid) -> Self {
        Self {
            receivers,
            start_ns: grid.start_ns(),
            width_ns: grid.width_ns(),
            grace_ns: grid.grace_ns(),
            pending: BTreeMap::new(),
            early: HashMap::new(),
            early_order: VecDeque::new(),
            finalized: BTreeSet::new(),
            recent: VecDeque::new(),
        }
    }

    /// Register a logged sensing round, never inventing untransmitted rounds.
    pub fn round(&mut self, value: Value) -> Result<(), String> {
        let skipped = value["skipped_rounds"].as_u64().unwrap_or(0);
        let Some(captured) = value["host_capture_ns"].as_u64() else {
            return Ok(());
        };
        if skipped != 0 {
            return Ok(());
        }
        let boot = value["transmitter_boot_id"]
            .as_u64()
            .ok_or("round lacks boot")? as u32;
        let sequence = value["sequence"].as_u64().ok_or("round lacks sequence")? as u32;
        let key = (boot, sequence);
        let index = (captured as i128 - self.start_ns as i128).div_euclid(self.width_ns as i128);
        let deadline =
            (self.start_ns as i128 + (index + 1) * self.width_ns as i128) as u64 + self.grace_ns;
        if self.pending.len() >= RECEIPT_CAPACITY {
            return Err("round receipt tracker overflow".into());
        }
        if !self.finalized.contains(&key) {
            let receipts = self.early.remove(&key).unwrap_or_default();
            self.early_order.retain(|item| *item != key);
            self.pending.insert(key, (value, deadline, receipts));
        }
        Ok(())
    }

    /// Track the earliest delivery for a receiver without revising finalized rounds.
    pub fn receive(&mut self, boot: u32, sequence: u32, receiver: usize, arrival_ns: u64) {
        let key = (boot, sequence);
        if self.finalized.contains(&key) {
            return;
        }
        let receipts = if let Some((_, _, receipts)) = self.pending.get_mut(&key) {
            receipts
        } else {
            if !self.early.contains_key(&key) {
                if self.early.len() >= RECEIPT_CAPACITY
                    && let Some(oldest) = self.early_order.pop_front()
                {
                    self.early.remove(&oldest);
                }
                self.early_order.push_back(key);
            }
            self.early.entry(key).or_default()
        };
        let earliest = receipts.entry(receiver).or_insert(arrival_ns);
        *earliest = (*earliest).min(arrival_ns);
    }

    /// Finalize round masks by deadline; the cause of unavailability stays unknown.
    pub fn advance(&mut self, now_ns: u64) -> Vec<Value> {
        let due: Vec<_> = self
            .pending
            .iter()
            .filter(|(_, (_, deadline, _))| *deadline <= now_ns)
            .map(|(key, _)| *key)
            .collect();
        let mut events = Vec::with_capacity(due.len());
        for key in due {
            let (mut value, deadline, receipts) = self.pending.remove(&key).unwrap();
            let availability: serde_json::Map<_, _> = self
                .receivers
                .iter()
                .enumerate()
                .map(|(slot, name)| {
                    let available = receipts.get(&slot).is_some_and(|time| *time <= deadline);
                    (name.clone(), Value::Bool(available))
                })
                .collect();
            value["deadline_ns"] = deadline.into();
            value["availability"] = availability.into();
            events.push(value);
            self.finalized.insert(key);
            self.recent.push_back(key);
            if self.recent.len() > FINALIZED_MEMORY
                && let Some(old) = self.recent.pop_front()
            {
                self.finalized.remove(&old);
            }
        }
        events
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn grid() -> Grid {
        Grid::new(vec!["rx-1".into(), "rx-2".into()], 1_000, 50, 100).unwrap()
    }

    #[test]
    fn late_delivery_never_revises_a_finalized_bin() {
        let mut grid = grid();
        let width = grid.width_ns();
        assert!(grid.observe(0, 1_000 + 10, 1_000 + 20).unwrap());
        assert!(
            !grid
                .observe(1, 1_000 + 10, 1_000 + width + 100_000_001)
                .unwrap()
        );
        let rows = grid.advance(1_000 + width + 100_000_000);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["receivers"]["rx-1"]["packet_count"], 1);
        assert_eq!(rows[0]["receivers"]["rx-2"]["available"], false);
        assert!(!grid.observe(0, 1_000 + 10, 1_000 + 20).unwrap());
        assert_eq!((grid.timely[0], grid.late[0], grid.late[1]), (1, 1, 1));
        assert!(!grid.observe(0, 999, 1_000).unwrap());
    }

    #[test]
    fn snapshot_marks_pre_run_bins_and_pending_counts() {
        let mut grid = grid();
        let width = grid.width_ns();
        grid.observe(0, 1_000 + width + 1, 1_000 + width + 2)
            .unwrap();
        let snapshot = grid.snapshot(1_000 + width + 5, 0.05).unwrap();
        assert_eq!(snapshot.packet_counts[0].first(), Some(&None));
        assert_eq!(snapshot.packet_counts[0].last(), Some(&Some(1)));
        assert_eq!(snapshot.packet_counts[1].last(), Some(&Some(0)));
        assert!(grid.snapshot(0, 11.0).is_err());
    }

    #[test]
    fn round_receipts_finalize_by_deadline_and_ignore_skips() {
        let mut grid = grid();
        let width = grid.width_ns();
        let mut receipts = Receipts::new(vec!["rx-1".into(), "rx-2".into()], &grid);
        receipts.receive(7, 3, 1, 1_000 + 50);
        receipts
            .round(
                json!({"transmitter_boot_id": 7, "sequence": 3, "host_capture_ns": 1_010,
                          "skipped_rounds": 0}),
            )
            .unwrap();
        receipts
            .round(
                json!({"transmitter_boot_id": 7, "sequence": 4, "host_capture_ns": 1_010,
                          "skipped_rounds": 2}),
            )
            .unwrap();
        receipts.receive(7, 3, 0, 1_000 + width + 100_000_001);
        assert!(receipts.advance(1_000 + width).is_empty());
        let events = receipts.advance(1_000 + width + 100_000_000);
        assert_eq!(events.len(), 1);
        assert_eq!(
            events[0]["availability"],
            json!({"rx-1": false, "rx-2": true})
        );
        receipts.receive(7, 3, 0, 0);
        assert!(receipts.advance(u64::MAX / 2).is_empty());
        grid.advance(0);
    }
}
