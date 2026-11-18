//! Python bindings for the session storage crate.
//!
//! The crate is the storage library: Python calls these functions and classes
//! directly. Reports and manifests come back as plain `dict`s and `list`s.
//! Tables come back as [`ArrowTable`], which implements the Arrow PyCapsule
//! interface, so `pyarrow.table(result)` (or Polars, DuckDB, ...) consumes it
//! without copying and without an Arrow-specific pyo3 feature. Every failure
//! raises `StorageError`.
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyCapsule, PyDict, PyList, PyString};
use radio_storage::arrow_array::ffi_stream::FFI_ArrowArrayStream;
use radio_storage::arrow_array::{RecordBatch, RecordBatchIterator};
use radio_storage::arrow_schema::SchemaRef;
use radio_storage::{
    ArchiveOptions, ConvertOptions, EnsureStage, FrameQuery, FrameScope, MigrateOptions,
    OpenedSession, Table, annotation_path, annotations_dir_for, archive_manifest,
    convert_session_locked, ensure_frames, extract_archive, extract_session_file, frame_counts,
    migrate_archive, open_session, open_source, read_session_file, resolve_source, session_files,
    verify_against_source, verify_archive, verify_dir, vfs, write_archive,
};
use serde_json::Value;
use std::path::{Path, PathBuf};

pyo3::create_exception!(
    _radio_native,
    StorageError,
    PyRuntimeError,
    "A session could not be read, resolved, converted or archived."
);

fn failure(error: radio_storage::Error) -> PyErr {
    StorageError::new_err(error.to_string())
}

/// Register the storage classes, functions and exception on the module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("StorageError", module.py().get_type::<StorageError>())?;
    module.add_class::<ArrowTable>()?;
    module.add_class::<FrameStore>()?;
    module.add_function(wrap_pyfunction!(storage_convert, module)?)?;
    module.add_function(wrap_pyfunction!(storage_verify, module)?)?;
    module.add_function(wrap_pyfunction!(storage_files, module)?)?;
    module.add_function(wrap_pyfunction!(storage_read, module)?)?;
    module.add_function(wrap_pyfunction!(storage_read_many, module)?)?;
    module.add_function(wrap_pyfunction!(storage_read_file, module)?)?;
    module.add_function(wrap_pyfunction!(storage_extract_member, module)?)?;
    module.add_function(wrap_pyfunction!(storage_source_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(storage_migrate, module)?)?;
    module.add_function(wrap_pyfunction!(storage_archive_session, module)?)?;
    module.add_function(wrap_pyfunction!(storage_extract_archive, module)?)?;
    module.add_function(wrap_pyfunction!(storage_verify_archive, module)?)?;
    module.add_function(wrap_pyfunction!(storage_archive_manifest, module)?)?;
    module.add_function(wrap_pyfunction!(storage_open_session, module)?)?;
    module.add_function(wrap_pyfunction!(storage_open_source, module)?)?;
    module.add_function(wrap_pyfunction!(storage_resolve_source, module)?)?;
    module.add_function(wrap_pyfunction!(storage_annotation_path, module)?)?;
    module.add_function(wrap_pyfunction!(storage_annotations_for, module)?)?;
    module.add_function(wrap_pyfunction!(storage_read_frames, module)?)?;
    module.add_function(wrap_pyfunction!(storage_frame_counts, module)?)?;
    Ok(())
}

/// Convert JSON into the equivalent Python `dict`, `list`, `str`, `int`,
/// `float`, `bool` and `None`.
fn to_py<'py>(py: Python<'py>, value: &Value) -> PyResult<Bound<'py, PyAny>> {
    Ok(match value {
        Value::Null => py.None().into_bound(py),
        Value::Bool(flag) => PyBool::new(py, *flag).to_owned().into_any(),
        Value::Number(number) => {
            if let Some(integer) = number.as_i64() {
                integer.into_pyobject(py)?.into_any()
            } else if let Some(unsigned) = number.as_u64() {
                unsigned.into_pyobject(py)?.into_any()
            } else {
                number
                    .as_f64()
                    .unwrap_or(f64::NAN)
                    .into_pyobject(py)?
                    .into_any()
            }
        }
        Value::String(text) => PyString::new(py, text).into_any(),
        Value::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(to_py(py, item)?)?;
            }
            list.into_any()
        }
        Value::Object(map) => {
            let dict = PyDict::new(py);
            for (key, item) in map {
                dict.set_item(key, to_py(py, item)?)?;
            }
            dict.into_any()
        }
    })
}

fn opened_json(opened: &OpenedSession) -> Value {
    let review = opened.review.as_ref().map(|opened| {
        serde_json::json!({
            "origin": opened.origin.as_str(),
            "path": opened.path.as_ref().map(|path| path.display().to_string()),
            "revision": opened.review.revision,
            "updated_at_utc": opened.review.updated_at_utc,
            "content_sha256": opened.review.content_sha256,
            "metadata": opened.review.metadata,
        })
    });
    let attempts: Vec<Value> = opened
        .attempts
        .iter()
        .map(|attempt| {
            serde_json::json!({
                "attempt_key": attempt.attempt_key,
                "trial_ordinal": attempt.trial_ordinal,
                "attempt": attempt.attempt,
                "activity_label": attempt.activity_label,
                "original_activity_label": attempt.original_activity_label,
                "status": attempt.status,
                "inclusion": attempt.inclusion,
                "quality": attempt.quality,
                "notes": attempt.notes,
                "review_revision": attempt.review_revision,
            })
        })
        .collect();
    serde_json::json!({
        "session_id": opened.session_id,
        "protocol_hash": opened.protocol_hash,
        "source": opened.source.display().to_string(),
        "archive_version": opened.archive_version,
        "source_fingerprint": opened.source_fingerprint,
        "review": review,
        "attempts": attempts,
    })
}

/// A table that exports itself through the Arrow PyCapsule interface.
///
/// Use `pyarrow.table(result)` to obtain a `pyarrow.Table`. It can be exported
/// any number of times.
#[pyclass(module = "fall_detection._radio_native", frozen)]
pub struct ArrowTable {
    schema: SchemaRef,
    batches: Vec<RecordBatch>,
}

impl ArrowTable {
    fn new(table: Table) -> Self {
        Self {
            schema: table.0,
            batches: table.1,
        }
    }
}

#[pymethods]
impl ArrowTable {
    /// Export an Arrow C stream capsule.
    #[pyo3(signature = (requested_schema=None))]
    fn __arrow_c_stream__<'py>(
        &self,
        py: Python<'py>,
        requested_schema: Option<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyCapsule>> {
        let _ = requested_schema; // the schema is exported as stored
        let reader = RecordBatchIterator::new(
            self.batches.clone().into_iter().map(Ok),
            self.schema.clone(),
        );
        let stream = FFI_ArrowArrayStream::new(Box::new(reader));
        PyCapsule::new_with_value_and_destructor(py, stream, c"arrow_array_stream", |stream, _| {
            drop(stream)
        })
    }

    /// Number of rows.
    #[getter]
    fn num_rows(&self) -> usize {
        self.batches.iter().map(RecordBatch::num_rows).sum()
    }

    fn __len__(&self) -> usize {
        self.num_rows()
    }
}

fn query(
    receiver_id: Option<String>,
    capture_start_ns: Option<i64>,
    capture_end_ns: Option<i64>,
    columns: Option<Vec<String>>,
) -> FrameQuery {
    FrameQuery {
        receiver_id,
        capture_start_ns,
        capture_end_ns,
        columns,
    }
}

/// One converted session: its manifest and the derived tables.
///
/// The directory holds `frames.parquet`, `attempts.parquet`, `phases.parquet`
/// and `conversion.json`; see `docs/storage-layout-spec.md`.
#[pyclass(module = "fall_detection._radio_native", frozen)]
pub struct FrameStore {
    inner: radio_storage::FrameStore,
}

#[pymethods]
impl FrameStore {
    /// Open a converted session directory.
    #[new]
    fn new(directory: PathBuf) -> PyResult<Self> {
        Self::open(directory)
    }

    /// Open a converted session directory.
    #[staticmethod]
    fn open(directory: PathBuf) -> PyResult<Self> {
        Ok(Self {
            inner: radio_storage::FrameStore::open(&directory).map_err(failure)?,
        })
    }

    /// Support pickling, so parallel analysis can pass stores to workers.
    fn __reduce__<'py>(&self, py: Python<'py>) -> PyResult<(Bound<'py, PyAny>, (String,))> {
        Ok((
            py.get_type::<Self>().into_any(),
            (self.inner.directory.display().to_string(),),
        ))
    }

    /// Open the tables of `source`, converting its journals only when needed.
    ///
    /// The tables are reused when `conversion.json` records the source's
    /// current fingerprint and the current schema version. The check and any
    /// conversion hold an exclusive lock on `<frames_dir>.lock`. `progress` is
    /// called once with a message if another conversion holds the lock, and
    /// again just before this call converts.
    #[staticmethod]
    #[pyo3(signature = (source, frames_dir, rebuild=false, progress=None))]
    fn ensure(
        py: Python<'_>,
        source: PathBuf,
        frames_dir: PathBuf,
        rebuild: bool,
        progress: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let converting = format!("Converting {} into typed frame tables", source.display());
        let waiting = format!("Waiting for another conversion of {}", frames_dir.display());
        let (inner, _) = py
            .detach(|| {
                let opened = vfs::open(&source)?;
                ensure_frames(opened.as_ref(), &frames_dir, rebuild, &mut |stage| {
                    if let Some(callback) = &progress {
                        let message = match stage {
                            EnsureStage::Waiting => &waiting,
                            EnsureStage::Converting => &converting,
                        };
                        Python::attach(|py| {
                            let _ = callback.call1(py, (message.as_str(),));
                        });
                    }
                })
            })
            .map_err(failure)?;
        Ok(Self { inner })
    }

    /// The converted directory.
    #[getter]
    fn directory(&self) -> String {
        self.inner.directory.display().to_string()
    }

    /// Identifier of the source session.
    #[getter]
    fn session_id(&self) -> String {
        self.inner.session_id().to_string()
    }

    /// Fingerprint of the raw source the tables were derived from.
    #[getter]
    fn source_fingerprint(&self) -> String {
        self.inner.source_fingerprint().to_string()
    }

    /// The contents of `conversion.json`.
    #[getter]
    fn manifest<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        to_py(py, &self.inner.manifest)
    }

    /// One row per recorded attempt.
    fn attempts(&self, py: Python<'_>) -> PyResult<ArrowTable> {
        py.detach(|| self.inner.attempts())
            .map(ArrowTable::new)
            .map_err(failure)
    }

    /// Phase intervals.
    fn phases(&self, py: Python<'_>) -> PyResult<ArrowTable> {
        py.detach(|| self.inner.phases())
            .map(ArrowTable::new)
            .map_err(failure)
    }

    /// Frames matching the filters, in journal order.
    ///
    /// Row groups ruled out by their statistics are skipped. Frames without a
    /// capture time never match a capture-time filter.
    #[pyo3(signature = (receiver_id=None, capture_start_ns=None, capture_end_ns=None, columns=None))]
    fn frames(
        &self,
        py: Python<'_>,
        receiver_id: Option<String>,
        capture_start_ns: Option<i64>,
        capture_end_ns: Option<i64>,
        columns: Option<Vec<String>>,
    ) -> PyResult<ArrowTable> {
        let query = query(receiver_id, capture_start_ns, capture_end_ns, columns);
        py.detach(|| self.inner.frames(&query))
            .map(ArrowTable::new)
            .map_err(failure)
    }

    /// Frames captured inside one attempt window, `start_ns <= t < end_ns`.
    ///
    /// `attempt_index` is a row of `attempts()`. An attempt without an end time
    /// extends to the end of the session.
    #[pyo3(signature = (attempt_index, receiver_id=None, columns=None))]
    fn attempt_frames(
        &self,
        py: Python<'_>,
        attempt_index: usize,
        receiver_id: Option<String>,
        columns: Option<Vec<String>>,
    ) -> PyResult<ArrowTable> {
        py.detach(|| {
            self.inner
                .attempt_frames(attempt_index, receiver_id, columns)
        })
        .map(ArrowTable::new)
        .map_err(failure)
    }
}

/// Convert a session directory or archive into frames, attempts and phases tables.
///
/// `scope` is `"attempts"` (frames inside attempt windows) or `"all"`. Returns
/// the conversion report, as stored in `conversion.json`.
#[pyfunction]
#[pyo3(signature = (source, out_dir, scope="attempts"))]
fn storage_convert<'py>(
    py: Python<'py>,
    source: PathBuf,
    out_dir: PathBuf,
    scope: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let scope = match scope {
        "attempts" => FrameScope::Attempts,
        "all" => FrameScope::All,
        other => {
            return Err(StorageError::new_err(format!(
                "scope must be 'attempts' or 'all', not {other:?}"
            )));
        }
    };
    let report = py
        .detach(|| {
            let source = vfs::open(&source)?;
            let options = ConvertOptions {
                scope,
                ..ConvertOptions::default()
            };
            // Same lock as FrameStore.ensure, so the two cannot interleave.
            Ok::<_, radio_storage::Error>(
                convert_session_locked(source.as_ref(), &out_dir, &options, &mut |_| {})?.to_json(),
            )
        })
        .map_err(failure)?;
    to_py(py, &report)
}

/// Verify a converted directory, optionally by re-converting `source`.
///
/// Returns `{"ok", "frames", "capture_backward_steps", "problems"}`.
#[pyfunction]
#[pyo3(signature = (out_dir, source=None))]
fn storage_verify<'py>(
    py: Python<'py>,
    out_dir: PathBuf,
    source: Option<PathBuf>,
) -> PyResult<Bound<'py, PyAny>> {
    let report = py
        .detach(|| {
            let report = match source {
                Some(source) => {
                    let source = vfs::open(&source)?;
                    verify_against_source(source.as_ref(), &out_dir, &ConvertOptions::default())?
                }
                None => verify_dir(&out_dir)?,
            };
            Ok::<_, radio_storage::Error>(serde_json::json!({
                "ok": report.ok(),
                "frames": report.frames,
                "capture_backward_steps": report.capture_backward_steps,
                "problems": report.problems,
            }))
        })
        .map_err(failure)?;
    to_py(py, &report)
}

/// Logical file paths of a session directory or archive, relative to its root.
#[pyfunction]
fn storage_files(py: Python<'_>, source: PathBuf) -> PyResult<Vec<String>> {
    py.detach(|| Ok::<_, radio_storage::Error>(session_files(vfs::open(&source)?.as_ref())))
        .map_err(failure)
}

/// Read one decoded file from a session directory or archive.
#[pyfunction]
fn storage_read<'py>(
    py: Python<'py>,
    source: PathBuf,
    member: String,
) -> PyResult<Bound<'py, PyBytes>> {
    let bytes = py
        .detach(|| read_session_file(vfs::open(&source)?.as_ref(), &member))
        .map_err(failure)?;
    Ok(PyBytes::new(py, &bytes))
}

/// Read several decoded files of a session with one open of the source.
///
/// Returns `{member: bytes}` for the members that exist; missing ones are left
/// out. Opening an archive lists its whole central directory, so reading many
/// small manifests in one call is much cheaper than one `storage_read` each.
#[pyfunction]
fn storage_read_many<'py>(
    py: Python<'py>,
    source: PathBuf,
    members: Vec<String>,
) -> PyResult<Bound<'py, PyDict>> {
    let found = py
        .detach(|| {
            let opened = vfs::open(&source)?;
            let mut found = Vec::new();
            for member in members {
                match read_session_file(opened.as_ref(), &member) {
                    Ok(bytes) => found.push((member, bytes)),
                    Err(_)
                        if !opened.exists(&member)
                            && !opened.exists(&format!("original/{member}")) => {}
                    Err(error) => return Err(error),
                }
            }
            Ok::<_, radio_storage::Error>(found)
        })
        .map_err(failure)?;
    let result = PyDict::new(py);
    for (member, bytes) in found {
        result.set_item(member, PyBytes::new(py, &bytes))?;
    }
    Ok(result)
}

/// Write one decoded file of a session directory or archive to `destination`.
///
/// Used to hand a single member, such as one attempt's video clip, to a reader
/// that needs a real file. The file appears only once complete. Returns its size.
#[pyfunction]
fn storage_extract_member(
    py: Python<'_>,
    source: PathBuf,
    member: String,
    destination: PathBuf,
) -> PyResult<u64> {
    py.detach(|| extract_session_file(vfs::open(&source)?.as_ref(), &member, &destination))
        .map_err(failure)
}

/// Read a recording file as logical bytes, independent of disk compression.
///
/// `path` may be the plain file or the logical name of a `<path>.zst` sibling;
/// concatenated Zstandard frames are decoded in order and a truncated final
/// frame raises `StorageError`.
#[pyfunction]
fn storage_read_file<'py>(py: Python<'py>, path: PathBuf) -> PyResult<Bound<'py, PyBytes>> {
    let bytes = py.detach(|| vfs::read_file(&path)).map_err(failure)?;
    Ok(PyBytes::new(py, &bytes))
}

/// Fingerprint of a session source, used to detect stale derived tables.
#[pyfunction]
fn storage_source_fingerprint(py: Python<'_>, source: PathBuf) -> PyResult<String> {
    py.detach(|| vfs::open(&source)?.fingerprint())
        .map_err(failure)
}

/// Write a version-3 archive from an older archive and prove the tables unchanged.
///
/// The per-receiver sidecars and `tables/` copies are dropped. Returns the
/// report with sizes and dropped member counts.
#[pyfunction]
#[pyo3(signature = (source, destination, zstd_level=9))]
fn storage_migrate<'py>(
    py: Python<'py>,
    source: PathBuf,
    destination: PathBuf,
    zstd_level: i32,
) -> PyResult<Bound<'py, PyAny>> {
    let report = py
        .detach(|| {
            migrate_archive(&source, &destination, &MigrateOptions { zstd_level })
                .map(|report| report.to_json())
        })
        .map_err(failure)?;
    to_py(py, &report)
}

/// Archive a session directory (or archive) as a version-3 archive.
///
/// Journals and receiver sidecars are stored as Zstandard frames and every
/// member is hashed in `manifest.json`. The destination is published only after
/// the tables converted from it equal those converted from the source; sessions
/// without journals skip that check. `drop_derived` leaves out the receiver
/// sidecars the journal determines; keep it off until the journal conversion of
/// that kind of session is validated.
#[pyfunction]
#[pyo3(signature = (source, destination, zstd_level=9, drop_derived=false))]
fn storage_archive_session<'py>(
    py: Python<'py>,
    source: PathBuf,
    destination: PathBuf,
    zstd_level: i32,
    drop_derived: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let report = py
        .detach(|| {
            write_archive(
                &source,
                &destination,
                &ArchiveOptions {
                    zstd_level,
                    drop_derived,
                },
            )
            .map(|report| report.to_json())
        })
        .map_err(failure)?;
    to_py(py, &report)
}

/// Verify a version-3 archive and write its members as a session directory.
///
/// Zstandard logs keep their `.zst` form. `destination` must not exist.
/// Returns the number of members written.
#[pyfunction]
fn storage_extract_archive(
    py: Python<'_>,
    archive: PathBuf,
    destination: PathBuf,
) -> PyResult<usize> {
    py.detach(|| extract_archive(&archive, &destination))
        .map_err(failure)
}

/// Check a version-3 archive against its manifest; returns the problems found.
#[pyfunction]
fn storage_verify_archive(py: Python<'_>, path: PathBuf) -> PyResult<Vec<String>> {
    py.detach(|| verify_archive(&path)).map_err(failure)
}

/// The version-3 manifest of an archive.
#[pyfunction]
fn storage_archive_manifest<'py>(py: Python<'py>, path: PathBuf) -> PyResult<Bound<'py, PyAny>> {
    let manifest = py.detach(|| archive_manifest(&path)).map_err(failure)?;
    to_py(py, &manifest)
}

/// Open the session `session_id` under the repository `root` with its review.
///
/// Returns `session_id`, `protocol_hash`, `source`, `archive_version`,
/// `source_fingerprint`, `review` (origin, path, revision, content hash,
/// metadata; `None` without one) and the effective `attempts`.
#[pyfunction]
fn storage_open_session<'py>(
    py: Python<'py>,
    root: PathBuf,
    session_id: String,
) -> PyResult<Bound<'py, PyAny>> {
    let opened = py
        .detach(|| open_session(&root, &session_id))
        .map_err(failure)?;
    to_py(py, &opened_json(&opened))
}

/// Open a session directory or archive, applying its review.
///
/// A review in `annotations_dir/<session id>/session_review.json` is preferred;
/// one inside the source is used only when that file does not exist. Without
/// `annotations_dir`, a source in `<root>/data/raw/sessions` uses
/// `<root>/data/annotations`.
#[pyfunction]
#[pyo3(signature = (source, annotations_dir=None))]
fn storage_open_source<'py>(
    py: Python<'py>,
    source: PathBuf,
    annotations_dir: Option<PathBuf>,
) -> PyResult<Bound<'py, PyAny>> {
    let opened = py
        .detach(|| {
            let annotations = annotations_dir.or_else(|| annotations_dir_for(&source));
            open_source(&source, annotations.as_deref())
        })
        .map_err(failure)?;
    to_py(py, &opened_json(&opened))
}

/// Locate and check the source of a session under the repository `root`.
///
/// Returns `(path, archive_version)`; the version is `None` for a directory.
#[pyfunction]
fn storage_resolve_source(
    py: Python<'_>,
    root: PathBuf,
    session_id: String,
) -> PyResult<(String, Option<u64>)> {
    let (path, version) = py
        .detach(|| resolve_source(&root, &session_id))
        .map_err(failure)?;
    Ok((path.display().to_string(), version))
}

/// Path of a session's review file under the repository `root`.
#[pyfunction]
fn storage_annotation_path(root: PathBuf, session_id: String) -> PyResult<String> {
    Ok(annotation_path(&root, &session_id)
        .map_err(failure)?
        .display()
        .to_string())
}

/// The annotations directory implied by a source in `data/raw/sessions`, else `None`.
#[pyfunction]
fn storage_annotations_for(source: PathBuf) -> Option<String> {
    annotations_dir_for(&source).map(|path| path.display().to_string())
}

/// Row count and row-group count of a frames table.
#[pyfunction]
fn storage_frame_counts(path: PathBuf) -> PyResult<(i64, usize)> {
    frame_counts(Path::new(&path)).map_err(failure)
}

/// Read frames from a `frames.parquet` file with optional filters.
#[pyfunction]
#[pyo3(signature = (path, receiver_id=None, capture_start_ns=None, capture_end_ns=None, columns=None))]
fn storage_read_frames(
    py: Python<'_>,
    path: PathBuf,
    receiver_id: Option<String>,
    capture_start_ns: Option<i64>,
    capture_end_ns: Option<i64>,
    columns: Option<Vec<String>>,
) -> PyResult<ArrowTable> {
    let query = query(receiver_id, capture_start_ns, capture_end_ns, columns);
    py.detach(|| radio_storage::read_frames_with_schema(&path, &query))
        .map(ArrowTable::new)
        .map_err(failure)
}
