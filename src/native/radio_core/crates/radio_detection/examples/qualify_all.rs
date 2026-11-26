//! Keep all verified exports resident and compare caller-prepared inputs.
use radio_detection::{
    bundle::{FAMILIES, inspect_exports},
    runtime::{Backend, Runtime},
};
use std::{fs, path::Path, time::Instant};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 6 {
        return Err(
            "usage: qualify_all CORE PLUGIN AMD_DEVICE_ID MODEL_ROOT INPUT_DIR PROFILE_DIR_OR_DASH"
                .into(),
        );
    }
    let mut gpu = Runtime::new(
        Path::new(&args[0]),
        Backend::AmdVulkan {
            plugin: Path::new(&args[1]),
            device_id: Some(args[2].parse()?),
        },
    )?;
    let mut cpu = gpu.cpu_diagnostic_peer();
    let profiled = args[5] != "-";
    if profiled {
        fs::create_dir_all(&args[5])?;
    }
    let mut models = Vec::new();
    for family in &FAMILIES {
        let directory = Path::new(&args[3]).join(family.name);
        if !directory.is_dir() {
            continue;
        }
        for export in inspect_exports(&directory)? {
            let bytes = fs::read(Path::new(&args[4]).join(format!("{}.f32le", export.id)))?;
            // The ONNX input: the window, or a front-end family's frame features.
            if bytes.len() != export.input[0] * export.input[1] * 4 {
                return Err(format!("invalid input size for {}", export.id).into());
            }
            let input: Vec<f32> = bytes
                .chunks_exact(4)
                .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
                .collect();
            if input.iter().any(|v| !v.is_finite()) {
                return Err("nonfinite prepared model input".into());
            }
            let cpu_session = cpu.load_unprofiled(&export.model)?;
            let gpu_session = if profiled {
                gpu.load(&export.model, &Path::new(&args[5]).join(&export.id))?
            } else {
                gpu.load_unprofiled(&export.model)?
            };
            models.push((export, input, cpu_session, gpu_session));
        }
    }
    let mut failed = false;
    for (export, input, cpu_session, gpu_session) in models {
        let reference = cpu.infer(cpu_session, export.input, input.clone())?;
        for _ in 0..3 {
            gpu.infer(gpu_session, export.input, input.clone())?;
        }
        let mut times = Vec::new();
        let mut maximum_error = 0.0f32;
        for _ in 0..20 {
            let start = Instant::now();
            let logit = gpu.infer(gpu_session, export.input, input.clone())?;
            times.push(start.elapsed().as_micros());
            maximum_error = maximum_error.max((logit - reference).abs());
        }
        times.sort_unstable();
        let parity = maximum_error <= 1e-4 + 1e-4 * reference.abs();
        failed |= !parity;
        let profile = if profiled {
            Some(gpu.finish_profile(gpu_session)?)
        } else {
            None
        };
        println!(
            "{}",
            serde_json::json!({"model":export.id,"cpu_logit":reference,
            "maximum_absolute_error":maximum_error,"parity":parity,"profile":profile,
            "submission_us_p50":times[9],"submission_us_p95":times[18],"submission_us_max":times[19],
            "runs":20,"all_sessions_resident":true,"input_provenance":"caller-supplied; not verified by this command"})
        );
    }
    if failed {
        return Err("GPU/CPU logit tolerance failed".into());
    }
    Ok(())
}
