//! Run a prepared recording through a resident native session.
use radio_detection::runtime::{Backend, Runtime};
use std::{env, fs, path::Path, time::Instant};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.len() != 5 && args.len() != 7 {
        return Err("usage: qualify CORE MODEL INPUT.f32le PROFILE_PREFIX STEPS [WEBGPU_PLUGIN AMD_DEVICE_ID]".into());
    }
    let steps: usize = args[4].parse()?;
    let bytes = fs::read(&args[2])?;
    if bytes.len() % 4 != 0 {
        return Err("prepared input is not float32 aligned".into());
    }
    let input: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();
    // STEPS rows of equal width: 1964 for window models, 65 for front-end heads.
    if steps == 0 || !input.len().is_multiple_of(steps) {
        return Err("input is not STEPS rows of equal width".into());
    }
    let shape = [steps, input.len() / steps];
    let backend = if args.len() == 7 {
        Backend::AmdVulkan {
            plugin: Path::new(&args[5]),
            device_id: Some(args[6].parse()?),
        }
    } else {
        Backend::CpuDiagnostic
    };
    let mut runtime = Runtime::new(Path::new(&args[0]), backend)?;
    let profiled = args[3] != "-";
    let model = if profiled {
        runtime.load(Path::new(&args[1]), Path::new(&args[3]))?
    } else {
        runtime.load_unprofiled(Path::new(&args[1]))?
    };
    for _ in 0..3 {
        runtime.infer(model, shape, input.clone())?;
    }
    for _ in 0..20 {
        let start = Instant::now();
        let logit = runtime.infer(model, shape, input.clone())?;
        println!(
            "{}",
            serde_json::json!({"logit":logit,"submission_us":start.elapsed().as_micros()})
        );
    }
    if profiled {
        eprintln!("profile: {}", runtime.finish_profile(model)?);
    }
    Ok(())
}
