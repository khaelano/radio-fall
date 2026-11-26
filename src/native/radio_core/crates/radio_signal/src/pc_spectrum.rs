//! Principal-component spectrum front end of the `pcspec` models.
//!
//! Input: one window `[frames, 1964]` as assembled for the sequence models
//! (normalized signals, validity flags, receiver presence; 4 receivers x 245
//! tones). For each receiver, the 238 interior tones (indices 2-120 and
//! 124-242) of samples with at least 90 % of them valid are centred over the
//! window; the five leading eigenvectors of their covariance give the axes; the
//! projections pass through a masked STFT (inner 64 samples of a 66-point Hann
//! window, hop 8, weighted mean and slope removed, power over the summed squared
//! weights), summed over the five components, as log power in bins 1-32. Frames
//! with at least 60 % usable samples count; mean and maximum over counting
//! receivers plus their share give `[stft_frames, 65]`. This is
//! `PCSpectrum.frame_features` in evaluation mode
//! (`artifacts/notebooks/diagnostics/20261126-pc-spectrum/pcspec_holdouts.py`).
//!
//! Exact path, kept fast: the per-receiver sums behind the covariance are float64
//! and, when consecutive windows overlap bit for bit, updated with only the
//! samples that enter and leave (otherwise, and every 1024 updates, recomputed);
//! the five eigenvectors come from a tridiagonal subset solver
//! ([`crate::symmetric_eigen`]); hot loops use AVX2 and FMA when available;
//! receivers without a counting frame are skipped; receivers can run on
//! separate threads.

use crate::symmetric_eigen::{self, Workspace};

pub const RECEIVERS: usize = 4;
pub const TONES: usize = 245;
pub const SIGNALS: usize = RECEIVERS * TONES;
/// Width of one assembled input row.
pub const FEATURES: usize = 2 * SIGNALS + RECEIVERS;
/// Interior tones per receiver.
pub const INTERIOR: usize = 238;
pub const COMPONENTS: usize = 5;
pub const WINDOW: usize = 64;
pub const HOP: usize = 8;
pub const BINS: usize = 32;
/// Features per STFT frame: mean and maximum log power per bin, receiver share.
pub const OUTPUTS: usize = 2 * BINS + 1;
const STRIDE: usize = 240;
const RUNS: [(usize, usize); 2] = [(2, 121), (124, 243)];
const MINIMUM_TONES: f32 = 0.9;
const MINIMUM_VALID: f32 = 0.6;
const LOG_FLOOR: f32 = 1e-6;
const RECOMPUTE_AFTER: u32 = 1024;
const CHUNK: usize = 64;

/// How a receiver's covariance was obtained for the latest window.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Update {
    /// Recomputed from every usable sample of the window.
    Full,
    /// Updated with the samples entering and leaving since the previous window.
    Sliding,
    /// No frame of this receiver counts; nothing was computed.
    Skipped,
}

/// STFT frames of a window of `frames` samples.
pub fn stft_frames(frames: usize) -> usize {
    (frames - WINDOW) / HOP + 1
}

struct Tables {
    taper: [f32; WINDOW],
    position: [f32; WINDOW],
    cos: Vec<f32>,
    sin: Vec<f32>,
}

impl Tables {
    fn new() -> Self {
        let mut taper = [0.0f32; WINDOW];
        let mut position = [0.0f32; WINDOW];
        for i in 0..WINDOW {
            // torch.hann_window(66, periodic=False)[1:-1]
            let phase = std::f64::consts::TAU * (i + 1) as f64 / (WINDOW + 1) as f64;
            taper[i] = (0.5 - 0.5 * phase.cos()) as f32;
            position[i] = i as f32 - (WINDOW as f32 - 1.0) / 2.0;
        }
        let mut cos = vec![0.0f32; WINDOW * BINS];
        let mut sin = vec![0.0f32; WINDOW * BINS];
        for t in 0..WINDOW {
            for b in 0..BINS {
                let angle = std::f64::consts::TAU * ((b + 1) * t) as f64 / WINDOW as f64;
                cos[t * BINS + b] = angle.cos() as f32;
                sin[t * BINS + b] = angle.sin() as f32;
            }
        }
        Self {
            taper,
            position,
            cos,
            sin,
        }
    }
}

struct Receiver {
    rows: Vec<f32>,
    usable: Vec<bool>,
    previous_rows: Vec<f32>,
    previous_usable: Vec<bool>,
    count: f64,
    sum: Vec<f64>,
    products: Vec<f64>,
    current: bool,
    updates: u32,
    eigen: Workspace,
    axes: Vec<f32>,
    mean: Vec<f32>,
    scores: Vec<f32>,
    logp: Vec<f32>,
    ok: Vec<bool>,
    plain: Vec<f64>,
    signed: Vec<f64>,
}

impl Receiver {
    fn new(frames: usize) -> Self {
        let stft = stft_frames(frames);
        Self {
            rows: vec![0.0; frames * STRIDE],
            usable: vec![false; frames],
            previous_rows: vec![0.0; frames * STRIDE],
            previous_usable: vec![false; frames],
            count: 0.0,
            sum: vec![0.0; STRIDE],
            products: vec![0.0; STRIDE * STRIDE],
            current: false,
            updates: 0,
            eigen: Workspace::new(INTERIOR, STRIDE),
            axes: vec![0.0; COMPONENTS * STRIDE],
            mean: vec![0.0; STRIDE],
            scores: vec![0.0; COMPONENTS * frames],
            logp: vec![0.0; stft * BINS],
            ok: vec![false; stft],
            plain: vec![0.0; CHUNK * STRIDE],
            signed: vec![0.0; CHUNK * STRIDE],
        }
    }

    /// Gather this receiver's interior tones and usable flags from the window.
    ///
    /// With `shift`, also checks while each row is hot that the window's first
    /// `frames - shift` rows equal the previous window's last ones bit for bit;
    /// returns whether they all do.
    fn gather(
        &mut self,
        window: &[f32],
        receiver: usize,
        frames: usize,
        shift: Option<usize>,
    ) -> bool {
        std::mem::swap(&mut self.rows, &mut self.previous_rows);
        std::mem::swap(&mut self.usable, &mut self.previous_usable);
        let values_at = receiver * TONES;
        let valid_at = SIGNALS + receiver * TONES;
        let shift = shift.filter(|&s| self.current && s > 0 && s < frames);
        let mut overlaps = shift.is_some();
        for t in 0..frames {
            let row = &window[t * FEATURES..(t + 1) * FEATURES];
            let target = &mut self.rows[t * STRIDE..t * STRIDE + INTERIOR];
            // Eight partial counts so the flag sum vectorizes; the flags are 0 or
            // 1, so the total is exact in any order.
            let mut lanes = [0.0f32; 8];
            let mut tail = 0.0f32;
            let mut offset = 0;
            for (low, high) in RUNS {
                let values = &row[values_at + low..values_at + high];
                let valid = &row[valid_at + low..valid_at + high];
                for ((out, &value), &flag) in target[offset..offset + high - low]
                    .iter_mut()
                    .zip(values)
                    .zip(valid)
                {
                    *out = value * flag;
                }
                let chunks = valid.chunks_exact(8);
                tail += chunks.remainder().iter().sum::<f32>();
                for chunk in chunks {
                    for (lane, &flag) in lanes.iter_mut().zip(chunk) {
                        *lane += flag;
                    }
                }
                offset += high - low;
            }
            let valid_count = lanes.iter().sum::<f32>() + tail;
            self.usable[t] = valid_count / INTERIOR as f32 >= MINIMUM_TONES;
            if overlaps && let Some(s) = shift.filter(|&s| t + s < frames) {
                let previous = &self.previous_rows[(t + s) * STRIDE..(t + s) * STRIDE + INTERIOR];
                overlaps = self.usable[t] == self.previous_usable[t + s]
                    && target
                        .iter()
                        .zip(previous)
                        .all(|(a, b)| a.to_bits() == b.to_bits());
            }
        }
        overlaps
    }

    /// Mark the STFT frames with at least 60 % usable samples; whether any counts.
    fn frame_flags(&mut self) -> bool {
        let mut any = false;
        for (f, ok) in self.ok.iter_mut().enumerate() {
            let present = self.usable[f * HOP..f * HOP + WINDOW]
                .iter()
                .filter(|&&u| u)
                .count();
            *ok = present as f32 / WINDOW as f32 >= MINIMUM_VALID;
            any |= *ok;
        }
        any
    }

    /// Add (`sign` 1) or remove (-1) the usable samples among `rows` of `source`.
    fn accumulate(&mut self, previous: bool, rows: std::ops::Range<usize>, sign: f64, simd: bool) {
        let mut pending = 0;
        for t in rows {
            let (usable, row) = if previous {
                (
                    self.previous_usable[t],
                    &self.previous_rows[t * STRIDE..(t + 1) * STRIDE],
                )
            } else {
                (self.usable[t], &self.rows[t * STRIDE..(t + 1) * STRIDE])
            };
            if !usable {
                continue;
            }
            let plain = &mut self.plain[pending * STRIDE..(pending + 1) * STRIDE];
            let signed = &mut self.signed[pending * STRIDE..(pending + 1) * STRIDE];
            for ((p, s), &value) in plain.iter_mut().zip(signed.iter_mut()).zip(row) {
                *p = f64::from(value);
                *s = sign * f64::from(value);
            }
            for (total, &value) in self.sum.iter_mut().zip(signed.iter()) {
                *total += value;
            }
            self.count += sign;
            pending += 1;
            if pending == CHUNK {
                syrk_lower(&mut self.products, &self.signed, &self.plain, pending, simd);
                pending = 0;
            }
        }
        if pending > 0 {
            syrk_lower(&mut self.products, &self.signed, &self.plain, pending, simd);
        }
    }

    fn process(
        &mut self,
        window: &[f32],
        receiver: usize,
        frames: usize,
        shift: Option<usize>,
        tables: &Tables,
        simd: bool,
    ) -> Update {
        let overlaps = self.gather(window, receiver, frames, shift);
        if !self.frame_flags() {
            self.current = false;
            return Update::Skipped;
        }
        let sliding = overlaps && self.updates < RECOMPUTE_AFTER;
        let update = if sliding {
            let s = shift.unwrap();
            self.accumulate(true, 0..s, -1.0, simd);
            self.accumulate(false, frames - s..frames, 1.0, simd);
            self.updates += 1;
            Update::Sliding
        } else {
            self.products.fill(0.0);
            self.sum.fill(0.0);
            self.count = 0.0;
            self.accumulate(false, 0..frames, 1.0, simd);
            self.updates = 0;
            Update::Full
        };
        self.current = true;
        self.axes_from_sums(simd);
        self.project(frames, simd);
        self.spectrum(frames, tables, simd);
        update
    }

    /// Five leading eigenvectors of the window covariance.
    fn axes_from_sums(&mut self, simd: bool) {
        self.covariance();
        symmetric_eigen::leading(&mut self.eigen, COMPONENTS, &mut self.axes, simd);
    }

    /// Mean and lower-triangle covariance `S2 / n - m m^T` of the usable samples.
    fn covariance(&mut self) {
        let inverse = 1.0 / self.count.max(1.0);
        let mut scaled = [0.0f64; STRIDE];
        for ((mean, target), &total) in self.mean.iter_mut().zip(&mut scaled).zip(&self.sum) {
            *target = total * inverse;
            *mean = *target as f32;
        }
        let matrix = &mut self.eigen.matrix;
        for i in 0..INTERIOR {
            let si = scaled[i];
            let products = &self.products[i * STRIDE..i * STRIDE + i + 1];
            let target = &mut matrix[i * STRIDE..i * STRIDE + i + 1];
            for ((out, &product), &sj) in target.iter_mut().zip(products).zip(&scaled) {
                *out = (product * inverse - si * sj) as f32;
            }
        }
    }

    /// Scores `[component][time]`: centred samples on the axes, zero if unusable.
    fn project(&mut self, frames: usize, simd: bool) {
        for t in 0..frames {
            let mut out = [0.0f32; COMPONENTS];
            if self.usable[t] {
                out = project_row(
                    &self.rows[t * STRIDE..(t + 1) * STRIDE],
                    &self.mean,
                    &self.axes,
                    simd,
                );
            }
            for (k, value) in out.into_iter().enumerate() {
                self.scores[k * frames + t] = value;
            }
        }
    }

    fn spectrum(&mut self, frames: usize, tables: &Tables, simd: bool) {
        let mut weight = [0.0f32; WINDOW];
        let mut offset = [0.0f32; WINDOW];
        let mut tapered = [0.0f32; WINDOW];
        for f in 0..self.ok.len() {
            if !self.ok[f] {
                continue;
            }
            let start = f * HOP;
            let (mut total, mut moment, mut squares) = (0.0f64, 0.0f64, 0.0f64);
            let usable = &self.usable[start..start + WINDOW];
            for (((target, &used), &taper), &position) in weight
                .iter_mut()
                .zip(usable)
                .zip(&tables.taper)
                .zip(&tables.position)
            {
                *target = if used { taper } else { 0.0 };
                total += f64::from(*target);
                moment += f64::from(*target * position);
                squares += f64::from(*target * *target);
            }
            let total = total.max(1e-6);
            let centre = moment / total;
            let mut spread = 0.0f64;
            for i in 0..WINDOW {
                offset[i] = (f64::from(tables.position[i]) - centre) as f32;
                spread += f64::from(weight[i] * offset[i] * offset[i]);
            }
            let spread = spread.max(1e-6);
            let mut power = [0.0f32; BINS];
            let mut moment_weight = [0.0f32; WINDOW];
            for i in 0..WINDOW {
                moment_weight[i] = weight[i] * offset[i];
            }
            let frame = Frame {
                weight: &weight,
                offset: &offset,
                moment_weight: &moment_weight,
                total: total as f32,
                spread: spread as f32,
            };
            for k in 0..COMPONENTS {
                let series: &[f32; WINDOW] = self.scores
                    [k * frames + start..k * frames + start + WINDOW]
                    .try_into()
                    .unwrap();
                detrend_power(series, &frame, &mut tapered, tables, &mut power, simd);
            }
            let norm = squares.max(1e-6) as f32;
            for (target, value) in self.logp[f * BINS..(f + 1) * BINS].iter_mut().zip(power) {
                *target = (value / norm + LOG_FLOOR).ln();
            }
        }
    }
}

/// Front end with per-receiver state for consecutive windows.
pub struct PcSpectrum {
    frames: usize,
    simd: bool,
    pool: Option<rayon::ThreadPool>,
    receivers: Vec<Receiver>,
    tables: Tables,
}

impl PcSpectrum {
    /// Front end for windows of `frames` samples; `simd` allows AVX2 and FMA
    /// kernels when the processor has them; `threads` (1-4) splits receivers.
    pub fn new(frames: usize, simd: bool, threads: usize) -> Result<Self, String> {
        if frames < WINDOW || !(1..=RECEIVERS).contains(&threads) {
            return Err("PC spectrum needs at least 64 frames and 1-4 threads".into());
        }
        // A persistent pool: spawning threads for every window would cost more
        // than the work they share.
        let pool = (threads > 1)
            .then(|| rayon::ThreadPoolBuilder::new().num_threads(threads).build())
            .transpose()
            .map_err(|error| error.to_string())?;
        Ok(Self {
            frames,
            simd: simd && symmetric_eigen::simd_available(),
            pool,
            receivers: (0..RECEIVERS).map(|_| Receiver::new(frames)).collect(),
            tables: Tables::new(),
        })
    }

    /// Samples per window.
    pub fn frames(&self) -> usize {
        self.frames
    }

    /// Floats in one output, `stft_frames(frames) * OUTPUTS`.
    pub fn outputs(&self) -> usize {
        stft_frames(self.frames) * OUTPUTS
    }

    /// Whether the AVX2 kernels are in use.
    pub fn simd(&self) -> bool {
        self.simd
    }

    /// Forget the previous window, so the next one is computed in full.
    pub fn reset(&mut self) {
        for receiver in &mut self.receivers {
            receiver.current = false;
        }
    }

    /// Features of `window` (`frames * 1964` finite floats) into `out`.
    ///
    /// `shift` claims that the window starts that many samples after the
    /// previous one; the overlap is verified bit for bit before the covariance
    /// sums are updated instead of recomputed, so the result never depends on
    /// the claim. Returns how each receiver's covariance was obtained.
    pub fn features(
        &mut self,
        window: &[f32],
        shift: Option<usize>,
        out: &mut [f32],
    ) -> Result<[Update; RECEIVERS], String> {
        let frames = self.frames;
        if window.len() != frames * FEATURES || out.len() != self.outputs() {
            return Err("PC spectrum window or output has the wrong size".into());
        }
        let (tables, simd) = (&self.tables, self.simd);
        let mut updates = [Update::Skipped; RECEIVERS];
        let work = |(r, receiver): (usize, &mut Receiver)| {
            receiver.process(window, r, frames, shift, tables, simd)
        };
        match &self.pool {
            None => {
                for (r, receiver) in self.receivers.iter_mut().enumerate() {
                    updates[r] = work((r, receiver));
                }
            }
            Some(pool) => {
                use rayon::prelude::*;
                let receivers = &mut self.receivers;
                let done: Vec<Update> =
                    pool.install(|| receivers.par_iter_mut().enumerate().map(work).collect());
                updates.copy_from_slice(&done);
            }
        }
        for f in 0..stft_frames(frames) {
            let row = &mut out[f * OUTPUTS..(f + 1) * OUTPUTS];
            let mut count = 0usize;
            let mut mean = [0.0f32; BINS];
            let mut peak = [-1e4f32; BINS];
            for receiver in &self.receivers {
                if !receiver.current || !receiver.ok[f] {
                    continue;
                }
                count += 1;
                for (b, &value) in receiver.logp[f * BINS..(f + 1) * BINS].iter().enumerate() {
                    mean[b] += value;
                    peak[b] = peak[b].max(value);
                }
            }
            let divisor = count.max(1) as f32;
            for b in 0..BINS {
                row[b] = mean[b] / divisor;
                row[BINS + b] = if count > 0 { peak[b] } else { 0.0 };
            }
            row[2 * BINS] = count as f32 / RECEIVERS as f32;
        }
        Ok(updates)
    }
}

/// Features of one window without state, for tests and offline use.
pub fn features_once(window: &[f32], frames: usize, simd: bool) -> Result<Vec<f32>, String> {
    let mut front = PcSpectrum::new(frames, simd, 1)?;
    let mut out = vec![0.0; front.outputs()];
    front.features(window, None, &mut out)?;
    Ok(out)
}

/// `products[i][j] += sum_r signed[r][i] * plain[r][j]` for `j <= i` (tiles may
/// also touch entries just above the diagonal, which are never read).
fn syrk_lower(products: &mut [f64], signed: &[f64], plain: &[f64], rows: usize, simd: bool) {
    assert!(products.len() >= STRIDE * STRIDE && signed.len() >= rows * STRIDE);
    assert!(plain.len() >= rows * STRIDE);
    #[cfg(target_arch = "x86_64")]
    if simd {
        // SAFETY: AVX2 and FMA were detected; the sizes were checked above.
        unsafe { avx::syrk_lower(products.as_mut_ptr(), signed.as_ptr(), plain.as_ptr(), rows) };
        return;
    }
    let _ = simd;
    for i in 0..STRIDE {
        for r in 0..rows {
            let y = signed[r * STRIDE + i];
            if y == 0.0 {
                continue;
            }
            let x = &plain[r * STRIDE..r * STRIDE + i + 1];
            for (target, &value) in products[i * STRIDE..i * STRIDE + i + 1].iter_mut().zip(x) {
                *target += y * value;
            }
        }
    }
}

fn project_row(row: &[f32], mean: &[f32], axes: &[f32], simd: bool) -> [f32; COMPONENTS] {
    assert!(row.len() >= STRIDE && mean.len() >= STRIDE && axes.len() >= COMPONENTS * STRIDE);
    #[cfg(target_arch = "x86_64")]
    if simd {
        // SAFETY: AVX2 and FMA were detected; the sizes were checked above.
        return unsafe { avx::project_row(row.as_ptr(), mean.as_ptr(), axes.as_ptr()) };
    }
    let _ = simd;
    let mut out = [0.0f32; COMPONENTS];
    for j in 0..STRIDE {
        let centred = row[j] - mean[j];
        for (k, value) in out.iter_mut().enumerate() {
            *value += centred * axes[k * STRIDE + j];
        }
    }
    out
}

/// Per-frame weights of the masked STFT, shared by the five components.
struct Frame<'a> {
    weight: &'a [f32; WINDOW],
    offset: &'a [f32; WINDOW],
    moment_weight: &'a [f32; WINDOW],
    total: f32,
    spread: f32,
}

/// Remove the weighted mean and slope of `series`, taper it, and add its
/// power in bins 1-32 to `power`.
fn detrend_power(
    series: &[f32; WINDOW],
    frame: &Frame,
    tapered: &mut [f32; WINDOW],
    tables: &Tables,
    power: &mut [f32; BINS],
    simd: bool,
) {
    #[cfg(target_arch = "x86_64")]
    if simd {
        // SAFETY: AVX2 and FMA were detected; every array holds WINDOW floats.
        unsafe { avx::detrend(series, frame, tapered) };
        dft_power(tapered, tables, power, simd);
        return;
    }
    let (mut level, mut trend) = (0.0f32, 0.0f32);
    for ((&x, &w), &m) in series.iter().zip(frame.weight).zip(frame.moment_weight) {
        level += w * x;
        trend += m * x;
    }
    let (mean, slope) = (level / frame.total, trend / frame.spread);
    for (((target, &x), &o), &w) in tapered
        .iter_mut()
        .zip(series)
        .zip(frame.offset)
        .zip(frame.weight)
    {
        *target = (x - mean - slope * o) * w;
    }
    dft_power(tapered, tables, power, simd);
}

fn dft_power(tapered: &[f32; WINDOW], tables: &Tables, power: &mut [f32; BINS], simd: bool) {
    #[cfg(target_arch = "x86_64")]
    if simd {
        // SAFETY: AVX2 and FMA were detected; the tables hold 64 x 32 floats.
        unsafe { avx::dft_power(tapered, tables.cos.as_ptr(), tables.sin.as_ptr(), power) };
        return;
    }
    let _ = simd;
    let mut real = [0.0f32; BINS];
    let mut imaginary = [0.0f32; BINS];
    for (t, &x) in tapered.iter().enumerate() {
        for b in 0..BINS {
            real[b] += x * tables.cos[t * BINS + b];
            imaginary[b] += x * tables.sin[t * BINS + b];
        }
    }
    for b in 0..BINS {
        power[b] += real[b] * real[b] + imaginary[b] * imaginary[b];
    }
}

#[cfg(target_arch = "x86_64")]
mod avx {
    use super::{BINS, COMPONENTS, Frame, STRIDE, WINDOW};
    use crate::symmetric_eigen::avx::sum;
    use std::arch::x86_64::*;

    #[target_feature(enable = "avx2,fma")]
    pub(super) unsafe fn syrk_lower(
        products: *mut f64,
        signed: *const f64,
        plain: *const f64,
        rows: usize,
    ) {
        // SAFETY: products holds STRIDE x STRIDE doubles, signed and plain rows x
        // STRIDE; tiles stay inside because STRIDE is a multiple of 8.
        unsafe {
            for i0 in (0..STRIDE).step_by(4) {
                let mut j0 = 0;
                while j0 <= i0 + 3 {
                    let (mut a0, mut a1, mut b0, mut b1) = (
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                    );
                    let (mut c0, mut c1, mut d0, mut d1) = (
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                        _mm256_setzero_pd(),
                    );
                    for r in 0..rows {
                        let x = plain.add(r * STRIDE + j0);
                        let (x0, x1) = (_mm256_loadu_pd(x), _mm256_loadu_pd(x.add(4)));
                        let y = signed.add(r * STRIDE + i0);
                        let ya = _mm256_broadcast_sd(&*y);
                        a0 = _mm256_fmadd_pd(ya, x0, a0);
                        a1 = _mm256_fmadd_pd(ya, x1, a1);
                        let yb = _mm256_broadcast_sd(&*y.add(1));
                        b0 = _mm256_fmadd_pd(yb, x0, b0);
                        b1 = _mm256_fmadd_pd(yb, x1, b1);
                        let yc = _mm256_broadcast_sd(&*y.add(2));
                        c0 = _mm256_fmadd_pd(yc, x0, c0);
                        c1 = _mm256_fmadd_pd(yc, x1, c1);
                        let yd = _mm256_broadcast_sd(&*y.add(3));
                        d0 = _mm256_fmadd_pd(yd, x0, d0);
                        d1 = _mm256_fmadd_pd(yd, x1, d1);
                    }
                    for (row, (low, high)) in [(a0, a1), (b0, b1), (c0, c1), (d0, d1)]
                        .into_iter()
                        .enumerate()
                    {
                        let target = products.add((i0 + row) * STRIDE + j0);
                        _mm256_storeu_pd(target, _mm256_add_pd(_mm256_loadu_pd(target), low));
                        _mm256_storeu_pd(
                            target.add(4),
                            _mm256_add_pd(_mm256_loadu_pd(target.add(4)), high),
                        );
                    }
                    j0 += 8;
                }
            }
        }
    }

    #[target_feature(enable = "avx2,fma")]
    pub(super) unsafe fn project_row(
        row: *const f32,
        mean: *const f32,
        axes: *const f32,
    ) -> [f32; COMPONENTS] {
        // SAFETY: row and mean hold STRIDE floats, axes COMPONENTS x STRIDE.
        unsafe {
            let mut acc = [_mm256_setzero_ps(); COMPONENTS];
            for j in (0..STRIDE).step_by(8) {
                let centred =
                    _mm256_sub_ps(_mm256_loadu_ps(row.add(j)), _mm256_loadu_ps(mean.add(j)));
                for (k, value) in acc.iter_mut().enumerate() {
                    *value =
                        _mm256_fmadd_ps(centred, _mm256_loadu_ps(axes.add(k * STRIDE + j)), *value);
                }
            }
            let mut out = [0.0f32; COMPONENTS];
            for (target, value) in out.iter_mut().zip(acc) {
                *target = sum(value);
            }
            out
        }
    }

    /// Weighted mean and slope of `series` removed, then the taper applied.
    #[target_feature(enable = "avx2,fma")]
    pub(super) unsafe fn detrend(
        series: &[f32; WINDOW],
        frame: &Frame,
        tapered: &mut [f32; WINDOW],
    ) {
        // SAFETY: every array holds WINDOW (64) floats, read in chunks of 8.
        unsafe {
            let (mut level, mut trend) = (_mm256_setzero_ps(), _mm256_setzero_ps());
            for j in (0..WINDOW).step_by(8) {
                let x = _mm256_loadu_ps(series.as_ptr().add(j));
                level = _mm256_fmadd_ps(_mm256_loadu_ps(frame.weight.as_ptr().add(j)), x, level);
                trend = _mm256_fmadd_ps(
                    _mm256_loadu_ps(frame.moment_weight.as_ptr().add(j)),
                    x,
                    trend,
                );
            }
            let mean = _mm256_set1_ps(sum(level) / frame.total);
            let slope = _mm256_set1_ps(sum(trend) / frame.spread);
            for j in (0..WINDOW).step_by(8) {
                let x = _mm256_sub_ps(_mm256_loadu_ps(series.as_ptr().add(j)), mean);
                let x = _mm256_fnmadd_ps(slope, _mm256_loadu_ps(frame.offset.as_ptr().add(j)), x);
                let x = _mm256_mul_ps(x, _mm256_loadu_ps(frame.weight.as_ptr().add(j)));
                _mm256_storeu_ps(tapered.as_mut_ptr().add(j), x);
            }
        }
    }

    #[target_feature(enable = "avx2,fma")]
    pub(super) unsafe fn dft_power(
        tapered: &[f32; WINDOW],
        cos: *const f32,
        sin: *const f32,
        power: &mut [f32; BINS],
    ) {
        // SAFETY: cos and sin hold WINDOW x BINS floats; BINS is 32.
        unsafe {
            let mut re = [_mm256_setzero_ps(); 4];
            let mut im = [_mm256_setzero_ps(); 4];
            for (t, &x) in tapered.iter().enumerate() {
                let value = _mm256_set1_ps(x);
                for q in 0..4 {
                    re[q] =
                        _mm256_fmadd_ps(value, _mm256_loadu_ps(cos.add(t * BINS + 8 * q)), re[q]);
                    im[q] =
                        _mm256_fmadd_ps(value, _mm256_loadu_ps(sin.add(t * BINS + 8 * q)), im[q]);
                }
            }
            for q in 0..4 {
                let target = power.as_mut_ptr().add(8 * q);
                let squared = _mm256_fmadd_ps(re[q], re[q], _mm256_mul_ps(im[q], im[q]));
                _mm256_storeu_ps(target, _mm256_add_ps(_mm256_loadu_ps(target), squared));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const FRAMES: usize = 480;

    /// A stream of assembled rows: low-rank motion plus noise per receiver, the
    /// receivers' staggered 12-in-68 gaps, a few invalid tones, receiver 4 absent
    /// when `absent` is set.
    fn stream(length: usize, seed: u64, absent: bool) -> Vec<f32> {
        let mut state = seed;
        let mut random = move || {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1442695040888963407);
            ((state >> 40) as f32 / (1u64 << 24) as f32) - 0.5
        };
        let mut out = vec![0.0f32; length * FEATURES];
        for t in 0..length {
            let row = &mut out[t * FEATURES..(t + 1) * FEATURES];
            for r in 0..RECEIVERS {
                let present = !(absent && r == 3) && (t + 17 * r) % 68 >= 12;
                row[2 * SIGNALS + r] = f32::from(present);
                if !present {
                    continue;
                }
                let phase = t as f32 / 120.0;
                let motion = [
                    (std::f32::consts::TAU * 3.0 * phase).sin(),
                    (std::f32::consts::TAU * 11.0 * phase + r as f32).sin(),
                    (std::f32::consts::TAU * 37.0 * phase).cos(),
                ];
                for tone in 0..TONES {
                    let valid = (tone * 31 + t * 7) % 101 != 0;
                    if !valid {
                        continue;
                    }
                    let shape = tone as f32 / TONES as f32;
                    row[r * TONES + tone] = 2.0 * motion[0] * shape
                        + motion[1] * (1.0 - shape)
                        + 0.5 * motion[2] * (shape * 6.0).sin()
                        + 0.3 * random();
                    row[SIGNALS + r * TONES + tone] = 1.0;
                }
            }
        }
        out
    }

    fn max_difference(a: &[f32], b: &[f32]) -> f32 {
        a.iter()
            .zip(b)
            .map(|(x, y)| (x - y).abs())
            .fold(0.0, f32::max)
    }

    #[test]
    fn sliding_updates_match_full_recomputation() {
        let data = stream(FRAMES + 30 * 20, 7, false);
        let mut streaming = PcSpectrum::new(FRAMES, true, 1).unwrap();
        let mut out = vec![0.0; streaming.outputs()];
        for hop in 0..=20 {
            let window = &data[hop * 30 * FEATURES..(hop * 30 + FRAMES) * FEATURES];
            let updates = streaming.features(window, Some(30), &mut out).unwrap();
            let expected = if hop == 0 {
                Update::Full
            } else {
                Update::Sliding
            };
            assert_eq!(updates, [expected; RECEIVERS]);
            let fresh = features_once(window, FRAMES, true).unwrap();
            assert!(max_difference(&out, &fresh) < 1e-4, "hop {hop}");
        }
    }

    #[test]
    fn a_changed_overlap_falls_back_to_full_recomputation() {
        let data = stream(FRAMES + 30, 11, false);
        let mut front = PcSpectrum::new(FRAMES, true, 1).unwrap();
        let mut out = vec![0.0; front.outputs()];
        front
            .features(&data[..FRAMES * FEATURES], None, &mut out)
            .unwrap();
        let mut next = data[30 * FEATURES..(30 + FRAMES) * FEATURES].to_vec();
        next[100 * FEATURES + 5] += 0.25; // first receiver, tone 5, inside the overlap
        let updates = front.features(&next, Some(30), &mut out).unwrap();
        assert_eq!(updates[0], Update::Full);
        assert_eq!(&updates[1..], &[Update::Sliding; 3]);
        assert!(max_difference(&out, &features_once(&next, FRAMES, true).unwrap()) < 1e-4);
    }

    #[test]
    fn an_absent_receiver_is_skipped_and_lowers_coverage() {
        let data = stream(FRAMES, 3, true);
        let mut front = PcSpectrum::new(FRAMES, true, 1).unwrap();
        let mut out = vec![0.0; front.outputs()];
        let updates = front.features(&data, None, &mut out).unwrap();
        assert_eq!(updates[3], Update::Skipped);
        for f in 0..stft_frames(FRAMES) {
            assert!(out[f * OUTPUTS + 2 * BINS] <= 0.75);
        }
    }

    #[test]
    fn scalar_simd_and_threads_agree() {
        let data = stream(FRAMES, 5, false);
        let reference = features_once(&data, FRAMES, false).unwrap();
        assert!(max_difference(&reference, &features_once(&data, FRAMES, true).unwrap()) < 1e-3);
        for threads in [2, 4] {
            let mut front = PcSpectrum::new(FRAMES, true, threads).unwrap();
            let mut out = vec![0.0; front.outputs()];
            front.features(&data, None, &mut out).unwrap();
            assert_eq!(out, features_once(&data, FRAMES, true).unwrap());
        }
    }

    #[test]
    fn a_sinusoid_peaks_in_its_bin() {
        // Every tone of every receiver follows a 15 Hz sinusoid (bin 8 of 64 at
        // 120 Hz) with a tone-dependent gain, plus faint noise so the covariance
        // has full rank.
        let mut data = stream(FRAMES, 9, false);
        for t in 0..FRAMES {
            let wave = (std::f32::consts::TAU * 15.0 * t as f32 / 120.0).sin();
            for r in 0..RECEIVERS {
                for tone in 0..TONES {
                    let index = t * FEATURES + r * TONES + tone;
                    if data[t * FEATURES + SIGNALS + r * TONES + tone] != 0.0 {
                        data[index] = wave * (1.0 + tone as f32 / 50.0) + 1e-3 * data[index];
                    }
                }
            }
        }
        let out = features_once(&data, FRAMES, true).unwrap();
        for f in 0..stft_frames(FRAMES) {
            let mean = &out[f * OUTPUTS..f * OUTPUTS + BINS];
            let best = (0..BINS)
                .max_by(|&a, &b| mean[a].total_cmp(&mean[b]))
                .unwrap();
            assert_eq!(best + 1, 8, "frame {f}");
        }
    }

    #[test]
    #[ignore = "benchmark; run with --release --ignored --nocapture"]
    fn benchmark_stages() {
        use std::time::Instant;
        let hops = 400;
        let data = stream(FRAMES + 30 * hops, 13, false);
        let tables = Tables::new();
        let mut receiver = Receiver::new(FRAMES);
        let simd = symmetric_eigen::simd_available();
        let mut totals = [0.0f64; 8];
        for hop in 0..hops {
            let window = &data[hop * 30 * FEATURES..(hop * 30 + FRAMES) * FEATURES];
            let mut clock = Instant::now();
            let mut lap = |slot: usize, totals: &mut [f64; 8]| {
                if hop > 0 {
                    totals[slot] += clock.elapsed().as_secs_f64() * 1e3;
                }
                clock = Instant::now();
            };
            let sliding = receiver.gather(window, 0, FRAMES, Some(30));
            assert!(receiver.frame_flags());
            lap(0, &mut totals);
            if sliding {
                receiver.accumulate(true, 0..30, -1.0, simd);
                receiver.accumulate(false, FRAMES - 30..FRAMES, 1.0, simd);
            } else {
                receiver.products.fill(0.0);
                receiver.sum.fill(0.0);
                receiver.count = 0.0;
                receiver.accumulate(false, 0..FRAMES, 1.0, simd);
            }
            receiver.current = true;
            lap(1, &mut totals);
            receiver.covariance();
            lap(2, &mut totals);
            symmetric_eigen::tridiagonalize(&mut receiver.eigen, simd);
            lap(3, &mut totals);
            let values = symmetric_eigen::largest_eigenvalues(&mut receiver.eigen, COMPONENTS);
            lap(4, &mut totals);
            for (index, &value) in values.iter().enumerate() {
                symmetric_eigen::tridiagonal_vector(
                    &mut receiver.eigen,
                    value,
                    index,
                    &mut receiver.axes,
                );
            }
            lap(5, &mut totals);
            symmetric_eigen::back_transform(&receiver.eigen, &mut receiver.axes, COMPONENTS, simd);
            receiver.project(FRAMES, simd);
            lap(6, &mut totals);
            receiver.spectrum(FRAMES, &tables, simd);
            lap(7, &mut totals);
        }
        let names = [
            "gather, overlap check, frame flags",
            "sums",
            "covariance",
            "tridiagonalize",
            "bisection",
            "inverse iteration",
            "back-transform + project",
            "spectrum",
        ];
        let mut total = 0.0;
        for (name, value) in names.iter().zip(totals) {
            let each = value / (hops - 1) as f64;
            total += each;
            println!("stage {name}: {each:.3} ms per receiver");
        }
        println!("stage total: {total:.3} ms per receiver");
    }

    #[test]
    #[ignore = "benchmark; run with --release --ignored --nocapture"]
    fn benchmark_pc_spectrum() {
        use std::{hint::black_box, time::Instant};
        let hops = 400;
        let data = stream(FRAMES + 30 * hops, 13, false);
        for simd in [true, false] {
            for threads in [1, 2, 4] {
                for sliding in [true, false] {
                    let mut front = PcSpectrum::new(FRAMES, simd, threads).unwrap();
                    let mut out = vec![0.0; front.outputs()];
                    let mut times = Vec::with_capacity(hops);
                    for hop in 0..hops {
                        let window = &data[hop * 30 * FEATURES..(hop * 30 + FRAMES) * FEATURES];
                        let started = Instant::now();
                        black_box(
                            front
                                .features(black_box(window), sliding.then_some(30), &mut out)
                                .unwrap(),
                        );
                        if hop > 0 {
                            times.push(started.elapsed().as_secs_f64() * 1e3);
                        }
                    }
                    times.sort_by(f64::total_cmp);
                    println!(
                        "simd={} threads={threads} sliding={sliding} median_ms={:.3} p90_ms={:.3}",
                        front.simd(),
                        times[times.len() / 2],
                        times[times.len() * 9 / 10],
                    );
                }
            }
        }
    }
}
