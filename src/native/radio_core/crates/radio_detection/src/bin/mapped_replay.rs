//! Reconstruct mapped capture timestamps from native envelope/reference journals.
use radio_transport::{
    journal::read_entry,
    replay::{ReferenceReplay, read_event},
};
use sha2::{Digest, Sha256};
use std::{fs::File, io::BufReader, path::Path};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args()
        .nth(1)
        .ok_or("usage: mapped_replay RUN_JOURNAL_DIR")?;
    let root = Path::new(&path);
    let mut events = BufReader::new(File::open(root.join("events.jsonl"))?);
    let initial = read_event(&mut events)?.ok_or("empty reference journal")?;
    let mut replay = ReferenceReplay::new(&initial)?;
    let mut next = read_event(&mut events)?;
    let mut envelopes = BufReader::new(File::open(root.join("envelopes.bin"))?);
    let mut hash = Sha256::new();
    let mut count = 0u64;
    let mut previous = 0;
    while let Some((arrival, batch)) = read_entry(&mut envelopes)? {
        if arrival < previous {
            return Err("envelope arrival clock moved backward".into());
        }
        previous = arrival;
        while next.as_ref().is_some_and(|e| {
            e["host_monotonic_ns"]
                .as_u64()
                .is_some_and(|t| t <= arrival)
        }) {
            replay.apply(next.as_ref().unwrap())?;
            next = read_event(&mut events)?;
        }
        for record in &batch.records {
            let capture = replay.reference.capture_ns(record.tx_timestamp, arrival)?;
            hash.update(record.receiver.as_bytes());
            hash.update(record.sequence.to_be_bytes());
            hash.update(capture.to_be_bytes());
            count += 1;
        }
    }
    while let Some(event) = next {
        replay.apply(&event)?;
        next = read_event(&mut events)?;
    }
    println!(
        "{}",
        serde_json::json!({"records":count,"mapped_capture_sha256":format!("{:x}",hash.finalize()),
        "mapping_policy":"reference evidence through original USB arrival; acceptance wait not reconstructed"})
    );
    Ok(())
}
