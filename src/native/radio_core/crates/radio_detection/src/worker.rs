//! One native inference submission thread with bounded latest-result storage.
use crate::{
    runtime::Runtime,
    scheduler::{Job, Outcome, Scheduler},
};
use std::{
    collections::BTreeMap,
    sync::{Arc, Condvar, Mutex},
    thread::{self, JoinHandle},
    time::Instant,
};

/// Completed inference, including the immutable capture window and publication clock.
#[derive(Debug)]
pub struct ResultRow {
    pub job: Job,
    pub outcome: Outcome,
    pub published_ns: u64,
    pub inference_ns: u64,
    pub started_ns: u64,
    pub queue_wait_ns: u64,
    pub provider: &'static str,
    pub error: Option<String>,
}

/// Bounded submission health, available without consuming predictions.
#[derive(Debug, Clone)]
pub struct Health {
    pub pending_jobs: usize,
    pub active_model: Option<String>,
    pub latest_results: usize,
    pub replacements: u64,
    pub completed_calls: u64,
    pub runtime_errors: u64,
    pub generation: u64,
    pub stopped: bool,
}

struct State {
    scheduler: Scheduler,
    rows: BTreeMap<String, ResultRow>,
    stopped: bool,
    completed_calls: u64,
    runtime_errors: u64,
}

/// Bounded native worker. Frontend stalls cannot accumulate results.
pub struct Worker {
    state: Arc<(Mutex<State>, Condvar)>,
    thread: Option<JoinHandle<()>>,
    maximum_age_ns: u64,
}

impl Worker {
    /// Start using an already warmed runtime and a stable model-to-session mapping.
    /// The clock must share the capture timestamp domain and never move backward.
    pub fn start(
        mut runtime: Runtime,
        sessions: BTreeMap<String, usize>,
        minimum_coverage: f32,
        maximum_age_ns: u64,
        clock: impl Fn() -> u64 + Send + 'static,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        runtime.validate_sessions(&sessions)?;
        let provider = runtime.provider_name();
        let scheduler = Scheduler::new(
            sessions.keys().cloned().collect(),
            minimum_coverage,
            maximum_age_ns,
        )?;
        let state = Arc::new((
            Mutex::new(State {
                scheduler,
                rows: BTreeMap::new(),
                stopped: false,
                completed_calls: 0,
                runtime_errors: 0,
            }),
            Condvar::new(),
        ));
        let shared = state.clone();
        let thread = thread::Builder::new()
            .name("detection-inference".into())
            .spawn(move || {
                loop {
                    let job = {
                        let (lock, changed) = &*shared;
                        let mut state = lock.lock().unwrap();
                        loop {
                            if state.stopped {
                                return;
                            }
                            if let Some(job) = state.scheduler.take_next() {
                                break job;
                            }
                            state = changed.wait(state).unwrap();
                        }
                    };
                    let started_ns = clock();
                    let start = Instant::now();
                    let eligible = started_ns >= job.finalized_ns
                        && started_ns <= job.deadline_ns
                        && started_ns.saturating_sub(job.end_ns) <= maximum_age_ns
                        && job.coverage.iter().all(|&c| c >= minimum_coverage);
                    let logit = if eligible {
                        runtime
                            .infer_view(sessions[&job.model_id], job.shape, &job.input)
                            .map_err(|e| e.to_string())
                    } else {
                        Err("input unavailable or stale before inference".into())
                    };
                    let inference_ns = if eligible {
                        start.elapsed().as_nanos().min(u64::MAX as u128) as u64
                    } else {
                        0
                    };
                    let error = if eligible {
                        logit.as_ref().err().cloned()
                    } else {
                        None
                    };
                    let published_ns = clock();
                    let mut state = shared.0.lock().unwrap();
                    if eligible {
                        state.completed_calls = state.completed_calls.saturating_add(1);
                    }
                    if error.is_some() {
                        state.runtime_errors = state.runtime_errors.saturating_add(1);
                    }
                    if let Ok((job, outcome)) = state.scheduler.complete(published_ns, logit)
                        && !state.stopped
                    {
                        let queue_wait_ns = started_ns.saturating_sub(job.finalized_ns);
                        state.rows.insert(
                            job.model_id.clone(),
                            ResultRow {
                                job,
                                outcome,
                                published_ns,
                                inference_ns,
                                started_ns,
                                queue_wait_ns,
                                provider,
                                error,
                            },
                        );
                    }
                }
            })?;
        Ok(Self {
            state,
            thread: Some(thread),
            maximum_age_ns,
        })
    }

    /// Submit without waiting for inference or involving Python callbacks.
    pub fn submit(&self, job: Job) -> Result<(), String> {
        let mut state = self.state.0.lock().map_err(|_| "worker poisoned")?;
        if state.stopped {
            return Err("worker stopped".into());
        }
        state.scheduler.submit(job)?;
        self.state.1.notify_one();
        Ok(())
    }

    /// Clear published and pending results and invalidate an in-flight call.
    pub fn reset(&self) -> Result<u64, String> {
        let mut state = self.state.0.lock().map_err(|_| "worker poisoned")?;
        state.rows.clear();
        state.scheduler.reset()
    }

    /// Drain at most one latest row per selected model.
    pub fn poll(&self, now_ns: u64) -> Vec<ResultRow> {
        std::mem::take(&mut self.state.0.lock().unwrap().rows)
            .into_values()
            .map(|mut row| {
                if now_ns < row.published_ns
                    || now_ns > row.job.deadline_ns
                    || now_ns.saturating_sub(row.job.end_ns) > self.maximum_age_ns
                {
                    row.outcome = Outcome::Unknown("stale");
                }
                row
            })
            .collect()
    }

    /// Report pending replacements without draining results.
    pub fn replacements(&self) -> u64 {
        self.state.0.lock().unwrap().scheduler.replacements
    }

    pub fn health(&self) -> Health {
        let state = self.state.0.lock().unwrap();
        Health {
            pending_jobs: state.scheduler.pending_count(),
            active_model: state.scheduler.active_model().map(str::to_owned),
            latest_results: state.rows.len(),
            replacements: state.scheduler.replacements,
            completed_calls: state.completed_calls,
            runtime_errors: state.runtime_errors,
            generation: state.scheduler.generation(),
            stopped: state.stopped,
        }
    }

    /// Stop scheduling and join the active native call before releasing sessions.
    pub fn stop(&mut self) {
        {
            self.state.0.lock().unwrap().stopped = true;
        }
        self.state.1.notify_all();
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::Backend;
    #[test]
    #[ignore = "requires local ONNX Runtime and DVC models"]
    fn resident_default_models_publish_through_native_worker() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../..");
        let core = root
            .join(".venv/lib64/python3.12/site-packages/onnxruntime/capi/libonnxruntime.so.1.31.1");
        let gpu = std::env::var("RADIO_WORKER_GPU").as_deref() == Ok("1");
        let plugin = &root.join(
            ".venv/lib64/python3.12/site-packages/onnxruntime_ep_webgpu/libonnxruntime_providers_webgpu.so",
        );
        let backend = if gpu {
            Backend::AmdVulkan {
                plugin,
                device_id: None,
            }
        } else {
            Backend::CpuDiagnostic
        };
        let mut runtime = Runtime::new(&core, backend).unwrap();
        let mut diagnostic = runtime.cpu_diagnostic_peer();
        let mut references = BTreeMap::new();
        let mut sessions = BTreeMap::new();
        for family in ["cnn", "lstm", "gru"] {
            let model = root.join(format!("artifacts/model/{family}/{family}-4s.onnx"));
            let profile =
                std::env::temp_dir().join(format!("radio-worker-{}-{family}", std::process::id()));
            let index = runtime.load(&model, &profile).unwrap();
            runtime
                .infer(index, [480, 1964], vec![0.0; 480 * 1964])
                .unwrap();
            let cpu_index = diagnostic.load_unprofiled(&model).unwrap();
            references.insert(
                family.to_owned(),
                diagnostic
                    .infer(cpu_index, [480, 1964], vec![0.0; 480 * 1964])
                    .unwrap(),
            );
            sessions.insert(family.to_owned(), index);
        }
        let start = Instant::now();
        let mut worker = Worker::start(runtime, sessions, 0.7, 10_000_000_000, move || {
            100 + start.elapsed().as_nanos() as u64
        })
        .unwrap();
        for model in ["cnn", "lstm", "gru"] {
            worker
                .submit(Job {
                    model_id: model.into(),
                    generation: 0,
                    start_ns: 0,
                    end_ns: 100,
                    finalized_ns: 100,
                    deadline_ns: 10_000_000_000,
                    coverage: [1.0; 4],
                    frames: 480,
                    shape: [480, 1964],
                    input: vec![0.0; 480 * 1964].into(),
                    front_end_ns: 0,
                    front_end_updates: None,
                })
                .unwrap();
        }
        let mut rows = Vec::new();
        while rows.len() < 3 && start.elapsed().as_secs() < 10 {
            rows.extend(worker.poll(100 + start.elapsed().as_nanos() as u64));
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert_eq!(rows.len(), 3);
        assert!(
            rows.iter()
                .all(|r| matches!(r.outcome, Outcome::Score { .. }))
        );
        assert_eq!(worker.replacements(), 0);
        assert_eq!(worker.health().completed_calls, 3);
        for row in &rows {
            assert_eq!(
                row.provider,
                if gpu {
                    "WebGPU/Vulkan"
                } else {
                    "CPU diagnostic"
                }
            );
            assert!(row.error.is_none());
            if let Outcome::Score { logit, .. } = row.outcome {
                assert!(
                    (logit - references[&row.job.model_id]).abs()
                        <= 1e-4 + 1e-4 * references[&row.job.model_id].abs()
                );
                println!(
                    "{} provider={} inference_ms={:.3} queue_ms={:.3} logit={logit}",
                    row.job.model_id,
                    row.provider,
                    row.inference_ns as f64 / 1e6,
                    row.queue_wait_ns as f64 / 1e6
                );
            }
        }
        worker
            .submit(Job {
                model_id: "cnn".into(),
                generation: 0,
                start_ns: 100,
                end_ns: 200,
                finalized_ns: 200,
                deadline_ns: 10_000_000_000,
                coverage: [0.1; 4],
                frames: 480,
                shape: [480, 1964],
                input: vec![0.0; 480 * 1964].into(),
                front_end_ns: 0,
                front_end_updates: None,
            })
            .unwrap();
        let mut rejected = None;
        while rejected.is_none() && start.elapsed().as_secs() < 10 {
            rejected = worker.poll(100 + start.elapsed().as_nanos() as u64).pop();
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        let rejected = rejected.unwrap();
        assert_eq!(rejected.outcome, Outcome::Unknown("coverage"));
        assert_eq!(rejected.inference_ns, 0);
        assert_eq!(worker.health().completed_calls, 3);
        worker.stop();
    }
}
