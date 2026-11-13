//! Converted session tables: open, check currency, convert on demand.
use crate::convert::{ConvertOptions, convert_session};
use crate::error::{Error, Result};
use crate::read::{FrameQuery, read_frames_with_schema};
use crate::schema::SCHEMA_VERSION;
use crate::vfs::Vfs;
use arrow_array::{Array, RecordBatch};
use arrow_schema::SchemaRef;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::Value;
use std::fs::File;
use std::path::{Path, PathBuf};

const TABLES: [&str; 3] = ["frames.parquet", "attempts.parquet", "phases.parquet"];

/// A table read whole: its schema, which exists even without rows, and batches.
pub type Table = (SchemaRef, Vec<RecordBatch>);

/// One converted session: its manifest and the directory of derived tables.
#[derive(Debug, Clone)]
pub struct FrameStore {
    pub directory: PathBuf,
    /// Contents of `conversion.json`.
    pub manifest: Value,
}

fn read_manifest(directory: &Path) -> Result<Value> {
    Ok(serde_json::from_slice(&std::fs::read(
        directory.join("conversion.json"),
    )?)?)
}

/// True when `directory` holds a complete conversion of the source with
/// `source_fingerprint` at the current table schema version.
pub fn tables_current(directory: &Path, source_fingerprint: &str) -> bool {
    let Ok(manifest) = read_manifest(directory) else {
        return false;
    };
    manifest["source_fingerprint"].as_str() == Some(source_fingerprint)
        && manifest["storage_schema_version"].as_u64() == Some(SCHEMA_VERSION as u64)
        && TABLES.iter().all(|name| directory.join(name).is_file())
}

fn read_table(path: &Path) -> Result<Table> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path)?)?;
    let schema = builder.schema().clone();
    let batches = builder
        .build()?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok((schema, batches))
}

impl FrameStore {
    /// Open a converted session directory.
    pub fn open(directory: &Path) -> Result<Self> {
        let manifest = read_manifest(directory).map_err(|error| {
            Error(format!(
                "{}: {error}",
                directory.join("conversion.json").display()
            ))
        })?;
        if !directory.join("frames.parquet").is_file() {
            return Err(Error(format!(
                "{} is missing",
                directory.join("frames.parquet").display()
            )));
        }
        Ok(Self {
            directory: directory.to_path_buf(),
            manifest,
        })
    }

    /// Identifier of the source session.
    pub fn session_id(&self) -> &str {
        self.manifest["session_id"].as_str().unwrap_or_default()
    }

    /// Fingerprint of the raw source the tables were derived from.
    pub fn source_fingerprint(&self) -> &str {
        self.manifest["source_fingerprint"]
            .as_str()
            .unwrap_or_default()
    }

    /// One row per recorded attempt.
    pub fn attempts(&self) -> Result<Table> {
        read_table(&self.directory.join("attempts.parquet"))
    }

    /// Phase intervals.
    pub fn phases(&self) -> Result<Table> {
        read_table(&self.directory.join("phases.parquet"))
    }

    /// Frames matching `query`, pruned by row-group statistics.
    pub fn frames(&self, query: &FrameQuery) -> Result<Table> {
        read_frames_with_schema(&self.directory.join("frames.parquet"), query)
    }

    /// Frames captured inside one attempt window, `start_ns <= t < end_ns`.
    ///
    /// An attempt without an end time extends to the end of the session.
    pub fn attempt_frames(
        &self,
        attempt_index: usize,
        receiver_id: Option<String>,
        columns: Option<Vec<String>>,
    ) -> Result<Table> {
        let (_, batches) = self.attempts()?;
        let mut remaining = attempt_index;
        for batch in &batches {
            if remaining < batch.num_rows() {
                let int = |name: &str| -> Result<&arrow_array::Int64Array> {
                    batch
                        .column_by_name(name)
                        .and_then(|column| column.as_any().downcast_ref())
                        .ok_or_else(|| Error(format!("attempts table has no int64 {name}")))
                };
                let (start, end) = (int("start_ns")?, int("end_ns")?);
                return self.frames(&FrameQuery {
                    receiver_id,
                    capture_start_ns: Some(start.value(remaining)),
                    capture_end_ns: (!end.is_null(remaining)).then(|| end.value(remaining)),
                    columns,
                });
            }
            remaining -= batch.num_rows();
        }
        Err(Error(format!("attempt {attempt_index} out of range")))
    }
}

/// Open the converted tables of `source`, converting only when needed.
///
/// The tables are reused when `conversion.json` records the source's current
/// fingerprint, the current schema version and a complete file set. Conversion
/// writes complete files atomically, so an interrupted run leaves the previous
/// tables untouched. `before_convert` runs just before a conversion starts.
///
/// Returns the store and whether a conversion happened.
pub fn ensure_frames(
    source: &dyn Vfs,
    directory: &Path,
    rebuild: bool,
    before_convert: &mut dyn FnMut(),
) -> Result<(FrameStore, bool)> {
    let fingerprint = source.fingerprint()?;
    if !rebuild && tables_current(directory, &fingerprint) {
        return Ok((FrameStore::open(directory)?, false));
    }
    before_convert();
    convert_session(source, directory, &ConvertOptions::default())?;
    Ok((FrameStore::open(directory)?, true))
}
