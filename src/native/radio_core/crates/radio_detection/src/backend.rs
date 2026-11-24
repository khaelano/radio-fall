//! Native live detection coordinator.
//!
//! A feed thread delivers accepted CSI batches (live gateway or paced replay).
//! The coordinator aligns receivers by sequence round, builds model inputs on
//! a fixed hop, and submits them to one resident inference worker. Results go
//! to `predictions.jsonl` and to the latest-result table read by the frontend.
use crate::{
    bundle,
    feed::{self, Clock, Feed, MappedBatch, RunInfo},
    preprocessing::Preprocessing,
    records::{self, Sequence},
    runtime::{Backend as RuntimeBackend, Runtime},
    scheduler::{Job, Outcome},
    sequence::Normalizer,
    stream::{History, WindowTiming},
    window::{self, SegmentEdges},
    worker::{ResultRow, Worker},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{BufWriter, Write},
    path::PathBuf,
    sync::{
        Arc, Mutex, MutexGuard,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, Receiver},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const NS_PER_SECOND: u64 = 1_000_000_000;
const RATE_HZ: u64 = 120;
/// Rounds kept below a segment's anchor so receivers that start slightly
/// earlier than the first observed record still map to nonnegative rounds.
const ROUND_MARGIN: i64 = 12_000;

/// Paced replay of recorded native captures instead of the USB gateway.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ReplayConfig {
    /// Capture directories containing `radio.cgcf` and `transport/gateway/<run>/`.
    pub captures: Vec<PathBuf>,
    /// Playback speed relative to real time.
    pub speed: f64,
    /// Restart from the first capture after the last one.
    pub repeat: bool,
}
impl Default for ReplayConfig {
    fn default() -> Self {
        Self {
            captures: Vec::new(),
            speed: 1.0,
            repeat: false,
        }
    }
}

/// Configuration supplied by the frontend; it is the only input crossing PyO3.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct BackendConfig {
    /// Gateway serial device; unused in replay mode.
    pub serial_path: String,
    /// Encoded CGCF v7 radio configuration; unused in replay mode.
    pub radio_config: Vec<u8>,
    pub replay: Option<ReplayConfig>,
    pub model_root: PathBuf,
    /// Native ONNX Runtime shared library.
    pub core_library: PathBuf,
    /// Native WebGPU execution-provider plugin, required for `webgpu`.
    pub webgpu_plugin: Option<PathBuf>,
    /// `webgpu` or `cpu`.
    pub backend: String,
    /// PCI device ID of the AMD GPU; `None` selects the only one present.
    pub adapter_id: Option<u32>,
    pub models: Vec<String>,
    /// Fresh directory for logs and journals; must not exist yet.
    pub output_dir: PathBuf,
    pub hop_ms: u64,
    pub delivery_grace_ms: u64,
    pub minimum_coverage: f32,
    pub packet_capacity: usize,
    /// Delay before a failed live radio run is restarted.
    pub restart_delay_ms: u64,
    /// Write every submitted model input to `inputs.f32` and `inputs.jsonl`.
    pub save_inputs: bool,
    /// Keep the latest raw and model-input window per model for display.
    pub preview: bool,
}
impl Default for BackendConfig {
    fn default() -> Self {
        Self {
            serial_path: String::new(),
            radio_config: Vec::new(),
            replay: None,
            model_root: "artifacts/model".into(),
            core_library: PathBuf::new(),
            webgpu_plugin: None,
            backend: "webgpu".into(),
            adapter_id: None,
            models: vec!["tonepool_tcn-4s".into()],
            output_dir: PathBuf::new(),
            hop_ms: 250,
            delivery_grace_ms: 900,
            minimum_coverage: 0.7,
            packet_capacity: 2048,
            restart_delay_ms: 2000,
            save_inputs: false,
            preview: false,
        }
    }
}
impl BackendConfig {
    fn validate(&self) -> Result<(), String> {
        match &self.replay {
            Some(replay) => {
                if replay.captures.is_empty()
                    || !replay.speed.is_finite()
                    || replay.speed <= 0.0
                    || replay.speed > 100.0
                {
                    return Err("replay needs captures and a speed in (0, 100]".into());
                }
            }
            None => {
                if self.serial_path.is_empty() {
                    return Err("live mode requires a gateway serial path".into());
                }
                feed::require_sequence_rate(&RunInfo::from_config(&self.radio_config)?)?;
            }
        }
        if self.core_library.as_os_str().is_empty()
            || self.output_dir.as_os_str().is_empty()
            || self.models.is_empty()
            || self.models.len() > bundle::MAX_MODELS
            || self.models.iter().collect::<BTreeSet<_>>().len() != self.models.len()
            || !(0.0..=1.0).contains(&self.minimum_coverage)
            || self.hop_ms == 0
            || self.hop_ms > 60_000
            || self.delivery_grace_ms > 60_000
            || self.packet_capacity == 0
            || self.packet_capacity > 16384
            || self.restart_delay_ms > 600_000
            || !["cpu", "webgpu"].contains(&self.backend.as_str())
            || (self.backend == "webgpu" && self.webgpu_plugin.is_none())
        {
            return Err("invalid native detector configuration".into());
        }
        Ok(())
    }
    fn provider(&self) -> &'static str {
        if self.backend == "webgpu" {
            "WebGPU/Vulkan"
        } else {
            "CPU diagnostic"
        }
    }
}

/// Latest window submitted for one model, kept for display only.
#[derive(Clone)]
pub struct Preview {
    pub model_id: String,
    pub generation: u64,
    pub start_ns: u64,
    pub end_ns: u64,
    pub frames: usize,
    pub coverage: [f32; 4],
    /// Unfiltered physical magnitudes, `[frames, 4 receivers x 245 tones]`; NaN is missing.
    pub raw: Arc<[f32]>,
    /// The exact model input, `[frames, 980 signals + 980 validity + 4 presence]`.
    pub input: Arc<[f32]>,
}

/// One received raw CSI row for the scrolling display.
#[derive(Clone)]
pub struct StreamRow {
    /// Increasing position in the stream; clients poll for rows after it.
    pub seq: u64,
    pub generation: u64,
    /// Sequence round within the segment (120 per second).
    pub round: u64,
    pub receiver: u8,
    /// Unfiltered physical magnitudes in tone order; NaN is masked.
    pub magnitude: [f32; 245],
}

/// Raw rows retained for display: about ten seconds at four receivers.
const STREAM_CAPACITY: usize = 6000;

/// State read by the frontend: health plus the latest unread result per model.
pub struct Shared {
    pub(crate) health: Value,
    rows: BTreeMap<String, Value>,
    previews: BTreeMap<String, Preview>,
    stream: std::collections::VecDeque<StreamRow>,
    next_stream_seq: u64,
}

fn lock(shared: &Arc<Mutex<Shared>>) -> MutexGuard<'_, Shared> {
    shared.lock().unwrap_or_else(|p| p.into_inner())
}

/// Native detector lifecycle; packets and tensors never leave Rust.
pub struct Backend {
    config: BackendConfig,
    shared: Arc<Mutex<Shared>>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    clock: Clock,
}
impl Backend {
    pub fn new(config: BackendConfig) -> Result<Self, String> {
        config.validate()?;
        let health = json!({
            "ready": false, "running": false, "state": "stopped", "error": null,
            "source": if config.replay.is_some() { "replay" } else { "gateway" },
            "models": config.models, "provider": config.provider(),
            "records": [0, 0, 0, 0], "generation": 0, "segments": 0,
            "queue_replacements": 0, "last_capture_ns": null,
        });
        Ok(Self {
            config,
            shared: Arc::new(Mutex::new(Shared {
                health,
                rows: BTreeMap::new(),
                previews: BTreeMap::new(),
                stream: std::collections::VecDeque::with_capacity(STREAM_CAPACITY),
                next_stream_seq: 1,
            })),
            stop: Arc::new(AtomicBool::new(false)),
            thread: None,
            clock: Clock::Host,
        })
    }

    /// Begin warmup and acquisition asynchronously; readiness is reported by health.
    pub fn start(&mut self) -> Result<(), String> {
        if self.thread.is_some() {
            return Err("native detector already started".into());
        }
        self.stop.store(false, Ordering::Release);
        self.clock = match &self.config.replay {
            Some(replay) => Clock::Replay {
                origin_ns: feed::monotonic_ns(),
                started: Instant::now(),
                speed: replay.speed,
            },
            None => Clock::Host,
        };
        {
            let mut state = lock(&self.shared);
            state.health["running"] = true.into();
            state.health["state"] = "warming_models".into();
            state.health["error"] = Value::Null;
        }
        let config = self.config.clone();
        let shared = self.shared.clone();
        let stop = self.stop.clone();
        let clock = self.clock.clone();
        let thread = thread::Builder::new()
            .name("live-detection".into())
            .spawn(move || {
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    run_backend(&config, &shared, &stop, clock)
                }));
                let outcome = result.unwrap_or_else(|_| Err("native detector thread panicked".into()));
                stop.store(true, Ordering::Release);
                let mut state = lock(&shared);
                state.health["ready"] = false.into();
                state.health["running"] = false.into();
                match outcome {
                    Ok(finished) => state.health["state"] = finished.into(),
                    Err(error) => {
                        state.health["state"] = "error".into();
                        state.health["error"] = error.clone().into();
                        for model in &config.models {
                            state.rows.insert(
                                model.clone(),
                                json!({"model_id": model, "state": "unknown", "score": null,
                                       "logit": null, "error": error, "provider": config.provider()}),
                            );
                        }
                    }
                }
            })
            .map_err(|e| e.to_string())?;
        self.thread = Some(thread);
        Ok(())
    }

    /// Drain at most `max_results` latest unread results, one per model.
    pub fn poll(&self, max_results: usize) -> Value {
        let mut shared = lock(&self.shared);
        let keys: Vec<_> = shared
            .rows
            .keys()
            .take(max_results.min(64))
            .cloned()
            .collect();
        Value::Array(
            keys.into_iter()
                .filter_map(|key| shared.rows.remove(&key))
                .collect(),
        )
    }

    /// Latest preview for `model_id` whose window ends after `after_end_ns`.
    pub fn preview(&self, model_id: &str, after_end_ns: u64) -> Option<Preview> {
        lock(&self.shared)
            .previews
            .get(model_id)
            .filter(|preview| preview.end_ns > after_end_ns)
            .cloned()
    }

    /// Raw rows received after `after_seq`, oldest first, at most `limit`.
    pub fn stream(&self, after_seq: u64, limit: usize) -> Vec<StreamRow> {
        let shared = lock(&self.shared);
        let start = shared.stream.partition_point(|row| row.seq <= after_seq);
        shared.stream.range(start..).take(limit).cloned().collect()
    }

    /// Health snapshot; `clock_ns` shares the result timestamps' clock domain.
    pub fn health(&self) -> Value {
        let mut health = lock(&self.shared).health.clone();
        health["clock_ns"] = self.clock.now().into();
        health
    }

    pub fn stop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
        let mut state = lock(&self.shared);
        state.health["ready"] = false.into();
        state.health["running"] = false.into();
        if state.health["state"] != "error" && state.health["state"] != "finished" {
            state.health["state"] = "stopped".into();
        }
    }
}
impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

/// Joins the feed thread when the coordinator exits for any reason.
struct FeedGuard {
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}
impl Drop for FeedGuard {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

struct Model {
    export: bundle::Export,
    normalizer: Normalizer,
    /// Capture time at which the next window ends.
    next_end_ns: Option<u64>,
}

type LoadedModels = (Runtime, BTreeMap<String, usize>, Vec<Model>);

/// Load, warm and check every selected model before the radio starts.
fn load_models(
    config: &BackendConfig,
    shared: &Arc<Mutex<Shared>>,
    stop: &AtomicBool,
) -> Result<Option<LoadedModels>, String> {
    let mut available = BTreeMap::new();
    for family in &bundle::FAMILIES {
        let directory = config.model_root.join(family.name);
        if !directory.is_dir() {
            continue;
        }
        for export in bundle::inspect_exports(&directory).map_err(|e| e.to_string())? {
            available.insert(export.id.clone(), export);
        }
    }
    let gpu = config.backend == "webgpu";
    let backend = match &config.webgpu_plugin {
        Some(plugin) if gpu => RuntimeBackend::AmdVulkan {
            plugin,
            device_id: config.adapter_id,
        },
        _ => RuntimeBackend::CpuDiagnostic,
    };
    let mut runtime = Runtime::new(&config.core_library, backend).map_err(|e| e.to_string())?;
    let mut sessions = BTreeMap::new();
    let mut models = Vec::new();
    for id in &config.models {
        if stop.load(Ordering::Acquire) {
            return Ok(None);
        }
        let export = available
            .remove(id)
            .ok_or_else(|| format!("model is not one of the current exports: {id}"))?;
        let normalizer = Normalizer::load(&export.normalizer).map_err(|e| e.to_string())?;
        let session = if gpu {
            runtime.load(
                &export.model,
                &config.output_dir.join(format!("operator-profile-{id}")),
            )
        } else {
            runtime.load_unprofiled(&export.model)
        }
        .map_err(|e| e.to_string())?;
        for _ in 0..3 {
            runtime
                .infer(session, export.frames, vec![0.0; export.frames * 1964])
                .map_err(|e| e.to_string())?;
        }
        if gpu {
            // Refuse a GPU session whose main operator silently ran on the CPU.
            let profile = runtime.finish_profile(session).map_err(|e| e.to_string())?;
            let trace = serde_json::from_reader(File::open(profile).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            let allowed = [
                "Shape",
                "Slice",
                "Concat",
                "Gather",
                "Mul",
                "Reshape",
                "Expand",
                "Transpose",
            ]
            .map(str::to_owned)
            .into();
            let placement = crate::audit_placement(&trace, &allowed)?;
            let main = bundle::family_of(id)
                .ok_or_else(|| format!("unknown model family: {id}"))?
                .main_operator;
            if !placement.webgpu_ops.contains(main) {
                return Err(format!("{id}: {main} did not run on WebGPU"));
            }
        }
        sessions.insert(id.clone(), session);
        models.push(Model {
            export,
            normalizer,
            next_end_ns: None,
        });
        lock(shared).health["warmed_models"] = models.len().into();
    }
    Ok(Some((runtime, sessions, models)))
}

/// Returns the final state name (`stopped` or `finished`) or an error.
fn run_backend(
    config: &BackendConfig,
    shared: &Arc<Mutex<Shared>>,
    stop: &Arc<AtomicBool>,
    clock: Clock,
) -> Result<&'static str, String> {
    fs::create_dir(&config.output_dir)
        .map_err(|e| format!("new output directory required: {e}"))?;
    if config.replay.is_none() {
        fs::write(config.output_dir.join("radio.cgcf"), &config.radio_config)
            .map_err(|e| e.to_string())?;
    }
    fs::write(
        config.output_dir.join("detector.json"),
        serde_json::to_vec_pretty(config).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let recordings = match &config.replay {
        Some(replay) => replay
            .captures
            .iter()
            .map(|capture| {
                feed::load_recording(capture).map_err(|e| format!("{}: {e}", capture.display()))
            })
            .collect::<Result<Vec<_>, _>>()?,
        None => Vec::new(),
    };
    let Some((runtime, sessions, models)) = load_models(config, shared, stop)? else {
        return Ok("stopped");
    };
    let mut coordinator =
        Coordinator::new(config, shared.clone(), runtime, sessions, models, &clock)?;
    let (sender, receiver) = mpsc::sync_channel(config.packet_capacity);
    let feed_config = config.clone();
    let feed_shared = shared.clone();
    let feed_stop = stop.clone();
    let feed_clock = clock.clone();
    let repeat = config.replay.as_ref().is_some_and(|r| r.repeat);
    // Live capture times arrive in real time; replay publishes its progress.
    let horizon = Arc::new(AtomicU64::new(if recordings.is_empty() {
        u64::MAX
    } else {
        0
    }));
    let feed_horizon = horizon.clone();
    lock(shared).health["state"] = if recordings.is_empty() {
        "starting_radio"
    } else {
        "replaying"
    }
    .into();
    let feed_thread = thread::Builder::new()
        .name("detection-feed".into())
        .spawn(move || {
            let result = if recordings.is_empty() {
                feed::live(&feed_config, &feed_shared, &feed_stop, &sender)
            } else {
                feed::replay(
                    &recordings,
                    repeat,
                    &feed_clock,
                    &feed_horizon,
                    &feed_shared,
                    &feed_stop,
                    &sender,
                )
            };
            if let Err(error) = result {
                lock(&feed_shared).health["feed_error"] = error.into();
            }
        })
        .map_err(|e| e.to_string())?;
    let _feed = FeedGuard {
        stop: stop.clone(),
        thread: Some(feed_thread),
    };
    let finished = coordinator.run(&receiver, stop, &clock, &horizon);
    coordinator.finish()?;
    finished
}

/// Samples of one contiguous segment: one run without a long all-receiver gap.
struct Segment {
    run: RunInfo,
    /// Shared sequence anchor and per-receiver unwrapping, set by the first record.
    sequences: Option<(u32, [Sequence; 4])>,
    /// Capture time of round zero on the nominal 120 Hz grid.
    origin_ns: Option<u64>,
    last_capture_ns: Option<u64>,
}

struct Coordinator {
    config: BackendConfig,
    shared: Arc<Mutex<Shared>>,
    worker: Worker,
    models: Vec<Model>,
    contract: Preprocessing,
    history: History,
    segment: Option<Segment>,
    generation: u64,
    segments: u64,
    counts: [u64; 4],
    dropped_records: u64,
    context_frames: u64,
    hop_ns: u64,
    grace_ns: u64,
    log: BufWriter<File>,
    inputs: Option<(BufWriter<File>, BufWriter<File>)>,
    last_capture_ns: Option<u64>,
}

impl Coordinator {
    fn new(
        config: &BackendConfig,
        shared: Arc<Mutex<Shared>>,
        runtime: Runtime,
        sessions: BTreeMap<String, usize>,
        models: Vec<Model>,
        clock: &Clock,
    ) -> Result<Self, String> {
        let contract = Preprocessing::operational();
        contract.validate()?;
        let hop_ns = config.hop_ms * 1_000_000;
        let grace_ns = config.delivery_grace_ms * 1_000_000;
        let maximum_age = contract.future_context_ns + grace_ns + 2 * hop_ns;
        let worker_clock = clock.clone();
        let worker = Worker::start(
            runtime,
            sessions,
            config.minimum_coverage,
            maximum_age,
            move || worker_clock.now(),
        )
        .map_err(|e| e.to_string())?;
        let generation = worker.health().generation;
        let max_frames = models.iter().map(|m| m.export.frames).max().unwrap() as u64;
        // Centered Hampel half-span plus the preceding difference sample.
        let context_frames = (contract.hampel_window_seconds * 60.0).ceil() as u64 + 2;
        let lag_frames = (maximum_age + hop_ns) * RATE_HZ / NS_PER_SECOND;
        let capacity = (max_frames + 2 * context_frames + lag_frames + 256) as usize;
        let create = |name: &str| -> Result<BufWriter<File>, String> {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(config.output_dir.join(name))
                .map(BufWriter::new)
                .map_err(|e| e.to_string())
        };
        let log = create("predictions.jsonl")?;
        let inputs = if config.save_inputs {
            Some((create("inputs.jsonl")?, create("inputs.f32")?))
        } else {
            None
        };
        Ok(Self {
            config: config.clone(),
            shared,
            worker,
            models,
            contract,
            history: History::new(capacity)?,
            segment: None,
            generation,
            segments: 0,
            counts: [0; 4],
            dropped_records: 0,
            context_frames,
            hop_ns,
            grace_ns,
            log,
            inputs,
            last_capture_ns: None,
        })
    }

    fn run(
        &mut self,
        receiver: &Receiver<Feed>,
        stop: &AtomicBool,
        clock: &Clock,
        horizon: &AtomicU64,
    ) -> Result<&'static str, String> {
        let mut ended = false;
        while !stop.load(Ordering::Acquire) {
            let mut message = match receiver.recv_timeout(Duration::from_millis(5)) {
                Ok(message) => Some(message),
                Err(mpsc::RecvTimeoutError::Timeout) => None,
                Err(mpsc::RecvTimeoutError::Disconnected) if !ended => {
                    let health = &lock(&self.shared).health;
                    return Err(health["feed_error"]
                        .as_str()
                        .unwrap_or("detection feed stopped")
                        .to_owned());
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => None,
            };
            // Ingest everything already delivered before building any window.
            while let Some(feed) = message {
                match feed {
                    Feed::Run(run) => self.start_segment(run, "new run")?,
                    Feed::Batch(batch) => self.ingest(&batch)?,
                    Feed::Ended => ended = true,
                }
                message = receiver.try_recv().ok();
            }
            // Replay finalizes only up to the time the feed has fully delivered.
            self.schedule(clock.now().min(horizon.load(Ordering::Acquire)))?;
            // Poll with a fresh clock: results may be published during scheduling.
            let now = clock.now();
            for row in self.worker.poll(now) {
                self.publish_result(row)?;
            }
            self.update_health();
            if ended && self.drained(now) {
                return Ok("finished");
            }
        }
        Ok("stopped")
    }

    fn finish(&mut self) -> Result<(), String> {
        self.worker.stop();
        self.log.flush().map_err(|e| e.to_string())?;
        if let Some((index, tensors)) = &mut self.inputs {
            index.flush().map_err(|e| e.to_string())?;
            tensors.flush().map_err(|e| e.to_string())?;
        }
        Ok(())
    }

    /// Replay end: every window that can still finalize has been published.
    fn drained(&self, now: u64) -> bool {
        let horizon = self.contract.future_context_ns + self.grace_ns + 2 * self.hop_ns;
        let worker = self.worker.health();
        self.last_capture_ns.is_none_or(|last| now > last + horizon)
            && worker.pending_jobs == 0
            && worker.active_model.is_none()
            && worker.latest_results == 0
    }

    /// Discard buffered samples and pending windows; later windows use a new generation.
    fn start_segment(&mut self, run: RunInfo, reason: &str) -> Result<(), String> {
        self.history.reset()?;
        self.generation = self.worker.reset()?;
        for model in &mut self.models {
            model.next_end_ns = None;
        }
        self.segment = Some(Segment {
            run,
            sequences: None,
            origin_ns: None,
            last_capture_ns: None,
        });
        self.segments += 1;
        let mut state = lock(&self.shared);
        state.previews.clear();
        state.health["segments"] = self.segments.into();
        state.health["generation"] = self.generation.into();
        state.health["last_reset"] = reason.into();
        Ok(())
    }

    fn ingest(&mut self, mapped: &MappedBatch) -> Result<(), String> {
        let Some(segment) = &self.segment else {
            return Err("batch received before its run".into());
        };
        let Some(slot) = segment
            .run
            .receivers
            .iter()
            .position(|m| m == &mapped.batch.mac)
        else {
            self.dropped_records += mapped.batch.records.len() as u64;
            return Ok(());
        };
        let channel = segment.run.channel;
        let mut stream = Vec::new();
        for (record, &capture) in mapped.batch.records.iter().zip(&mapped.captures) {
            if record.fields[11] != channel {
                continue;
            }
            // A long all-receiver silence splits segments, as in the offline export.
            let last = self.segment.as_ref().and_then(|s| s.last_capture_ns);
            if last.is_some_and(|last| {
                capture > last && capture - last >= self.contract.segment_gap_ns
            }) {
                let run = self.segment.as_ref().unwrap().run.clone();
                self.start_segment(run, "acquisition gap")?;
            }
            let Ok(packet) = records::prepare(record, mapped.arrival_ns, capture) else {
                self.dropped_records += 1;
                continue;
            };
            let segment = self.segment.as_mut().unwrap();
            let (_, sequences) = segment.sequences.get_or_insert_with(|| {
                let anchor = record.sequence;
                (anchor, std::array::from_fn(|_| Sequence::new(anchor)))
            });
            // Backward or reset sequence numbers cannot be placed on the grid.
            let Ok(offset) = sequences[slot].observe(record.sequence) else {
                self.dropped_records += 1;
                continue;
            };
            let Ok(round) = u64::try_from(offset + ROUND_MARGIN) else {
                self.dropped_records += 1;
                continue;
            };
            if segment.origin_ns.is_none() {
                let origin = capture
                    .checked_sub(round * NS_PER_SECOND / RATE_HZ)
                    .ok_or("capture clock precedes the round grid")?;
                segment.origin_ns = Some(origin);
                // The first window starts at the segment's first sample.
                for model in &mut self.models {
                    let frames = model.export.frames as u64;
                    model.next_end_ns = Some(origin + (round + frames) * NS_PER_SECOND / RATE_HZ);
                }
            }
            segment.last_capture_ns = Some(last.unwrap_or(capture).max(capture));
            self.last_capture_ns = segment.last_capture_ns;
            if self.config.preview {
                let magnitude = packet.magnitude.map(|v| v as f32);
                stream.push((self.generation, round, slot as u8, magnitude));
            }
            if self.history.insert(round, slot, packet).is_err() {
                // Overflow means the coordinator fell behind; start cleanly.
                let run = segment.run.clone();
                self.start_segment(run, "history overflow")?;
                continue;
            }
            self.counts[slot] += 1;
        }
        if !stream.is_empty() {
            let mut state = lock(&self.shared);
            for (generation, round, receiver, magnitude) in stream {
                let seq = state.next_stream_seq;
                state.next_stream_seq += 1;
                if state.stream.len() == STREAM_CAPACITY {
                    state.stream.pop_front();
                }
                state.stream.push_back(StreamRow {
                    seq,
                    generation,
                    round,
                    receiver,
                    magnitude,
                });
            }
        }
        Ok(())
    }

    /// Build and submit every window whose future context and grace have elapsed.
    fn schedule(&mut self, now: u64) -> Result<(), String> {
        let Some(origin) = self.segment.as_ref().and_then(|s| s.origin_ns) else {
            return Ok(());
        };
        let wait = self.contract.future_context_ns + self.grace_ns;
        let mut groups = BTreeMap::<u64, Vec<usize>>::new();
        for (index, model) in self.models.iter_mut().enumerate() {
            let Some(mut due) = model.next_end_ns else {
                continue;
            };
            if now < due + wait {
                continue;
            }
            // Skip windows that are already too old to publish.
            while now >= due + self.hop_ns + wait {
                due += self.hop_ns;
            }
            model.next_end_ns = Some(due + self.hop_ns);
            let end_frame = ((due - origin) as f64 * RATE_HZ as f64 / 1e9).round_ties_even() as u64;
            groups.entry(end_frame).or_default().push(index);
        }
        for (end_frame, indices) in groups {
            self.submit_group(origin, end_frame, &indices, now)?;
        }
        let earliest = self
            .models
            .iter()
            .filter_map(|m| {
                let duration = m.export.frames as u64 * NS_PER_SECOND / RATE_HZ;
                m.next_end_ns.map(|end| end.saturating_sub(duration))
            })
            .min();
        if let Some(earliest) = earliest {
            let first = earliest.saturating_sub(origin) * RATE_HZ / NS_PER_SECOND;
            self.history
                .evict_before(first.saturating_sub(self.context_frames));
        }
        Ok(())
    }

    /// Models ending on the same frame share one filtered snapshot.
    fn submit_group(
        &mut self,
        origin: u64,
        end_frame: u64,
        indices: &[usize],
        now: u64,
    ) -> Result<(), String> {
        let longest = indices
            .iter()
            .map(|&i| self.models[i].export.frames)
            .max()
            .unwrap();
        let start_frame = end_frame
            .checked_sub(longest as u64)
            .ok_or("window precedes the segment grid")?;
        let first = start_frame.saturating_sub(self.context_frames);
        let end = end_frame + self.context_frames + 1;
        let delivery_deadline = origin
            + end_frame * NS_PER_SECOND / RATE_HZ
            + self.contract.future_context_ns
            + self.grace_ns;
        let snapshot =
            self.history
                .snapshot(first, (end - first) as usize, Some(delivery_deadline))?;
        let times: Vec<_> = (first..end).map(|f| f as f64 / RATE_HZ as f64).collect();
        let range_start = (start_frame - first) as usize;
        let reference = indices
            .iter()
            .copied()
            .find(|&i| self.models[i].export.frames == longest)
            .unwrap();
        let started = Instant::now();
        let prepared = window::prepare(
            &snapshot,
            &times,
            range_start..range_start + longest,
            SegmentEdges {
                start: first == 0,
                end: false,
            },
            &self.contract,
            &self.models[reference].normalizer,
        )?;
        let preprocessing_ns = started.elapsed().as_nanos() as u64;
        let segment = self.segment.as_ref().unwrap();
        let anchor = segment.sequences.as_ref().map_or(0, |(anchor, _)| *anchor);
        let run = segment.run.run.to_string();
        let mut shared_inputs = BTreeMap::<(usize, String), Arc<[f32]>>::new();
        for &index in indices {
            let model = &self.models[index];
            let frames = model.export.frames;
            let skip = longest - frames;
            let mut buffer = Vec::new();
            let coverage = model.normalizer.assemble(
                &prepared.transformed[skip * 980..],
                &snapshot.presence[range_start + skip..range_start + longest],
                &mut buffer,
            )?;
            let input = shared_inputs
                .entry((frames, model.export.normalizer_hash.clone()))
                .or_insert_with(|| buffer.into())
                .clone();
            let window_start_frame = end_frame - frames as u64;
            let start_ns = origin + window_start_frame * NS_PER_SECOND / RATE_HZ;
            let timing = WindowTiming::new(
                start_ns,
                frames as u64 * NS_PER_SECOND / RATE_HZ,
                self.contract.future_context_ns,
                self.grace_ns,
            )?;
            let deadline = timing.finalize_after_ns + 2 * self.hop_ns;
            let model_id = model.export.id.clone();
            if self.config.preview {
                let rows = range_start + skip..range_start + longest;
                let raw: Arc<[f32]> = snapshot.magnitude[rows.start * 980..rows.end * 980]
                    .iter()
                    .map(|&v| v as f32)
                    .collect();
                let preview = Preview {
                    model_id: model_id.clone(),
                    generation: self.generation,
                    start_ns,
                    end_ns: timing.end_ns,
                    frames,
                    coverage,
                    raw,
                    input: input.clone(),
                };
                lock(&self.shared)
                    .previews
                    .insert(model_id.clone(), preview);
            }
            if let Some((index_log, tensor_log)) = &mut self.inputs {
                let first_sequence =
                    anchor.wrapping_add((window_start_frame as i64 - ROUND_MARGIN) as u32);
                let entry = json!({
                    "model_id": model_id, "run": run, "generation": self.generation,
                    "first_sequence": first_sequence, "frames": frames,
                    "coverage": coverage, "end_ns": timing.end_ns,
                });
                serde_json::to_writer(&mut *index_log, &entry).map_err(|e| e.to_string())?;
                index_log.write_all(b"\n").map_err(|e| e.to_string())?;
                let bytes: Vec<u8> = input.iter().flat_map(|v| v.to_le_bytes()).collect();
                tensor_log.write_all(&bytes).map_err(|e| e.to_string())?;
            }
            if now > deadline {
                let row = json!({
                    "model_id": model_id, "run": run, "generation": self.generation,
                    "state": "unknown", "score": null, "logit": null, "coverage": coverage,
                    "start_ns": start_ns, "center_ns": timing.center_ns, "end_ns": timing.end_ns,
                    "finalized_ns": now, "published_ns": now, "provider": self.config.provider(),
                    "error": "preprocessing deadline exceeded",
                    "timings": {"preprocessing_ns": preprocessing_ns},
                });
                self.publish(row)?;
                continue;
            }
            self.worker.submit(Job {
                model_id,
                generation: self.generation,
                start_ns,
                end_ns: timing.end_ns,
                finalized_ns: now,
                deadline_ns: deadline,
                coverage,
                frames,
                input,
            })?;
        }
        Ok(())
    }

    fn publish_result(&mut self, row: ResultRow) -> Result<(), String> {
        let (logit, score, state, error) = match row.outcome {
            Outcome::Score { logit, sigmoid } => (Some(logit), Some(sigmoid), "score", row.error),
            Outcome::Unknown(reason) => (
                None,
                None,
                "unknown",
                Some(row.error.unwrap_or_else(|| reason.into())),
            ),
        };
        let run = self
            .segment
            .as_ref()
            .map(|s| s.run.run.to_string())
            .unwrap_or_default();
        let job = &row.job;
        let value = json!({
            "model_id": job.model_id, "run": run, "generation": job.generation,
            "start_ns": job.start_ns, "center_ns": job.start_ns + (job.end_ns - job.start_ns) / 2,
            "end_ns": job.end_ns, "finalized_ns": job.finalized_ns,
            "published_ns": row.published_ns, "logit": logit, "score": score,
            "coverage": job.coverage, "provider": row.provider, "state": state, "error": error,
            "timings": {
                "queue_wait_ns": row.queue_wait_ns,
                "inference_ns": row.inference_ns,
                "publication_age_ns": row.published_ns.saturating_sub(job.end_ns),
            },
        });
        self.publish(value)
    }

    fn publish(&mut self, value: Value) -> Result<(), String> {
        serde_json::to_writer(&mut self.log, &value).map_err(|e| e.to_string())?;
        self.log
            .write_all(b"\n")
            .and_then(|_| self.log.flush())
            .map_err(|e| e.to_string())?;
        let id = value["model_id"]
            .as_str()
            .ok_or("result lacks model ID")?
            .to_owned();
        lock(&self.shared).rows.insert(id, value);
        Ok(())
    }

    fn update_health(&self) {
        let worker = self.worker.health();
        let mut state = lock(&self.shared);
        let health = &mut state.health;
        health["records"] = json!(self.counts);
        health["dropped_records"] = self.dropped_records.into();
        health["last_capture_ns"] = json!(self.last_capture_ns);
        health["queue_replacements"] = worker.replacements.into();
        health["completed_inferences"] = worker.completed_calls.into();
        health["runtime_errors"] = worker.runtime_errors.into();
        let receiving = self.last_capture_ns.is_some();
        if receiving && health["state"] != "running" && health["state"] != "restarting_radio" {
            health["state"] = "running".into();
        }
        health["ready"] = receiving.into();
    }
}
