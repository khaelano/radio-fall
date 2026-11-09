//! Native bounded recording worker; Python admission never executes disk I/O.
use pyo3::{
    exceptions::{PyBufferError, PyOSError, PyTimeoutError, PyValueError},
    prelude::*,
};
#[cfg(unix)]
use std::os::fd::AsRawFd;
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    io::Write,
    sync::{
        Arc, Condvar, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

struct Status {
    closed: AtomicBool,
    saved: AtomicBool,
    fd: i32,
}
struct Stream {
    file: File,
    bytes: Vec<u8>,
    status: Arc<Status>,
}
struct State {
    streams: HashMap<u64, Stream>,
    pending: usize,
    peak: usize,
    next: u64,
    force: u64,
    done: u64,
    closing: bool,
    stopped: bool,
    failure: Option<String>,
    writes: u64,
    flushes: u64,
}
struct Shared {
    state: Mutex<State>,
    changed: Condvar,
    capacity: usize,
    interval: Duration,
}
fn check(s: &State) -> PyResult<()> {
    if let Some(e) = &s.failure {
        Err(PyOSError::new_err(format!("recording write failed: {e}")))
    } else {
        Ok(())
    }
}
#[pyclass(frozen)]
pub struct RecordingStream {
    shared: Arc<Shared>,
    id: u64,
    status: Arc<Status>,
}
#[pymethods]
impl RecordingStream {
    #[getter]
    fn closed(&self) -> bool {
        self.status.closed.load(Ordering::Acquire)
    }
    #[getter]
    fn saved(&self) -> bool {
        self.status.saved.load(Ordering::Acquire)
    }
    fn fileno(&self) -> PyResult<i32> {
        if self.saved() {
            Err(PyValueError::new_err("recording file is closed"))
        } else {
            Ok(self.status.fd)
        }
    }
    fn write(&self, py: Python<'_>, data: &[u8]) -> PyResult<usize> {
        py.detach(|| {
            let mut s = self.shared.state.lock().unwrap();
            check(&s)?;
            if self.closed() {
                return Err(PyValueError::new_err("write to closed recording"));
            }
            if s.pending
                .checked_add(data.len())
                .is_none_or(|v| v > self.shared.capacity)
            {
                return Err(PyBufferError::new_err("recording memory buffer overflow"));
            }
            s.streams
                .get_mut(&self.id)
                .ok_or_else(|| PyValueError::new_err("recording stream is closed"))?
                .bytes
                .extend_from_slice(data);
            s.pending += data.len();
            s.peak = s.peak.max(s.pending);
            Ok(data.len())
        })
    }
    fn flush(&self) -> PyResult<()> {
        check(&self.shared.state.lock().unwrap())
    }
    fn close(&self) {
        self.status.closed.store(true, Ordering::Release);
        self.shared.changed.notify_all();
    }
}
impl Drop for RecordingStream {
    fn drop(&mut self) {
        self.status.closed.store(true, Ordering::Release);
        self.shared.changed.notify_all();
    }
}

#[pyclass]
pub struct RecordingWriter {
    shared: Arc<Shared>,
    thread: Mutex<Option<thread::JoinHandle<()>>>,
}
#[pymethods]
impl RecordingWriter {
    #[new]
    #[pyo3(signature=(interval_s=5.0,capacity_bytes=33554432))]
    fn new(interval_s: f64, capacity_bytes: usize) -> PyResult<Self> {
        if !interval_s.is_finite() || interval_s <= 0. || interval_s > 3600. || capacity_bytes == 0
        {
            return Err(PyValueError::new_err("invalid recording buffer limits"));
        }
        let state = State {
            streams: HashMap::new(),
            pending: 0,
            peak: 0,
            next: 0,
            force: 0,
            done: 0,
            closing: false,
            stopped: false,
            failure: None,
            writes: 0,
            flushes: 0,
        };
        let shared = Arc::new(Shared {
            state: Mutex::new(state),
            changed: Condvar::new(),
            capacity: capacity_bytes,
            interval: Duration::from_secs_f64(interval_s),
        });
        let worker = shared.clone();
        let handle = thread::Builder::new()
            .name("csi-native-recording".into())
            .spawn(move || run(worker))
            .map_err(|e| PyOSError::new_err(e.to_string()))?;
        Ok(Self {
            shared,
            thread: Mutex::new(Some(handle)),
        })
    }
    #[getter]
    fn pending_bytes(&self) -> usize {
        self.shared.state.lock().unwrap().pending
    }
    #[getter]
    fn failure(&self) -> Option<String> {
        self.shared.state.lock().unwrap().failure.clone()
    }
    fn check(&self) -> PyResult<()> {
        check(&self.shared.state.lock().unwrap())
    }
    fn open(&self, py: Python<'_>, path: String, mode: String) -> PyResult<RecordingStream> {
        py.detach(|| {
            {
                let s = self.shared.state.lock().unwrap();
                check(&s)?;
                if s.closing {
                    return Err(PyValueError::new_err("recording writer is closed"));
                }
            }
            let mut o = OpenOptions::new();
            o.write(true);
            match mode.trim_end_matches('b') {
                "x" => {
                    o.create_new(true);
                }
                "w" => {
                    o.create(true).truncate(true);
                }
                "a" => {
                    o.create(true).append(true);
                }
                _ => return Err(PyValueError::new_err("unsupported recording open mode")),
            };
            let file = o
                .open(path)
                .map_err(|e| PyOSError::new_err(e.to_string()))?;
            #[cfg(unix)]
            let fd = file.as_raw_fd();
            #[cfg(not(unix))]
            let fd = -1;
            let status = Arc::new(Status {
                closed: AtomicBool::new(false),
                saved: AtomicBool::new(false),
                fd,
            });
            let mut s = self.shared.state.lock().unwrap();
            check(&s)?;
            if s.closing {
                return Err(PyValueError::new_err("recording writer is closed"));
            }
            let id = s.next;
            s.next += 1;
            s.streams.insert(
                id,
                Stream {
                    file,
                    bytes: Vec::new(),
                    status: status.clone(),
                },
            );
            Ok(RecordingStream {
                shared: self.shared.clone(),
                id,
                status,
            })
        })
    }
    #[pyo3(signature=(timeout=10.0))]
    fn flush(&self, py: Python<'_>, timeout: f64) -> PyResult<()> {
        if !timeout.is_finite() || !(0.0..=3600.).contains(&timeout) {
            return Err(PyValueError::new_err("invalid recording flush timeout"));
        }
        let deadline = Instant::now() + Duration::from_secs_f64(timeout);
        py.detach(|| {
            let mut s = self.shared.state.lock().unwrap();
            check(&s)?;
            if s.stopped {
                return Ok(());
            }
            s.force += 1;
            let target = s.force;
            self.shared.changed.notify_all();
            while s.done < target && !s.stopped && s.failure.is_none() {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    return Err(PyTimeoutError::new_err("recording writer flush timed out"));
                }
                s = self.shared.changed.wait_timeout(s, remaining).unwrap().0;
            }
            check(&s)
        })
    }
    #[pyo3(signature=(timeout=10.0))]
    fn close(&self, py: Python<'_>, timeout: f64) -> PyResult<()> {
        if !timeout.is_finite() || !(0.0..=3600.).contains(&timeout) {
            return Err(PyValueError::new_err("invalid recording close timeout"));
        }
        let deadline = Instant::now() + Duration::from_secs_f64(timeout);
        py.detach(|| {
            let mut s = self.shared.state.lock().unwrap();
            s.closing = true;
            self.shared.changed.notify_all();
            while !s.stopped {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    return Err(PyTimeoutError::new_err(
                        "recording writer shutdown timed out",
                    ));
                }
                s = self.shared.changed.wait_timeout(s, remaining).unwrap().0;
            }
            let error = s.failure.clone();
            drop(s);
            if let Some(h) = self.thread.lock().unwrap().take() {
                h.join()
                    .map_err(|_| PyOSError::new_err("recording thread panicked"))?;
            }
            if let Some(e) = error {
                Err(PyOSError::new_err(format!("recording write failed: {e}")))
            } else {
                Ok(())
            }
        })
    }
    fn stats_json(&self) -> String {
        let s = self.shared.state.lock().unwrap();
        serde_json::json!({"pending_bytes":s.pending,"peak_bytes":s.peak,"capacity_bytes":self.shared.capacity,"open_streams":s.streams.len(),"write_calls":s.writes,"flush_cycles":s.flushes,"failure":s.failure,"backend":"rust"}).to_string()
    }
}
impl Drop for RecordingWriter {
    fn drop(&mut self) {
        let mut s = self.shared.state.lock().unwrap();
        s.closing = true;
        self.shared.changed.notify_all();
    }
}

fn run(shared: Arc<Shared>) {
    let mut deadline = Instant::now() + shared.interval;
    loop {
        let (mut jobs, target, all) = {
            let mut s = shared.state.lock().unwrap();
            while !s.closing
                && s.force <= s.done
                && !s
                    .streams
                    .values()
                    .any(|v| v.status.closed.load(Ordering::Acquire))
                && Instant::now() < deadline
            {
                s = shared
                    .changed
                    .wait_timeout(s, deadline.saturating_duration_since(Instant::now()))
                    .unwrap()
                    .0;
            }
            let all = s.closing || s.force > s.done || Instant::now() >= deadline;
            let ids: Vec<u64> = s
                .streams
                .iter()
                .filter(|(_, v)| all || v.status.closed.load(Ordering::Acquire))
                .map(|(id, _)| *id)
                .collect();
            let mut jobs = Vec::new();
            for id in ids {
                // File ownership moves out of the admission mutex for I/O. An
                // empty placeholder keeps writes to the same live stream safe.
                let v = s.streams.get_mut(&id).unwrap();
                let data = std::mem::take(&mut v.bytes);
                let file = match v.file.try_clone() {
                    Ok(f) => f,
                    Err(e) => {
                        s.failure = Some(e.to_string());
                        s.stopped = true;
                        s.streams.clear();
                        shared.changed.notify_all();
                        return;
                    }
                };
                jobs.push((id, file, data, v.status.clone(), s.closing));
            }
            if all {
                deadline = Instant::now() + shared.interval;
                s.flushes += 1;
            }
            (jobs, s.force, all)
        };
        for (id, mut file, data, status, closing) in jobs.drain(..) {
            let result = (|| {
                if !data.is_empty() {
                    file.write_all(&data)?;
                }
                file.flush()
            })(); // No fsync guarantee.
            let mut s = shared.state.lock().unwrap();
            if let Err(e) = result {
                s.failure = Some(e.to_string());
                s.stopped = true;
                s.streams.clear();
                shared.changed.notify_all();
                return;
            }
            if !data.is_empty() {
                s.writes += 1;
            }
            s.pending -= data.len();
            if closing || status.closed.load(Ordering::Acquire) {
                // If close raced the I/O, newly admitted bytes still require a
                // final drain; do not mark saved until the entire stream ends.
                if s.streams.get(&id).is_some_and(|v| v.bytes.is_empty()) {
                    s.streams.remove(&id);
                    drop(file);
                    status.closed.store(true, Ordering::Release);
                    status.saved.store(true, Ordering::Release);
                }
            }
        }
        let mut s = shared.state.lock().unwrap();
        if all {
            s.done = target;
        }
        shared.changed.notify_all();
        if s.closing && s.streams.is_empty() {
            s.stopped = true;
            shared.changed.notify_all();
            return;
        }
    }
}
