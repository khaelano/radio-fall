//! Python bindings for the offline HE20 amplitude and Hampel kernels in `radio_signal`.
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
