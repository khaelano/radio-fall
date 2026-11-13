//! Sources of accepted CSI batches for the live coordinator.
//!
//! The live feed runs a shared transport session: it configures a sensing run,
//! maps transmitter timestamps to host capture times and restarts the run after
//! a recoverable radio failure. The replay feed streams recorded native
//! captures at wall-clock pace, so the complete pipeline can run without hardware.
use crate::{
    backend::{BackendConfig, Shared},
    preprocessing::Preprocessing,
};
pub use radio_transport::session::{MappedBatch, RunInfo, monotonic_ns};
use radio_transport::{
    journal::read_entry,
    replay::{ReferenceReplay, read_event},
    session::{self, RunContext, SINK_STOPPED, SessionConfig, Sink},
};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::BufReader,
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{SyncSender, TrySendError},
    },
    thread,
    time::{Duration, Instant},
};

/// Current sequence exports were trained on 120 Hz rounds only.
pub fn require_sequence_rate(info: &RunInfo) -> Result<(), String> {
    if info.rate_hz != 120 {
        return Err("current sequence exports require a 120 Hz radio configuration".into());
    }
    Ok(())
}

/// Messages from a feed thread to the coordinator.
pub enum Feed {
    /// A new sensing run begins; earlier samples must not be combined with it.
    Run(RunInfo),
    Batch(MappedBatch),
    /// A replay finished; no further batches will arrive.
    Ended,
}

/// Scheduling clock. Live mode uses the host clock; replay maps wall time onto
/// the recording's timeline so capture times and deadlines stay comparable.
#[derive(Clone)]
pub enum Clock {
    Host,
    Replay {
        origin_ns: u64,
        started: Instant,
        speed: f64,
    },
}

impl Clock {
    pub fn now(&self) -> u64 {
        match self {
            Self::Host => monotonic_ns(),
            Self::Replay {
                origin_ns,
                started,
                speed,
            } => origin_ns + (started.elapsed().as_nanos() as f64 * speed) as u64,
        }
    }
}

fn set_health(shared: &Arc<Mutex<Shared>>, key: &str, value: Value) {
    shared.lock().unwrap_or_else(|p| p.into_inner()).health[key] = value;
}

// ---------------------------------------------------------------------------
// Live gateway feed
// ---------------------------------------------------------------------------

/// Forward session runs and batches to the coordinator without blocking acceptance.
struct LiveSink<'a> {
    shared: &'a Arc<Mutex<Shared>>,
    sender: &'a SyncSender<Feed>,
    restarts: u64,
}

impl Sink for LiveSink<'_> {
    fn run_started(&mut self, run: &RunContext) -> Result<(), String> {
        require_sequence_rate(&run.info)?;
        self.sender
            .send(Feed::Run(run.info.clone()))
            .map_err(|_| SINK_STOPPED.to_owned())?;
        set_health(self.shared, "radio_error", Value::Null);
        set_health(self.shared, "state", "running".into());
        Ok(())
    }

    fn batch(&mut self, batch: MappedBatch) -> Result<(), String> {
        match self.sender.try_send(Feed::Batch(batch)) {
            Ok(()) => Ok(()),
            Err(TrySendError::Full(_)) => Err("native packet queue overflow".into()),
            Err(TrySendError::Disconnected(_)) => Err(SINK_STOPPED.into()),
        }
    }

    fn observe(&mut self, health: Value) {
        match health["state"].as_str() {
            Some("running") => set_health(self.shared, "radio", health),
            Some("starting_radio") => set_health(self.shared, "state", "starting_radio".into()),
            Some("restarting") => {
                self.restarts += 1;
                set_health(self.shared, "radio_error", health["error"].clone());
                set_health(self.shared, "radio_restarts", self.restarts.into());
                set_health(self.shared, "state", "restarting_radio".into());
            }
            Some(_) => set_health(self.shared, "radio_error", health["error"].clone()),
            None => {}
        }
    }
}

/// Run the gateway until stop, restarting a fresh run after each recoverable failure.
pub fn live(
    config: &BackendConfig,
    shared: &Arc<Mutex<Shared>>,
    stop: &AtomicBool,
    sender: &SyncSender<Feed>,
) -> Result<(), String> {
    let session = SessionConfig {
        serial_path: PathBuf::from(&config.serial_path),
        radio_config: config.radio_config.clone(),
        journal_root: config.output_dir.clone(),
        metadata: json!({
            "source": "rust-live-detector",
            "models": config.models,
            "preprocessing": Preprocessing::operational(),
        }),
        bin_hz: 50,
        delivery_grace_ms: config.delivery_grace_ms,
        restart_delay_ms: config.restart_delay_ms,
        maximum_restart_delay_ms: config.restart_delay_ms.max(30_000),
        relay_ready_timeout_ms: 8_000,
    };
    let mut sink = LiveSink {
        shared,
        sender,
        restarts: 0,
    };
    session::run(&session, stop, &mut sink)
}

// ---------------------------------------------------------------------------
// Replay feed
// ---------------------------------------------------------------------------

/// Recorded batches of one native capture, with their recorded acceptance times.
pub struct Recording {
    pub info: RunInfo,
    /// `(accepted_ns, batch)` in acceptance order; times use the recording's clock.
    pub batches: Vec<(u64, MappedBatch)>,
    /// Batches whose capture time could not be reconstructed.
    pub skipped: usize,
}

fn single_run_directory(capture: &Path) -> Result<PathBuf, String> {
    let parent = capture.join("transport/gateway");
    let mut runs: Vec<_> = std::fs::read_dir(&parent)
        .map_err(|e| format!("{}: {e}", parent.display()))?
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path.is_dir())
        .collect();
    if runs.len() != 1 {
        return Err(format!(
            "{} must contain exactly one run journal",
            parent.display()
        ));
    }
    Ok(runs.remove(0))
}

fn slot_of(info: &RunInfo, batch: &radio_transport::wire::Batch) -> Result<usize, String> {
    info.receivers
        .iter()
        .position(|mac| *mac == batch.mac)
        .ok_or_else(|| format!("capture batch from unconfigured receiver {}", batch.mac))
}

/// Load a native capture directory written by the live detector or capture probe.
///
/// Captures that logged acceptance events use their recorded capture times
/// directly. Older captures reconstruct the mapping from reference events at
/// USB arrival time. Captures without reference evidence are rejected.
pub fn load_recording(capture: &Path) -> Result<Recording, Box<dyn std::error::Error>> {
    let info = RunInfo::from_config(&std::fs::read(capture.join("radio.cgcf"))?)?;
    require_sequence_rate(&info)?;
    let journal = single_run_directory(capture)?;
    let mut events = Vec::new();
    let mut reader = BufReader::new(File::open(journal.join("events.jsonl"))?);
    while let Some(event) = read_event(&mut reader)? {
        events.push(event);
    }
    let mut envelopes = Vec::new();
    let mut reader = BufReader::new(File::open(journal.join("envelopes.bin"))?);
    while let Some(entry) = read_entry(&mut reader)? {
        envelopes.push(entry);
    }
    let mut batches = Vec::with_capacity(envelopes.len());
    let mut skipped = 0;
    if events.iter().any(|e| e["kind"] == "batch_acceptance") {
        let acceptances = events.iter().filter(|e| e["kind"] == "batch_acceptance");
        for (event, (arrival_ns, batch)) in acceptances.zip(envelopes) {
            let accepted = event["available_ns"]
                .as_u64()
                .ok_or("acceptance event lacks available_ns")?;
            let captures = event["records"]
                .as_array()
                .ok_or("acceptance event lacks records")?
                .iter()
                .map(|record| record["capture_ns"].as_u64())
                .collect::<Option<Vec<_>>>()
                .ok_or("acceptance record lacks capture_ns")?;
            if event["batch"] != batch.id || captures.len() != batch.records.len() {
                return Err("acceptance event does not match its envelope".into());
            }
            batches.push((
                accepted,
                MappedBatch {
                    slot: slot_of(&info, &batch)?,
                    batch,
                    arrival_ns,
                    available_ns: accepted,
                    captures,
                    clock_uncertainty_us: f64::NAN,
                },
            ));
        }
    } else if events
        .first()
        .is_some_and(|e| e["kind"] == "reference_initial")
    {
        let mut replay = ReferenceReplay::new(&events[0])?;
        let mut pending = events[1..].iter().peekable();
        for (arrival_ns, batch) in envelopes {
            while let Some(event) =
                pending.next_if(|e| e["host_monotonic_ns"].as_u64() <= Some(arrival_ns))
            {
                replay.apply(event)?;
            }
            let captures: Result<Vec<_>, _> = batch
                .records
                .iter()
                .map(|r| replay.reference.capture_ns(r.tx_timestamp, arrival_ns))
                .collect();
            match captures {
                Ok(captures) => batches.push((
                    arrival_ns,
                    MappedBatch {
                        slot: slot_of(&info, &batch)?,
                        batch,
                        arrival_ns,
                        available_ns: arrival_ns,
                        captures,
                        clock_uncertainty_us: replay.reference.estimate().uncertainty_us,
                    },
                )),
                Err(_) => skipped += 1,
            }
        }
    } else {
        return Err(format!(
            "{} lacks reference timing evidence and cannot be replayed",
            capture.display()
        )
        .into());
    }
    if batches.is_empty() {
        return Err(format!("{} contains no replayable batches", capture.display()).into());
    }
    Ok(Recording {
        info,
        batches,
        skipped,
    })
}

/// Gap inserted between consecutive replayed captures; longer than the
/// segment gap, so each capture starts a fresh segment as a new run would.
pub const REPLAY_GAP_NS: u64 = 2_000_000_000;

/// Stream recordings in order at `clock` pace; times are shifted onto one timeline.
///
/// `horizon` is advanced to the clock time up to which every due batch has been
/// sent, so the coordinator never finalizes a window ahead of the feed.
pub fn replay(
    recordings: &[Recording],
    repeat: bool,
    clock: &Clock,
    horizon: &AtomicU64,
    shared: &Arc<Mutex<Shared>>,
    stop: &AtomicBool,
    sender: &SyncSender<Feed>,
) -> Result<(), String> {
    let speed = match clock {
        Clock::Replay { speed, .. } => *speed,
        Clock::Host => return Err("replay requires a replay clock".into()),
    };
    let mut cursor = clock.now();
    let mut pass = 0u64;
    loop {
        pass += 1;
        for (index, recording) in recordings.iter().enumerate() {
            let first = recording.batches[0].0;
            // Shift recorded host times onto the replay timeline.
            let shift = |t: u64| (t as i128 - first as i128 + cursor as i128) as u64;
            set_health(
                shared,
                "replay",
                json!({"pass": pass, "capture": index, "captures": recordings.len(),
                       "run": recording.info.run.to_string(), "skipped_batches": recording.skipped}),
            );
            for (position, (accepted, mapped)) in recording.batches.iter().enumerate() {
                let due = shift(*accepted);
                loop {
                    if stop.load(Ordering::Acquire) {
                        return Ok(());
                    }
                    let now = clock.now();
                    if now >= due {
                        break;
                    }
                    // Every batch due at or before `now` has been sent.
                    horizon.store(now, Ordering::Release);
                    let wait = ((due - now) as f64 / speed) as u64;
                    thread::sleep(Duration::from_nanos(wait.min(5_000_000)));
                }
                if position == 0 {
                    sender
                        .send(Feed::Run(recording.info.clone()))
                        .map_err(|_| "coordinator stopped")?;
                }
                let batch = MappedBatch {
                    batch: mapped.batch.clone(),
                    slot: mapped.slot,
                    arrival_ns: shift(mapped.arrival_ns),
                    available_ns: shift(mapped.available_ns),
                    captures: mapped.captures.iter().map(|&c| shift(c)).collect(),
                    clock_uncertainty_us: mapped.clock_uncertainty_us,
                };
                sender
                    .send(Feed::Batch(batch))
                    .map_err(|_| "coordinator stopped")?;
            }
            cursor = shift(recording.batches.last().unwrap().0) + REPLAY_GAP_NS;
        }
        if !repeat {
            break;
        }
    }
    sender
        .send(Feed::Ended)
        .map_err(|_| "coordinator stopped")?;
    horizon.store(u64::MAX, Ordering::Release);
    Ok(())
}
