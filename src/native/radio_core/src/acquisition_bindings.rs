//! Live gateway acquisition for Python frontends; Rust owns the radio session.
//!
//! A native thread runs the transport session: startup, journal-before-ACK
//! acceptance, capture mapping, availability and restarts. Python polls
//! accepted first-capture records for recording and display, and reads health
//! and availability snapshots. No Python code runs on the acquisition thread.
use crate::bindings::NativeRecord;
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::*,
};
use radio_transport::{
    availability::Grid,
    quality::Quality,
    session::{self, MappedBatch, RunContext, SINK_STOPPED, SessionConfig, Sink, monotonic_ns},
    wire::Record,
};
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

/// One accepted record with its run identity and host clock evidence.
struct Item {
    record: Arc<Record>,
    slot: usize,
    run: u64,
    transmitter_boot: u32,
    receiver_boot: u32,
    batch: u32,
    capture_ns: u64,
    arrival_ns: u64,
    available_ns: u64,
    clock_uncertainty_us: f64,
}

/// `(record, slot, run, transmitter_boot, receiver_boot, batch, capture_ns,
/// arrival_ns, available_ns, clock_uncertainty_us)` for one polled record.
type PolledRecord = (NativeRecord, usize, u64, u32, u32, u32, u64, u64, u64, f64);

#[derive(Default)]
struct State {
    queue: VecDeque<Item>,
    capacity: usize,
    peak: usize,
    quality: Quality,
    session: Value,
    run: Option<(String, PathBuf, Arc<Mutex<Grid>>)>,
    runs: u64,
    restarts: u64,
    failure: Option<String>,
    fatal: bool,
    finished: bool,
}

fn lock(state: &Mutex<State>) -> std::sync::MutexGuard<'_, State> {
    state.lock().unwrap_or_else(|p| p.into_inner())
}

struct QueueSink {
    state: Arc<Mutex<State>>,
}

impl Sink for QueueSink {
    fn run_started(&mut self, run: &RunContext) -> Result<(), String> {
        let mut state = lock(&self.state);
        state.quality.start_run(run.info.run);
        state.run = Some((
            run.info.run.to_string(),
            run.journal_dir.clone(),
            run.grid.clone(),
        ));
        state.runs += 1;
        state.failure = None;
        Ok(())
    }

    fn batch(&mut self, mapped: MappedBatch) -> Result<(), String> {
        let mut state = lock(&self.state);
        let now = monotonic_ns();
        let fresh = state.quality.accept(mapped.slot, &mapped.batch, now);
        if state.queue.len() + fresh.len() > state.capacity {
            return Err("native record queue overflow".into());
        }
        for index in fresh {
            state.queue.push_back(Item {
                record: mapped.batch.records[index].clone(),
                slot: mapped.slot,
                run: mapped.batch.run,
                transmitter_boot: mapped.batch.tx_boot,
                receiver_boot: mapped.batch.rx_boot,
                batch: mapped.batch.id,
                capture_ns: mapped.captures[index],
                arrival_ns: mapped.arrival_ns,
                available_ns: mapped.available_ns,
                clock_uncertainty_us: mapped.clock_uncertainty_us,
            });
        }
        state.peak = state.peak.max(state.queue.len());
        Ok(())
    }

    fn observe(&mut self, health: Value) {
        let mut state = lock(&self.state);
        match health["state"].as_str() {
            Some("restarting") => {
                state.restarts += 1;
                state.failure = health["error"].as_str().map(str::to_owned);
            }
            Some("failed") => {
                state.failure = health["error"].as_str().map(str::to_owned);
                state.fatal = true;
            }
            _ => {}
        }
        state.session = health;
    }
}

fn number<T: TryFrom<u64>>(config: &Value, key: &str, default: u64) -> PyResult<T> {
    let value = match &config[key] {
        Value::Null => default,
        value => value.as_u64().ok_or_else(|| {
            PyValueError::new_err(format!("{key} must be a non-negative integer"))
        })?,
    };
    T::try_from(value).map_err(|_| PyValueError::new_err(format!("{key} is out of range")))
}

#[pyclass]
pub struct NativeAcquisition {
    config: SessionConfig,
    state: Arc<Mutex<State>>,
    stop: Arc<AtomicBool>,
    thread: Mutex<Option<JoinHandle<()>>>,
}

#[pymethods]
impl NativeAcquisition {
    /// Validate configuration without opening hardware.
    ///
    /// Keys: `serial_path`, `radio_config` (CGCF v7 bytes), `journal_root`,
    /// `metadata`, `bin_hz`, `delivery_grace_ms`, `restart_delay_ms`,
    /// `maximum_restart_delay_ms`, `relay_ready_timeout_ms`, `record_capacity`.
    #[new]
    fn new(config_json: &str) -> PyResult<Self> {
        let value: Value =
            serde_json::from_str(config_json).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let radio_config = value["radio_config"]
            .as_array()
            .ok_or_else(|| PyValueError::new_err("radio_config must be a byte list"))?
            .iter()
            .map(|byte| byte.as_u64().and_then(|b| u8::try_from(b).ok()))
            .collect::<Option<Vec<u8>>>()
            .ok_or_else(|| PyValueError::new_err("radio_config must be a byte list"))?;
        radio_transport::startup::validate_config(&radio_config).map_err(PyValueError::new_err)?;
        let text = |key: &str| {
            value[key]
                .as_str()
                .filter(|s| !s.is_empty())
                .map(PathBuf::from)
                .ok_or_else(|| PyValueError::new_err(format!("{key} must be a non-empty path")))
        };
        let metadata = match &value["metadata"] {
            Value::Null => json!({}),
            Value::Object(_) => value["metadata"].clone(),
            _ => return Err(PyValueError::new_err("metadata must be an object")),
        };
        let capacity: usize = number(&value, "record_capacity", 65_536)?;
        if !(1..=1 << 22).contains(&capacity) {
            return Err(PyValueError::new_err("record_capacity must be 1..4194304"));
        }
        let config = SessionConfig {
            serial_path: text("serial_path")?,
            radio_config,
            journal_root: text("journal_root")?,
            metadata,
            bin_hz: number(&value, "bin_hz", 50)?,
            delivery_grace_ms: number(&value, "delivery_grace_ms", 500)?,
            restart_delay_ms: number(&value, "restart_delay_ms", 3_000)?,
            maximum_restart_delay_ms: number(&value, "maximum_restart_delay_ms", 30_000)?,
            relay_ready_timeout_ms: number(&value, "relay_ready_timeout_ms", 8_000)?,
        };
        if !(1..=100).contains(&config.bin_hz) || config.delivery_grace_ms > 1000 {
            return Err(PyValueError::new_err(
                "bin_hz must be 1..100 and grace at most 1000 ms",
            ));
        }
        Ok(Self {
            config,
            state: Arc::new(Mutex::new(State {
                capacity,
                session: json!({"state": "idle"}),
                ..State::default()
            })),
            stop: Arc::new(AtomicBool::new(false)),
            thread: Mutex::new(None),
        })
    }

    /// Start the acquisition thread once; hardware errors are reported in `health`.
    fn start(&self) -> PyResult<()> {
        let mut thread = self.thread.lock().unwrap_or_else(|p| p.into_inner());
        if thread.is_some() {
            return Err(PyRuntimeError::new_err("acquisition already started"));
        }
        let config = self.config.clone();
        let state = self.state.clone();
        let stop = self.stop.clone();
        let handle = std::thread::Builder::new()
            .name("radio-acquisition".into())
            .spawn(move || {
                let mut sink = QueueSink {
                    state: state.clone(),
                };
                let result = session::run(&config, &stop, &mut sink);
                let mut state = lock(&state);
                if let Err(error) = result
                    && error != SINK_STOPPED
                {
                    state.failure = Some(error);
                    state.fatal = true;
                }
                state.finished = true;
            })
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        *thread = Some(handle);
        Ok(())
    }

    /// Remove up to `max_records` accepted records in acceptance order.
    #[pyo3(signature=(max_records=4096))]
    fn poll(&self, max_records: usize) -> PyResult<Vec<PolledRecord>> {
        if !(1..=65_536).contains(&max_records) {
            return Err(PyValueError::new_err("max_records must be 1..65536"));
        }
        let mut state = lock(&self.state);
        let count = state.queue.len().min(max_records);
        Ok(state
            .queue
            .drain(..count)
            .map(|item| {
                (
                    NativeRecord { core: item.record },
                    item.slot,
                    item.run,
                    item.transmitter_boot,
                    item.receiver_boot,
                    item.batch,
                    item.capture_ns,
                    item.arrival_ns,
                    item.available_ns,
                    item.clock_uncertainty_us,
                )
            })
            .collect())
    }

    /// Session, run, queue and per-receiver quality state as JSON.
    fn health(&self) -> String {
        let state = lock(&self.state);
        let now = monotonic_ns();
        json!({
            "monotonic_ns": now,
            "session": state.session,
            "run": state.run.as_ref().map(|(run, _, _)| run),
            "journal_dir": state.run.as_ref().map(|(_, dir, _)| dir.display().to_string()),
            "runs": state.runs,
            "restarts": state.restarts,
            "failure": state.failure,
            "fatal": state.fatal,
            "finished": state.finished,
            "queue": {"pending": state.queue.len(), "peak": state.peak, "capacity": state.capacity},
            "receivers": state.quality.receivers.iter().map(|r| r.to_json(now)).collect::<Vec<_>>(),
            "totals": state.quality.totals(),
        })
        .to_string()
    }

    /// Recent availability bins of the current run as JSON, or `None` before a run.
    #[pyo3(signature=(seconds=10.0))]
    fn availability(&self, seconds: f64) -> PyResult<Option<String>> {
        let grid = lock(&self.state)
            .run
            .as_ref()
            .map(|(_, _, grid)| grid.clone());
        let Some(grid) = grid else {
            return Ok(None);
        };
        let snapshot = grid
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .snapshot(monotonic_ns(), seconds)
            .map_err(PyValueError::new_err)?;
        Ok(Some(snapshot.to_json().to_string()))
    }

    /// Request shutdown and wait for the run to stop and close its journal.
    #[pyo3(signature=(timeout_s=10.0))]
    fn stop(&self, py: Python<'_>, timeout_s: f64) -> PyResult<()> {
        if !(timeout_s > 0.0 && timeout_s.is_finite()) {
            return Err(PyValueError::new_err("timeout_s must be positive"));
        }
        self.stop.store(true, Ordering::Release);
        let handle = self.thread.lock().unwrap_or_else(|p| p.into_inner()).take();
        let Some(handle) = handle else {
            return Ok(());
        };
        py.detach(|| {
            let deadline = Instant::now() + Duration::from_secs_f64(timeout_s);
            while !handle.is_finished() {
                if Instant::now() >= deadline {
                    return Err(PyRuntimeError::new_err("radio acquisition did not stop"));
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            handle
                .join()
                .map_err(|_| PyRuntimeError::new_err("radio acquisition thread panicked"))
        })
    }

    #[getter]
    fn running(&self) -> bool {
        self.thread
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .as_ref()
            .is_some_and(|handle| !handle.is_finished())
    }
}

impl Drop for NativeAcquisition {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(handle) = self.thread.get_mut().ok().and_then(Option::take) {
            let _ = handle.join();
        }
    }
}
