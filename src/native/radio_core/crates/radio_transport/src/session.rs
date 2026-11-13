//! Live gateway sessions: startup, acceptance, capture mapping and restarts.
//!
//! A session owns the USB gateway. Each run is configured from the CGCF wire
//! configuration, journals every accepted envelope before its ACK, maps
//! transmitter timestamps to host capture times and publishes availability.
//! A recoverable failure ends the run; the next run gets a fresh identity,
//! journal and clock fit. Consumers receive accepted batches through a sink.
use crate::{
    acceptance::{Acceptor, Identities},
    acquisition::{Acquisition, BufferedIo, FrameIo, Monitor},
    availability::{Grid, Receipts},
    clock::monotonic_us,
    control::Controller,
    framing::Frame,
    journal::Journal,
    receivers::Ledger,
    reference::Reference,
    startup,
    wire::{Batch, mac, u16be, u64be},
};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

/// Error returned by a sink to end the session without counting as a radio failure.
pub const SINK_STOPPED: &str = "session consumer stopped";

const STATUS_TIMEOUT_NS: u64 = 2_500_000_000;
const PENDING_POLICY: (usize, u64) = (256, 750_000_000);
const REFERENCE_POLICY: (u64, u64) = (1_000_000_000, 2_500_000_000);
const OBSERVE_INTERVAL_NS: u64 = 100_000_000;

/// Host monotonic clock in nanoseconds, shared with Python's `time.monotonic_ns`.
pub fn monotonic_ns() -> u64 {
    monotonic_us() * 1000
}

/// Identity of one sensing run and its receivers in configured slot order.
#[derive(Clone, Debug)]
pub struct RunInfo {
    pub run: u64,
    pub receivers: [String; 4],
    pub channel: u8,
    pub rate_hz: u16,
}

impl RunInfo {
    /// Read run identity, receiver order, channel and rate from CGCF v7 bytes.
    pub fn from_config(config: &[u8]) -> Result<Self, String> {
        startup::validate_config(config)?;
        Ok(Self {
            run: u64be(config, 8),
            receivers: std::array::from_fn(|slot| mac(&config[44 + slot * 6..50 + slot * 6])),
            channel: config[6],
            rate_hz: u16be(config, 16),
        })
    }
}

/// One accepted batch with per-record capture times in the host monotonic clock.
pub struct MappedBatch {
    pub batch: Arc<Batch>,
    /// Receiver slot of the batch in configured order.
    pub slot: usize,
    pub arrival_ns: u64,
    pub available_ns: u64,
    pub captures: Vec<u64>,
    pub clock_uncertainty_us: f64,
}

/// A started run, with its journal directory and live availability grid.
pub struct RunContext {
    pub info: RunInfo,
    pub journal_dir: PathBuf,
    pub grid: Arc<Mutex<Grid>>,
}

/// Consumer of a live session. Returning `SINK_STOPPED` ends the session.
pub trait Sink {
    /// A new run begins; data from earlier runs must not be combined with it.
    fn run_started(&mut self, run: &RunContext) -> Result<(), String>;
    /// One fresh accepted batch, called before its acknowledgement is released.
    fn batch(&mut self, batch: MappedBatch) -> Result<(), String>;
    /// Periodic health of the current run, or state changes between runs.
    fn observe(&mut self, health: Value);
}

/// Static session configuration; host policies are explicit, never defaulted by firmware.
#[derive(Clone, Debug)]
pub struct SessionConfig {
    pub serial_path: PathBuf,
    /// Operational CGCF v7 configuration; its run identity seeds later runs.
    pub radio_config: Vec<u8>,
    /// Directory receiving `transport/gateway/<run>` journals.
    pub journal_root: PathBuf,
    pub metadata: Value,
    pub bin_hz: u32,
    pub delivery_grace_ms: u64,
    pub restart_delay_ms: u64,
    pub maximum_restart_delay_ms: u64,
    pub relay_ready_timeout_ms: u64,
}

/// Distinguish interrupted links from configuration, storage and identity failures.
///
/// Fatal failures would recur on every new run, so the session stops.
pub fn recoverable(message: &str) -> bool {
    let text = message.to_lowercase();
    ![
        "mismatch",
        "journal",
        "permission denied",
        "no space",
        "read-only",
        "lacks",
        "invalid four-receiver",
        "invalid gateway identity",
        "differs from configured",
        "refused",
        "rejected",
        "file exists",
    ]
    .iter()
    .any(|word| text.contains(word))
}

/// Send a best-effort stop to the gateway and relay when a run is abandoned.
struct RadioStop<T: FrameIo> {
    inner: T,
    run: u64,
}
impl<T: FrameIo> FrameIo for RadioStop<T> {
    fn read_frames(&mut self) -> std::io::Result<Vec<Frame>> {
        self.inner.read_frames()
    }
    fn write_frame(&mut self, kind: u8, data: &[u8]) -> std::io::Result<()> {
        self.inner.write_frame(kind, data)
    }
    fn framing_errors(&self) -> (u64, u64) {
        self.inner.framing_errors()
    }
}
impl<T: FrameIo> Drop for RadioStop<T> {
    fn drop(&mut self) {
        let mut payload = b"CGSP".to_vec();
        payload.extend_from_slice(&self.run.to_be_bytes());
        let mut relay = vec![20];
        relay.extend_from_slice(&payload);
        let _ = self.inner.write_frame(26, &relay);
        let _ = self.inner.write_frame(20, &payload);
    }
}

/// Sleep for up to `duration`, returning early when stop is requested.
fn pause(stop: &AtomicBool, duration: Duration) {
    let until = Instant::now() + duration;
    while !stop.load(Ordering::Acquire) && Instant::now() < until {
        thread::sleep(Duration::from_millis(20).min(until - Instant::now()));
    }
}

/// Run until stop, restarting a fresh run after each recoverable failure.
///
/// Returns `Err` only for a fatal failure; a requested stop returns `Ok`.
#[cfg(target_os = "linux")]
pub fn run(config: &SessionConfig, stop: &AtomicBool, sink: &mut impl Sink) -> Result<(), String> {
    startup::validate_config(&config.radio_config)?;
    let first_run = u64be(&config.radio_config, 8);
    let mut restarts = 0u64;
    let mut attempt = 0u64;
    let mut previous: Option<(u64, String)> = None;
    loop {
        let run = first_run.wrapping_add(restarts).max(1);
        let radio_config = startup::with_run(&config.radio_config, run)?;
        let mut accepted = false;
        let result = run_once(
            config,
            &radio_config,
            previous.as_ref(),
            stop,
            sink,
            &mut accepted,
        );
        let error = match result {
            Ok(()) => return Ok(()),
            Err(error) if error == SINK_STOPPED => return Ok(()),
            Err(error) => error,
        };
        let fatal = !recoverable(&error);
        sink.observe(json!({
            "state": if stop.load(Ordering::Acquire) {
                "stopped"
            } else if fatal {
                "failed"
            } else {
                "restarting"
            },
            "run": run.to_string(),
            "error": error,
            "fatal": fatal,
            "restarts": restarts,
        }));
        if stop.load(Ordering::Acquire) {
            return Ok(());
        }
        if fatal {
            return Err(error);
        }
        restarts += 1;
        attempt = if accepted { 1 } else { attempt + 1 };
        let delay = config
            .restart_delay_ms
            .saturating_mul(attempt)
            .min(config.maximum_restart_delay_ms);
        pause(stop, Duration::from_millis(delay));
        if stop.load(Ordering::Acquire) {
            return Ok(());
        }
        previous = Some((run, error));
    }
}

#[cfg(target_os = "linux")]
fn run_once(
    config: &SessionConfig,
    radio_config: &[u8],
    previous: Option<&(u64, String)>,
    stop: &AtomicBool,
    sink: &mut impl Sink,
    accepted: &mut bool,
) -> Result<(), String> {
    let info = RunInfo::from_config(radio_config)?;
    let run = info.run;
    let rate = u32::from(info.rate_hz);
    let mut metadata = config.metadata.clone();
    if !metadata.is_object() {
        return Err("invalid journal metadata".into());
    }
    metadata["transport"] = "espnow_gateway".into();
    metadata["recovery"] = previous
        .map(|(run, reason)| json!({"previous_run_id": run.to_string(), "reason": reason}))
        .unwrap_or(Value::Null);
    metadata["host_policy"] = json!({
        "bin_hz": config.bin_hz,
        "delivery_grace_ms": config.delivery_grace_ms,
        "status_timeout_ns": STATUS_TIMEOUT_NS,
        "pending_capacity": PENDING_POLICY.0,
        "pending_timeout_ns": PENDING_POLICY.1,
        "reference_interval_ns": REFERENCE_POLICY.0,
        "reference_timeout_ns": REFERENCE_POLICY.1,
    });
    let mut journal = Journal::create(&config.journal_root, run, metadata)
        .map_err(|e| format!("journal: {e}"))?;
    sink.observe(json!({"state": "starting_radio", "run": run.to_string()}));
    let serial = crate::serial::Serial::open(Path::new(&config.serial_path))
        .map_err(|e| format!("could not open gateway port: {e}"))?;
    let mut controller = Controller::new(RadioStop { inner: serial, run });
    startup::prepare(
        &mut controller,
        &mac(&radio_config[32..38]),
        previous.is_some(),
        Duration::from_millis(config.relay_ready_timeout_ms),
    )?;
    let configured = startup::configure(&mut controller, radio_config, monotonic_us)?;
    let initial_ns = monotonic_ns();
    let journal_event = |journal: &mut Journal, kind: &str, now: u64, value: Value| {
        journal
            .event(kind, now, value)
            .map_err(|e| format!("journal: {e}"))
    };
    if let Some((previous_run, reason)) = previous {
        journal_event(
            &mut journal,
            "run_resuming",
            initial_ns,
            json!({"previous_run_id": previous_run.to_string(), "reason": reason}),
        )?;
    }
    journal_event(
        &mut journal,
        "reference_initial",
        initial_ns,
        json!({
            "run": run.to_string(),
            "boot": configured.transmitter_boot,
            "drops": configured.reference_drops,
            "sample_rate_hz": rate,
            "samples": configured.estimator.samples().map(|s| json!({
                "boot": s.boot, "t1": s.t1, "t2": s.t2, "t3": s.t3, "t4": s.t4,
            })).collect::<Vec<_>>(),
            "interval_ns": REFERENCE_POLICY.0,
            "timeout_ns": REFERENCE_POLICY.1,
            "minimum_drift_span_us": 10_000_000u64,
        }),
    )?;
    let receivers = Ledger::new(
        run,
        configured.transmitter_boot,
        configured.receivers.clone(),
        STATUS_TIMEOUT_NS,
    )?;
    let acceptor = Acceptor::awaiting_receivers(
        Identities {
            run,
            transmitter_boot: configured.transmitter_boot,
            transmitter_mac: configured.transmitter_mac,
            fingerprint: configured.fingerprint,
            receivers: configured
                .receivers
                .iter()
                .cloned()
                .map(|mac| (mac, 0))
                .collect(),
        },
        journal,
        radio_config[103] & 4 == 0,
    )?;
    let reference = Reference::new(
        run,
        configured.reference_drops,
        rate,
        configured.estimator,
        configured.clock,
        initial_ns,
        REFERENCE_POLICY,
    )?;
    let grid = Arc::new(Mutex::new(Grid::new(
        configured.receivers.to_vec(),
        monotonic_ns(),
        config.bin_hz,
        config.delivery_grace_ms,
    )?));
    let receipts = Receipts::new(
        configured.receivers.to_vec(),
        &grid.lock().unwrap_or_else(|p| p.into_inner()),
    );
    let mut start = b"CGGO".to_vec();
    start.extend_from_slice(&run.to_be_bytes());
    controller.command(true, &start, Duration::from_secs(2))?;
    let (serial, pending) = controller.into_parts();
    let pending = pending
        .into_iter()
        .map(|(relay, frame)| {
            if relay {
                let mut data = vec![frame.kind];
                data.extend(frame.data);
                Frame { kind: 27, data }
            } else {
                frame
            }
        })
        .collect();
    let mut acquisition = Acquisition::new(
        BufferedIo {
            inner: serial,
            pending,
        },
        acceptor,
        configured.gateway_mac,
        configured.gateway_boot,
        STATUS_TIMEOUT_NS,
        receivers,
        PENDING_POLICY,
    )?;
    acquisition.install_reference(reference)?;
    acquisition.install_monitor(Monitor {
        grid: grid.clone(),
        receipts,
    })?;
    sink.run_started(&RunContext {
        info: info.clone(),
        journal_dir: acquisition.journal_directory().to_path_buf(),
        grid,
    })?;
    let mut last_observed = 0u64;
    let result = (|| -> Result<(), String> {
        while !stop.load(Ordering::Acquire) {
            acquisition.step_mapped(monotonic_ns, |batch, arrival_ns, reference| {
                let reference = reference.ok_or("reference unavailable")?;
                let available_ns = monotonic_ns();
                let captures = batch
                    .records
                    .iter()
                    .map(|record| reference.capture_ns(record.tx_timestamp, available_ns))
                    .collect::<Result<Vec<_>, _>>()?;
                let slot = info
                    .receivers
                    .iter()
                    .position(|mac| *mac == batch.mac)
                    .ok_or("unregistered receiver batch")?;
                *accepted = true;
                sink.batch(MappedBatch {
                    batch: Arc::new(batch.clone()),
                    slot,
                    arrival_ns,
                    available_ns,
                    captures,
                    clock_uncertainty_us: reference.estimate().uncertainty_us,
                })
            })?;
            let now = monotonic_ns();
            if now.saturating_sub(last_observed) >= OBSERVE_INTERVAL_NS {
                last_observed = now;
                sink.observe(health(&acquisition, &info, now));
            }
        }
        Ok(())
    })();
    if let Err(error) = &result
        && error != SINK_STOPPED
    {
        acquisition.record_interruption(monotonic_ns(), error);
    }
    result?;
    acquisition.stop_run(run)
}

/// Summarize the current run for display and diagnostics.
pub fn health<T: FrameIo>(acquisition: &Acquisition<T>, info: &RunInfo, now_ns: u64) -> Value {
    let health = &acquisition.health;
    let receivers: Vec<Value> = acquisition
        .receivers()
        .latest()
        .iter()
        .enumerate()
        .map(|(slot, latest)| match latest {
            None => json!({"slot": slot, "mac": info.receivers[slot], "status": null}),
            Some((status, arrival)) => json!({
                "slot": slot,
                "mac": info.receivers[slot],
                "status_age_ns": now_ns.saturating_sub(*arrival),
                "status": {
                    "boot_id": status.boot,
                    "state": status.state,
                    "grant": status.grant,
                    "captured": status.captured,
                    "dropped": status.dropped,
                    "expired": status.expired,
                    "queued": status.queued,
                    "peak": status.peak,
                    "queue_event_loss": status.queue_event_loss,
                    "send_errors": status.send_errors,
                },
            }),
        })
        .collect();
    let clock = acquisition.reference().map(|reference| {
        let estimate = reference.estimate();
        json!({
            "ready": reference.ready(now_ns),
            "uncertainty_us": estimate.uncertainty_us,
            "drift_ppm": estimate.drift_ppm,
            "samples": estimate.sample_count,
        })
    });
    json!({
        "state": "running",
        "run": info.run.to_string(),
        "batches": health.batches,
        "records": health.records,
        "duplicates": health.duplicates,
        "acks": health.acknowledgements,
        "pending": health.pending,
        "peak_pending": health.peak_pending,
        "rounds": health.rounds,
        "gateway": health.gateway,
        "gateway_age_ns": health.status_ns.map(|t| now_ns.saturating_sub(t)),
        "receivers": receivers,
        "clock": clock,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interrupted_links_restart_and_identity_or_storage_failures_stop() {
        for message in [
            "gateway status timed out",
            "control transaction timed out",
            "gateway USB framing error",
            "could not open gateway port: No such file or directory (os error 2)",
            "reference failed or stale",
            "receiver/transmitter boot or clock discontinuity",
            "native record queue overflow",
            "wireless reference handshake timed out",
        ] {
            assert!(recoverable(message), "{message}");
        }
        for message in [
            "gateway preflight identity mismatch",
            "journal: No space left on device (os error 28)",
            "gateway firmware lacks automatic relay recovery",
            "verified receiver set differs from configured inventory",
            "device rejected control command; refused",
        ] {
            assert!(!recoverable(message), "{message}");
        }
    }

    #[test]
    fn run_info_reads_slot_order_and_rate() {
        assert!(RunInfo::from_config(&[0; 108]).is_err());
    }
}
