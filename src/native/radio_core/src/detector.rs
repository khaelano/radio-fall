//! Bounded capture-time CNN preprocessing; no Python work on the numeric worker.
use crate::{bindings::NativeRecord, wire::Record};
use pyo3::{exceptions::PyValueError, prelude::*, types::PyBytes};
use rayon::prelude::*;
use serde::Serialize;
use std::{
    collections::BTreeMap,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const RX: usize = 4;
const TONES: usize = 242;
const BINS: usize = 100;
const PLANE: usize = BINS * TONES;
const WINDOW: u64 = 4_000_000_000;
const LAG: u64 = 100_000_000;
const MAX_LAG: u64 = 150_000_000;
const RECORD_LIMIT: usize = 2048;
type TimedRecord = (Py<NativeRecord>, usize, u64);

fn now_ns() -> u64 {
    #[cfg(unix)]
    {
        crate::pipeline::monotonic_ns()
    }
    #[cfg(not(unix))]
    {
        0
    }
}

struct Prepared {
    capture: u64,
    available: u64,
    values: [f64; TONES],
    phase: [f64; TONES],
}

fn prepare(record: &Record, capture: u64, available: u64) -> Option<Prepared> {
    if record.fields[1] != 4 || record.fields[2] != 0 || record.fields[3] != 0 {
        return None;
    }
    let p = record.phase.as_ref()?;
    let mut values = [f64::NAN; TONES];
    let mut phase = [f64::NAN; TONES];
    if record.fields[14] == 0 {
        for (i, tone) in p.indices.iter().enumerate() {
            let slot = match *tone {
                -122..=-2 => Some((*tone + 122) as usize),
                2..=122 => Some((*tone + 119) as usize),
                _ => None,
            };
            if let Some(j) = slot {
                if p.raw[i].is_finite() && p.calibrated[i].is_finite() {
                    values[j] = p.amplitudes[i].ln_1p();
                    phase[j] = p.calibrated[i];
                }
            }
        }
    }
    Some(Prepared {
        capture,
        available,
        values,
        phase,
    })
}

fn add_scalar(values: &[f64], sum: &mut [f64], count: &mut [f64]) {
    for ((v, s), c) in values.iter().zip(sum).zip(count) {
        if v.is_finite() {
            *s += v;
            *c += 1.;
        }
    }
}

fn add(values: &[f64], sum: &mut [f64], count: &mut [f64], simd: bool) {
    #[cfg(target_arch = "x86_64")]
    if simd {
        // SAFETY: constructor checks AVX2; slices have the same bounded length.
        unsafe { add_avx2(values, sum, count) };
        return;
    }
    let _ = simd;
    add_scalar(values, sum, count);
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn add_avx2(values: &[f64], sum: &mut [f64], count: &mut [f64]) {
    use std::arch::x86_64::*;
    let end = values.len() / 4 * 4;
    for i in (0..end).step_by(4) {
        // SAFETY: every load/store covers four initialized elements inside the slices.
        unsafe {
            let v = _mm256_loadu_pd(values.as_ptr().add(i));
            let magnitude = _mm256_andnot_pd(_mm256_set1_pd(-0.0), v);
            let valid = _mm256_cmp_pd::<_CMP_LE_OQ>(magnitude, _mm256_set1_pd(f64::MAX));
            let s = _mm256_loadu_pd(sum.as_ptr().add(i));
            let c = _mm256_loadu_pd(count.as_ptr().add(i));
            _mm256_storeu_pd(
                sum.as_mut_ptr().add(i),
                _mm256_add_pd(s, _mm256_and_pd(v, valid)),
            );
            _mm256_storeu_pd(
                count.as_mut_ptr().add(i),
                _mm256_add_pd(c, _mm256_and_pd(_mm256_set1_pd(1.), valid)),
            );
        }
    }
    add_scalar(&values[end..], &mut sum[end..], &mut count[end..]);
}

fn finish_scalar(
    sum: &[f64],
    count: &[f64],
    mean: &[f32],
    scale: &[f32],
    raw: &mut [f32],
    out: &mut [f32],
    masks: &mut [f32],
) {
    for i in 0..sum.len() {
        if count[i] > 0. {
            raw[i] = (sum[i] / count[i]) as f32;
            out[i] = (raw[i] - mean[i]) / scale[i];
            masks[i] = 1.;
        } else {
            raw[i] = f32::NAN;
            out[i] = 0.;
            masks[i] = 0.;
        }
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn finish_avx2(
    sum: &[f64],
    count: &[f64],
    mean: &[f32],
    scale: &[f32],
    raw: &mut [f32],
    out: &mut [f32],
    masks: &mut [f32],
) {
    use std::arch::x86_64::*;
    let end = sum.len() / 4 * 4;
    for i in (0..end).step_by(4) {
        // SAFETY: validated equal slice lengths and four-element bounded chunks.
        unsafe {
            let c = _mm256_loadu_pd(count.as_ptr().add(i));
            let valid = _mm256_cmp_pd::<_CMP_GT_OQ>(c, _mm256_setzero_pd());
            let v = _mm256_cvtpd_ps(_mm256_div_pd(_mm256_loadu_pd(sum.as_ptr().add(i)), c));
            let packed = _mm256_permutevar8x32_epi32(
                _mm256_castpd_si256(valid),
                _mm256_setr_epi32(0, 2, 4, 6, 0, 0, 0, 0),
            );
            let mask = _mm_castsi128_ps(_mm256_castsi256_si128(packed));
            let normalized = _mm_div_ps(
                _mm_sub_ps(v, _mm_loadu_ps(mean.as_ptr().add(i))),
                _mm_loadu_ps(scale.as_ptr().add(i)),
            );
            _mm_storeu_ps(raw.as_mut_ptr().add(i), v);
            _mm_storeu_ps(out.as_mut_ptr().add(i), _mm_and_ps(normalized, mask));
            _mm_storeu_ps(masks.as_mut_ptr().add(i), _mm_and_ps(_mm_set1_ps(1.), mask));
        }
    }
    finish_scalar(
        &sum[end..],
        &count[end..],
        &mean[end..],
        &scale[end..],
        &mut raw[end..],
        &mut out[end..],
        &mut masks[end..],
    );
}

#[derive(Clone, Serialize)]
struct Diagnostics {
    start_ns: u64,
    end_ns: u64,
    generation: u64,
    amplitude_coverage: Vec<f64>,
    phase_change_coverage: Vec<f64>,
    packets: Vec<usize>,
    valid: bool,
    reason: String,
    preprocessing_ms: f64,
    kernel: String,
}

#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct CnnWindow {
    tensor: Arc<Vec<f32>>,
    raw: Arc<Vec<f32>>,
    diagnostic: Diagnostics,
}

fn floats(v: &[f32]) -> &[u8] {
    // SAFETY: initialized f32 has no padding; lifetime is tied to the source slice.
    unsafe { std::slice::from_raw_parts(v.as_ptr().cast(), std::mem::size_of_val(v)) }
}

#[pymethods]
impl CnnWindow {
    fn tensor_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, floats(&self.tensor))
    }
    fn raw_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, floats(&self.raw))
    }
    fn metadata_json(&self) -> String {
        serde_json::to_string(&self.diagnostic).unwrap()
    }
}

struct Builder {
    mean: Vec<f32>,
    scale: Vec<f32>,
    simd: bool,
    minimum: f64,
    grace: u64,
    pool: rayon::ThreadPool,
    phase_only: bool,
}
impl Builder {
    fn phase_part(
        &self,
        records: &[&Arc<Prepared>],
        start: u64,
    ) -> (Vec<f32>, Vec<f32>, Vec<f32>, f64, f64, usize) {
        let (mut sum, mut count) = (vec![0.; 2 * PLANE], vec![0.; 2 * PLANE]);
        let mut amplitude_valid = vec![false; PLANE];
        let mut packets = 0;
        for current in records {
            if current.capture < start || current.capture >= start.saturating_add(WINDOW) {
                continue;
            }
            packets += 1;
            let bin = ((current.capture - start) as u128 * 25 / 1_000_000_000) as usize;
            let offset = bin * TONES;
            for j in 0..TONES {
                amplitude_valid[offset + j] |= current.phase[j].is_finite();
            }
            let Some(cutoff) = current.capture.checked_sub(LAG) else {
                continue;
            };
            let index = records.partition_point(|r| r.capture <= cutoff);
            if index == 0 {
                continue;
            }
            let previous = records[index - 1];
            if current.capture - previous.capture > MAX_LAG {
                continue;
            }
            let mut sine = [f64::NAN; TONES];
            let mut cosine = [f64::NAN; TONES];
            for j in 0..TONES {
                if current.phase[j].is_finite() && previous.phase[j].is_finite() {
                    // sin/cos are periodic: equivalent to wrapping delta then
                    // taking its sine/cosine, without a discontinuity at +/-pi.
                    (sine[j], cosine[j]) = (current.phase[j] - previous.phase[j]).sin_cos();
                }
            }
            add(
                &sine,
                &mut sum[offset..offset + TONES],
                &mut count[offset..offset + TONES],
                self.simd,
            );
            add(
                &cosine,
                &mut sum[PLANE + offset..PLANE + offset + TONES],
                &mut count[PLANE + offset..PLANE + offset + TONES],
                self.simd,
            );
        }
        let (mut raw, mut output, mut masks) = (
            vec![f32::NAN; 2 * PLANE],
            vec![0.; 2 * PLANE],
            vec![0.; 2 * PLANE],
        );
        let mean = [0.; TONES];
        let scale = [1.; TONES];
        for bin in 0..2 * BINS {
            let range = bin * TONES..(bin + 1) * TONES;
            #[cfg(target_arch = "x86_64")]
            if self.simd {
                // SAFETY: runtime-dispatched AVX2, equal TONES-long slices.
                unsafe {
                    finish_avx2(
                        &sum[range.clone()],
                        &count[range.clone()],
                        &mean,
                        &scale,
                        &mut raw[range.clone()],
                        &mut output[range.clone()],
                        &mut masks[range],
                    );
                }
                continue;
            }
            finish_scalar(
                &sum[range.clone()],
                &count[range.clone()],
                &mean,
                &scale,
                &mut raw[range.clone()],
                &mut output[range.clone()],
                &mut masks[range],
            );
        }
        let coverage = amplitude_valid.iter().filter(|v| **v).count() as f64 / PLANE as f64;
        let phase_coverage = masks.iter().map(|v| *v as f64).sum::<f64>() / (2 * PLANE) as f64;
        (raw, output, masks, coverage, phase_coverage, packets)
    }

    fn build(&self, rows: &[Vec<Arc<Prepared>>], start: u64, generation: u64) -> CnnWindow {
        let began = Instant::now();
        let end = start.saturating_add(WINDOW);
        let parts: Vec<_> = self.pool.install(|| {
            rows.par_iter()
                .enumerate()
                .map(|(rx, records)| {
                    let records: Vec<_> = records
                        .iter()
                        .filter(|r| r.available <= end.saturating_add(self.grace))
                        .collect();
                    if self.phase_only {
                        return self.phase_part(&records, start);
                    }
                    let (mut sum, mut count) = (vec![0.; PLANE], vec![0.; PLANE]);
                    let mut changes = vec![false; PLANE];
                    let mut packets = 0;
                    for current in &records {
                        if current.capture < start || current.capture >= end {
                            continue;
                        }
                        packets += 1;
                        let bin = ((current.capture - start) as u128 * 25 / 1_000_000_000) as usize;
                        let offset = bin * TONES;
                        add(
                            &current.values,
                            &mut sum[offset..offset + TONES],
                            &mut count[offset..offset + TONES],
                            self.simd,
                        );
                        if let Some(cutoff) = current.capture.checked_sub(LAG) {
                            let previous = records.partition_point(|r| r.capture <= cutoff);
                            if previous > 0 {
                                let old = &records[previous - 1];
                                if current.capture - old.capture <= MAX_LAG {
                                    for j in 0..TONES {
                                        changes[offset + j] |= current.values[j].is_finite()
                                            && old.values[j].is_finite();
                                    }
                                }
                            }
                        }
                    }
                    let (mut raw, mut output, mut mask) =
                        (vec![f32::NAN; PLANE], vec![0.; PLANE], vec![0.; PLANE]);
                    for bin in 0..BINS {
                        let s = bin * TONES;
                        let range = s..s + TONES;
                        let m = &self.mean[rx * TONES..(rx + 1) * TONES];
                        let scale = &self.scale[rx * TONES..(rx + 1) * TONES];
                        #[cfg(target_arch = "x86_64")]
                        if self.simd {
                            // SAFETY: runtime-dispatched AVX2; ranges are all exactly TONES.
                            unsafe {
                                finish_avx2(
                                    &sum[range.clone()],
                                    &count[range.clone()],
                                    m,
                                    scale,
                                    &mut raw[range.clone()],
                                    &mut output[range.clone()],
                                    &mut mask[range],
                                )
                            };
                            continue;
                        }
                        finish_scalar(
                            &sum[range.clone()],
                            &count[range.clone()],
                            m,
                            scale,
                            &mut raw[range.clone()],
                            &mut output[range.clone()],
                            &mut mask[range],
                        );
                    }
                    let coverage = mask.iter().map(|v| *v as f64).sum::<f64>() / PLANE as f64;
                    let change_coverage =
                        changes.iter().filter(|v| **v).count() as f64 / PLANE as f64;
                    (raw, output, mask, coverage, change_coverage, packets)
                })
                .collect()
        });
        let mut tensor = Vec::with_capacity((if self.phase_only { 4 } else { 2 }) * RX * PLANE);
        for part in &parts {
            tensor.extend_from_slice(&part.1);
        }
        for part in &parts {
            tensor.extend_from_slice(&part.2);
        }
        let valid = parts.iter().all(|p| p.4 >= self.minimum);
        CnnWindow {
            tensor: Arc::new(tensor),
            raw: Arc::new(parts.iter().flat_map(|p| p.0.iter().copied()).collect()),
            diagnostic: Diagnostics {
                start_ns: start,
                end_ns: end,
                generation,
                amplitude_coverage: parts.iter().map(|p| p.3).collect(),
                phase_change_coverage: parts.iter().map(|p| p.4).collect(),
                packets: parts.iter().map(|p| p.5).collect(),
                valid,
                reason: if valid {
                    String::new()
                } else {
                    "Insufficient data: phase-change coverage below minimum".into()
                },
                preprocessing_ms: began.elapsed().as_secs_f64() * 1000.,
                kernel: if self.simd { "avx2" } else { "scalar" }.into(),
            },
        }
    }
}

struct Input {
    record: Arc<Record>,
    receiver: usize,
    capture: u64,
    run: (u64, u32, u32),
    generation: u64,
}
#[derive(Default, Serialize)]
struct Stats {
    submitted: u64,
    overflow: u64,
    late: u64,
    duplicates: u64,
    filtered: u64,
    windows: u64,
    skipped_windows: u64,
    pending: usize,
    maximum_pending: usize,
}
struct Shared {
    latest: Mutex<Option<CnnWindow>>,
    stats: Mutex<Stats>,
    generation: AtomicU64,
    stop: AtomicBool,
}

#[pyclass]
pub struct CnnPreprocessor {
    builder: Arc<Builder>,
    tx: mpsc::SyncSender<Input>,
    shared: Arc<Shared>,
    worker: Option<JoinHandle<()>>,
}

fn worker(
    builder: Arc<Builder>,
    shared: Arc<Shared>,
    channel: mpsc::Receiver<Input>,
    hop: u64,
    grace: u64,
) {
    let mut rows: [BTreeMap<(u64, u32), Arc<Prepared>>; RX] =
        std::array::from_fn(|_| BTreeMap::new());
    let mut epochs = [None; RX];
    let mut common_epoch = None;
    let mut generation = shared.generation.load(Ordering::Acquire);
    let mut first = None;
    let mut next = None;
    let mut finalized = 0u64;
    while !shared.stop.load(Ordering::Acquire) {
        let incoming = channel.recv_timeout(Duration::from_millis(10));
        let observed = shared.generation.load(Ordering::Acquire);
        if observed != generation {
            rows.iter_mut().for_each(|r| r.clear());
            epochs.fill(None);
            common_epoch = None;
            first = None;
            next = None;
            finalized = 0;
            generation = observed;
            *shared.latest.lock().unwrap() = None;
        }
        match incoming {
            Ok(input) => {
                {
                    let mut s = shared.stats.lock().unwrap();
                    s.pending = s.pending.saturating_sub(1);
                }
                if input.generation != generation {
                    continue;
                }
                if epochs[input.receiver].is_some_and(|e| e != input.run)
                    || common_epoch.is_some_and(|e| e != (input.run.0, input.run.1))
                {
                    shared.generation.fetch_add(1, Ordering::AcqRel);
                    continue;
                }
                epochs[input.receiver] = Some(input.run);
                common_epoch = Some((input.run.0, input.run.1));
                if input.capture < finalized.saturating_sub(WINDOW + MAX_LAG) {
                    shared.stats.lock().unwrap().late += 1;
                    continue;
                }
                if let Some(prepared) = prepare(&input.record, input.capture, now_ns()) {
                    let map = &mut rows[input.receiver];
                    match map.entry((input.capture, input.record.sequence)) {
                        std::collections::btree_map::Entry::Vacant(entry) => {
                            entry.insert(Arc::new(prepared));
                        }
                        std::collections::btree_map::Entry::Occupied(_) => {
                            shared.stats.lock().unwrap().duplicates += 1;
                        }
                    }
                    if map.len() > RECORD_LIMIT {
                        shared.stats.lock().unwrap().overflow += 1;
                        shared.generation.fetch_add(1, Ordering::AcqRel);
                        continue;
                    }
                    let origin = *first.get_or_insert(input.capture);
                    next.get_or_insert(origin.saturating_add(WINDOW + MAX_LAG));
                } else {
                    shared.stats.lock().unwrap().filtered += 1;
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => (),
        }
        // Do not finalize a window while accepted inputs are waiting behind this row.
        if shared.stats.lock().unwrap().pending > 0 {
            continue;
        }
        let now = now_ns();
        if let Some(mut end) = next {
            if end.saturating_add(grace) <= now {
                let skipped = (now - end - grace) / hop;
                end = end.saturating_add(skipped * hop);
                let snapshot: Vec<_> = rows.iter().map(|r| r.values().cloned().collect()).collect();
                let frame = builder.build(&snapshot, end - WINDOW, generation);
                if shared.generation.load(Ordering::Acquire) == generation {
                    *shared.latest.lock().unwrap() = Some(frame);
                    let mut stats = shared.stats.lock().unwrap();
                    stats.windows += 1;
                    stats.skipped_windows += skipped;
                }
                finalized = end;
                let keep = end.saturating_add(hop).saturating_sub(WINDOW + MAX_LAG);
                for r in &mut rows {
                    r.retain(|(capture, _), _| *capture >= keep);
                }
                next = Some(end.saturating_add(hop));
            }
        }
    }
}

#[pymethods]
impl CnnPreprocessor {
    #[new]
    #[pyo3(signature=(mean, scale, minimum_coverage=0.7, workers=2, hop_ms=250, grace_ms=900, capacity=4096, kernel="auto", representation="amplitude"))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        mean: Vec<f32>,
        scale: Vec<f32>,
        minimum_coverage: f64,
        workers: usize,
        hop_ms: u64,
        grace_ms: u64,
        capacity: usize,
        kernel: &str,
        representation: &str,
    ) -> PyResult<Self> {
        if !["amplitude", "phase_change"].contains(&representation)
            || (representation == "phase_change"
                && (mean.iter().any(|v| *v != 0.) || scale.iter().any(|v| *v != 1.)))
        {
            return Err(PyValueError::new_err(
                "Phase-change inputs require identity parameters and a supported representation",
            ));
        }
        if mean.len() != RX * TONES
            || scale.len() != RX * TONES
            || mean.iter().any(|v| !v.is_finite())
            || scale.iter().any(|v| !v.is_finite() || *v < 0.05)
            || !(0. ..=1.).contains(&minimum_coverage)
            || workers == 0
            || workers > 4
            || !(40..=4000).contains(&hop_ms)
            || grace_ms > 2000
            || capacity == 0
            || capacity > 16384
        {
            return Err(PyValueError::new_err(
                "Invalid CNN normalization or bounded preprocessing configuration",
            ));
        }
        let available = crate::numeric::kernel() == "avx2";
        let simd = match kernel {
            "auto" => available,
            "scalar" => false,
            "avx2" if available => true,
            _ => {
                return Err(PyValueError::new_err(
                    "kernel must be auto, scalar or supported avx2",
                ));
            }
        };
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(workers)
            .thread_name(|i| format!("cnn-bin-{i}"))
            .build()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let builder = Arc::new(Builder {
            mean,
            scale,
            simd,
            minimum: minimum_coverage,
            grace: grace_ms * 1_000_000,
            pool,
            phase_only: representation == "phase_change",
        });
        let shared = Arc::new(Shared {
            latest: Mutex::new(None),
            stats: Mutex::new(Stats::default()),
            generation: AtomicU64::new(1),
            stop: AtomicBool::new(false),
        });
        let (tx, rx) = mpsc::sync_channel(capacity);
        let b = builder.clone();
        let s = shared.clone();
        let worker = thread::Builder::new()
            .name("cnn-preprocessing".into())
            .spawn(move || worker(b, s, rx, hop_ms * 1_000_000, grace_ms * 1_000_000))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self {
            builder,
            tx,
            shared,
            worker: Some(worker),
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn submit(
        &self,
        record: &NativeRecord,
        receiver: usize,
        capture_ns: u64,
        run_id: u64,
        transmitter_boot_id: u32,
        receiver_boot_id: u32,
    ) -> PyResult<bool> {
        if receiver >= RX || capture_ns == 0 {
            return Err(PyValueError::new_err("Invalid receiver or capture clock"));
        }
        if self.shared.stop.load(Ordering::Acquire) {
            return Ok(false);
        }
        let input = Input {
            record: record.core.clone(),
            receiver,
            capture: capture_ns,
            run: (run_id, transmitter_boot_id, receiver_boot_id),
            generation: self.shared.generation.load(Ordering::Acquire),
        };
        let mut stats = self.shared.stats.lock().unwrap();
        match self.tx.try_send(input) {
            Ok(()) => {
                stats.submitted += 1;
                stats.pending += 1;
                stats.maximum_pending = stats.maximum_pending.max(stats.pending);
                Ok(true)
            }
            Err(_) => {
                stats.overflow += 1;
                self.shared.generation.fetch_add(1, Ordering::AcqRel);
                Ok(false)
            }
        }
    }

    fn poll(&self) -> Option<CnnWindow> {
        self.shared.latest.lock().unwrap().take()
    }
    fn reset(&self) {
        self.shared.generation.fetch_add(1, Ordering::AcqRel);
        *self.shared.latest.lock().unwrap() = None;
    }
    fn stats_json(&self) -> String {
        let mut value = serde_json::to_value(&*self.shared.stats.lock().unwrap()).unwrap();
        value["generation"] = self.shared.generation.load(Ordering::Acquire).into();
        value["kernel"] = if self.builder.simd { "avx2" } else { "scalar" }.into();
        value.to_string()
    }

    fn build(
        &self,
        py: Python<'_>,
        records: Vec<TimedRecord>,
        start_ns: u64,
    ) -> PyResult<CnnWindow> {
        if records.len() > RX * RECORD_LIMIT || records.iter().any(|(_, rx, _)| *rx >= RX) {
            return Err(PyValueError::new_err("Invalid bounded replay input"));
        }
        let records: Vec<_> = records
            .into_iter()
            .map(|(r, rx, t)| (r.borrow(py).core.clone(), rx, t))
            .collect();
        py.detach(|| {
            let mut rows: Vec<BTreeMap<(u64, u32), Arc<Prepared>>> =
                (0..RX).map(|_| BTreeMap::new()).collect();
            for (record, rx, capture) in records {
                if let Some(p) = prepare(&record, capture, 0) {
                    rows[rx]
                        .entry((capture, record.sequence))
                        .or_insert_with(|| Arc::new(p));
                }
            }
            Ok(self.builder.build(
                &rows
                    .into_iter()
                    .map(|r| r.into_values().collect())
                    .collect::<Vec<_>>(),
                start_ns,
                0,
            ))
        })
    }

    fn close(&mut self, py: Python<'_>) {
        self.shared.stop.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            py.detach(|| {
                let _ = worker.join();
            });
        }
    }
}

impl Drop for CnnPreprocessor {
    fn drop(&mut self) {
        self.shared.stop.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

#[pyfunction]
pub fn decode_cnn_record(py: Python<'_>, encoded: &[u8]) -> PyResult<NativeRecord> {
    py.detach(|| Record::decode(encoded))
        .map(|core| NativeRecord { core })
        .map_err(PyValueError::new_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn builder(simd: bool) -> Builder {
        Builder {
            mean: vec![1.; RX * TONES],
            scale: vec![2.; RX * TONES],
            simd,
            minimum: 0.7,
            grace: 900_000_000,
            pool: rayon::ThreadPoolBuilder::new()
                .num_threads(2)
                .build()
                .unwrap(),
            phase_only: false,
        }
    }

    #[test]
    fn vector_reductions_match_scalar_with_missing_values_and_tails() {
        let values: Vec<_> = (0..TONES)
            .map(|i| match i % 7 {
                0 => f64::NAN,
                1 => f64::INFINITY,
                2 => f64::NEG_INFINITY,
                _ => i as f64 / 7.,
            })
            .collect();
        let (mut sum, mut count) = (vec![0.; TONES], vec![0.; TONES]);
        let (mut expected, mut counts) = (sum.clone(), count.clone());
        add_scalar(&values, &mut expected, &mut counts);
        add(
            &values,
            &mut sum,
            &mut count,
            crate::numeric::kernel() == "avx2",
        );
        assert_eq!(sum, expected);
        assert_eq!(count, counts);
    }

    #[test]
    fn windows_are_half_open_and_use_past_lag_support_without_filling_gaps() {
        let start = 10_000_000_000;
        let records: Vec<_> = [(start - LAG, 1.), (start, 3.), (start + WINDOW, 99.)]
            .into_iter()
            .map(|(capture, v)| {
                Arc::new(Prepared {
                    capture,
                    available: 0,
                    values: [v; TONES],
                    phase: [v; TONES],
                })
            })
            .collect();
        let rows = vec![records; RX];
        let result = builder(false).build(&rows, start, 7);
        assert_eq!(result.diagnostic.packets, vec![1; RX]);
        assert_eq!(result.diagnostic.phase_change_coverage, vec![0.01; RX]);
        assert!(!result.diagnostic.valid);
        for rx in 0..RX {
            assert_eq!(result.raw[rx * PLANE], 3.);
            assert_eq!(result.tensor[rx * PLANE], 1.);
            assert_eq!(result.tensor[(rx + RX) * PLANE], 1.);
            assert!(result.raw[rx * PLANE + TONES].is_nan());
            assert_eq!(result.tensor[rx * PLANE + TONES], 0.);
            assert_eq!(result.tensor[(rx + RX) * PLANE + TONES], 0.);
        }
    }

    #[test]
    fn late_availability_cannot_backfill_a_finalized_window() {
        let start = 10_000_000_000;
        let late = Arc::new(Prepared {
            capture: start,
            available: start + WINDOW + 900_000_001,
            values: [3.; TONES],
            phase: [3.; TONES],
        });
        let result = builder(false).build(&vec![vec![late]; RX], start, 1);
        assert_eq!(result.diagnostic.packets, vec![0; RX]);
        assert!(result.tensor.iter().all(|v| *v == 0.));
    }

    #[test]
    fn simd_normalized_windows_equal_scalar_including_tail_and_mask_channels() {
        let start = 10_000_000_000;
        let records: Vec<_> = (0..410)
            .map(|i| {
                Arc::new(Prepared {
                    capture: start - 100_000_000 + i * 10_000_000,
                    available: 0,
                    values: std::array::from_fn(|j| {
                        if (i + j as u64) % 13 == 0 {
                            f64::NAN
                        } else {
                            (i + j as u64) as f64 / 37.
                        }
                    }),
                    phase: [0.; TONES],
                })
            })
            .collect();
        let rows = vec![records; RX];
        let scalar = builder(false).build(&rows, start, 1);
        let vector = builder(crate::numeric::kernel() == "avx2").build(&rows, start, 1);
        assert_eq!(*scalar.tensor, *vector.tensor);
        assert_eq!(
            scalar.diagnostic.phase_change_coverage,
            vector.diagnostic.phase_change_coverage
        );
    }

    #[test]
    fn a_full_input_queue_invalidates_the_generation_without_blocking() {
        let (tx, _receiver) = mpsc::sync_channel(1);
        let shared = Arc::new(Shared {
            latest: Mutex::new(None),
            stats: Mutex::new(Stats::default()),
            generation: AtomicU64::new(1),
            stop: AtomicBool::new(false),
        });
        let processor = CnnPreprocessor {
            builder: Arc::new(builder(false)),
            tx,
            shared,
            worker: None,
        };
        let mut encoded = vec![10u8; 87 + 490];
        encoded[..4].copy_from_slice(b"CSI1");
        encoded[4] = 3;
        encoded[5] = 0;
        encoded[6..8].copy_from_slice(&87u16.to_be_bytes());
        encoded[8..10].copy_from_slice(&490u16.to_be_bytes());
        encoded[36..51].fill(0);
        encoded[37] = 4;
        encoded[53..55].copy_from_slice(&490u16.to_be_bytes());
        encoded[71..87].copy_from_slice(b"0123456789abcdef");
        let record = NativeRecord {
            core: Record::decode(&encoded).unwrap(),
        };
        assert!(processor.submit(&record, 0, 10, 1, 2, 3).unwrap());
        assert!(!processor.submit(&record, 0, 11, 1, 2, 3).unwrap());
        assert_eq!(processor.shared.generation.load(Ordering::Acquire), 2);
        let stats = processor.shared.stats.lock().unwrap();
        assert_eq!(stats.pending, 1);
        assert_eq!(stats.overflow, 1);
    }

    #[test]
    fn phase_windows_use_wrapped_lagged_changes_and_ignore_static_profiles() {
        let start = 10_000_000_000;
        let records: Vec<_> = [
            (start - LAG, 3.13),
            (start, -3.13),
            (start + MAX_LAG + 1, 1.),
        ]
        .into_iter()
        .map(|(capture, phase)| {
            Arc::new(Prepared {
                capture,
                available: 0,
                values: [99.; TONES],
                phase: [phase; TONES],
            })
        })
        .collect();
        let mut scalar = builder(false);
        scalar.phase_only = true;
        let rows = vec![records.clone(); RX];
        let result = scalar.build(&rows, start, 1);
        assert_eq!(result.tensor.len(), 16 * PLANE);
        assert!((result.raw[0] - (-6.26f64).sin() as f32).abs() < 1e-6);
        assert!((result.raw[PLANE] - (-6.26f64).cos() as f32).abs() < 1e-6);
        // The third packet has no sufficiently recent lag predecessor.
        assert_eq!(result.tensor[3 * TONES], 0.);
        assert_eq!(result.tensor[8 * PLANE + 3 * TONES], 0.);
        let shifted: Vec<_> = records
            .iter()
            .map(|row| {
                Arc::new(Prepared {
                    capture: row.capture,
                    available: 0,
                    values: [0.; TONES],
                    phase: std::array::from_fn(|j| row.phase[j] + 0.25 + j as f64 / 1000.),
                })
            })
            .collect();
        let other = scalar.build(&vec![shifted; RX], start, 1);
        for (a, b) in result.tensor.iter().zip(other.tensor.iter()) {
            assert!((a - b).abs() < 1e-6);
        }
        let mut vector = builder(crate::numeric::kernel() == "avx2");
        vector.phase_only = true;
        assert_eq!(*result.tensor, *vector.build(&rows, start, 1).tensor);
    }
}
