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
use std::fs::{File, TryLockError};
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

/// Stage reported by [`ensure_frames`] to its progress callback.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnsureStage {
    /// Another process or thread holds the conversion lock; reported once.
    Waiting,
    /// The tables are stale and conversion is about to start.
    Converting,
}

/// Exclusive advisory lock released when dropped, on every path.
struct ConversionLock(File);

impl Drop for ConversionLock {
    fn drop(&mut self) {
        let _ = self.0.unlock();
    }
}

/// Path of the lock file guarding `directory`.
///
/// It is the sibling `<directory>.lock` rather than a file inside the
/// directory, so the lock stays valid while the directory is created or
/// replaced. The file is never deleted; removing it would let two holders lock
/// different inodes.
fn lock_path(directory: &Path) -> Result<PathBuf> {
    let name = directory
        .file_name()
        .ok_or_else(|| Error(format!("{} has no directory name", directory.display())))?;
    let mut name = name.to_os_string();
    name.push(".lock");
    Ok(directory.with_file_name(name))
}

fn acquire_lock(directory: &Path, progress: &mut dyn FnMut(EnsureStage)) -> Result<ConversionLock> {
    let path = lock_path(directory)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let file = File::options()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(&path)?;
    match file.try_lock() {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => {
            progress(EnsureStage::Waiting);
            file.lock()?;
        }
        Err(TryLockError::Error(error)) => return Err(error.into()),
    }
    Ok(ConversionLock(file))
}

/// Open the converted tables of `source`, converting only when needed.
///
/// The tables are reused when `conversion.json` records the source's current
/// fingerprint, the current schema version and a complete file set. Conversion
/// writes complete files atomically, so an interrupted run leaves the previous
/// tables untouched.
///
/// The staleness check, the conversion and the publish all run under an
/// exclusive advisory lock on the sibling file `<directory>.lock`, so
/// concurrent callers (threads or processes) on one directory are serialised.
/// A caller that has to wait reports [`EnsureStage::Waiting`] once, then
/// re-checks currency and reuses tables another caller just finished.
/// [`EnsureStage::Converting`] is reported just before a conversion starts.
/// An explicit `rebuild` always converts, even after waiting. If the lock file
/// cannot be created (for example a read-only location), current tables are
/// still reused without locking.
///
/// Returns the store and whether a conversion happened.
pub fn ensure_frames(
    source: &dyn Vfs,
    directory: &Path,
    rebuild: bool,
    progress: &mut dyn FnMut(EnsureStage),
) -> Result<(FrameStore, bool)> {
    let fingerprint = source.fingerprint()?;
    let _lock = match acquire_lock(directory, progress) {
        Ok(lock) => lock,
        // A read-only location can still serve tables that are already current.
        Err(_) if !rebuild && tables_current(directory, &fingerprint) => {
            return Ok((FrameStore::open(directory)?, false));
        }
        Err(error) => return Err(error),
    };
    if !rebuild && tables_current(directory, &fingerprint) {
        return Ok((FrameStore::open(directory)?, false));
    }
    progress(EnsureStage::Converting);
    convert_session(source, directory, &ConvertOptions::default())?;
    Ok((FrameStore::open(directory)?, true))
}
