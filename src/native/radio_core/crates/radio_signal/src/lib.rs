//! Exact signed-I/Q reductions, runtime AVX2 dispatch and phase detrending.
use std::f64::consts::{PI, TAU};

pub fn kernel() -> &'static str {
    #[cfg(target_arch = "x86_64")]
    if std::is_x86_feature_detected!("avx2") {
        return "avx2";
    }
    "scalar"
}

pub fn iq_scalar(raw: &[u8]) -> (Vec<f64>, i64, i64) {
    let mut amplitudes = Vec::with_capacity(raw.len() / 2);
    let (mut si, mut sq) = (0i64, 0i64);
    for p in raw.chunks_exact(2) {
        let q = p[0] as i8 as i32;
        let i = p[1] as i8 as i32;
        si += i as i64;
        sq += q as i64;
        amplitudes.push(((i * i + q * q) as f64).sqrt());
    }
    (amplitudes, si, sq)
}

pub fn iq(raw: &[u8]) -> (Vec<f64>, i64, i64) {
    #[cfg(target_arch = "x86_64")]
    if std::is_x86_feature_detected!("avx2") {
        // SAFETY: dispatch checks the ISA; the kernel uses unaligned loads only
        // for complete 16-byte chunks and scalar code for its bounded tail.
        return unsafe { iq_avx2(raw) };
    }
    iq_scalar(raw)
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn iq_avx2(raw: &[u8]) -> (Vec<f64>, i64, i64) {
    use std::arch::x86_64::*;
    let mut a = vec![0f64; raw.len() / 2];
    let (mut si, mut sq) = (0i64, 0i64);
    let count = raw.len() / 16 * 16;
    for offset in (0..count).step_by(16) {
        // SAFETY: offset+16 <= raw.len(); each output has eight f64 slots.
        unsafe {
            let bytes = _mm_loadu_si128(raw.as_ptr().add(offset).cast());
            let values = _mm256_cvtepi8_epi16(bytes);
            let energy = _mm256_madd_epi16(values, values);
            let lo = _mm256_sqrt_pd(_mm256_cvtepi32_pd(_mm256_castsi256_si128(energy)));
            let hi = _mm256_sqrt_pd(_mm256_cvtepi32_pd(_mm256_extracti128_si256::<1>(energy)));
            _mm256_storeu_pd(a.as_mut_ptr().add(offset / 2), lo);
            _mm256_storeu_pd(a.as_mut_ptr().add(offset / 2 + 4), hi);
            let iv = _mm256_madd_epi16(values, _mm256_set1_epi32(0x00010000));
            let qv = _mm256_madd_epi16(values, _mm256_set1_epi32(1));
            let (mut is, mut qs) = ([0i32; 8], [0i32; 8]);
            _mm256_storeu_si256(is.as_mut_ptr().cast(), iv);
            _mm256_storeu_si256(qs.as_mut_ptr().cast(), qv);
            si += is.iter().map(|v| *v as i64).sum::<i64>();
            sq += qs.iter().map(|v| *v as i64).sum::<i64>();
        }
    }
    for (j, p) in raw[count..].chunks_exact(2).enumerate() {
        let (q, i) = (p[0] as i8 as i32, p[1] as i8 as i32);
        si += i as i64;
        sq += q as i64;
        a[count / 2 + j] = ((i * i + q * q) as f64).sqrt();
    }
    (a, si, sq)
}

#[derive(Clone)]
pub struct Phase {
    pub indices: Vec<i32>,
    pub amplitudes: Vec<f64>,
    pub raw: Vec<f64>,
    pub calibrated: Vec<f64>,
}

/// One LTF layout: block name, serialized signed subcarrier indices, valid tones.
#[derive(Clone, Debug)]
pub struct Layout {
    pub name: &'static str,
    pub indices: Vec<i32>,
    pub valid: fn(i32) -> bool,
}

fn ht20_valid(index: i32) -> bool {
    index != 0 && (-28..=28).contains(&index)
}

fn he20_valid(index: i32) -> bool {
    index.abs() <= 122 && index.abs() > 1
}

fn ht20_indices() -> Vec<i32> {
    (0..32).chain(-32..0).collect()
}

/// Supported Espressif 20 MHz LTF layouts of one CSI payload, in serialized order.
///
/// HE SU (`sig_mode` 4) uses a complete 256-slot FFT or the older compact
/// 245-slot vector. Classic HT reports one or more 64-slot blocks. Unsupported
/// layouts return no blocks; raw CSI remains available to callers.
pub fn layouts(sig_mode: u32, bandwidth: u32, stbc: u32, pairs: usize) -> Vec<Layout> {
    if bandwidth != 0 {
        return Vec::new();
    }
    if sig_mode == 4 && stbc == 0 {
        if pairs == 256 {
            return vec![Layout {
                name: "HE-LTF",
                indices: (-128..128).collect(),
                valid: he20_valid,
            }];
        }
        if pairs == 245 {
            return vec![Layout {
                name: "HE-LTF",
                indices: (0..123).chain(-122..0).collect(),
                valid: he20_valid,
            }];
        }
    }
    if pairs % 64 != 0 {
        return Vec::new();
    }
    let blocks = pairs / 64;
    let names: &[&'static str] = match (sig_mode, stbc != 0, blocks) {
        (1, false, 1 | 2) => &["LLTF", "HT-LTF"][..blocks],
        (1, true, 3) => &["LLTF", "HT-LTF", "STBC-HT-LTF"],
        (mode, _, 1) if mode != 1 => &["LLTF"],
        _ => &[],
    };
    names
        .iter()
        .map(|name| Layout {
            name,
            indices: ht20_indices(),
            valid: ht20_valid,
        })
        .collect()
}

/// Wrapped phase of usable tones; NaN for invalid, weak, non-finite or null tones.
pub fn usable_phases(
    re: &[f64],
    im: &[f64],
    amplitudes: &[f64],
    indices: &[i32],
    valid: &dyn Fn(i32) -> bool,
    invalid: &[bool],
    floor: f64,
) -> Vec<f64> {
    (0..indices.len())
        .map(|j| {
            let usable = !invalid.get(j).copied().unwrap_or(false)
                && re[j].is_finite()
                && im[j].is_finite()
                && amplitudes[j] > 0.
                && amplitudes[j] >= floor
                && valid(indices[j]);
            if usable { im[j].atan2(re[j]) } else { f64::NAN }
        })
        .collect()
}

/// Remove each packet's phase offset and frequency slope.
///
/// Usable (non-NaN) phases are unwrapped in ascending subcarrier order, then an
/// amplitude-weighted line is fitted and removed. Fewer than three usable tones
/// yield all-NaN output, as do unusable tones.
pub fn calibrate(phases: &[f64], amplitudes: &[f64], indices: &[i32]) -> Vec<f64> {
    let mut valid: Vec<usize> = (0..phases.len()).filter(|&j| !phases[j].is_nan()).collect();
    valid.sort_unstable_by_key(|j| indices[*j]);
    let mut calibrated = vec![f64::NAN; phases.len()];
    if valid.len() < 3 {
        return calibrated;
    }
    let mut unwrapped = Vec::with_capacity(valid.len());
    let (mut previous, mut correction) = (phases[valid[0]], 0.);
    for &j in &valid {
        let current = phases[j];
        let d = current - previous;
        let mut wrapped = (d + PI).rem_euclid(TAU) - PI;
        if wrapped == -PI && d > 0. {
            wrapped = PI;
        }
        if d.abs() >= PI {
            correction += wrapped - d;
        }
        unwrapped.push(current + correction);
        previous = current;
    }
    // Centered weighted two-parameter least squares, avoiding an allocation
    // and SVD per record. No fast-math or floating-point reassociation.
    let weight: f64 = valid.iter().map(|j| amplitudes[*j]).sum();
    let mx = valid
        .iter()
        .map(|j| amplitudes[*j] * indices[*j] as f64)
        .sum::<f64>()
        / weight;
    let my = valid
        .iter()
        .zip(&unwrapped)
        .map(|(j, y)| amplitudes[*j] * y)
        .sum::<f64>()
        / weight;
    let xx = valid
        .iter()
        .map(|j| amplitudes[*j] * (indices[*j] as f64 - mx).powi(2))
        .sum::<f64>();
    let xy = valid
        .iter()
        .zip(&unwrapped)
        .map(|(j, y)| amplitudes[*j] * (indices[*j] as f64 - mx) * (y - my))
        .sum::<f64>();
    let slope = xy / xx;
    for (&j, y) in valid.iter().zip(unwrapped) {
        calibrated[j] = (y - (slope * (indices[j] as f64 - mx) + my) + PI).rem_euclid(TAU) - PI;
    }
    calibrated
}

/// Amplitudes, usable wrapped phase and calibrated phase of one LTF block.
pub fn block(
    re: &[f64],
    im: &[f64],
    indices: &[i32],
    valid: &dyn Fn(i32) -> bool,
    invalid: &[bool],
    floor: f64,
) -> Phase {
    let amplitudes: Vec<f64> = re
        .iter()
        .zip(im)
        .map(|(r, i)| {
            let value = r.hypot(*i);
            if value.is_finite() { value } else { f64::NAN }
        })
        .collect();
    let raw = usable_phases(re, im, &amplitudes, indices, valid, invalid, floor);
    let calibrated = calibrate(&raw, &amplitudes, indices);
    Phase {
        indices: indices.to_vec(),
        amplitudes,
        raw,
        calibrated,
    }
}

/// HE20 phase of a live record from interleaved signed `(Q, I)` bytes.
///
/// Uses the record's exact integer amplitudes, so live preparation is
/// independent of floating-point `hypot` rounding.
pub fn phase(
    raw: &[u8],
    format: u8,
    bandwidth: u8,
    stbc: u8,
    invalid: bool,
    amplitudes: Vec<f64>,
) -> Option<Phase> {
    let n = raw.len() / 2;
    if format != 4 || bandwidth != 0 || stbc != 0 || (n != 245 && n != 256) {
        return None;
    }
    let layout = layouts(4, 0, 0, n).pop()?;
    let re: Vec<f64> = raw.chunks_exact(2).map(|p| p[1] as i8 as f64).collect();
    let im: Vec<f64> = raw.chunks_exact(2).map(|p| p[0] as i8 as f64).collect();
    let mask: Vec<bool> = (0..n).map(|j| invalid && j < 2).collect();
    let phases = usable_phases(
        &re,
        &im,
        &amplitudes,
        &layout.indices,
        &layout.valid,
        &mask,
        4.,
    );
    let calibrated = calibrate(&phases, &amplitudes, &layout.indices);
    Some(Phase {
        indices: layout.indices,
        amplitudes,
        raw: phases,
        calibrated,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_signed_iq_pairs_match_scalar() {
        for n in [2, 14, 16, 18, 32, 490, 512, 612] {
            let data: Vec<u8> = (0..n).map(|i| ((i * 137 + 91) % 256) as u8).collect();
            assert_eq!(iq(&data), iq_scalar(&data));
        }
        for q in 0..=255u8 {
            for i in 0..=255u8 {
                let data = [q, i].repeat(8);
                assert_eq!(iq(&data), iq_scalar(&data));
            }
        }
    }

    #[test]
    #[ignore = "timing observation; run in release with --ignored --nocapture"]
    fn benchmark_iq_kernel() {
        use std::{hint::black_box, time::Instant};
        let raw: Vec<u8> = (0..490).map(|i| (i * 137 + 91) as u8).collect();
        for round in 0..7 {
            for vector in [round % 2 == 0, round % 2 != 0] {
                let start = Instant::now();
                for _ in 0..100_000 {
                    black_box(if vector {
                        iq(black_box(&raw))
                    } else {
                        iq_scalar(black_box(&raw))
                    });
                }
                println!(
                    "round={round} mode={} kernel={} ns_per_record={}",
                    if vector { "dispatch" } else { "scalar" },
                    kernel(),
                    start.elapsed().as_nanos() / 100_000
                );
            }
        }
    }

    #[test]
    fn layouts_follow_espressif_serialization() {
        assert_eq!(layouts(4, 0, 0, 256)[0].indices.first(), Some(&-128));
        assert_eq!(layouts(4, 0, 0, 245)[0].indices[123], -122);
        let ht: Vec<_> = layouts(1, 0, 0, 128).iter().map(|l| l.name).collect();
        assert_eq!(ht, ["LLTF", "HT-LTF"]);
        assert_eq!(layouts(1, 0, 1, 192).len(), 3);
        assert_eq!(layouts(0, 0, 0, 64)[0].name, "LLTF");
        assert!(layouts(1, 1, 0, 128).is_empty());
        assert!(layouts(1, 0, 0, 100).is_empty());
        assert!(layouts(0, 0, 0, 128).is_empty());
    }

    #[test]
    fn calibration_removes_offset_and_slope_and_needs_three_tones() {
        let indices: Vec<i32> = (-5..=5).collect();
        let phases: Vec<f64> = indices.iter().map(|&k| 0.3 + 0.2 * k as f64).collect();
        let amplitudes = vec![10.0; indices.len()];
        let calibrated = calibrate(&phases, &amplitudes, &indices);
        assert!(calibrated.iter().all(|v| v.abs() < 1e-12));
        let mut sparse = vec![f64::NAN; indices.len()];
        sparse[0] = 0.1;
        sparse[1] = 0.2;
        assert!(
            calibrate(&sparse, &amplitudes, &indices)
                .iter()
                .all(|v| v.is_nan())
        );
    }
}
