//! Batch HE20 amplitude decoding and scaling, without unused phase calibration.
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};
use rayon::prelude::*;

fn bytes(values: &[f64]) -> &[u8] {
    // SAFETY: initialized contiguous f64s have no padding; view cannot outlive values.
    unsafe { std::slice::from_raw_parts(values.as_ptr().cast(), std::mem::size_of_val(values)) }
}

type Buffers<'py> = (
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
    Bound<'py, PyBytes>,
);

fn magnitude(real: f64, imag: f64) -> f64 {
    let larger = real.abs().max(imag.abs());
    let smaller = real.abs().min(imag.abs());
    let ratio = if larger == 0.0 { 0.0 } else { smaller / larger };
    ratio.mul_add(ratio, 1.0).sqrt() * larger
}

fn sample(data: &[u8], index: usize) -> f64 {
    i16::from_ne_bytes(data[index * 2..index * 2 + 2].try_into().unwrap()) as f64
}

fn magnitudes(i: &[u8], q: &[u8], out: &mut [f64]) {
    #[cfg(target_arch = "x86_64")]
    if std::is_x86_feature_detected!("avx2") && std::is_x86_feature_detected!("fma") {
        // SAFETY: both required features were checked and all buffers have
        // exactly two input bytes per output sample.
        unsafe { magnitudes_avx2(i, q, out) };
        return;
    }
    for (index, value) in out.iter_mut().enumerate() {
        *value = magnitude(sample(i, index), sample(q, index));
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2,fma")]
unsafe fn magnitudes_avx2(i: &[u8], q: &[u8], out: &mut [f64]) {
    use std::arch::x86_64::*;
    let count = out.len() / 4 * 4;
    // SAFETY: input reads are checked byte slices; stores write four f64s
    // only when offset + 4 <= out.len(). No alignment is assumed.
    unsafe {
        let sign = _mm256_set1_pd(-0.0);
        let one = _mm256_set1_pd(1.0);
        for offset in (0..count).step_by(4) {
            let real = _mm256_andnot_pd(
                sign,
                _mm256_set_pd(
                    sample(i, offset + 3),
                    sample(i, offset + 2),
                    sample(i, offset + 1),
                    sample(i, offset),
                ),
            );
            let imag = _mm256_andnot_pd(
                sign,
                _mm256_set_pd(
                    sample(q, offset + 3),
                    sample(q, offset + 2),
                    sample(q, offset + 1),
                    sample(q, offset),
                ),
            );
            let larger = _mm256_max_pd(real, imag);
            let smaller = _mm256_min_pd(real, imag);
            let zero = _mm256_cmp_pd::<_CMP_EQ_OQ>(larger, _mm256_setzero_pd());
            let denominator = _mm256_blendv_pd(larger, one, zero);
            let ratio = _mm256_div_pd(smaller, denominator);
            let result = _mm256_mul_pd(_mm256_sqrt_pd(_mm256_fmadd_pd(ratio, ratio, one)), larger);
            _mm256_storeu_pd(out.as_mut_ptr().add(offset), result);
        }
    }
    for (index, value) in out.iter_mut().enumerate().skip(count) {
        *value = magnitude(sample(i, index), sample(q, index));
    }
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
    let rows = first_word.len();
    if rows == 0
        || driver_valid.len() != rows
        || offsets.len() != rows + 1
        || offsets[0] != 0
        || i.len() != q.len()
        || i.len() % 2 != 0
        || offsets[rows] != i.len() / 2
        || offsets
            .windows(2)
            .any(|v| v[1] < v[0] || ![245, 256].contains(&(v[1] - v[0])))
    {
        return Err(PyValueError::new_err("Invalid HE20 I/Q lengths or offsets"));
    }
    let (masked, normalized, lower, upper) = py.detach(|| {
        let mut masked = vec![f64::NAN; rows * 245];
        masked
            .par_chunks_mut(245)
            .enumerate()
            .for_each(|(row, out)| {
                if !driver_valid[row] {
                    return;
                }
                let start = offsets[row];
                let count = offsets[row + 1] - start;
                let mut amplitudes = [0.0; 256];
                magnitudes(
                    &i[start * 2..(start + count) * 2],
                    &q[start * 2..(start + count) * 2],
                    &mut amplitudes[..count],
                );
                for (column, value) in out.iter_mut().enumerate() {
                    let physical = column as i32 - 122;
                    let slot = if count == 256 {
                        (physical + 128) as usize
                    } else if physical >= 0 {
                        physical as usize
                    } else {
                        (245 + physical) as usize
                    };
                    if physical.abs() <= 1 || (first_word[row] && slot < 2) {
                        continue;
                    }
                    let amplitude = amplitudes[slot];
                    if amplitude >= 4.0 {
                        *value = amplitude;
                    }
                }
            });
        let mut normalized = vec![f64::NAN; masked.len()];
        let mut lower = vec![f64::NAN; 245];
        let mut upper = vec![f64::NAN; 245];
        normalized
            .par_chunks_mut(rows)
            .zip(lower.par_iter_mut())
            .zip(upper.par_iter_mut())
            .enumerate()
            .for_each(|(col, ((out, low), high))| {
                let mut min = f64::INFINITY;
                let mut max = f64::NEG_INFINITY;
                for row in 0..rows {
                    let value = masked[row * 245 + col];
                    if value.is_finite() {
                        min = min.min(value);
                        max = max.max(value);
                    }
                }
                if !min.is_finite() {
                    return;
                }
                *low = min;
                *high = max;
                for row in 0..rows {
                    let value = masked[row * 245 + col];
                    if value.is_finite() {
                        out[row] = if max > min {
                            (2.0 * (value - min) / (max - min) - 1.0).clamp(-1.0, 1.0)
                        } else {
                            0.0
                        };
                    }
                }
            });
        (masked, normalized, lower, upper)
    });
    Ok((
        PyBytes::new(py, bytes(&masked)),
        PyBytes::new(py, bytes(&normalized)),
        PyBytes::new(py, bytes(&lower)),
        PyBytes::new(py, bytes(&upper)),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dispatched_magnitudes_match_scalar_for_signed_pairs_and_tails() {
        let values: Vec<i16> = (-128..128).collect();
        let i: Vec<u8> = values
            .iter()
            .flat_map(|v| std::iter::repeat_n(*v, 256).flat_map(i16::to_ne_bytes))
            .collect();
        let q: Vec<u8> = (0..256)
            .flat_map(|_| values.iter().copied().flat_map(i16::to_ne_bytes))
            .collect();
        let mut actual = vec![0.0; i.len() / 2];
        magnitudes(&i, &q, &mut actual);
        for (index, value) in actual.iter().enumerate() {
            assert_eq!(*value, magnitude(sample(&i, index), sample(&q, index)));
        }
        let extremes: Vec<u8> = [i16::MIN, i16::MAX, 0, 1, -1, 4, -4]
            .into_iter()
            .flat_map(i16::to_ne_bytes)
            .collect();
        for count in 1..=7 {
            let mut actual = vec![0.0; count];
            magnitudes(&extremes[..count * 2], &extremes[..count * 2], &mut actual);
            for (index, value) in actual.iter().enumerate() {
                assert_eq!(
                    *value,
                    magnitude(sample(&extremes, index), sample(&extremes, index))
                );
            }
        }
    }
}
