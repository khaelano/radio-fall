//! Native serial acceptance loop for a preflight-verified sensing run.
use crate::{
    acceptance::Acceptor,
    availability::{Grid, Receipts},
    framing::Frame,
    wire::Batch,
};
use std::{
    collections::VecDeque,
    io,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
};

/// Testable bounded frame transport. Implementations own their read timeout.
pub trait FrameIo {
    fn read_frames(&mut self) -> io::Result<Vec<Frame>>;
    fn write_frame(&mut self, kind: u8, payload: &[u8]) -> io::Result<()>;
    /// Cumulative malformed and oversized frame counts, when the transport tracks them.
    fn framing_errors(&self) -> (u64, u64) {
        (0, 0)
    }
}

/// Preserve bounded preflight frames when transferring serial ownership.
pub struct BufferedIo<T> {
    pub inner: T,
    pub pending: VecDeque<Frame>,
}
impl<T: FrameIo> FrameIo for BufferedIo<T> {
    fn read_frames(&mut self) -> io::Result<Vec<Frame>> {
        if !self.pending.is_empty() {
            return Ok(self.pending.drain(..self.pending.len().min(64)).collect());
        }
        self.inner.read_frames()
    }
    fn write_frame(&mut self, kind: u8, payload: &[u8]) -> io::Result<()> {
        self.inner.write_frame(kind, payload)
    }
    fn framing_errors(&self) -> (u64, u64) {
        self.inner.framing_errors()
    }
}

#[cfg(target_os = "linux")]
impl FrameIo for crate::serial::Serial {
    fn read_frames(&mut self) -> io::Result<Vec<Frame>> {
        self.read()
    }
    fn write_frame(&mut self, kind: u8, payload: &[u8]) -> io::Result<()> {
        self.write(kind, payload)
    }
    fn framing_errors(&self) -> (u64, u64) {
        crate::serial::Serial::framing_errors(self)
    }
}

/// Latest cumulative health; no per-packet data need cross a frontend boundary.
#[derive(Default, Debug)]
pub struct Health {
    pub batches: u64,
    pub duplicates: u64,
    pub records: u64,
    pub acknowledgements: u64,
    pub status_ns: Option<u64>,
    pub failure: Option<String>,
    pub pending: usize,
    pub peak_pending: usize,
    /// Latest validated gateway status document.
    pub gateway: Option<serde_json::Value>,
    pub rounds: u64,
}

/// Availability bins and round receipts for the current run.
pub struct Monitor {
    pub grid: Arc<Mutex<Grid>>,
    pub receipts: Receipts,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Own a live run's journal/acceptance state and serial transport.
pub struct Acquisition<T> {
    io: T,
    acceptor: Acceptor,
    gateway_mac: String,
    gateway_boot: u64,
    status_timeout_ns: u64,
    started_ns: Option<u64>,
    receivers: crate::receivers::Ledger,
    reference: Option<crate::reference::Reference>,
    pending: VecDeque<(u64, Vec<u8>)>,
    pending_capacity: usize,
    pending_timeout_ns: u64,
    monitor: Option<Monitor>,
    framing_baseline: (u64, u64),
    pub health: Health,
}

impl<T: FrameIo> Acquisition<T> {
    /// Attempt transmitter and gateway stop writes even after acquisition failure.
    pub fn stop_run(&mut self, run: u64) -> Result<(), String> {
        if run == 0 {
            return Err("invalid stop run".into());
        }
        let mut stop = b"CGSP".to_vec();
        stop.extend_from_slice(&run.to_be_bytes());
        let mut relay = vec![20];
        relay.extend_from_slice(&stop);
        let transmitter = self.io.write_frame(26, &relay);
        let gateway = self.io.write_frame(20, &stop);
        transmitter.and(gateway).map_err(|e| e.to_string())
    }
    /// Require verified gateway identity and an explicit status freshness policy.
    pub fn new(
        io: T,
        acceptor: Acceptor,
        gateway_mac: String,
        gateway_boot: u64,
        status_timeout_ns: u64,
        receivers: crate::receivers::Ledger,
        pending_policy: (usize, u64),
    ) -> Result<Self, String> {
        if gateway_mac.is_empty()
            || status_timeout_ns == 0
            || pending_policy.0 == 0
            || pending_policy.1 == 0
        {
            return Err("invalid gateway identity or timeout".into());
        }
        let framing_baseline = io.framing_errors();
        Ok(Self {
            io,
            acceptor,
            gateway_mac,
            gateway_boot,
            status_timeout_ns,
            started_ns: None,
            receivers,
            pending: VecDeque::new(),
            pending_capacity: pending_policy.0,
            reference: None,
            pending_timeout_ns: pending_policy.1,
            monitor: None,
            framing_baseline,
            health: Health::default(),
        })
    }

    /// Publish availability bins and round receipts for this run.
    pub fn install_monitor(&mut self, monitor: Monitor) -> Result<(), String> {
        if self.started_ns.is_some() || self.monitor.is_some() {
            return Err("monitor must be installed once before acquisition".into());
        }
        self.monitor = Some(monitor);
        Ok(())
    }

    /// Receiver status evidence for health reporting.
    pub fn receivers(&self) -> &crate::receivers::Ledger {
        &self.receivers
    }

    /// Continuous reference state, when installed.
    pub fn reference(&self) -> Option<&crate::reference::Reference> {
        self.reference.as_ref()
    }

    /// Directory of the run journal.
    pub fn journal_directory(&self) -> &std::path::Path {
        self.acceptor.journal_directory()
    }

    /// Best-effort journal of the failure that ended this run.
    pub fn record_interruption(&mut self, now_ns: u64, reason: &str) {
        let _ = self.acceptor.event(
            "run_interrupted",
            now_ns,
            serde_json::json!({"reason": reason}),
        );
    }

    /// Install continuous reference monitoring before the first acquisition read.
    pub fn install_reference(
        &mut self,
        reference: crate::reference::Reference,
    ) -> Result<(), String> {
        if self.started_ns.is_some() || self.reference.is_some() {
            return Err("reference must be installed once before acquisition".into());
        }
        self.reference = Some(reference);
        Ok(())
    }

    /// Drain a bounded read, process native batches, then send accepted ACKs.
    /// Any failure latches; callers must reset detector history before restarting.
    pub fn step(
        &mut self,
        clock: impl Fn() -> u64,
        mut sink: impl FnMut(&Batch, u64) -> Result<(), String>,
    ) -> Result<(), String> {
        self.step_mapped(clock, |batch, arrival, _| sink(batch, arrival))
    }

    /// Expose the current native reference only during synchronous batch acceptance.
    pub fn step_mapped(
        &mut self,
        clock: impl Fn() -> u64,
        mut sink: impl FnMut(&Batch, u64, Option<&crate::reference::Reference>) -> Result<(), String>,
    ) -> Result<(), String> {
        if let Some(error) = &self.health.failure {
            return Err(error.clone());
        }
        let started = *self.started_ns.get_or_insert_with(&clock);
        let result = (|| -> Result<(), Box<dyn std::error::Error>> {
            let frames = self.io.read_frames()?;
            let arrival = clock();
            for frame in frames {
                match frame.kind {
                    6 => {
                        let status: serde_json::Value = serde_json::from_slice(&frame.data)?;
                        if status["role"] != "gateway"
                            || status["target"] != "esp32c6"
                            || status["protocol_version"] != 3
                            || status["csi_transport"] != "espnow_gateway"
                            || status["mac"] != self.gateway_mac
                            || status["boot_id"].as_u64() != Some(self.gateway_boot)
                            || status["ready"] != true
                        {
                            return Err("gateway status identity/boot/readiness mismatch".into());
                        }
                        self.health.status_ns = Some(arrival);
                        self.health.gateway = Some(status.clone());
                        self.acceptor.event("gateway_status", arrival, status)?;
                    }
                    24 => {
                        // Validate wire integrity immediately, before retaining raw bytes.
                        Batch::decode(&frame.data)?;
                        if self.pending.len() == self.pending_capacity {
                            return Err("receiver-status pending queue overflow".into());
                        }
                        self.pending.push_back((arrival, frame.data));
                        self.health.pending = self.pending.len();
                        self.health.peak_pending = self.health.peak_pending.max(self.pending.len());
                    }
                    27 => {
                        for event in crate::control::relay_frames(&frame.data)? {
                            self.acceptor.event(
                                "reference_frame",
                                arrival,
                                serde_json::json!({"frame_type": event.kind, "payload_hex": hex(&event.data)}),
                            )?;
                            if event.kind == 23 && event.data.starts_with(b"CGST") {
                                self.receivers.observe(&event.data, arrival)?;
                            } else if let Some(reference) = &mut self.reference {
                                match event.kind {
                                    21 => {
                                        reference.response(&event.data, arrival)?;
                                    }
                                    22 => {
                                        if let Some(round) =
                                            reference.round(&event.data, arrival)?
                                        {
                                            self.health.rounds =
                                                self.health.rounds.saturating_add(1);
                                            let value = serde_json::json!({
                                                "run_id": crate::wire::u64be(&event.data, 4).to_string(),
                                                "transmitter_boot_id": reference.boot(),
                                                "sequence": round.sequence,
                                                "tx_enqueue_us": round.enqueue_us,
                                                "scheduled_us": round.scheduled_us,
                                                "period_us": 1_000_000 / reference.rate_hz(),
                                                "send_mask": round.result & 0xF,
                                                "skipped_rounds": if round.result & 0x8000_0000 != 0 {
                                                    round.result & 0x7fff_ffff
                                                } else {
                                                    0
                                                },
                                                "log_drops": 0,
                                                "lifetime_log_drops": reference.drops(),
                                                "owners": round.owners,
                                                "host_capture_ns": reference.capture_ns(round.enqueue_us, arrival).ok(),
                                            });
                                            self.acceptor.event("round", arrival, value.clone())?;
                                            if let Some(monitor) = &mut self.monitor {
                                                monitor.receipts.round(value)?;
                                            }
                                        }
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                    _ => {} // Startup/reference controller integration is still required.
                }
            }
            if let Some(reference) = &mut self.reference {
                if let Some(payload) = reference.request(arrival)? {
                    let mut relay = vec![20];
                    relay.extend_from_slice(&payload);
                    self.io.write_frame(26, &relay)?;
                    self.acceptor.event(
                        "clock_request",
                        arrival,
                        serde_json::json!({"payload_hex": hex(&payload)}),
                    )?;
                }
            }
            while let Some((received, _)) = self.pending.front() {
                if arrival < *received || arrival - *received > self.pending_timeout_ns {
                    return Err("receiver boot evidence unavailable before deadline".into());
                }
                let Ok(boots) = self.receivers.verified_boots(arrival) else {
                    break;
                };
                self.acceptor.verify_receiver_boots(boots)?;
                if self
                    .health
                    .status_ns
                    .is_none_or(|last| arrival < last || arrival - last > self.status_timeout_ns)
                {
                    break;
                }
                let (received, bytes) = self.pending.pop_front().unwrap();
                self.health.pending = self.pending.len();
                if let Some(accepted) = self.acceptor.accept(&bytes, received, |batch| {
                    sink(batch, received, self.reference.as_ref())
                })? {
                    if accepted.fresh {
                        let available_ns = clock();
                        let slot = self
                            .receivers
                            .macs()
                            .iter()
                            .position(|mac| *mac == accepted.batch.mac);
                        // One reference estimate maps the whole batch, so its
                        // uncertainty is journaled once per batch (null when
                        // no reference exists yet).
                        let uncertainty = self
                            .reference
                            .as_ref()
                            .map(|reference| reference.estimate().uncertainty_us);
                        let mapped = accepted
                            .batch
                            .records
                            .iter()
                            .map(|record| {
                                let capture = self
                                    .reference
                                    .as_ref()
                                    .map(|reference| {
                                        reference.capture_ns(record.tx_timestamp, available_ns)
                                    })
                                    .transpose()?;
                                if let (Some(monitor), Some(slot)) = (&mut self.monitor, slot) {
                                    if let Some(capture) = capture {
                                        monitor
                                            .grid
                                            .lock()
                                            .unwrap_or_else(|p| p.into_inner())
                                            .observe(slot, capture, available_ns)?;
                                    }
                                    monitor.receipts.receive(
                                        accepted.batch.tx_boot,
                                        record.sequence,
                                        slot,
                                        available_ns,
                                    );
                                }
                                Ok::<_, String>(serde_json::json!({
                                    "receiver": record.receiver,
                                    "sequence": record.sequence,
                                    "tx_enqueue_us": record.tx_timestamp,
                                    "capture_ns": capture,
                                }))
                            })
                            .collect::<Result<Vec<_>, _>>()?;
                        self.acceptor.event("batch_acceptance",available_ns,serde_json::json!({
                            "run":accepted.batch.run.to_string(),"transmitter_boot":accepted.batch.tx_boot,
                            "receiver_boot":accepted.batch.rx_boot,"receiver":accepted.batch.mac,"batch":accepted.batch.id,
                            "arrival_ns":received,"available_ns":available_ns,
                            "clock_uncertainty_us":uncertainty,"records":mapped}))?;
                        self.health.batches = self.health.batches.saturating_add(1);
                        self.health.records = self
                            .health
                            .records
                            .saturating_add(accepted.batch.records.len() as u64);
                    } else {
                        self.health.duplicates = self.health.duplicates.saturating_add(1);
                    }
                    if let Some(ack) = accepted.acknowledgement {
                        self.io.write_frame(25, &ack)?;
                        self.health.acknowledgements =
                            self.health.acknowledgements.saturating_add(1);
                    }
                }
            }
            if let Some(monitor) = &mut self.monitor {
                let rows = monitor
                    .grid
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .advance(arrival);
                for row in rows {
                    self.acceptor.bin(&row)?;
                }
                for event in monitor.receipts.advance(arrival) {
                    self.acceptor.event("round_availability", arrival, event)?;
                }
            }
            if self.io.framing_errors() != self.framing_baseline {
                return Err("gateway USB framing error".into());
            }
            let last = self.health.status_ns.unwrap_or(started);
            if arrival < last || arrival - last > self.status_timeout_ns {
                return Err("gateway status timed out".into());
            }
            Ok(())
        })();
        result.map_err(|error| {
            let message = error.to_string();
            self.health.failure = Some(message.clone());
            message
        })
    }

    /// Continue draining until requested shutdown or the first acquisition failure.
    pub fn run(
        &mut self,
        stop: &AtomicBool,
        clock: impl Fn() -> u64,
        mut sink: impl FnMut(&Batch, u64) -> Result<(), String>,
    ) -> Result<(), String> {
        while !stop.load(Ordering::Acquire) {
            self.step(&clock, &mut sink)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{acceptance::Identities, journal::Journal};
    #[test]
    #[ignore = "requires RADIO_JOURNAL_FIXTURE envelope"]
    fn waits_for_receiver_evidence_without_acknowledging_early() {
        struct ScriptedIo(
            VecDeque<Vec<Frame>>,
            std::sync::Arc<std::sync::Mutex<usize>>,
        );
        impl FrameIo for ScriptedIo {
            fn read_frames(&mut self) -> io::Result<Vec<Frame>> {
                Ok(self.0.pop_front().unwrap_or_default())
            }
            fn write_frame(&mut self, kind: u8, _: &[u8]) -> io::Result<()> {
                assert_eq!(kind, 25);
                *self.1.lock().unwrap() += 1;
                Ok(())
            }
        }
        let bytes = std::fs::read(std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()).unwrap();
        let batch = Batch::decode(&bytes).unwrap();
        let macs = std::array::from_fn(|i| {
            if i == 0 {
                batch.mac.clone()
            } else {
                format!("00:00:00:00:00:{i:02x}")
            }
        });
        let boots = std::array::from_fn::<_, 4, _>(|i| if i == 0 { batch.rx_boot } else { 1 });
        let identities = Identities {
            run: batch.run,
            transmitter_boot: batch.tx_boot,
            transmitter_mac: batch.records[0].transmitter.clone(),
            fingerprint: batch.records[0].fingerprint.clone(),
            receivers: macs.iter().cloned().zip(boots).collect(),
        };
        let root = std::env::temp_dir().join(format!(
            "radio-delayed-status-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let journal = Journal::create(&root, batch.run, serde_json::json!({})).unwrap();
        let acceptor = Acceptor::awaiting_receivers(identities, journal, true).unwrap();
        let receivers =
            crate::receivers::Ledger::new(batch.run, batch.tx_boot, macs, 1000).unwrap();
        let gateway = serde_json::to_vec(
            &serde_json::json!({"role":"gateway","target":"esp32c6","protocol_version":3,
            "csi_transport":"espnow_gateway","mac":"gateway","boot_id":1,"ready":true}),
        )
        .unwrap();
        let mut events = Vec::new();
        for (slot, boot) in boots.into_iter().enumerate() {
            let mut status = vec![0; 96];
            status[..4].copy_from_slice(b"CGST");
            status[4] = 1;
            status[5] = slot as u8;
            status[8..16].copy_from_slice(&batch.run.to_be_bytes());
            status[16..20].copy_from_slice(&batch.tx_boot.to_be_bytes());
            status[20..24].copy_from_slice(&boot.to_be_bytes());
            let crc = crc32fast::hash(&status[..92]);
            status[92..].copy_from_slice(&crc.to_be_bytes());
            let mut relay = vec![23];
            relay.extend(status);
            events.push(Frame {
                kind: 27,
                data: relay,
            });
        }
        let writes = std::sync::Arc::new(std::sync::Mutex::new(0));
        let io = ScriptedIo(
            VecDeque::from([
                vec![
                    Frame {
                        kind: 6,
                        data: gateway,
                    },
                    Frame {
                        kind: 24,
                        data: bytes,
                    },
                ],
                events,
            ]),
            writes.clone(),
        );
        let mut acquisition =
            Acquisition::new(io, acceptor, "gateway".into(), 1, 1000, receivers, (4, 750)).unwrap();
        let mut arrivals = Vec::new();
        acquisition
            .step(
                || 10,
                |_, arrival| {
                    arrivals.push(arrival);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(acquisition.health.pending, 1);
        assert_eq!(*writes.lock().unwrap(), 0);
        assert!(arrivals.is_empty());
        acquisition
            .step(
                || 20,
                |_, arrival| {
                    arrivals.push(arrival);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(arrivals, vec![10]);
        assert_eq!(acquisition.health.pending, 0);
        assert_eq!(*writes.lock().unwrap(), 1);
    }
    struct EmptyIo;
    impl FrameIo for EmptyIo {
        fn read_frames(&mut self) -> io::Result<Vec<Frame>> {
            Ok(Vec::new())
        }
        fn write_frame(&mut self, _: u8, _: &[u8]) -> io::Result<()> {
            panic!("no ACK permitted without accepted data")
        }
    }
    #[test]
    fn initial_status_timeout_latches_failure() {
        let root = std::env::temp_dir().join(format!(
            "radio-status-timeout-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let journal = Journal::create(&root, 1, serde_json::json!({})).unwrap();
        let identities = Identities {
            run: 1,
            transmitter_boot: 1,
            transmitter_mac: "tx".into(),
            fingerprint: "profile".into(),
            receivers: (0..4).map(|i| (format!("rx-{i}"), 1)).collect(),
        };
        let acceptor = Acceptor::awaiting_receivers(identities, journal, true).unwrap();
        let receivers =
            crate::receivers::Ledger::new(1, 1, std::array::from_fn(|i| format!("rx-{i}")), 100)
                .unwrap();
        let mut acquisition = Acquisition::new(
            EmptyIo,
            acceptor,
            "gateway".into(),
            1,
            10,
            receivers,
            (256, 750_000_000),
        )
        .unwrap();
        let clock = std::cell::Cell::new(0);
        let error = acquisition
            .step(
                || {
                    let value = clock.get();
                    clock.set(value + 20);
                    value
                },
                |_, _| Ok(()),
            )
            .unwrap_err();
        assert_eq!(error, "gateway status timed out");
        assert_eq!(acquisition.step(|| 0, |_, _| Ok(())).unwrap_err(), error);
        assert_eq!(acquisition.health.acknowledgements, 0);
    }
}
