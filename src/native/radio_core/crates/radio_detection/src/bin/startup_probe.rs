//! Configure and immediately stop a run; never sends a sensing-start command.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: startup_probe SERIAL_PATH CGCF.bin".into());
    }
    let config = std::fs::read(&args[1])?;
    radio_transport::startup::validate_config(&config)?;
    let serial = radio_transport::serial::Serial::open(std::path::Path::new(&args[0]))?;
    let mut controller = radio_transport::control::Controller::new(serial);
    let configured = radio_transport::startup::configure(
        &mut controller,
        &config,
        radio_transport::clock::monotonic_us,
    )?;
    controller.stop_run(configured.run)?;
    println!(
        "{}",
        serde_json::json!({"run":configured.run.to_string(),"configured":true,
        "stop_writes_completed":true,"sensing_start_sent":false,"transmitter_boot":configured.transmitter_boot,
        "clock_uncertainty_us":configured.clock.uncertainty_us})
    );
    Ok(())
}
