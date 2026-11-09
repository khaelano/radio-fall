//! Offline centered Hampel filtering with column-local storage and scratch space.
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};
use rayon::prelude::*;

fn median(values: &mut [f64]) -> f64 {
    let len = values.len();
    let mid = len / 2;
    let (left, upper, _) = values.select_nth_unstable_by(mid, f64::total_cmp);
    if mid * 2 == len {
        let lower = left.iter().copied().max_by(f64::total_cmp).unwrap();
        (lower + *upper) / 2.0
    } else {
        *upper
    }
}

fn deviations(values: &mut [f64], center: f64, simd: bool) {
    #[cfg(target_arch = "x86_64")]
    if simd && std::is_x86_feature_detected!("avx2") {
        // SAFETY: runtime dispatch checks the ISA; the kernel bounds all loads.
        unsafe { deviations_avx2(values, center) };
        return;
    }
    let _ = simd;
    for value in values {
        *value = (*value - center).abs();
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn deviations_avx2(values: &mut [f64], center: f64) {
    use std::arch::x86_64::*;
    let count = values.len() / 4 * 4;
    // SAFETY: every unaligned load/store has four initialized, writable f64s.
    unsafe {
        let middle = _mm256_set1_pd(center);
        let sign = _mm256_set1_pd(-0.0);
        for offset in (0..count).step_by(4) {
            let ptr = values.as_mut_ptr().add(offset);
            let delta = _mm256_sub_pd(_mm256_loadu_pd(ptr), middle);
            _mm256_storeu_pd(ptr, _mm256_andnot_pd(sign, delta));
        }
    }
    for value in &mut values[count..] {
        *value = (*value - center).abs();
    }
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
    let (output, replaced) = py.detach(|| {
        let half = window_seconds / 2.0;
        let bounds: Vec<_> = times
            .iter()
            .map(|t| {
                (
                    times.partition_point(|v| *v < t - half),
                    times.partition_point(|v| *v <= t + half),
                )
            })
            .collect();
        let mut output = input.clone();
        let mut replaced = vec![0u8; input.len()];
        if rows != 0 {
            let process = |column: usize, out: &mut [f64], mask: &mut [u8]| {
                let source = &input[column * rows..(column + 1) * rows];
                let mut scratch = Vec::new();
                for (row, &(start, stop)) in bounds.iter().enumerate() {
                    if !source[row].is_finite() || stop - start < min_periods {
                        continue;
                    }
                    scratch.clear();
                    scratch.extend(
                        source[start..stop]
                            .iter()
                            .copied()
                            .filter(|v| v.is_finite()),
                    );
                    if scratch.len() < min_periods {
                        continue;
                    }
                    let middle = median(&mut scratch);
                    deviations(&mut scratch, middle, simd);
                    let mad = median(&mut scratch);
                    if mad > 0.0 && (source[row] - middle).abs() > threshold * 1.4826 * mad {
                        out[row] = middle;
                        mask[row] = 1;
                    }
                }
            };
            if parallel {
                output
                    .par_chunks_mut(rows)
                    .zip(replaced.par_chunks_mut(rows))
                    .enumerate()
                    .for_each(|(col, (out, mask))| process(col, out, mask));
            } else {
                for (col, (out, mask)) in output
                    .chunks_mut(rows)
                    .zip(replaced.chunks_mut(rows))
                    .enumerate()
                {
                    process(col, out, mask);
                }
            }
        }
        (output, replaced)
    });
    // SAFETY: initialized f64 values have no padding; the read-only byte view
    // cannot outlive output and PyBytes::new copies it before returning.
    let bytes = unsafe {
        std::slice::from_raw_parts(
            output.as_ptr().cast(),
            std::mem::size_of_val(output.as_slice()),
        )
    };
    Ok((PyBytes::new(py, bytes), PyBytes::new(py, &replaced)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn simd_deviations_match_scalar_with_tails() {
        for n in 0..40 {
            let mut scalar: Vec<_> = (0..n).map(|i| i as f64 / 7.0 - 2.0).collect();
            let mut vector = scalar.clone();
            deviations(&mut scalar, 0.31, false);
            deviations(&mut vector, 0.31, true);
            assert_eq!(scalar, vector);
        }
    }
}
