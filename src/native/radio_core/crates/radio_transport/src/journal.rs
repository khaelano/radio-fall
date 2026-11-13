//! Append-only journals compatible with Python's GatewayJournal and iter_envelopes.
use crate::wire::{Batch, MAX_ENVELOPE};
use std::{
    collections::{BTreeMap, VecDeque},
    fs::{self, File, OpenOptions},
    io::{self, BufWriter, Read, Write},
    path::Path,
    sync::Arc,
};

type Key = (u64, u32, String, u32, u32);
pub type JournalEntry = (u64, Arc<Batch>);

/// Accepted-envelope journal. A successful flush precedes any caller ACK.
pub struct Journal {
    run: u64,
    data: BufWriter<File>,
    events: BufWriter<File>,
    bins: BufWriter<File>,
    directory: std::path::PathBuf,
    seen: BTreeMap<Key, Vec<u8>>,
    order: VecDeque<Key>,
    failed: bool,
}

impl Journal {
    /// Create a new run directory without overwriting an existing recording.
    pub fn create(
        root: &Path,
        run: u64,
        mut metadata: serde_json::Value,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        if run == 0 || !metadata.is_object() {
            return Err("invalid journal run or metadata".into());
        }
        let parent = root.join("transport/gateway");
        fs::create_dir_all(&parent)?;
        let directory = parent.join(format!("{run:016x}"));
        fs::create_dir(&directory)?;
        let create = |name| {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(directory.join(name))
        };
        metadata["schema_version"] = 1.into();
        metadata["run_id"] = run.to_string().into();
        let mut manifest = create("manifest.json")?;
        serde_json::to_writer_pretty(&mut manifest, &metadata)?;
        manifest.write_all(b"\n")?;
        let bins = BufWriter::new(create("availability.jsonl")?);
        Ok(Self {
            run,
            data: BufWriter::new(create("envelopes.bin")?),
            events: BufWriter::new(create("events.jsonl")?),
            bins,
            directory,
            seen: BTreeMap::new(),
            order: VecDeque::new(),
            failed: false,
        })
    }

    /// Validate, persist and flush one envelope. Reused identities must match bytes.
    pub fn accept(
        &mut self,
        bytes: &[u8],
        arrival_ns: u64,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        if self.failed {
            return Err("journal failed; acquisition must stop".into());
        }
        let batch = Batch::decode(bytes)?;
        if batch.run != self.run {
            return Err("journal run mismatch".into());
        }
        let key = (
            batch.run,
            batch.tx_boot,
            batch.mac.clone(),
            batch.rx_boot,
            batch.id,
        );
        if let Some(old) = self.seen.get(&key) {
            if old != bytes {
                return Err("batch identity reused for different bytes".into());
            }
            return Ok(false);
        }
        let write = (|| -> io::Result<()> {
            self.data.write_all(&arrival_ns.to_be_bytes())?;
            self.data.write_all(&(bytes.len() as u32).to_be_bytes())?;
            self.data.write_all(bytes)?;
            self.data.flush()
        })();
        if let Err(error) = write {
            self.failed = true;
            return Err(error.into());
        }
        self.order.push_back(key.clone());
        self.seen.insert(key, bytes.to_vec());
        if self.order.len() > 4096
            && let Some(old) = self.order.pop_front()
        {
            self.seen.remove(&old);
        }
        Ok(true)
    }

    /// Directory holding this run's manifest, envelopes and sidecars.
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// Append one finalized availability bin to the availability sidecar.
    pub fn bin(&mut self, row: &serde_json::Value) -> Result<(), Box<dyn std::error::Error>> {
        if self.failed || !row.is_object() {
            return Err("failed journal or invalid availability bin".into());
        }
        let write = (|| -> Result<(), Box<dyn std::error::Error>> {
            serde_json::to_writer(&mut self.bins, row)?;
            self.bins.write_all(b"\n")?;
            self.bins.flush()?;
            Ok(())
        })();
        if write.is_err() {
            self.failed = true;
        }
        write
    }

    /// Append a timestamped diagnostic event; propagate failure before further ACKs.
    pub fn event(
        &mut self,
        kind: &str,
        now_ns: u64,
        mut value: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error>> {
        if self.failed || !value.is_object() {
            return Err("failed journal or invalid event".into());
        }
        value["kind"] = kind.into();
        value["host_monotonic_ns"] = now_ns.into();
        let write = (|| -> Result<(), Box<dyn std::error::Error>> {
            serde_json::to_writer(&mut self.events, &value)?;
            self.events.write_all(b"\n")?;
            self.events.flush()?;
            Ok(())
        })();
        if write.is_err() {
            self.failed = true;
        }
        write
    }
}

/// Read one bounded, fully validated journal entry; reject partial headers/payloads.
pub fn read_entry(
    reader: &mut impl Read,
) -> Result<Option<JournalEntry>, Box<dyn std::error::Error>> {
    let mut header = [0; 12];
    match reader.read(&mut header[..1])? {
        0 => return Ok(None),
        1 => {}
        _ => unreachable!(),
    }
    reader.read_exact(&mut header[1..])?;
    let arrival = u64::from_be_bytes(header[..8].try_into().unwrap());
    let length = u32::from_be_bytes(header[8..].try_into().unwrap()) as usize;
    if length > MAX_ENVELOPE {
        return Err("oversized journal envelope".into());
    }
    let mut bytes = vec![0; length];
    reader.read_exact(&mut bytes)?;
    Ok(Some((arrival, Batch::decode(&bytes)?)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires RADIO_JOURNAL_FIXTURE envelope"]
    fn writes_and_replays_python_protocol_fixture() {
        let bytes = fs::read(std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()).unwrap();
        let batch = Batch::decode(&bytes).unwrap();
        let root = std::env::temp_dir().join(format!(
            "radio-native-journal-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut journal = Journal::create(
            &root,
            batch.run,
            serde_json::json!({"source":"synthetic-fixture"}),
        )
        .unwrap();
        assert!(journal.accept(&bytes, 123456).unwrap());
        assert!(!journal.accept(&bytes, 123457).unwrap());
        let mut conflict = bytes.clone();
        conflict[60] ^= 1;
        let end = conflict.len() - 4;
        let crc = crc32fast::hash(&conflict[..end]);
        conflict[end..].copy_from_slice(&crc.to_be_bytes());
        assert!(journal.accept(&conflict, 123458).is_err());
        drop(journal);
        let path = root.join(format!(
            "transport/gateway/{:016x}/envelopes.bin",
            batch.run
        ));
        let mut reader = File::open(&path).unwrap();
        let (arrival, decoded) = read_entry(&mut reader).unwrap().unwrap();
        assert_eq!(arrival, 123456);
        assert_eq!(decoded.id, batch.id);
        assert!(read_entry(&mut reader).unwrap().is_none());
        println!("fixture journal: {}", path.display());
    }
    #[test]
    fn replay_rejects_partial_and_oversized_entries() {
        assert!(read_entry(&mut &[][..]).unwrap().is_none());
        for length in 1..12 {
            assert!(read_entry(&mut &vec![0; length][..]).is_err());
        }
        let mut header = vec![0; 8];
        header.extend_from_slice(&1401u32.to_be_bytes());
        assert!(read_entry(&mut &header[..]).is_err());
        header[8..].copy_from_slice(&100u32.to_be_bytes());
        assert!(read_entry(&mut &header[..]).is_err());
    }
}
