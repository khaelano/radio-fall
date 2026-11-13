use pyo3::prelude::*;
use pyo3::types::PyBytes;
pub use radio_transport::framing::Decoder;
#[pyclass]
#[derive(Default)]
pub struct FrameDecoder {
    inner: Decoder,
}
#[pymethods]
impl FrameDecoder {
    #[new]
    fn new() -> Self {
        Self::default()
    }
    #[getter]
    fn malformed_frames(&self) -> u64 {
        self.inner.malformed
    }
    #[getter]
    fn oversized_frames(&self) -> u64 {
        self.inner.oversized
    }
    fn feed<'py>(&mut self, py: Python<'py>, data: &[u8]) -> Vec<(u8, Bound<'py, PyBytes>)> {
        let frames = py.detach(|| self.inner.feed(data));
        frames
            .into_iter()
            .map(|f| (f.kind, PyBytes::new(py, &f.data)))
            .collect()
    }
}
#[pyfunction]
pub fn encode_frame<'py>(
    py: Python<'py>,
    kind: u8,
    payload: &[u8],
) -> PyResult<Bound<'py, PyBytes>> {
    let encoded = py
        .detach(|| radio_transport::framing::encode(kind, payload))
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    Ok(PyBytes::new(py, &encoded))
}
