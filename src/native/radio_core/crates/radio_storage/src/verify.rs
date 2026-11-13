//! Verify a converted session directory against its own manifest.
use crate::convert::{ConvertOptions, FrameScope, convert_session, sha256_file};
use crate::error::{Error, Result};
use crate::schema::SCHEMA_VERSION;
use crate::vfs::Vfs;
use arrow_array::{Array, Int64Array, StringArray, UInt16Array, UInt32Array};
use parquet::arrow::ProjectionMask;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::Value;
use std::collections::{BTreeMap, HashSet};
use std::fs::File;
use std::path::Path;

/// Outcome of a verification.
#[derive(Debug, Default)]
pub struct VerifyReport {
    /// Problems found; empty means the table set is consistent.
    pub problems: Vec<String>,
    pub frames: u64,
    /// Backward steps in `capture_time_ns` (reported, not a failure).
    pub capture_backward_steps: u64,
}

impl VerifyReport {
    /// True when no problem was found.
    pub fn ok(&self) -> bool {
        self.problems.is_empty()
    }
}

/// Check hashes, metadata, row counts and journal order of a converted directory.
pub fn verify_dir(dir: &Path) -> Result<VerifyReport> {
    let mut report = VerifyReport::default();
    let manifest: Value = serde_json::from_slice(&std::fs::read(dir.join("conversion.json"))?)?;
    if let Some(outputs) = manifest["outputs"].as_object() {
        for (name, expected) in outputs {
            let path = dir.join(name);
            match sha256_file(&path) {
                Ok(actual) if Some(actual.as_str()) == expected["sha256"].as_str() => {}
                Ok(_) => report
                    .problems
                    .push(format!("{name}: sha256 differs from conversion.json")),
                Err(error) => report.problems.push(format!("{name}: {error}")),
            }
        }
    } else {
        report
            .problems
            .push("conversion.json has no outputs".into());
    }
    if manifest["storage_schema_version"].as_u64() != Some(SCHEMA_VERSION as u64) {
        report
            .problems
            .push("conversion.json has an unexpected schema version".into());
    }

    let frames = dir.join("frames.parquet");
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(&frames)?)?;
    let metadata = builder.metadata().file_metadata();
    let kv: BTreeMap<String, String> = metadata
        .key_value_metadata()
        .map(|items| {
            items
                .iter()
                .filter_map(|i| Some((i.key.clone(), i.value.clone()?)))
                .collect()
        })
        .unwrap_or_default();
    if kv.get("storage_schema_version").map(String::as_str) != Some(&SCHEMA_VERSION.to_string()) {
        report
            .problems
            .push("frames.parquet has an unexpected schema version".into());
    }
    if kv.get("source_fingerprint").map(String::as_str) != manifest["source_fingerprint"].as_str() {
        report
            .problems
            .push("source fingerprint differs between file and manifest".into());
    }
    let recorded: BTreeMap<String, u64> = kv
        .get("row_count")
        .and_then(|v| serde_json::from_str(v).ok())
        .unwrap_or_default();
    report.frames = metadata.num_rows() as u64;
    if recorded.values().sum::<u64>() != report.frames {
        report
            .problems
            .push("row_count metadata does not add up to the file's rows".into());
    }

    let schema = builder.schema().clone();
    let columns = [
        "run_index",
        "receiver_id",
        "host_arrival_ns",
        "sequence",
        "capture_time_ns",
    ];
    let indices: Vec<usize> = columns
        .iter()
        .map(|c| {
            schema
                .index_of(c)
                .map_err(|_| Error(format!("missing column {c}")))
        })
        .collect::<Result<_>>()?;
    let mask = ProjectionMask::roots(builder.parquet_schema(), indices);
    let reader = builder
        .with_projection(mask)
        .with_batch_size(65_536)
        .build()?;

    let mut finished: HashSet<(u16, String)> = HashSet::new();
    let mut current: Option<(u16, String)> = None;
    let mut last: Option<(i64, u32)> = None;
    let mut last_capture: Option<i64> = None;
    let mut counted: BTreeMap<String, u64> = BTreeMap::new();
    for batch in reader {
        let batch = batch?;
        let named = |name: &str| {
            batch
                .column_by_name(name)
                .ok_or_else(|| Error(format!("missing column {name}")))
        };
        let run = named("run_index")?
            .as_any()
            .downcast_ref::<UInt16Array>()
            .ok_or_else(|| Error("run_index is not UInt16".into()))?;
        let receiver = named("receiver_id")?
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| Error("receiver_id is not Utf8".into()))?;
        let arrival = named("host_arrival_ns")?
            .as_any()
            .downcast_ref::<Int64Array>()
            .ok_or_else(|| Error("host_arrival_ns is not Int64".into()))?;
        let sequence = named("sequence")?
            .as_any()
            .downcast_ref::<UInt32Array>()
            .ok_or_else(|| Error("sequence is not UInt32".into()))?;
        let capture = named("capture_time_ns")?
            .as_any()
            .downcast_ref::<Int64Array>()
            .ok_or_else(|| Error("capture_time_ns is not Int64".into()))?;
        for row in 0..batch.num_rows() {
            let group = (run.value(row), receiver.value(row).to_string());
            *counted.entry(group.1.clone()).or_default() += 1;
            if current.as_ref() != Some(&group) {
                if let Some(done) = current.take() {
                    finished.insert(done);
                }
                if finished.contains(&group) {
                    report
                        .problems
                        .push(format!("group {group:?} is not contiguous"));
                }
                current = Some(group);
                last = None;
                last_capture = None;
            }
            let point = (arrival.value(row), sequence.value(row));
            if let Some(before) = last {
                if point.0 < before.0 {
                    report
                        .problems
                        .push(format!("arrival decreases at sequence {}", point.1));
                }
                if point.1 <= before.1 {
                    report
                        .problems
                        .push(format!("sequence does not increase at {}", point.1));
                }
            }
            last = Some(point);
            if !capture.is_null(row) {
                let value = capture.value(row);
                if last_capture.is_some_and(|before| value < before) {
                    report.capture_backward_steps += 1;
                }
                last_capture = Some(value);
            }
        }
        if report.problems.len() > 50 {
            report
                .problems
                .push("too many ordering problems; stopping".into());
            break;
        }
    }
    if counted != recorded {
        report
            .problems
            .push("per-receiver row counts differ from file metadata".into());
    }
    Ok(report)
}

/// Re-convert `source` and require byte-identical derived tables.
///
/// Proves the conversion is a pure function of the source: the recorded hash
/// of each output must equal the hash of a fresh conversion.
pub fn verify_against_source(
    vfs: &dyn Vfs,
    dir: &Path,
    options: &ConvertOptions,
) -> Result<VerifyReport> {
    let mut report = verify_dir(dir)?;
    // Reproduce with the scope the tables were built with.
    let manifest: Value = serde_json::from_slice(&std::fs::read(dir.join("conversion.json"))?)?;
    let mut options = *options;
    options.scope = match manifest["frame_scope"].as_str() {
        Some("all") => FrameScope::All,
        _ => FrameScope::Attempts,
    };
    let options = &options;
    let scratch = dir.join(".verify-reproduction");
    if scratch.exists() {
        std::fs::remove_dir_all(&scratch)?;
    }
    let result = convert_session(vfs, &scratch, options);
    let outcome = result.and_then(|_| {
        for name in ["frames.parquet", "attempts.parquet", "phases.parquet"] {
            let fresh = sha256_file(&scratch.join(name))?;
            let recorded = sha256_file(&dir.join(name))?;
            if fresh != recorded {
                report.problems.push(format!(
                    "{name}: fresh conversion differs from stored table"
                ));
            }
        }
        Ok(())
    });
    let _ = std::fs::remove_dir_all(&scratch);
    outcome?;
    Ok(report)
}
