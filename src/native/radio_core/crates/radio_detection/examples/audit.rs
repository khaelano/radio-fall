//! Audit a saved ORT operator profile or inspect the current model exports.

use std::{collections::BTreeSet, env, fs, process::ExitCode};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("native detection check failed: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let path = args
        .next()
        .ok_or("usage: audit PROFILE.json [REVIEWED_CPU_OP ...]")?;
    if path == "--inspect-exports" {
        let directory = args
            .next()
            .ok_or("--inspect-exports requires a bundle directory")?;
        if args.next().is_some() {
            return Err("unexpected argument".into());
        }
        let exports = radio_detection::bundle::inspect_exports(std::path::Path::new(&directory))?;
        for export in exports {
            println!("{export:?}");
        }
        println!("Artifact integrity passed.");
        return Ok(());
    }
    let allowed: BTreeSet<String> = args.collect();
    let trace = serde_json::from_slice(&fs::read(path)?)?;
    let placement = radio_detection::audit_placement(&trace, &allowed)?;
    println!("Placement audit passed: {placement:?}");
    Ok(())
}
