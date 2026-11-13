//! Verify recorded live acceptance timestamps against reconstructed reference state.
use radio_transport::{
    journal::read_entry,
    replay::{ReferenceReplay, read_event},
};
use sha2::{Digest, Sha256};
use std::{fs::File, io::BufReader, path::Path};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args()
        .nth(1)
        .ok_or("usage: accepted_replay RUN_JOURNAL_DIR")?;
    let root = Path::new(&path);
    let mut events = BufReader::new(File::open(root.join("events.jsonl"))?);
    let mut envelopes = BufReader::new(File::open(root.join("envelopes.bin"))?);
    let mut replay = ReferenceReplay::new(&read_event(&mut events)?.ok_or("empty event journal")?)?;
    let mut hash = Sha256::new();
    let mut records = 0u64;
    let mut batches = 0u64;
    while let Some(event) = read_event(&mut events)? {
        replay.apply(&event)?;
        if event["kind"] != "batch_acceptance" {
            continue;
        }
        let (arrival, batch) =
            read_entry(&mut envelopes)?.ok_or("acceptance event without envelope")?;
        if event["arrival_ns"].as_u64() != Some(arrival)
            || event["run"]
                .as_str()
                .and_then(|run| run.parse::<u64>().ok())
                != Some(batch.run)
            || event["transmitter_boot"] != batch.tx_boot
            || event["receiver_boot"] != batch.rx_boot
            || event["receiver"] != batch.mac
            || event["batch"] != batch.id
        {
            return Err("acceptance event/envelope identity mismatch".into());
        }
        let available = event["available_ns"]
            .as_u64()
            .ok_or("missing availability timestamp")?;
        if available < arrival || event["host_monotonic_ns"].as_u64() != Some(available) {
            return Err("invalid acceptance clock".into());
        }
        let mapped = event["records"]
            .as_array()
            .ok_or("missing accepted records")?;
        if mapped.len() != batch.records.len() {
            return Err("accepted record count mismatch".into());
        }
        for (record, saved) in batch.records.iter().zip(mapped) {
            let capture = replay
                .reference
                .capture_ns(record.tx_timestamp, available)?;
            if saved["capture_ns"].as_u64() != Some(capture)
                || saved["sequence"] != record.sequence
                || saved["receiver"] != record.receiver
                || saved["tx_enqueue_us"] != record.tx_timestamp
            {
                return Err("replayed capture differs from live accepted record".into());
            }
            hash.update(record.receiver.as_bytes());
            hash.update(record.sequence.to_be_bytes());
            hash.update(capture.to_be_bytes());
            records += 1;
        }
        batches += 1;
    }
    if records == 0 || read_entry(&mut envelopes)?.is_some() {
        return Err("missing live acceptance evidence".into());
    }
    println!(
        "{}",
        serde_json::json!({"records":records,"batches":batches,"exact_live_mapping":true,
        "mapped_capture_sha256":format!("{:x}",hash.finalize())})
    );
    Ok(())
}
