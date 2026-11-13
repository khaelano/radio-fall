//! Adapt verified native CSI records using the existing offline magnitude kernel.
use radio_transport::wire::Record;

/// Runtime identities and sensing link, supplied by verified deployment/preflight.
pub struct Sensing {
    pub run: u64,
    pub transmitter_boot: u32,
    pub receiver_boots: [u32; 4],
    pub receivers: [String; 4],
    pub transmitter: String,
    pub fingerprint: String,
    pub channel: u8,
}

/// Native accepted-batch to aligned-history handoff. Errors invalidate all history.
pub struct Ingress {
    sensing: Sensing,
    sequences: [Sequence; 4],
    history: crate::stream::History,
    failed: bool,
}
const ROUND_BIAS: i64 = 1 << 31;
impl Ingress {
    pub fn new(sensing: Sensing, anchor: u32, capacity: usize) -> Result<Self, String> {
        if sensing.run == 0
            || sensing.channel == 0
            || sensing.transmitter.is_empty()
            || sensing.fingerprint.len() != 16
            || sensing
                .receivers
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != 4
        {
            return Err("incomplete sensing contract".into());
        }
        Ok(Self {
            sensing,
            sequences: std::array::from_fn(|_| Sequence::new(anchor)),
            history: crate::stream::History::new(capacity)?,
            failed: false,
        })
    }
    /// Receive an accepted batch using the current verified reference mapping.
    pub fn ingest(
        &mut self,
        batch: &radio_transport::wire::Batch,
        arrival_ns: u64,
        now_ns: u64,
        reference: &radio_transport::reference::Reference,
    ) -> Result<(), String> {
        if self.failed {
            return Err("ingress failed; start a new generation".into());
        }
        let result = (|| {
            let receiver = self
                .sensing
                .receivers
                .iter()
                .position(|m| m == &batch.mac)
                .ok_or("unconfigured receiver")?;
            if batch.run != self.sensing.run
                || batch.tx_boot != self.sensing.transmitter_boot
                || batch.rx_boot != self.sensing.receiver_boots[receiver]
            {
                return Err("batch epoch differs from sensing contract".into());
            }
            for record in &batch.records {
                if record.transmitter != self.sensing.transmitter
                    || record.fingerprint != self.sensing.fingerprint
                {
                    return Err("record identity/profile mismatch".into());
                }
                if record.fields[11] != self.sensing.channel {
                    continue;
                }
                let capture = reference.capture_ns(record.tx_timestamp, now_ns)?;
                let offset = self.sequences[receiver].observe(record.sequence)?;
                let round = offset
                    .checked_add(ROUND_BIAS)
                    .and_then(|v| u64::try_from(v).ok())
                    .ok_or("aligned round overflow")?;
                self.history
                    .insert(round, receiver, prepare(record, arrival_ns, capture)?)?;
            }
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
            self.history.reset()?;
        }
        result
    }
    /// Read signed shared-anchor offsets, preserving the history's internal bias.
    pub fn snapshot(
        &self,
        first_offset: i64,
        frames: usize,
        deadline: Option<u64>,
    ) -> Result<crate::stream::Snapshot, String> {
        if self.failed {
            return Err("ingress failed".into());
        }
        let first = first_offset
            .checked_add(ROUND_BIAS)
            .and_then(|v| u64::try_from(v).ok())
            .ok_or("invalid snapshot offset")?;
        self.history.snapshot(first, frames, deadline)
    }
    /// Release rounds older than all selected windows and filter dependencies.
    pub fn evict_before(&mut self, first_offset: i64) -> Result<(), String> {
        let first = first_offset
            .checked_add(ROUND_BIAS)
            .and_then(|v| u64::try_from(v).ok())
            .ok_or("invalid history offset")?;
        self.history.evict_before(first);
        Ok(())
    }
}

/// Prepare a sensing-link record after deployment identity/channel filtering.
/// Capture time must come from the qualified reference mapping, never USB arrival.
pub fn prepare(
    record: &Record,
    arrival_ns: u64,
    capture_ns: u64,
) -> Result<crate::stream::Packet, String> {
    if record.fields[1] != 4
        || record.fields[3] != 0
        || record.fields[7] != 0
        || ![490, 512].contains(&record.raw.len())
        || record.flags & 2 == 0
    {
        return Err("unsupported HE20 record layout or absent capture timestamp".into());
    }
    let mut i = Vec::with_capacity(record.raw.len());
    let mut q = Vec::with_capacity(record.raw.len());
    for pair in record.raw.chunks_exact(2) {
        q.extend_from_slice(&(pair[0] as i8 as i16).to_ne_bytes());
        i.extend_from_slice(&(pair[1] as i8 as i16).to_ne_bytes());
    }
    let values = radio_preprocessing::amplitude::decode_magnitudes(
        &i,
        &q,
        &[0, record.raw.len() / 2],
        &[record.flags & 1 != 0],
        &[record.fields[14] == 0],
    )?;
    Ok(crate::stream::Packet {
        arrival_ns,
        capture_ns,
        magnitude: values
            .try_into()
            .map_err(|_| "invalid physical magnitude shape")?,
    })
}

/// Ordered uint32 sequence unwrapping, matching offline duplicate/rollover rules.
pub struct Sequence {
    anchor: u32,
    previous: Option<u32>,
    offset: i64,
    span: u64,
}
impl Sequence {
    /// Use the same explicit anchor for every receiver within a transport epoch.
    pub fn new(anchor: u32) -> Self {
        Self {
            anchor,
            previous: None,
            offset: 0,
            span: 0,
        }
    }
    /// Match signed first offsets and ordered steps from offline sequence_offsets.
    pub fn observe(&mut self, value: u32) -> Result<i64, String> {
        let (offset, span) = if let Some(previous) = self.previous {
            let step = value.wrapping_sub(previous);
            if step >= 1 << 31 {
                return Err("sequence reset or backward packet; split epoch".into());
            }
            let span = self.span + step as u64;
            if span >= 1 << 31 {
                return Err("sequence epoch spans half the counter range".into());
            }
            (self.offset + step as i64, span)
        } else {
            (value.wrapping_sub(self.anchor) as i32 as i64, 0)
        };
        self.offset = offset;
        self.span = span;
        self.previous = Some(value);
        Ok(offset)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires RADIO_JOURNAL_FIXTURE from Python protocol fixture"]
    fn accepted_batch_maps_into_aligned_history() {
        use radio_transport::{
            clock::{Estimator, Sample},
            reference::Reference,
        };
        let bytes = std::fs::read(std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()).unwrap();
        let batch = radio_transport::wire::Batch::decode(&bytes).unwrap();
        let mut estimator = Estimator::new(32, 0).unwrap();
        let estimate = estimator
            .add(Sample {
                boot: batch.tx_boot,
                t1: 0,
                t2: 150,
                t3: 160,
                t4: 110,
            })
            .unwrap();
        let mut reference = Reference::new(
            batch.run,
            0,
            120,
            estimator,
            estimate,
            110000,
            (1_000_000, 10_000_000),
        )
        .unwrap();
        let mut round = b"CGRD".to_vec();
        round.extend_from_slice(&batch.run.to_be_bytes());
        round.extend_from_slice(&batch.tx_boot.to_be_bytes());
        round.extend_from_slice(&0u32.to_be_bytes());
        round.extend_from_slice(&1000u64.to_be_bytes());
        round.extend_from_slice(&1000u64.to_be_bytes());
        round.extend_from_slice(&8333u32.to_be_bytes());
        round.extend_from_slice(&1u32.to_be_bytes());
        round.extend_from_slice(&0u32.to_be_bytes());
        round.extend_from_slice(&[0, 1, 2]);
        reference.round(&round, 2_000_000).unwrap();
        let sensing = Sensing {
            run: batch.run,
            transmitter_boot: batch.tx_boot,
            receiver_boots: [batch.rx_boot, 1, 1, 1],
            receivers: std::array::from_fn(|i| {
                if i == 0 {
                    batch.mac.clone()
                } else {
                    format!("rx-{i}")
                }
            }),
            transmitter: batch.records[0].transmitter.clone(),
            fingerprint: batch.records[0].fingerprint.clone(),
            channel: 44,
        };
        let mut ingress = Ingress::new(sensing, 1, 4).unwrap();
        ingress
            .ingest(&batch, 1_100_000, 2_000_000, &reference)
            .unwrap();
        let snapshot = ingress.snapshot(0, 1, None).unwrap();
        assert_eq!(snapshot.presence, vec![[true, false, false, false]]);
        assert_eq!(snapshot.capture_ns[0][0], Some(901000));
        assert_eq!(
            snapshot.magnitude.iter().filter(|v| v.is_finite()).count(),
            242
        );
        let mut changed = (*batch).clone();
        changed.tx_boot += 1;
        assert!(
            ingress
                .ingest(&changed, 2_000_000, 2_000_000, &reference)
                .is_err()
        );
        assert!(ingress.snapshot(0, 1, None).is_err());
    }
    #[test]
    #[ignore = "requires RADIO_JOURNAL_FIXTURE from existing Python protocol fixture"]
    fn shared_physical_magnitude_fixture() {
        let bytes = std::fs::read(std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()).unwrap();
        let batch = radio_transport::wire::Batch::decode(&bytes).unwrap();
        let packet = prepare(&batch.records[0], 123, 456).unwrap();
        assert_eq!(packet.arrival_ns, 123);
        assert_eq!(packet.capture_ns, 456);
        assert_eq!(
            packet.magnitude.iter().filter(|v| v.is_finite()).count(),
            242
        );
        for (column, value) in packet.magnitude.iter().enumerate() {
            if (121..=123).contains(&column) {
                assert!(value.is_nan());
            } else {
                assert!((*value - 36.05551275463989).abs() < 1e-12);
            }
        }
    }
    #[test]
    fn rollover_duplicates_and_backward_jumps() {
        let mut sequence = Sequence::new(u32::MAX);
        assert_eq!(sequence.observe(u32::MAX).unwrap(), 0);
        assert_eq!(sequence.observe(0).unwrap(), 1);
        assert_eq!(sequence.observe(0).unwrap(), 1);
        assert!(sequence.observe(u32::MAX).is_err());
        let mut other = Sequence::new(u32::MAX);
        assert_eq!(other.observe(1).unwrap(), 2);
        let mut preceding = Sequence::new(1);
        assert_eq!(preceding.observe(0).unwrap(), -1);
    }
}
