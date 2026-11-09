//! Reader and CPU workers never call Python. Completed work has its own bounded
//! handoff; GUI stalls cannot prevent USB draining or numeric preparation.
use crate::{
    bindings::NativeBatch,
    framing::{Decoder, Frame},
    wire::Batch,
};
use pyo3::types::PyBytes;
use pyo3::{
    exceptions::{PyOSError, PyTimeoutError},
    prelude::*,
};
use rayon::prelude::*;
use std::{
    collections::VecDeque,
    os::fd::{AsRawFd, FromRawFd, OwnedFd},
    sync::{
        Arc, Condvar, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

pub fn monotonic_ns() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: ts is valid writable storage; CLOCK_MONOTONIC shares Python's
    // monotonic clock on the supported POSIX host.
    unsafe {
        libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts);
    }
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}
struct Chunk {
    arrival: u64,
    data: Vec<u8>,
}
#[derive(Clone)]
struct Completed {
    arrival: u64,
    processed: u64,
    frame: Frame,
    batch: Option<Arc<Batch>>,
}
#[derive(Default)]
struct Queues {
    raw: VecDeque<Chunk>,
    ready: VecDeque<Completed>,
    raw_bytes: usize,
    ready_bytes: usize,
    peak_raw_bytes: usize,
    peak_raw_chunks: usize,
    peak_ready_bytes: usize,
    peak_ready_frames: usize,
    maximum_wait: u64,
    maximum_processing: u64,
    maximum_application_wait: u64,
    groups: u64,
    chunks: u64,
    malformed: u64,
    oversized: u64,
    reader_done: bool,
    processor_done: bool,
    failure: Option<String>,
}
struct Shared {
    q: Mutex<Queues>,
    changed: Condvar,
    stop: AtomicBool,
    raw_capacity: usize,
    ready_capacity: usize,
    maximum_age: u64,
}
impl Completed {
    fn retained_bytes(&self) -> usize {
        let records = self
            .batch
            .as_ref()
            .map(|b| {
                b.payload.len()
                    + b.records
                        .iter()
                        .map(|r| {
                            r.wire.len()
                                + r.raw.len()
                                + r.csv.get().map_or(0, |s| s.len())
                                + r.phase
                                    .as_ref()
                                    .map_or(0, |p| p.indices.len() * 4 + p.amplitudes.len() * 24)
                                + 256
                        })
                        .sum::<usize>()
            })
            .unwrap_or(0);
        self.frame.data.len() + records + 128
    }
}
impl Shared {
    fn fail(&self, s: impl Into<String>) {
        let mut q = self.q.lock().unwrap();
        if q.failure.is_none() {
            q.failure = Some(s.into());
        }
        self.stop.store(true, Ordering::Release);
        self.changed.notify_all();
    }
}
#[pyclass(frozen)]
pub struct ProcessedFrame {
    inner: Completed,
}
#[pymethods]
impl ProcessedFrame {
    #[getter]
    fn arrival_ns(&self) -> u64 {
        self.inner.arrival
    }
    #[getter]
    fn processed_ns(&self) -> u64 {
        self.inner.processed
    }
    #[getter]
    fn r#type(&self) -> u8 {
        self.inner.frame.kind
    }
    #[getter]
    fn payload<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.inner.frame.data)
    }
    #[getter]
    fn batch(&self) -> Option<NativeBatch> {
        self.inner
            .batch
            .as_ref()
            .map(|core| NativeBatch { core: core.clone() })
    }
}

#[pyclass]
pub struct Pipeline {
    shared: Arc<Shared>,
    threads: Mutex<Vec<thread::JoinHandle<()>>>,
}
#[pymethods]
impl Pipeline {
    #[new]
    #[pyo3(signature=(fd,maximum_age_ns=200_000_000,raw_capacity_bytes=262144,completed_capacity_bytes=16777216,workers=2))]
    fn new(
        fd: i32,
        maximum_age_ns: u64,
        raw_capacity_bytes: usize,
        completed_capacity_bytes: usize,
        workers: usize,
    ) -> PyResult<Self> {
        if maximum_age_ns == 0
            || raw_capacity_bytes < 4096
            || completed_capacity_bytes < 4096
            || !(1..=8).contains(&workers)
        {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "invalid native pipeline limits",
            ));
        }
        // SAFETY: fcntl duplicates an already opened serial descriptor; only our
        // reader owns this duplicate and closes it on its exit.
        let duplicate = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 0) };
        if duplicate < 0 {
            return Err(PyOSError::new_err(
                std::io::Error::last_os_error().to_string(),
            ));
        }
        // SAFETY: fcntl returned a new descriptor owned exclusively by us.
        // RAII also closes it if pool or thread construction fails.
        let owned = unsafe { OwnedFd::from_raw_fd(duplicate) };
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(workers)
            .thread_name(|i| format!("csi-decode-{i}"))
            .build()
            .map_err(|e| PyOSError::new_err(e.to_string()))?;
        let shared = Arc::new(Shared {
            q: Mutex::new(Queues::default()),
            changed: Condvar::new(),
            stop: AtomicBool::new(false),
            raw_capacity: raw_capacity_bytes,
            ready_capacity: completed_capacity_bytes,
            maximum_age: maximum_age_ns,
        });
        let state = shared.clone();
        let reader = thread::Builder::new()
            .name("csi-native-usb".into())
            .spawn(move || {
                let mut buf = [0u8; 4096];
                while !state.stop.load(Ordering::Acquire) {
                    let mut poll = libc::pollfd {
                        fd: owned.as_raw_fd(),
                        events: libc::POLLIN,
                        revents: 0,
                    };
                    // SAFETY: poll points to exactly one valid pollfd, and read's
                    // destination has buf.len() initialized writable bytes.
                    let result = unsafe { libc::poll(&mut poll, 1, 5) };
                    if result < 0 {
                        if std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted
                        {
                            continue;
                        }
                        state.fail("native USB poll failed");
                        break;
                    }
                    if result == 0 {
                        continue;
                    }
                    if poll.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                        state.fail("gateway USB disconnected");
                        break;
                    }
                    let n = unsafe {
                        libc::read(owned.as_raw_fd(), buf.as_mut_ptr().cast(), buf.len())
                    };
                    let arrival = monotonic_ns();
                    if n < 0 {
                        let e = std::io::Error::last_os_error();
                        if matches!(
                            e.kind(),
                            std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                        ) {
                            continue;
                        }
                        state.fail(format!("gateway USB read failed: {e}"));
                        break;
                    }
                    if n == 0 {
                        state.fail("gateway USB disconnected");
                        break;
                    }
                    let n = n as usize;
                    let mut q = state.q.lock().unwrap();
                    if q.raw_bytes + n > state.raw_capacity || q.raw.len() >= 256 {
                        drop(q);
                        state.fail("native raw USB buffer overflow");
                        break;
                    }
                    q.raw.push_back(Chunk {
                        arrival,
                        data: buf[..n].to_vec(),
                    });
                    q.raw_bytes += n;
                    q.peak_raw_bytes = q.peak_raw_bytes.max(q.raw_bytes);
                    q.peak_raw_chunks = q.peak_raw_chunks.max(q.raw.len());
                    state.changed.notify_all();
                }
                drop(owned);
                let mut q = state.q.lock().unwrap();
                q.reader_done = true;
                state.changed.notify_all();
            })
            .map_err(|e| PyOSError::new_err(e.to_string()))?;
        let state = shared.clone();
        let processor = thread::Builder::new()
            .name("csi-native-dispatch".into())
            .spawn(move || {
                let mut decoder = Decoder::default();
                loop {
                    let chunks = {
                        let mut q = state.q.lock().unwrap();
                        while q.raw.is_empty() && !q.reader_done && q.failure.is_none() {
                            q = state.changed.wait(q).unwrap();
                        }
                        if q.failure.is_some() || (q.raw.is_empty() && q.reader_done) {
                            break;
                        }
                        let mut chunks = Vec::new();
                        for _ in 0..8 {
                            if let Some(c) = q.raw.pop_front() {
                                q.raw_bytes -= c.data.len();
                                chunks.push(c);
                            } else {
                                break;
                            }
                        }
                        q.groups += 1;
                        q.chunks += chunks.len() as u64;
                        chunks
                    };
                    let mut frames = Vec::new();
                    let mut waits = 0;
                    for chunk in chunks {
                        let waited = monotonic_ns().saturating_sub(chunk.arrival);
                        waits = waits.max(waited);
                        if waited > state.maximum_age {
                            state.fail("native USB processing buffer age exceeded");
                            break;
                        }
                        frames.extend(
                            decoder
                                .feed(&chunk.data)
                                .into_iter()
                                .map(|f| (chunk.arrival, f)),
                        );
                    }
                    if state.q.lock().unwrap().failure.is_some() {
                        break;
                    }
                    let done: Vec<Result<Completed, String>> = pool.install(|| {
                        frames
                            .into_par_iter()
                            .map(|(arrival, frame)| {
                                let batch = if frame.kind == 24 {
                                    Some(Batch::decode(&frame.data)?)
                                } else {
                                    None
                                };
                                Ok(Completed {
                                    arrival,
                                    processed: monotonic_ns(),
                                    frame,
                                    batch,
                                })
                            })
                            .collect()
                    });
                    let mut q = state.q.lock().unwrap();
                    q.maximum_wait = q.maximum_wait.max(waits);
                    q.malformed = decoder.malformed;
                    q.oversized = decoder.oversized;
                    for completed in done {
                        let f = match completed {
                            Ok(v) => v,
                            Err(e) => {
                                q.failure = Some(e);
                                break;
                            }
                        };
                        q.maximum_processing = q
                            .maximum_processing
                            .max(f.processed.saturating_sub(f.arrival));
                        if f.processed.saturating_sub(f.arrival) > state.maximum_age {
                            q.failure = Some("native USB processing deadline exceeded".into());
                            break;
                        }
                        if q.ready_bytes + f.retained_bytes() > state.ready_capacity
                            || q.ready.len() >= 8192
                        {
                            q.failure = Some("native completed-frame handoff overflow".into());
                            break;
                        }
                        q.ready_bytes += f.retained_bytes();
                        q.ready.push_back(f);
                        q.peak_ready_bytes = q.peak_ready_bytes.max(q.ready_bytes);
                        q.peak_ready_frames = q.peak_ready_frames.max(q.ready.len());
                    }
                    if q.failure.is_some() {
                        state.stop.store(true, Ordering::Release);
                    }
                    state.changed.notify_all();
                }
                let mut q = state.q.lock().unwrap();
                q.processor_done = true;
                state.changed.notify_all();
            });
        let processor = match processor {
            Ok(handle) => handle,
            Err(error) => {
                shared.stop.store(true, Ordering::Release);
                shared.changed.notify_all();
                let _ = reader.join();
                return Err(PyOSError::new_err(error.to_string()));
            }
        };
        Ok(Self {
            shared,
            threads: Mutex::new(vec![reader, processor]),
        })
    }
    #[pyo3(signature=(max_frames=128,timeout_s=0.1))]
    fn frames(
        &self,
        py: Python<'_>,
        max_frames: usize,
        timeout_s: f64,
    ) -> PyResult<Vec<ProcessedFrame>> {
        if max_frames == 0 || !timeout_s.is_finite() || !(0.0..=60.).contains(&timeout_s) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "invalid frame receive limits",
            ));
        }
        py.detach(|| {
            let mut q = self.shared.q.lock().unwrap();
            if q.ready.is_empty() && !q.processor_done && q.failure.is_none() {
                q = self
                    .shared
                    .changed
                    .wait_timeout(q, Duration::from_secs_f64(timeout_s))
                    .unwrap()
                    .0;
            }
            if let Some(e) = &q.failure {
                return Err(PyOSError::new_err(e.clone()));
            }
            let mut out = Vec::new();
            for _ in 0..max_frames {
                if let Some(f) = q.ready.pop_front() {
                    q.ready_bytes -= f.retained_bytes();
                    q.maximum_application_wait = q
                        .maximum_application_wait
                        .max(monotonic_ns().saturating_sub(f.arrival));
                    out.push(ProcessedFrame { inner: f });
                } else {
                    break;
                }
            }
            Ok(out)
        })
    }
    fn stats_json(&self) -> String {
        let q = self.shared.q.lock().unwrap();
        let now = monotonic_ns();
        serde_json::json!({"queued_bytes":q.raw_bytes,"queued_chunks":q.raw.len(),"peak_bytes":q.peak_raw_bytes,"peak_chunks":q.peak_raw_chunks,
            "maximum_wait_ns":q.maximum_wait,"maximum_processing_ns":q.maximum_processing,"maximum_application_wait_ns":q.maximum_application_wait,"oldest_age_ns":q.raw.front().map(|v|now.saturating_sub(v.arrival)).unwrap_or(0),
            "groups":q.groups,"consumed_chunks":q.chunks,"capacity_bytes":self.shared.raw_capacity,"capacity_chunks":256,"maximum_age_ns":self.shared.maximum_age,
            "completed_bytes":q.ready_bytes,"completed_frames":q.ready.len(),"completed_peak_bytes":q.peak_ready_bytes,"completed_peak_frames":q.peak_ready_frames,
            "application_oldest_age_ns":q.ready.front().map(|v|now.saturating_sub(v.arrival)).unwrap_or(0),"completed_capacity_bytes":self.shared.ready_capacity,
            "malformed_frames":q.malformed,"oversized_frames":q.oversized,"done":q.processor_done,"failure":q.failure,"backend":"rust"}).to_string()
    }
    fn request_stop(&self) {
        self.shared.stop.store(true, Ordering::Release);
        self.shared.changed.notify_all();
    }
    #[pyo3(signature=(timeout_s=2.0))]
    fn close(&self, py: Python<'_>, timeout_s: f64) -> PyResult<()> {
        if !timeout_s.is_finite() || !(0.0..=60.).contains(&timeout_s) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "invalid shutdown timeout",
            ));
        }
        self.request_stop();
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_s);
        py.detach(|| {
            {
                let mut q = self.shared.q.lock().unwrap();
                while !q.processor_done || !q.reader_done {
                    let remaining = deadline.saturating_duration_since(Instant::now());
                    if remaining.is_zero() {
                        return Err(PyTimeoutError::new_err(
                            "native pipeline shutdown timed out",
                        ));
                    }
                    q = self.shared.changed.wait_timeout(q, remaining).unwrap().0;
                }
            }
            for thread in self.threads.lock().unwrap().drain(..) {
                thread
                    .join()
                    .map_err(|_| PyOSError::new_err("native pipeline worker panicked"))?;
            }
            Ok(())
        })
    }
}
impl Drop for Pipeline {
    fn drop(&mut self) {
        self.shared.stop.store(true, Ordering::Release);
        self.shared.changed.notify_all();
    }
}
