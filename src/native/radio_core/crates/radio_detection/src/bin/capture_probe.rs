//! Bounded native sensing/journaling probe. No model scores or firmware changes.
use radio_transport::{
    acceptance::{Acceptor, Identities},
    acquisition::{Acquisition, BufferedIo},
    clock::monotonic_us,
    control::Controller,
    journal::Journal,
    receivers::Ledger,
    reference::Reference,
    serial::Serial,
    startup,
};
use std::{
    path::Path,
    time::{Duration, Instant},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 4 {
        return Err("usage: capture_probe SERIAL CGCF.bin NEW_OUTPUT_DIR SECONDS".into());
    }
    let seconds: u64 = args[3].parse()?;
    if !(1..=60).contains(&seconds) {
        return Err("probe duration must be 1..60 seconds".into());
    }
    let bytes = std::fs::read(&args[1])?;
    startup::validate_config(&bytes)?;
    let run = radio_transport::wire::u64be(&bytes, 8);
    let root = Path::new(&args[2]);
    std::fs::create_dir(root)?;
    std::fs::write(root.join("radio.cgcf"), &bytes)?;
    let mut journal = Journal::create(
        root,
        run,
        serde_json::json!({"source":"native-capture-probe","model_scores":false}),
    )?;
    let serial = Serial::open(Path::new(&args[0]))?;
    let mut controller = Controller::new(serial);
    let configured = startup::configure(&mut controller, &bytes, monotonic_us)?;
    let initial_ns = monotonic_us() * 1000;
    let initial = serde_json::json!({"run":run.to_string(),"boot":configured.transmitter_boot,"drops":configured.reference_drops,
        "sample_rate_hz":120,"samples":configured.estimator.samples().map(|s|serde_json::json!({"boot":s.boot,"t1":s.t1,"t2":s.t2,"t3":s.t3,"t4":s.t4})).collect::<Vec<_>>(),
        "interval_ns":1_000_000_000u64,"timeout_ns":2_500_000_000u64,"minimum_drift_span_us":10_000_000u64});
    if let Err(error) = journal.event("reference_initial", initial_ns, initial) {
        let _ = controller.stop_run(run);
        return Err(error);
    }
    let mut start = b"CGGO".to_vec();
    start.extend_from_slice(&run.to_be_bytes());
    if let Err(error) = controller.command(true, &start, Duration::from_secs(2)) {
        let _ = controller.stop_run(run);
        return Err(error.into());
    }
    let prepared = (|| -> Result<_, String> {
        let receivers = Ledger::new(
            run,
            configured.transmitter_boot,
            configured.receivers.clone(),
            2_500_000_000,
        )?;
        let identities = Identities {
            run,
            transmitter_boot: configured.transmitter_boot,
            transmitter_mac: configured.transmitter_mac,
            fingerprint: configured.fingerprint,
            receivers: configured
                .receivers
                .into_iter()
                .map(|mac| (mac, 0))
                .collect(),
        };
        let acceptor = Acceptor::awaiting_receivers(identities, journal, bytes[103] & 4 == 0)?;
        let reference = Reference::new(
            run,
            configured.reference_drops,
            120,
            configured.estimator,
            configured.clock,
            initial_ns,
            (1_000_000_000, 2_500_000_000),
        )?;
        Ok((receivers, acceptor, reference))
    })();
    let (receivers, acceptor, reference) = match prepared {
        Ok(value) => value,
        Err(error) => {
            let _ = controller.stop_run(run);
            return Err(error.into());
        }
    };
    let (serial, pending) = controller.into_parts();
    let pending = pending
        .into_iter()
        .map(|(relay, frame)| {
            if relay {
                let mut data = vec![frame.kind];
                data.extend(frame.data);
                radio_transport::framing::Frame { kind: 27, data }
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
        2_500_000_000,
        receivers,
        (256, 750_000_000),
    )?;
    acquisition.install_reference(reference)?;
    let mut counts = std::collections::BTreeMap::<String, u64>::new();
    let until = Instant::now();
    let result = (|| -> Result<(), String> {
        while until.elapsed() < Duration::from_secs(seconds) {
            acquisition.step_mapped(
                || monotonic_us() * 1000,
                |batch, _, reference| {
                    let reference = reference.ok_or("reference unavailable")?;
                    for record in &batch.records {
                        reference.capture_ns(record.tx_timestamp, monotonic_us() * 1000)?;
                    }
                    *counts.entry(batch.mac.clone()).or_default() += batch.records.len() as u64;
                    Ok(())
                },
            )?;
        }
        Ok(())
    })();
    let stopped = acquisition.stop_run(run);
    let summary = serde_json::json!({"records":counts,"batches":acquisition.health.batches,
        "acks":acquisition.health.acknowledgements,"peak_pending":acquisition.health.peak_pending,
        "failure":acquisition.health.failure,"stop_writes_completed":stopped.is_ok(),"elapsed_seconds":until.elapsed().as_secs_f64()});
    std::fs::write(
        root.join("capture-summary.json"),
        serde_json::to_vec_pretty(&summary)?,
    )?;
    println!("{summary}");
    result?;
    stopped?;
    Ok(())
}
