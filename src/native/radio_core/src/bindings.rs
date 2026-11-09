use crate::wire::{Batch, Record};
use num_complex::Complex64;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyTuple};
use std::sync::Arc;

type PhaseBytes<'py> = (
    Vec<i32>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
);

fn doubles(v: &[f64]) -> &[u8] {
    // SAFETY: f64 slices are contiguous initialized values with no padding.
    // The byte view is read-only, uses native endianness, and cannot outlive v.
    unsafe { std::slice::from_raw_parts(v.as_ptr().cast(), std::mem::size_of_val(v)) }
}

#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct NativeRecord {
    pub core: Arc<Record>,
}
#[pymethods]
impl NativeRecord {
    #[getter]
    fn sequence(&self) -> u32 {
        self.core.sequence
    }
    #[getter]
    fn transport_sequence(&self) -> u32 {
        self.core.transport_sequence
    }
    #[getter]
    fn timestamp_us(&self) -> u32 {
        self.core.timestamp
    }
    #[getter]
    fn mac(&self) -> &str {
        &self.core.transmitter
    }
    #[getter]
    fn receiver_mac(&self) -> &str {
        &self.core.receiver
    }
    #[getter]
    fn profile_fingerprint(&self) -> &str {
        &self.core.fingerprint
    }
    #[getter]
    fn raw_line(&self) -> &str {
        ""
    }
    #[getter]
    fn mean_i(&self) -> f64 {
        self.core.mean_i
    }
    #[getter]
    fn mean_q(&self) -> f64 {
        self.core.mean_q
    }
    #[getter]
    fn csi_length(&self) -> usize {
        self.core.raw.len()
    }
    #[getter]
    fn sample_count(&self) -> usize {
        self.core.raw.len() / 2
    }
    #[getter]
    fn first_word_invalid(&self) -> bool {
        self.core.flags & 1 != 0
    }
    #[getter]
    fn tx_timestamp_us(&self) -> Option<u64> {
        (self.core.flags & 2 != 0).then_some(self.core.tx_timestamp)
    }
    #[getter]
    fn rx_callback_timestamp_us(&self) -> Option<u64> {
        (self.core.flags & 2 != 0).then_some(self.core.callback)
    }
    #[getter]
    fn rssi(&self) -> i8 {
        self.core.rssi
    }
    #[getter]
    fn noise_floor(&self) -> i8 {
        self.core.noise
    }
    #[getter]
    fn sig_len(&self) -> u16 {
        self.core.sig_len
    }
    #[getter]
    fn csv_line(&self) -> &str {
        self.core.csv.get().unwrap()
    }
    #[getter]
    fn wire<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.core.wire)
    }
    #[getter]
    fn raw_csi<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.core
                .raw
                .chunks_exact(2)
                .map(|p| Complex64::new(p[1] as i8 as f64, p[0] as i8 as f64)),
        )
    }
    #[getter]
    fn csi<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(
            py,
            self.core.raw.chunks_exact(2).enumerate().map(|(i, p)| {
                if self.core.flags & 1 != 0 && i < 2 {
                    Complex64::new(f64::NAN, f64::NAN)
                } else {
                    Complex64::new(p[1] as i8 as f64, p[0] as i8 as f64)
                }
            }),
        )
    }
    fn phase_bytes<'py>(&self, py: Python<'py>) -> Option<PhaseBytes<'py>> {
        self.core.phase.as_ref().map(|p| {
            (
                p.indices.clone(),
                PyBytes::new(py, doubles(&p.amplitudes)),
                PyBytes::new(py, doubles(&p.raw)),
                PyBytes::new(py, doubles(&p.calibrated)),
            )
        })
    }
    fn views_bytes<'py>(
        &self,
        py: Python<'py>,
    ) -> (
        Bound<'py, PyBytes>,
        Bound<'py, PyBytes>,
        Bound<'py, PyBytes>,
        Bound<'py, PyBytes>,
    ) {
        let mut i = Vec::new();
        let mut q = Vec::new();
        let mut a = Vec::new();
        let mut phase = Vec::new();
        for (n, p) in self.core.raw.chunks_exact(2).enumerate() {
            let (iv, qv) = if self.core.flags & 1 != 0 && n < 2 {
                (f64::NAN, f64::NAN)
            } else {
                (p[1] as i8 as f64, p[0] as i8 as f64)
            };
            i.push(iv);
            q.push(qv);
            a.push(iv.hypot(qv));
            phase.push(qv.atan2(iv));
        }
        (
            PyBytes::new(py, doubles(&i)),
            PyBytes::new(py, doubles(&q)),
            PyBytes::new(py, doubles(&a)),
            PyBytes::new(py, doubles(&phase)),
        )
    }
    #[getter]
    fn rate(&self) -> u8 {
        self.core.fields[0]
    }
    #[getter]
    fn sig_mode(&self) -> u8 {
        self.core.fields[1]
    }
    #[getter]
    fn mcs(&self) -> u8 {
        self.core.fields[2]
    }
    #[getter]
    fn bandwidth(&self) -> u8 {
        self.core.fields[3]
    }
    #[getter]
    fn smoothing(&self) -> u8 {
        self.core.fields[4]
    }
    #[getter]
    fn not_sounding(&self) -> u8 {
        self.core.fields[5]
    }
    #[getter]
    fn aggregation(&self) -> u8 {
        self.core.fields[6]
    }
    #[getter]
    fn stbc(&self) -> u8 {
        self.core.fields[7]
    }
    #[getter]
    fn fec_coding(&self) -> u8 {
        self.core.fields[8]
    }
    #[getter]
    fn sgi(&self) -> u8 {
        self.core.fields[9]
    }
    #[getter]
    fn ampdu_count(&self) -> u8 {
        self.core.fields[10]
    }
    #[getter]
    fn channel(&self) -> u8 {
        self.core.fields[11]
    }
    #[getter]
    fn secondary_channel(&self) -> u8 {
        self.core.fields[12]
    }
    #[getter]
    fn antenna(&self) -> u8 {
        self.core.fields[13]
    }
    #[getter]
    fn rx_state(&self) -> u8 {
        self.core.fields[14]
    }
}
#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct NativeBatch {
    pub core: Arc<Batch>,
}
#[pymethods]
impl NativeBatch {
    #[getter]
    fn run_id(&self) -> u64 {
        self.core.run
    }
    #[getter]
    fn transmitter_boot_id(&self) -> u32 {
        self.core.tx_boot
    }
    #[getter]
    fn receiver_boot_id(&self) -> u32 {
        self.core.rx_boot
    }
    #[getter]
    fn batch_id(&self) -> u32 {
        self.core.id
    }
    #[getter]
    fn receiver_mac(&self) -> &str {
        &self.core.mac
    }
    #[getter]
    fn records(&self) -> Vec<NativeRecord> {
        self.core
            .records
            .iter()
            .map(|r| NativeRecord { core: r.clone() })
            .collect()
    }
    #[getter]
    fn receiver_stats(&self) -> Vec<u32> {
        self.core.stats.to_vec()
    }
    #[getter]
    fn payload<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.core.payload)
    }
}
#[pyfunction]
pub fn decode_envelope(py: Python<'_>, data: &[u8]) -> PyResult<NativeBatch> {
    py.detach(|| Batch::decode(data))
        .map(|core| NativeBatch { core })
        .map_err(pyo3::exceptions::PyValueError::new_err)
}
#[pyfunction]
pub fn simd_kernel() -> &'static str {
    crate::numeric::kernel()
}
