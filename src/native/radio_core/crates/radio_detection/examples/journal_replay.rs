//! Inspect accepted envelopes using the shared native decoder.
use std::{fs::File, io::BufReader};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args()
        .nth(1)
        .ok_or("usage: journal_replay ENVELOPES.bin")?;
    let mut reader = BufReader::new(File::open(path)?);
    let mut batches = 0u64;
    let mut records = 0u64;
    while let Some((arrival, batch)) = radio_transport::journal::read_entry(&mut reader)? {
        batches += 1;
        records += batch.records.len() as u64;
        println!(
            "{}",
            serde_json::json!({"arrival_ns":arrival,"run":batch.run.to_string(),
            "receiver":batch.mac,"batch":batch.id,"records":batch.records.len()})
        );
    }
    eprintln!("validated {batches} batches and {records} records");
    Ok(())
}
