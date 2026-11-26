//! Python bindings for the offline HE20 amplitude and Hampel kernels and the
//! principal-component spectrum front end in `radio_signal`.
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};

type Buffers<'py> = (
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
);

fn bytes(values: &[f64]) -> &[u8] {
    // SAFETY: initialized contiguous f64s have no padding; view cannot outlive values.
    unsafe { std::slice::from_raw_parts(values.as_ptr().cast(), std::mem::size_of_val(values)) }
}

fn doubles(data: &[u8]) -> Vec<f64> {
    data.chunks_exact(8)
        .map(|chunk| f64::from_ne_bytes(chunk.try_into().unwrap()))
        .collect()
}

/// Inputs and outputs are native-endian float64 matrices in column-major order.
/// Immutable bytes own the input while the GIL is released (no NumPy alias race).
#[pyfunction]
#[pyo3(signature = (amplitude, times, columns, window_seconds=0.1, min_periods=5, threshold=5.0, parallel=true, simd=true))]
#[allow(clippy::too_many_arguments)]
pub fn hampel_filter<'py>(
    py: Python<'py>,
    amplitude: &[u8],
    times: &[u8],
    columns: usize,
    window_seconds: f64,
    min_periods: usize,
    threshold: f64,
    parallel: bool,
    simd: bool,
) -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
    let rows = times.len() / 8;
    if times.len() % 8 != 0
        || rows.checked_mul(columns).and_then(|n| n.checked_mul(8)) != Some(amplitude.len())
        || !window_seconds.is_finite()
        || window_seconds <= 0.0
        || min_periods == 0
        || !threshold.is_finite()
        || threshold < 0.0
    {
        return Err(PyValueError::new_err("Invalid Hampel shape or parameters"));
    }
    let times = doubles(times);
    if times.iter().any(|v| !v.is_finite()) || times.windows(2).any(|v| v[1] < v[0]) {
        return Err(PyValueError::new_err(
            "Capture times must be finite and sorted",
        ));
    }
    let input = doubles(amplitude);
    if input.iter().any(|v| v.is_infinite()) {
        return Err(PyValueError::new_err(
            "Amplitude must contain finite values or NaN",
        ));
    }
    let (output, replaced) = py
        .detach(|| {
            radio_signal::hampel::filter_native(
                &input,
                &times,
                columns,
                window_seconds,
                min_periods,
                threshold,
                parallel,
                simd,
            )
        })
        .map_err(PyValueError::new_err)?;
    Ok((
        PyBytes::new(py, bytes(&output)),
        PyBytes::new(py, &replaced),
    ))
}

/// Decode masked physical HE20 magnitudes without fitting normalization.
#[pyfunction]
pub fn prepare_magnitude<'py>(
    py: Python<'py>,
    i: &[u8],
    q: &[u8],
    offsets: Vec<usize>,
    first_word: Vec<bool>,
    driver_valid: Vec<bool>,
) -> PyResult<Bound<'py, PyBytes>> {
    let masked = py
        .detach(|| {
            radio_signal::amplitude::decode_magnitudes(i, q, &offsets, &first_word, &driver_valid)
        })
        .map_err(PyValueError::new_err)?;
    Ok(PyBytes::new(py, bytes(&masked)))
}

/// Per-row flags: pair count is inferred from offsets; flags encode first-word
/// invalidity and driver validity. Python validates HE20 format before entry.
#[pyfunction]
pub fn prepare_amplitude<'py>(
    py: Python<'py>,
    i: &[u8],
    q: &[u8],
    offsets: Vec<usize>,
    first_word: Vec<bool>,
    driver_valid: Vec<bool>,
) -> PyResult<Buffers<'py>> {
    let (masked, normalized, lower, upper) = py
        .detach(|| {
            radio_signal::amplitude::prepare_amplitude(i, q, &offsets, &first_word, &driver_valid)
        })
        .map_err(PyValueError::new_err)?;
    Ok((
        PyBytes::new(py, bytes(&masked)),
        PyBytes::new(py, bytes(&normalized)),
        PyBytes::new(py, bytes(&lower)),
        PyBytes::new(py, bytes(&upper)),
    ))
}

fn floats(data: &[u8]) -> std::borrow::Cow<'_, [f32]> {
    // SAFETY: every bit pattern is a valid f32; misaligned input is copied.
    let (head, body, tail) = unsafe { data.align_to::<f32>() };
    if head.is_empty() && tail.is_empty() {
        std::borrow::Cow::Borrowed(body)
    } else {
        std::borrow::Cow::Owned(
            data.chunks_exact(4)
                .map(|chunk| f32::from_ne_bytes(chunk.try_into().unwrap()))
                .collect(),
        )
    }
}

fn float_bytes(values: &[f32]) -> &[u8] {
    // SAFETY: initialized contiguous f32s have no padding; view cannot outlive values.
    unsafe { std::slice::from_raw_parts(values.as_ptr().cast(), std::mem::size_of_val(values)) }
}

/// Principal-component spectrum front end of the `pcspec` models, with the
/// state that lets consecutive windows reuse their covariance sums.
///
/// Windows are native-endian float32 `[frames, 1964]` (normalized signals,
/// validity, presence); features are float32 `[stft_frames, 65]`.
#[pyclass(module = "fall_detection._radio_native")]
pub struct PcSpectrumFrontEnd {
    inner: std::sync::Mutex<radio_signal::pc_spectrum::PcSpectrum>,
}

#[pymethods]
impl PcSpectrumFrontEnd {
    #[new]
    #[pyo3(signature = (frames=480, simd=true, threads=1))]
    fn new(frames: usize, simd: bool, threads: usize) -> PyResult<Self> {
        let inner = radio_signal::pc_spectrum::PcSpectrum::new(frames, simd, threads)
            .map_err(PyValueError::new_err)?;
        Ok(Self {
            inner: std::sync::Mutex::new(inner),
        })
    }

    /// Samples per window.
    #[getter]
    fn frames(&self) -> usize {
        self.inner.lock().unwrap().frames()
    }

    /// Floats per output (`stft_frames * 65`).
    #[getter]
    fn outputs(&self) -> usize {
        self.inner.lock().unwrap().outputs()
    }

    /// Whether the AVX2 kernels are in use.
    #[getter]
    fn simd(&self) -> bool {
        self.inner.lock().unwrap().simd()
    }

    /// Forget the previous window.
    fn reset(&self) {
        self.inner.lock().unwrap().reset();
    }

    /// Features of one window. `shift` claims the window starts that many
    /// samples after the previous one; the overlap is verified before it is
    /// used. Returns the features, each receiver's update (`full`, `sliding` or
    /// `skipped`) and the kernel time in nanoseconds.
    #[pyo3(signature = (window, shift=None))]
    fn features<'py>(
        &self,
        py: Python<'py>,
        window: &[u8],
        shift: Option<usize>,
    ) -> PyResult<(Bound<'py, PyBytes>, Vec<&'static str>, u64)> {
        let (out, updates, nanoseconds) = py
            .detach(|| {
                let window = floats(window);
                if window.iter().any(|v| !v.is_finite()) {
                    return Err("PC spectrum window must be finite".to_string());
                }
                let mut front = self.inner.lock().unwrap();
                let mut out = vec![0.0f32; front.outputs()];
                let started = std::time::Instant::now();
                let updates = front.features(&window, shift, &mut out)?;
                Ok((out, updates, started.elapsed().as_nanos() as u64))
            })
            .map_err(PyValueError::new_err)?;
        let names = updates
            .iter()
            .map(|update| match update {
                radio_signal::pc_spectrum::Update::Full => "full",
                radio_signal::pc_spectrum::Update::Sliding => "sliding",
                radio_signal::pc_spectrum::Update::Skipped => "skipped",
            })
            .collect();
        Ok((PyBytes::new(py, float_bytes(&out)), names, nanoseconds))
    }
}
