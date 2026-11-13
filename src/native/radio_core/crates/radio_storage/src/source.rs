//! Raw session inputs: manifest, run discovery, journals, and capture events.
use crate::error::{Error, Result};
use crate::vfs::{Vfs, session_prefix};
use radio_transport::wire::MAX_ENVELOPE;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
use std::io::{BufRead, BufReader, Read};
use std::path::Path;

/// Identity and receiver mapping read from `session.json`.
#[derive(Debug, Clone)]
pub struct SessionInfo {
    /// Logical prefix of the session root (`original/` inside archives).
    pub prefix: &'static str,
    pub session_id: String,
    pub protocol_hash: String,
    /// Lowercase colon-separated receiver MAC to receiver id.
    pub receiver_ids: BTreeMap<String, String>,
}

/// Read `session.json` from a source.
pub fn session_info(vfs: &dyn Vfs) -> Result<SessionInfo> {
    let prefix = session_prefix(vfs);
    let bytes = vfs.read_all(&format!("{prefix}session.json"))?;
    let value: Value = serde_json::from_slice(&bytes)?;
    let text = |key: &str| value[key].as_str().unwrap_or_default().to_string();
    let mut receiver_ids = BTreeMap::new();
    if let Some(map) = value["environment"]["receiver_ids"].as_object() {
        for (mac, id) in map {
            if let Some(id) = id.as_str() {
                receiver_ids.insert(mac.to_lowercase(), id.to_string());
            }
        }
    }
    Ok(SessionInfo {
        prefix,
        session_id: text("session_id"),
        protocol_hash: text("protocol_hash"),
        receiver_ids,
    })
}

/// Logical files of a session, relative to the session root.
///
/// Archives wrap the session in `original/`; that prefix is removed so callers
/// see the same paths for directories and archives.
pub fn session_files(vfs: &dyn Vfs) -> Vec<String> {
    let prefix = session_prefix(vfs);
    vfs.files()
        .iter()
        .filter_map(|file| file.strip_prefix(prefix).map(str::to_string))
        .collect()
}

/// Read one file by its path relative to the session root.
pub fn read_session_file(vfs: &dyn Vfs, relative: &str) -> Result<Vec<u8>> {
    if relative
        .split('/')
        .any(|part| part == ".." || part.is_empty())
    {
        return Err(Error(format!("invalid session path: {relative}")));
    }
    vfs.read_all(&format!("{}{relative}", session_prefix(vfs)))
}

/// Write one decoded file of a session to `destination`; returns its size.
///
/// The file appears at `destination` only once it is complete, so an
/// interrupted copy never leaves a partial file under the final name. Parent
/// directories are created.
pub fn extract_session_file(vfs: &dyn Vfs, relative: &str, destination: &Path) -> Result<u64> {
    if relative
        .split('/')
        .any(|part| part == ".." || part.is_empty())
    {
        return Err(Error(format!("invalid session path: {relative}")));
    }
    if let Some(parent) = destination.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut partial = destination.as_os_str().to_os_string();
    partial.push(".part");
    let partial = std::path::PathBuf::from(partial);
    let mut written = 0u64;
    let result = vfs.read(
        &format!("{}{relative}", session_prefix(vfs)),
        &mut |reader| {
            let mut out = std::fs::File::create(&partial)?;
            written = std::io::copy(reader, &mut out)?;
            out.sync_all()?;
            Ok(())
        },
    );
    match result {
        Ok(()) => {
            std::fs::rename(&partial, destination)?;
            Ok(written)
        }
        Err(error) => {
            let _ = std::fs::remove_file(&partial);
            Err(error)
        }
    }
}

/// One transport run found in a session.
#[derive(Debug, Clone)]
pub struct RunSource {
    pub run_id: u64,
    pub envelopes: String,
    pub events: Option<String>,
}

/// Find every run directory that contains an `envelopes.bin`.
pub fn discover_runs(vfs: &dyn Vfs, info: &SessionInfo) -> Result<Vec<RunSource>> {
    let base = format!("{}transport/gateway/", info.prefix);
    let mut runs = Vec::new();
    for file in vfs.files() {
        let Some(rest) = file.strip_prefix(&base) else {
            continue;
        };
        let Some((dir, name)) = rest.split_once('/') else {
            continue;
        };
        if name != "envelopes.bin" {
            continue;
        }
        let run_id = u64::from_str_radix(dir, 16)
            .map_err(|_| Error(format!("run directory is not hexadecimal: {dir}")))?;
        let events = format!("{base}{dir}/events.jsonl");
        runs.push(RunSource {
            run_id,
            envelopes: file.clone(),
            events: vfs.exists(&events).then_some(events),
        });
    }
    Ok(runs)
}

/// Outcome of walking a journal.
#[derive(Debug, Default, Clone, Copy)]
pub struct JournalTail {
    pub entries: u64,
    /// True when the file ends inside an entry (crash while writing).
    pub torn: bool,
}

/// Call `visit(arrival_ns, envelope)` for each complete journal entry.
///
/// A truncated final entry is reported in the result, not as an error.
pub fn for_each_envelope(
    vfs: &dyn Vfs,
    path: &str,
    visit: &mut dyn FnMut(u64, &[u8]) -> Result<()>,
) -> Result<JournalTail> {
    let mut tail = JournalTail::default();
    vfs.read(path, &mut |reader| {
        let mut reader = BufReader::with_capacity(1 << 20, reader);
        let mut envelope = Vec::with_capacity(MAX_ENVELOPE);
        loop {
            let mut header = [0u8; 12];
            let got = read_full(&mut reader, &mut header)?;
            if got == 0 {
                return Ok(());
            }
            if got < 12 {
                tail.torn = true;
                return Ok(());
            }
            let arrival = u64::from_be_bytes(header[..8].try_into().unwrap());
            let length = u32::from_be_bytes(header[8..].try_into().unwrap()) as usize;
            if length > MAX_ENVELOPE {
                return Err(Error(format!("oversized journal envelope in {path}")));
            }
            envelope.resize(length, 0);
            if read_full(&mut reader, &mut envelope)? < length {
                tail.torn = true;
                return Ok(());
            }
            visit(arrival, &envelope)?;
            tail.entries += 1;
        }
    })?;
    Ok(tail)
}

/// Arrival time of the first journal entry, or `None` for an empty journal.
pub fn first_arrival(vfs: &dyn Vfs, path: &str) -> Result<Option<u64>> {
    let mut first = None;
    vfs.read(path, &mut |reader| {
        let mut header = [0u8; 8];
        if read_full(reader, &mut header)? == 8 {
            first = Some(u64::from_be_bytes(header));
        }
        Ok(())
    })?;
    Ok(first)
}

fn read_full(reader: &mut dyn Read, buffer: &mut [u8]) -> Result<usize> {
    let mut filled = 0;
    while filled < buffer.len() {
        match reader.read(&mut buffer[filled..])? {
            0 => break,
            n => filled += n,
        }
    }
    Ok(filled)
}

/// Capture metadata for one frame from a Python-era `record` event.
#[derive(Debug, Clone, Copy)]
pub struct PythonCapture {
    pub capture_ns: Option<i64>,
    pub uncertainty_us: Option<f32>,
    pub timely: Option<bool>,
}

/// Key joining a `record` event to a journal frame.
pub type PythonKey = (u8, u32, u32, u32);

/// One Rust-era `batch_acceptance` event.
#[derive(Debug, Clone)]
pub struct BatchEvent {
    pub run: u64,
    pub tx_boot: u32,
    pub rx_boot: u32,
    pub receiver: String,
    pub batch: u32,
    pub uncertainty_us: Option<f32>,
    /// `(sequence, capture_ns)` per record, in envelope order.
    pub records: Vec<(u32, Option<i64>)>,
}

/// Capture events found in one run.
#[derive(Debug, Default)]
pub enum CaptureEvents {
    #[default]
    None,
    Python {
        receivers: HashMap<String, u8>,
        records: HashMap<PythonKey, PythonCapture>,
    },
    Rust(Vec<BatchEvent>),
}

/// Result of scanning a run's event log.
#[derive(Debug, Default)]
pub struct EventScan {
    pub capture: CaptureEvents,
    /// Number of unterminated final lines that were ignored.
    pub torn_lines: u64,
}

// Cheap prefilters on the kind value alone, so spacing in the JSON does not matter.
const RECORD: &[u8] = b"\"record\"";
const ACCEPTANCE: &[u8] = b"batch_acceptance";

/// Scan a run's `events.jsonl` for per-frame capture information.
///
/// Only lines containing the two capture kinds are parsed. Both kinds in one
/// run is an error because no collector ever wrote both.
pub fn scan_events(vfs: &dyn Vfs, path: &str) -> Result<EventScan> {
    let mut scan = EventScan::default();
    let mut receivers: HashMap<String, u8> = HashMap::new();
    let mut records: HashMap<PythonKey, PythonCapture> = HashMap::new();
    let mut batches: Vec<BatchEvent> = Vec::new();
    vfs.read(path, &mut |reader| {
        let mut reader = BufReader::with_capacity(1 << 20, reader);
        let mut line = Vec::new();
        loop {
            line.clear();
            if reader.read_until(b'\n', &mut line)? == 0 {
                return Ok(());
            }
            if line.last() != Some(&b'\n') {
                scan.torn_lines += 1;
                return Ok(());
            }
            let acceptance = memchr::memmem::find(&line, ACCEPTANCE).is_some();
            if !acceptance && memchr::memmem::find(&line, RECORD).is_none() {
                continue;
            }
            let value: Value = serde_json::from_slice(&line)?;
            if acceptance && value["kind"] == "batch_acceptance" {
                batches.push(parse_acceptance(&value)?);
            } else if value["kind"] == "record" {
                let name = value["receiver_id"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string();
                let next = receivers.len() as u8;
                let slot = *receivers.entry(name).or_insert(next);
                let key = (
                    slot,
                    value["receiver_boot_id"].as_u64().unwrap_or(0) as u32,
                    value["transmitter_boot_id"].as_u64().unwrap_or(0) as u32,
                    value["sequence"].as_u64().unwrap_or(0) as u32,
                );
                records.insert(
                    key,
                    PythonCapture {
                        capture_ns: value["capture_host_ns"].as_i64(),
                        uncertainty_us: value["clock_uncertainty_us"].as_f64().map(|v| v as f32),
                        timely: value["timely"].as_bool(),
                    },
                );
            }
        }
    })?;
    scan.capture = match (records.is_empty(), batches.is_empty()) {
        (true, true) => CaptureEvents::None,
        (false, true) => CaptureEvents::Python { receivers, records },
        (true, false) => CaptureEvents::Rust(batches),
        (false, false) => {
            return Err(Error(format!(
                "{path} mixes record and batch_acceptance events"
            )));
        }
    };
    Ok(scan)
}

fn parse_acceptance(value: &Value) -> Result<BatchEvent> {
    let number = |v: &Value, key: &str| -> Result<u64> {
        v[key]
            .as_u64()
            .ok_or_else(|| Error(format!("batch_acceptance missing {key}")))
    };
    let run = value["run"]
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .ok_or_else(|| Error("batch_acceptance missing run".into()))?;
    let records = value["records"]
        .as_array()
        .ok_or_else(|| Error("batch_acceptance missing records".into()))?
        .iter()
        .map(|record| {
            Ok((
                number(record, "sequence")? as u32,
                record["capture_ns"].as_i64(),
            ))
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(BatchEvent {
        run,
        tx_boot: number(value, "transmitter_boot")? as u32,
        rx_boot: number(value, "receiver_boot")? as u32,
        receiver: value["receiver"].as_str().unwrap_or_default().to_string(),
        batch: number(value, "batch")? as u32,
        uncertainty_us: value["clock_uncertainty_us"].as_f64().map(|v| v as f32),
        records,
    })
}
