//! Passive native serial smoke test; sends no configuration commands.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 1 && !(args.len() == 2 && args[1] == "--discover") {
        return Err("usage: gateway_probe SERIAL_PATH [--discover]".into());
    }
    let mut serial = radio_transport::serial::Serial::open(std::path::Path::new(&args[0]))?;
    if args.len() == 2 {
        let mut controller = radio_transport::control::Controller::new(serial);
        for relay in [false, true] {
            let status = controller.discover(relay, std::time::Duration::from_secs(3))?;
            println!("{}", serde_json::json!({"relay":relay,"status":status}));
        }
        let mut estimator = radio_transport::clock::Estimator::new(32, 10_000_000)?;
        let mut drops = None;
        for id in 0..8 {
            let (sample, current_drops) =
                controller.sync(id, radio_transport::clock::monotonic_us)?;
            if drops.is_some_and(|old| old != current_drops) {
                return Err("transmitter reference dropped messages".into());
            }
            drops = Some(current_drops);
            let estimate = estimator.add(sample)?;
            println!("clock estimate: {estimate:?}");
        }
        return Ok(());
    }
    let start = std::time::Instant::now();
    let mut counts = std::collections::BTreeMap::<u8, u64>::new();
    while start.elapsed().as_secs() < 5 {
        for frame in serial.read()? {
            *counts.entry(frame.kind).or_default() += 1;
        }
    }
    println!(
        "{}",
        serde_json::json!({"frame_types":counts,"framing_errors":serial.framing_errors()})
    );
    Ok(())
}
