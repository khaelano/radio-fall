//! Command-line access to session conversion and verification.
use radio_storage::{
    ConvertOptions, FrameScope, MigrateOptions, convert_session, migrate_archive,
    verify_against_source, verify_archive, verify_dir, vfs,
};
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("convert") if args.len() == 3 => convert(&args[1], &args[2], FrameScope::Attempts),
        Some("convert") if args.len() == 4 && args[3] == "--all-frames" => {
            convert(&args[1], &args[2], FrameScope::All)
        }
        Some("migrate") if args.len() >= 3 => migrate(&args[1], &args[2], args.get(3).map(String::as_str)),
        Some("verify-archive") if args.len() == 2 => verify_archive_command(&args[1]),
        Some("verify") if args.len() == 2 => verify(&args[1], None),
        Some("verify") if args.len() == 3 => verify(&args[1], Some(&args[2])),
        _ => Err("usage: radio_storage convert <session dir|zip> <out dir> [--all-frames]\n       radio_storage migrate <source zip> <new v3 zip> [zstd level]\n       radio_storage verify-archive <v3 zip>\n       radio_storage verify <out dir> [<session dir|zip>]".into()),
    };
    if let Err(error) = result {
        eprintln!("error: {error}");
        std::process::exit(1);
    }
}

fn convert(source: &str, output: &str, scope: FrameScope) -> radio_storage::Result<()> {
    let source = vfs::open(&PathBuf::from(source))?;
    let options = ConvertOptions {
        scope,
        ..ConvertOptions::default()
    };
    let report = convert_session(source.as_ref(), &PathBuf::from(output), &options)?;
    println!("{}", serde_json::to_string_pretty(&report.to_json())?);
    Ok(())
}

fn verify(directory: &str, source: Option<&str>) -> radio_storage::Result<()> {
    let directory = PathBuf::from(directory);
    let report = match source {
        Some(source) => {
            let source = vfs::open(&PathBuf::from(source))?;
            verify_against_source(source.as_ref(), &directory, &ConvertOptions::default())?
        }
        None => verify_dir(&directory)?,
    };
    println!(
        "frames {} capture_backward_steps {} problems {}",
        report.frames,
        report.capture_backward_steps,
        report.problems.len()
    );
    for problem in &report.problems {
        println!("  problem: {problem}");
    }
    if report.ok() {
        Ok(())
    } else {
        Err("verification failed".into())
    }
}

fn migrate(source: &str, destination: &str, level: Option<&str>) -> radio_storage::Result<()> {
    let mut options = MigrateOptions::default();
    if let Some(level) = level {
        options.zstd_level = level.parse().map_err(|_| "zstd level must be an integer")?;
    }
    let report = migrate_archive(
        &PathBuf::from(source),
        &PathBuf::from(destination),
        &options,
    )?;
    println!("{}", serde_json::to_string_pretty(&report.to_json())?);
    Ok(())
}

fn verify_archive_command(path: &str) -> radio_storage::Result<()> {
    let problems = verify_archive(&PathBuf::from(path))?;
    println!("problems {}", problems.len());
    for problem in &problems {
        println!("  problem: {problem}");
    }
    if problems.is_empty() {
        Ok(())
    } else {
        Err("verification failed".into())
    }
}
