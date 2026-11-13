//! Thin configuration/result interface; native code owns packets and model tensors.
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::*,
    types::PyBytes,
};
use radio_detection::backend::{Backend, BackendConfig};
use std::sync::Mutex;

/// `(metadata_json, raw_float32, model_input_float32)` for one display window.
type PreviewTuple<'py> = (String, Bound<'py, PyBytes>, Bound<'py, PyBytes>);

/// View float32 values as their little-endian bytes without copying.
#[cfg(target_endian = "little")]
fn f32_bytes(values: &[f32]) -> &[u8] {
    // SAFETY: f32 has no padding or invalid bit patterns as bytes, u8 has
    // alignment 1, and the length covers exactly the same memory.
    unsafe {
        std::slice::from_raw_parts(values.as_ptr().cast::<u8>(), std::mem::size_of_val(values))
    }
}

#[pyclass]
pub struct NativeDetector {
    backend: Mutex<Backend>,
}
#[pymethods]
impl NativeDetector {
    #[new]
    fn new(config_json: &str) -> PyResult<Self> {
        let config: BackendConfig =
            serde_json::from_str(config_json).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let backend = Backend::new(config).map_err(PyValueError::new_err)?;
        Ok(Self {
            backend: Mutex::new(backend),
        })
    }
    fn start(&self, py: Python<'_>) -> PyResult<()> {
        py.detach(|| {
            self.backend
                .lock()
                .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?
                .start()
                .map_err(PyRuntimeError::new_err)
        })
    }
    #[pyo3(signature=(max_results=64))]
    fn poll(&self, max_results: usize) -> PyResult<String> {
        if !(1..=64).contains(&max_results) {
            return Err(PyValueError::new_err("max_results must be 1..64"));
        }
        let backend = self
            .backend
            .lock()
            .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?;
        serde_json::to_string(&backend.poll(max_results))
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    /// Latest display window for one model, newer than `after_end_ns`.
    ///
    /// Returns `(metadata_json, raw, model_input)` with little-endian float32
    /// buffers shaped `[frames, 980]` and `[frames, 1964]`, or `None`.
    #[pyo3(signature=(model_id, after_end_ns=0))]
    fn preview<'py>(
        &self,
        py: Python<'py>,
        model_id: &str,
        after_end_ns: u64,
    ) -> PyResult<Option<PreviewTuple<'py>>> {
        let preview = self
            .backend
            .lock()
            .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?
            .preview(model_id, after_end_ns);
        let Some(preview) = preview else {
            return Ok(None);
        };
        let metadata = serde_json::json!({
            "model_id": preview.model_id, "generation": preview.generation,
            "start_ns": preview.start_ns, "end_ns": preview.end_ns,
            "frames": preview.frames, "coverage": preview.coverage,
        });
        Ok(Some((
            metadata.to_string(),
            PyBytes::new(py, f32_bytes(&preview.raw)),
            PyBytes::new(py, f32_bytes(&preview.input)),
        )))
    }
    /// Raw CSI rows received after `after_seq`, for the scrolling display.
    ///
    /// Returns `(metadata_json, magnitudes)`. Metadata lists `seq`, and per row
    /// `generation`, `round` and `receiver`; magnitudes are little-endian
    /// float32 `[rows, 245]` with NaN for masked tones.
    #[pyo3(signature=(after_seq=0, limit=4096))]
    fn stream<'py>(
        &self,
        py: Python<'py>,
        after_seq: u64,
        limit: usize,
    ) -> PyResult<(String, Bound<'py, PyBytes>)> {
        let rows = self
            .backend
            .lock()
            .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?
            .stream(after_seq, limit.min(16384));
        let metadata = serde_json::json!({
            "seq": rows.last().map_or(after_seq, |row| row.seq),
            "generation": rows.iter().map(|row| row.generation).collect::<Vec<_>>(),
            "round": rows.iter().map(|row| row.round).collect::<Vec<_>>(),
            "receiver": rows.iter().map(|row| row.receiver).collect::<Vec<_>>(),
        });
        let magnitudes: Vec<f32> = rows.iter().flat_map(|row| row.magnitude).collect();
        Ok((
            metadata.to_string(),
            PyBytes::new(py, f32_bytes(&magnitudes)),
        ))
    }
    fn health(&self) -> PyResult<String> {
        let backend = self
            .backend
            .lock()
            .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?;
        serde_json::to_string(&backend.health()).map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
    fn stop(&self, py: Python<'_>) -> PyResult<()> {
        py.detach(|| {
            self.backend
                .lock()
                .map_err(|_| PyRuntimeError::new_err("detector lock poisoned"))?
                .stop();
            Ok(())
        })
    }
}
