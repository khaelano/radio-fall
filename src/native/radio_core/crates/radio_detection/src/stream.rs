//! Bounded aligned packet history. Capture rounds and host delivery are distinct.
use std::collections::BTreeMap;

/// Capture and delivery clocks for one immutable publication input.
#[derive(Debug, PartialEq, Eq)]
pub struct WindowTiming {
    pub start_ns: u64,
    pub center_ns: u64,
    pub end_ns: u64,
    pub finalize_after_ns: u64,
}

impl WindowTiming {
    /// Reserve explicit verified future context and operational delivery grace.
    /// Context is supplied by the deployment contract, never inferred here.
    pub fn new(
        start_ns: u64,
        duration_ns: u64,
        future_context_ns: u64,
        grace_ns: u64,
    ) -> Result<Self, String> {
        if duration_ns == 0 {
            return Err("window duration must be positive".into());
        }
        let end_ns = start_ns
            .checked_add(duration_ns)
            .ok_or("window clock overflow")?;
        let finalize_after_ns = end_ns
            .checked_add(future_context_ns)
            .and_then(|v| v.checked_add(grace_ns))
            .ok_or("finalization clock overflow")?;
        Ok(Self {
            start_ns,
            center_ns: start_ns + duration_ns / 2,
            end_ns,
            finalize_after_ns,
        })
    }

    /// Finalization requires the complete future context and grace on the host clock.
    pub fn ready(&self, now_ns: u64) -> bool {
        now_ns >= self.finalize_after_ns
    }
}

/// One receiver's physical magnitudes before filtering, in physical tone order.
#[derive(Clone)]
pub struct Packet {
    pub arrival_ns: u64,
    pub capture_ns: u64,
    pub magnitude: [f64; 245],
}

/// Immutable aligned snapshot for filtering and parity inspection.
pub struct Snapshot {
    pub generation: u64,
    pub first_round: u64,
    pub magnitude: Vec<f64>,
    pub presence: Vec<[bool; 4]>,
    pub capture_ns: Vec<[Option<u64>; 4]>,
}

impl Snapshot {
    /// Apply the existing offline Hampel kernel to a nominal sampling grid.
    pub fn filter(
        &self,
        times_seconds: &[f64],
        window_seconds: f64,
        min_periods: usize,
        threshold: f64,
    ) -> Result<(Vec<f64>, Vec<u8>), String> {
        let rows = self.presence.len();
        if times_seconds.len() != rows
            || self.magnitude.len() != rows.checked_mul(980).ok_or("shape overflow")?
        {
            return Err("snapshot/grid shape mismatch".into());
        }
        let mut columns = vec![f64::NAN; self.magnitude.len()];
        for row in 0..rows {
            for col in 0..980 {
                columns[col * rows + row] = self.magnitude[row * 980 + col];
            }
        }
        let (filtered, replaced) = radio_preprocessing::hampel::filter_native(
            &columns,
            times_seconds,
            980,
            window_seconds,
            min_periods,
            threshold,
            true,
            true,
        )?;
        let mut values = vec![f64::NAN; columns.len()];
        let mut masks = vec![0; columns.len()];
        for row in 0..rows {
            for col in 0..980 {
                values[row * 980 + col] = filtered[col * rows + row];
                masks[row * 980 + col] = replaced[col * rows + row];
            }
        }
        Ok((values, masks))
    }
}

/// Round-indexed bounded history. A transport epoch change must call `reset`.
pub struct History {
    rows: BTreeMap<u64, [Option<Packet>; 4]>,
    capacity: usize,
    generation: u64,
    pub duplicates: u64,
    pub overflows: u64,
}

impl History {
    /// Capacity includes the longest window, filter context, grace and spare rounds.
    pub fn new(capacity: usize) -> Result<Self, String> {
        if capacity == 0 {
            return Err("history capacity must be positive".into());
        }
        Ok(Self {
            rows: BTreeMap::new(),
            capacity,
            generation: 0,
            duplicates: 0,
            overflows: 0,
        })
    }

    /// Clear every receiver together; never difference across the returned generation.
    pub fn reset(&mut self) -> Result<u64, String> {
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or("generation exhausted")?;
        self.rows.clear();
        Ok(self.generation)
    }

    /// Keep the first duplicate. Overflow invalidates history instead of hiding loss.
    pub fn insert(&mut self, round: u64, receiver: usize, packet: Packet) -> Result<(), String> {
        if receiver >= 4 || packet.magnitude.iter().any(|v| v.is_infinite() || *v < 0.0) {
            return Err("invalid receiver or physical magnitude".into());
        }
        if !self.rows.contains_key(&round) && self.rows.len() == self.capacity {
            self.overflows = self.overflows.saturating_add(1);
            self.reset()?;
            return Err("acquisition history overflow: generation reset".into());
        }
        let row = self
            .rows
            .entry(round)
            .or_insert_with(|| std::array::from_fn(|_| None));
        if row[receiver].is_some() {
            self.duplicates = self.duplicates.saturating_add(1);
        } else {
            row[receiver] = Some(packet);
        }
        Ok(())
    }

    /// Discard only rounds older than all future window/context dependencies.
    pub fn evict_before(&mut self, first_required_round: u64) {
        self.rows = self.rows.split_off(&first_required_round);
    }

    /// Copy an immutable deadline-limited grid including explicit missing rows.
    /// `None` admits unlimited delivery context for offline parity replay.
    pub fn snapshot(
        &self,
        first_round: u64,
        frames: usize,
        delivery_deadline_ns: Option<u64>,
    ) -> Result<Snapshot, String> {
        if frames == 0 || frames > self.capacity {
            return Err("snapshot exceeds configured history bound".into());
        }
        let stop = first_round
            .checked_add(frames as u64)
            .ok_or("round overflow")?;
        let size = frames.checked_mul(980).ok_or("snapshot size overflow")?;
        let mut result = Snapshot {
            generation: self.generation,
            first_round,
            magnitude: vec![f64::NAN; size],
            presence: vec![[false; 4]; frames],
            capture_ns: vec![[None; 4]; frames],
        };
        for (time, round) in (first_round..stop).enumerate() {
            if let Some(row) = self.rows.get(&round) {
                for (receiver, packet) in row.iter().enumerate() {
                    if let Some(packet) = packet
                        && delivery_deadline_ns.is_none_or(|deadline| packet.arrival_ns <= deadline)
                    {
                        result.magnitude
                            [time * 980 + receiver * 245..time * 980 + (receiver + 1) * 245]
                            .copy_from_slice(&packet.magnitude);
                        result.presence[time][receiver] = true;
                        result.capture_ns[time][receiver] = Some(packet.capture_ns);
                    }
                }
            }
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn centered_context_and_grace_are_explicit() {
        let timing = WindowTiming::new(10, 4000, 250, 900).unwrap();
        assert_eq!(timing.center_ns, 2010);
        assert_eq!(timing.finalize_after_ns, 5160);
        assert!(!timing.ready(5159));
        assert!(timing.ready(5160));
        assert!(WindowTiming::new(u64::MAX, 1, 0, 0).is_err());
    }
    fn packet(arrival_ns: u64, value: f64) -> Packet {
        Packet {
            arrival_ns,
            capture_ns: 1,
            magnitude: [value; 245],
        }
    }
    #[test]
    fn deadlines_duplicates_and_immutable_snapshots() {
        let mut history = History::new(4).unwrap();
        history.insert(10, 0, packet(20, 2.0)).unwrap();
        history.insert(10, 0, packet(21, 3.0)).unwrap();
        let before = history.snapshot(10, 2, Some(20)).unwrap();
        history.insert(11, 1, packet(30, 5.0)).unwrap();
        assert_eq!(before.magnitude[0], 2.0);
        assert!(!before.presence[1][1]);
        assert!(!history.snapshot(10, 2, Some(20)).unwrap().presence[1][1]);
        assert!(history.snapshot(10, 2, None).unwrap().presence[1][1]);
        assert_eq!(history.duplicates, 1);
    }
    #[test]
    fn overflow_and_resets_clear_all_receivers() {
        let mut history = History::new(1).unwrap();
        history.insert(1, 0, packet(1, 1.0)).unwrap();
        assert!(history.insert(2, 1, packet(2, 1.0)).is_err());
        let snapshot = history.snapshot(1, 1, None).unwrap();
        assert_eq!(snapshot.generation, 1);
        assert_eq!(snapshot.presence, vec![[false; 4]]);
    }
}
