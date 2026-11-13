//! Attempt windows and phase intervals taken from the small session manifests.
use crate::error::{Error, Result};
use crate::source::SessionInfo;
use crate::vfs::Vfs;
use arrow_array::{ArrayRef, BooleanArray, Int64Array, RecordBatch, StringArray, UInt32Array};
use arrow_schema::{DataType, Field, Schema};
use parquet::arrow::ArrowWriter;
use parquet::basic::{Compression, ZstdLevel};
use parquet::file::properties::WriterProperties;
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;

/// Phase names in protocol order.
pub const PHASES: [&str; 3] = ["countdown", "action", "recovery"];

/// One recorded attempt.
#[derive(Debug, Clone)]
pub struct Attempt {
    pub trial_ordinal: u32,
    pub attempt: u32,
    pub repetition: Option<u32>,
    pub scenario_id: String,
    pub activity_label: String,
    pub status: Option<String>,
    pub start_ns: i64,
    pub end_ns: Option<i64>,
    pub action_confirmed: bool,
    pub action_confirmed_ns: Option<i64>,
    pub directory: String,
}

/// One phase interval of an attempt.
#[derive(Debug, Clone)]
pub struct PhaseInterval {
    pub trial_ordinal: u32,
    pub attempt: u32,
    pub phase: String,
    pub start_ns: i64,
    pub end_ns: Option<i64>,
}

/// Read every `attempt.json`, sorted by trial and attempt number.
pub fn read_attempts(vfs: &dyn Vfs, info: &SessionInfo) -> Result<Vec<Attempt>> {
    let base = format!("{}trials/", info.prefix);
    let mut attempts = Vec::new();
    for file in vfs.files() {
        let Some(rest) = file.strip_prefix(&base) else {
            continue;
        };
        let parts: Vec<&str> = rest.split('/').collect();
        if parts.len() != 3 || parts[2] != "attempt.json" {
            continue;
        }
        let number = parts[1]
            .strip_prefix("attempt_")
            .and_then(|n| n.parse::<u32>().ok())
            .ok_or_else(|| Error(format!("unexpected attempt directory {}", parts[1])))?;
        let value: Value = serde_json::from_slice(&vfs.read_all(file)?)?;
        let ordinal = value["trial_ordinal"]
            .as_u64()
            .or_else(|| parts[0].split('_').next().and_then(|n| n.parse().ok()))
            .ok_or_else(|| Error(format!("attempt without trial ordinal: {file}")))?
            as u32;
        attempts.push(Attempt {
            trial_ordinal: ordinal,
            attempt: number,
            repetition: value["repetition"].as_u64().map(|v| v as u32),
            scenario_id: value["scenario_id"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            activity_label: value["activity_label"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            status: value["status"].as_str().map(str::to_string),
            start_ns: value["started_monotonic_ns"]
                .as_i64()
                .ok_or_else(|| Error(format!("attempt without start time: {file}")))?,
            end_ns: value["ended_monotonic_ns"].as_i64(),
            action_confirmed: value["action_confirmed"].as_bool().unwrap_or(false),
            action_confirmed_ns: value["action_confirmed_monotonic_ns"].as_i64(),
            // Relative to the session, so tables from a directory and from an
            // archive of it are identical.
            directory: file
                .strip_prefix(info.prefix)
                .unwrap_or(file)
                .trim_end_matches("/attempt.json")
                .to_string(),
        });
    }
    attempts.sort_by_key(|a| (a.trial_ordinal, a.attempt));
    Ok(attempts)
}

/// Rebuild phase intervals from `phase_changed` events.
///
/// Mirrors the interval rule of the analysis timeline: a phase ends where the
/// next transition starts, and the last one ends at the attempt's end time or
/// its final `trial_resolved` event.
pub fn read_phases(
    vfs: &dyn Vfs,
    info: &SessionInfo,
    attempts: &[Attempt],
) -> Result<Vec<PhaseInterval>> {
    let path = format!("{}events.jsonl", info.prefix);
    if !vfs.exists(&path) {
        return Ok(Vec::new());
    }
    let mut grouped: BTreeMap<(u32, u32), Vec<Value>> = BTreeMap::new();
    for line in String::from_utf8_lossy(&vfs.read_all(&path)?).lines() {
        if line.trim().is_empty() {
            continue;
        }
        let Ok(event) = serde_json::from_str::<Value>(line) else {
            continue; // a torn final line from a crash
        };
        if let (Some(trial), Some(attempt)) =
            (event["trial_ordinal"].as_u64(), event["attempt"].as_u64())
        {
            grouped
                .entry((trial as u32, attempt as u32))
                .or_default()
                .push(event);
        }
    }
    let mut phases = Vec::new();
    for attempt in attempts {
        let Some(events) = grouped.get_mut(&(attempt.trial_ordinal, attempt.attempt)) else {
            continue;
        };
        events.sort_by_key(|e| e["monotonic_ns"].as_i64().unwrap_or(i64::MAX));
        let transitions: Vec<&Value> = events
            .iter()
            .filter(|e| e["kind"] == "phase_changed")
            .collect();
        let resolved_end = events
            .iter()
            .rfind(|e| e["kind"] == "trial_resolved")
            .and_then(|e| e["monotonic_ns"].as_i64());
        let end = attempt.end_ns.or(resolved_end);
        for (index, event) in transitions.iter().enumerate() {
            let Some(state) = event["state"].as_str().filter(|s| PHASES.contains(s)) else {
                continue;
            };
            let Some(start) = event["monotonic_ns"].as_i64() else {
                continue;
            };
            let stop = transitions
                .get(index + 1)
                .and_then(|next| next["monotonic_ns"].as_i64())
                .or(end);
            phases.push(PhaseInterval {
                trial_ordinal: attempt.trial_ordinal,
                attempt: attempt.attempt,
                phase: state.to_string(),
                start_ns: start,
                end_ns: stop,
            });
        }
    }
    Ok(phases)
}

fn small_properties() -> Result<WriterProperties> {
    Ok(WriterProperties::builder()
        .set_compression(Compression::ZSTD(ZstdLevel::try_new(3)?))
        .build())
}

fn write_batch(path: &Path, batch: &RecordBatch) -> Result<()> {
    let temporary = path.with_extension("parquet.tmp");
    let mut writer = ArrowWriter::try_new(
        File::create(&temporary)?,
        batch.schema(),
        Some(small_properties()?),
    )?;
    writer.write(batch)?;
    writer.close()?;
    File::open(&temporary)?.sync_all()?;
    std::fs::rename(&temporary, path)?;
    Ok(())
}

/// Write `attempts.parquet`; `attempt_index` is the row number.
pub fn write_attempts(path: &Path, attempts: &[Attempt]) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("attempt_index", DataType::UInt32, false),
        Field::new("trial_ordinal", DataType::UInt32, false),
        Field::new("attempt", DataType::UInt32, false),
        Field::new("repetition", DataType::UInt32, true),
        Field::new("scenario_id", DataType::Utf8, false),
        Field::new("activity_label", DataType::Utf8, false),
        Field::new("status", DataType::Utf8, true),
        Field::new("start_ns", DataType::Int64, false),
        Field::new("end_ns", DataType::Int64, true),
        Field::new("action_confirmed", DataType::Boolean, false),
        Field::new("action_confirmed_ns", DataType::Int64, true),
        Field::new("directory", DataType::Utf8, false),
    ]));
    let columns: Vec<ArrayRef> = vec![
        Arc::new(UInt32Array::from_iter_values(0..attempts.len() as u32)),
        Arc::new(UInt32Array::from_iter_values(
            attempts.iter().map(|a| a.trial_ordinal),
        )),
        Arc::new(UInt32Array::from_iter_values(
            attempts.iter().map(|a| a.attempt),
        )),
        Arc::new(UInt32Array::from_iter(
            attempts.iter().map(|a| a.repetition),
        )),
        Arc::new(StringArray::from_iter_values(
            attempts.iter().map(|a| a.scenario_id.as_str()),
        )),
        Arc::new(StringArray::from_iter_values(
            attempts.iter().map(|a| a.activity_label.as_str()),
        )),
        Arc::new(StringArray::from_iter(
            attempts.iter().map(|a| a.status.as_deref()),
        )),
        Arc::new(Int64Array::from_iter_values(
            attempts.iter().map(|a| a.start_ns),
        )),
        Arc::new(Int64Array::from_iter(attempts.iter().map(|a| a.end_ns))),
        Arc::new(BooleanArray::from_iter(
            attempts.iter().map(|a| Some(a.action_confirmed)),
        )),
        Arc::new(Int64Array::from_iter(
            attempts.iter().map(|a| a.action_confirmed_ns),
        )),
        Arc::new(StringArray::from_iter_values(
            attempts.iter().map(|a| a.directory.as_str()),
        )),
    ];
    write_batch(path, &RecordBatch::try_new(schema, columns)?)
}

/// Write `phases.parquet`, with `attempt_index` pointing into `attempts.parquet`.
pub fn write_phases(path: &Path, attempts: &[Attempt], phases: &[PhaseInterval]) -> Result<()> {
    let index = |p: &PhaseInterval| {
        attempts
            .iter()
            .position(|a| a.trial_ordinal == p.trial_ordinal && a.attempt == p.attempt)
            .unwrap_or(usize::MAX) as u32
    };
    let schema = Arc::new(Schema::new(vec![
        Field::new("attempt_index", DataType::UInt32, false),
        Field::new("trial_ordinal", DataType::UInt32, false),
        Field::new("attempt", DataType::UInt32, false),
        Field::new("phase", DataType::Utf8, false),
        Field::new("start_ns", DataType::Int64, false),
        Field::new("end_ns", DataType::Int64, true),
    ]));
    let columns: Vec<ArrayRef> = vec![
        Arc::new(UInt32Array::from_iter_values(phases.iter().map(index))),
        Arc::new(UInt32Array::from_iter_values(
            phases.iter().map(|p| p.trial_ordinal),
        )),
        Arc::new(UInt32Array::from_iter_values(
            phases.iter().map(|p| p.attempt),
        )),
        Arc::new(StringArray::from_iter_values(
            phases.iter().map(|p| p.phase.as_str()),
        )),
        Arc::new(Int64Array::from_iter_values(
            phases.iter().map(|p| p.start_ns),
        )),
        Arc::new(Int64Array::from_iter(phases.iter().map(|p| p.end_ns))),
    ];
    write_batch(path, &RecordBatch::try_new(schema, columns)?)
}
