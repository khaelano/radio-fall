//! Synthetic session builder: writes valid journals, events, and manifests.
#![allow(dead_code)]
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};

pub struct TempDir(pub PathBuf);

impl TempDir {
    pub fn new(label: &str) -> Self {
        static COUNTER: AtomicU32 = AtomicU32::new(0);
        let path = std::env::temp_dir().join(format!(
            "radio-storage-{label}-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }
    pub fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

pub const RX1: [u8; 6] = [0x44, 0xbd, 0x8d, 0xd0, 0xb1, 0x4c];
pub const RX2: [u8; 6] = [0x44, 0xbd, 0x8d, 0xd0, 0xb3, 0x50];
pub const TX: [u8; 6] = [0x10, 0xbd, 0xa3, 0x9e, 0xcd, 0x68];

pub fn mac_text(mac: &[u8; 6]) -> String {
    mac.iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(":")
}

#[derive(Clone)]
pub struct Frame {
    pub receiver: [u8; 6],
    pub sequence: u32,
    pub rx_radio_us: u32,
    pub rssi: i8,
    pub payload: Vec<u8>,
    pub flags: u8,
}

impl Frame {
    pub fn new(receiver: [u8; 6], sequence: u32, width: usize) -> Self {
        let payload = (0..width)
            .map(|i| ((sequence as usize * 7 + i * 3) % 251) as u8)
            .collect();
        Self {
            receiver,
            sequence,
            rx_radio_us: 1_000_000 + sequence * 10_000,
            rssi: -40,
            payload,
            flags: 0,
        }
    }
}

pub fn record_bytes(frame: &Frame) -> Vec<u8> {
    let n = frame.payload.len();
    let mut out = Vec::with_capacity(87 + n);
    out.extend_from_slice(b"CSI1");
    out.push(3);
    out.push(frame.flags);
    out.extend_from_slice(&87u16.to_be_bytes());
    out.extend_from_slice(&(n as u16).to_be_bytes());
    out.extend_from_slice(&frame.receiver);
    out.extend_from_slice(&TX);
    out.extend_from_slice(&(frame.sequence / 2).to_be_bytes());
    out.extend_from_slice(&frame.sequence.to_be_bytes());
    out.extend_from_slice(&frame.rx_radio_us.to_be_bytes());
    out.push(frame.rssi as u8);
    out.push((-95i8) as u8);
    let fields: [u8; 15] = [11, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 44, 0, 0, 0];
    out.extend_from_slice(&fields);
    out.extend_from_slice(&36u16.to_be_bytes());
    out.extend_from_slice(&(n as u16).to_be_bytes());
    out.extend_from_slice(&(5_000 + frame.sequence as u64).to_be_bytes());
    out.extend_from_slice(&(6_000 + frame.sequence as u64).to_be_bytes());
    out.extend_from_slice(b"0123456789abcdef");
    out.extend_from_slice(&frame.payload);
    out
}

pub fn envelope(
    run: u64,
    tx_boot: u32,
    rx_boot: u32,
    id: u32,
    mac: [u8; 6],
    frames: &[Frame],
) -> Vec<u8> {
    let mut batch = Vec::new();
    batch.extend_from_slice(b"CSIB");
    batch.push(1);
    batch.push(0);
    batch.extend_from_slice(&60u16.to_be_bytes());
    batch.extend_from_slice(&rx_boot.to_be_bytes());
    batch.extend_from_slice(&id.to_be_bytes());
    batch.extend_from_slice(&(frames.len() as u16).to_be_bytes());
    batch.extend_from_slice(&0u16.to_be_bytes());
    batch.extend_from_slice(&[0u8; 40]);
    for frame in frames {
        let record = record_bytes(frame);
        batch.extend_from_slice(&(record.len() as u16).to_be_bytes());
        batch.extend_from_slice(&record);
    }
    let mut out = Vec::new();
    out.extend_from_slice(b"CGWY");
    out.push(1);
    out.push(0);
    out.extend_from_slice(&40u16.to_be_bytes());
    out.extend_from_slice(&run.to_be_bytes());
    out.extend_from_slice(&tx_boot.to_be_bytes());
    out.extend_from_slice(&rx_boot.to_be_bytes());
    out.extend_from_slice(&id.to_be_bytes());
    out.extend_from_slice(&mac);
    out.extend_from_slice(&(batch.len() as u16).to_be_bytes());
    out.extend_from_slice(&0u32.to_be_bytes());
    out.extend_from_slice(&batch);
    let crc = crc32fast::hash(&out);
    out.extend_from_slice(&crc.to_be_bytes());
    out
}

pub fn journal_entry(arrival_ns: u64, envelope: &[u8]) -> Vec<u8> {
    let mut out = arrival_ns.to_be_bytes().to_vec();
    out.extend_from_slice(&(envelope.len() as u32).to_be_bytes());
    out.extend_from_slice(envelope);
    out
}

#[derive(Clone, Copy, PartialEq)]
pub enum Era {
    Python,
    Rust,
}

/// Parameters of one synthetic run.
pub struct Run {
    pub run: u64,
    pub era: Era,
    /// Journal arrival of the first envelope, in nanoseconds.
    pub start_ns: u64,
    /// Envelopes per receiver, two frames each.
    pub batches: u32,
    pub width: usize,
    pub receivers: Vec<[u8; 6]>,
}

pub fn capture_for(run: &Run, sequence: u32) -> i64 {
    run.start_ns as i64 - 40_000_000 + sequence as i64 * 10_000_000
}

/// Write one run directory: journal plus events of the chosen era.
pub fn write_run(root: &Path, run: &Run) {
    let dir = root
        .join("transport/gateway")
        .join(format!("{:016x}", run.run));
    fs::create_dir_all(&dir).unwrap();
    let mut journal = Vec::new();
    let mut events = Vec::new();
    let mut arrival = run.start_ns;
    let rx_boot = 77u32;
    for batch_index in 0..run.batches {
        for (slot, receiver) in run.receivers.iter().enumerate() {
            let first = batch_index * 2;
            let frames: Vec<Frame> = (first..first + 2)
                .map(|sequence| Frame::new(*receiver, sequence, run.width))
                .collect();
            let id = batch_index;
            let bytes = envelope(run.run, 9, rx_boot, id, *receiver, &frames);
            journal.extend(journal_entry(arrival, &bytes));
            match run.era {
                Era::Python => {
                    for frame in &frames {
                        let line = serde_json::json!({
                            "kind": "record",
                            "host_monotonic_ns": arrival + 1000,
                            "receiver_id": format!("rx-{}", slot + 1),
                            "sequence": frame.sequence,
                            "receiver_boot_id": rx_boot,
                            "transmitter_boot_id": 9,
                            "capture_host_ns": capture_for(run, frame.sequence),
                            "arrival_ns": arrival,
                            "clock_uncertainty_us": 1500.5,
                            "timely": true,
                        });
                        events.extend(format!("{line}\n").into_bytes());
                    }
                }
                Era::Rust => {
                    let records: Vec<_> = frames
                        .iter()
                        .map(|f| {
                            // The first frame of the run has no mapped capture time.
                            let capture = if f.sequence == 0 {
                                serde_json::Value::Null
                            } else {
                                capture_for(run, f.sequence).into()
                            };
                            serde_json::json!({
                                "receiver": mac_text(receiver),
                                "sequence": f.sequence,
                                "tx_enqueue_us": 5_000 + f.sequence as u64,
                                "capture_ns": capture,
                            })
                        })
                        .collect();
                    let line = serde_json::json!({
                        "kind": "batch_acceptance",
                        "host_monotonic_ns": arrival + 1000,
                        "run": run.run.to_string(),
                        "transmitter_boot": 9,
                        "receiver_boot": rx_boot,
                        "receiver": mac_text(receiver),
                        "batch": id,
                        "arrival_ns": arrival,
                        "available_ns": arrival + 500,
                        "clock_uncertainty_us": 250.0,
                        "records": records,
                    });
                    events.extend(format!("{line}\n").into_bytes());
                }
            }
            // Unrelated diagnostic events must be ignored.
            events.extend(b"{\"kind\":\"gateway_status\",\"host_monotonic_ns\":1}\n");
            arrival += 5_000_000;
        }
    }
    fs::write(dir.join("envelopes.bin"), journal).unwrap();
    fs::write(dir.join("events.jsonl"), events).unwrap();
    fs::write(dir.join("manifest.json"), b"{\"schema_version\":1}\n").unwrap();
}

pub fn write_session_files(root: &Path, attempt_start_ns: i64, attempt_end_ns: i64) {
    fs::create_dir_all(root).unwrap();
    let session = serde_json::json!({
        "artifact_schema_version": 2,
        "session_id": "20261113T000000000000Z",
        "protocol_hash": "abc123",
        "environment": {"receiver_ids": {
            mac_text(&RX1): "rx-1",
            mac_text(&RX2): "rx-2",
        }},
    });
    fs::write(
        root.join("session.json"),
        serde_json::to_vec_pretty(&session).unwrap(),
    )
    .unwrap();
    let attempt_dir = root.join("trials/001_activity/attempt_01");
    fs::create_dir_all(&attempt_dir).unwrap();
    let attempt = serde_json::json!({
        "trial_ordinal": 1, "repetition": 1, "scenario_id": "activity",
        "activity_label": "non_fall", "status": "accepted",
        "started_monotonic_ns": attempt_start_ns, "ended_monotonic_ns": attempt_end_ns,
        "action_confirmed": true, "action_confirmed_monotonic_ns": attempt_start_ns + 2_000,
    });
    fs::write(
        attempt_dir.join("attempt.json"),
        serde_json::to_vec(&attempt).unwrap(),
    )
    .unwrap();
    let mut events = Vec::new();
    for (state, offset) in [("countdown", 0i64), ("action", 1_000), ("recovery", 3_000)] {
        let line = serde_json::json!({
            "kind": "phase_changed", "state": state, "trial_ordinal": 1, "attempt": 1,
            "monotonic_ns": attempt_start_ns + offset,
        });
        events.extend(format!("{line}\n").into_bytes());
    }
    events.extend(b"{\"kind\":\"session_started\",\"monotonic_ns\":1}\n");
    fs::File::create(root.join("events.jsonl"))
        .unwrap()
        .write_all(&events)
        .unwrap();
}

/// Zip a session directory under `original/`, adding the given extra members.
pub fn zip_session(source: &Path, zip_path: &Path, extra: &[(&str, &[u8])]) {
    use std::io::Write;
    let file = fs::File::create(zip_path).unwrap();
    let mut writer = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let mut stack = vec![source.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let mut entries: Vec<_> = fs::read_dir(&dir)
            .unwrap()
            .map(|e| e.unwrap().path())
            .collect();
        entries.sort();
        for path in entries {
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let relative = path
                .strip_prefix(source)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            writer
                .start_file(format!("original/{relative}"), options)
                .unwrap();
            writer.write_all(&fs::read(&path).unwrap()).unwrap();
        }
    }
    for (name, data) in extra {
        writer.start_file(*name, options).unwrap();
        writer.write_all(data).unwrap();
    }
    writer.finish().unwrap();
}
