//! Headless Rust live detector. Configuration contains model paths and radio settings only.
use radio_detection::backend::{Backend, BackendConfig};
use std::{
    io::{self, Write},
    time::{Duration, Instant},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.is_empty() || args.len() > 2 {
        return Err("usage: live_detect CONFIG.json [SECONDS]".into());
    }
    let config: BackendConfig = serde_json::from_reader(std::fs::File::open(&args[0])?)?;
    let duration = if let Some(value) = args.get(1) {
        Some(Duration::from_secs(value.parse()?))
    } else {
        None
    };
    let mut backend = Backend::new(config)?;
    backend.start()?;
    let start = Instant::now();
    let mut last_health = Instant::now();
    loop {
        for row in backend.poll(64).as_array().unwrap() {
            println!("{row}");
        }
        io::stdout().flush()?;
        let health = backend.health();
        if last_health.elapsed() >= Duration::from_secs(1) {
            eprintln!("{health}");
            last_health = Instant::now();
        }
        if health["running"] == false
            || duration.is_some_and(|duration| start.elapsed() >= duration)
        {
            break;
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    backend.stop();
    let health = backend.health();
    if let Some(error) = health["error"].as_str()
        && !error.is_empty()
    {
        return Err(error.to_owned().into());
    }
    Ok(())
}
