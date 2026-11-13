mod support;

use radio_storage::{
    ArchiveOptions, ConvertOptions, FrameScope, MigrateOptions, archive_manifest, convert_session,
    extract_archive, extract_session_file, migrate_archive, tables_differences, verify_archive,
    vfs, write_archive,
};
use std::fs;
use support::*;

fn old_layout_archive(label: &str) -> (TempDir, std::path::PathBuf) {
    let spec = Run {
        run: 0xc1,
        era: Era::Python,
        start_ns: 2_000_000,
        batches: 6,
        width: 490,
        receivers: vec![RX1, RX2],
    };
    let source = TempDir::new(label);
    write_session_files(source.path(), capture_for(&spec, 1), capture_for(&spec, 9));
    write_run(source.path(), &spec);
    let zip = source.path().join("old.zip");
    // Old archives held CSV sidecars and string-typed table copies.
    let csv = b"CSI_DATA,0\n".repeat(200);
    zip_session(
        source.path(),
        &zip,
        &[
            (
                "original/trials/001_activity/attempt_01/receivers/rx-1/csi.csv",
                &csv,
            ),
            (
                "original/trials/001_activity/attempt_01/receivers/rx-1/radio_timing.csv",
                &csv,
            ),
            (
                "original/trials/001_activity/attempt_01/receivers/rx-1/gateway_timing.jsonl",
                &csv,
            ),
            (
                "tables/trials/001_activity/attempt_01/receivers/rx-1/csi.parquet",
                &csv,
            ),
            ("manifest.json", b"{\"format\":\"old\",\"version\":2}"),
        ],
    );
    (source, zip)
}

#[test]
fn migration_drops_derived_members_keeps_the_raw_record_and_proves_the_tables() {
    let (dir, zip) = old_layout_archive("mig");
    let target = dir.path().join("new.zip");
    let report = migrate_archive(&zip, &target, &MigrateOptions::default()).unwrap();
    assert_eq!(report.session_id, "20261113T000000000000Z");
    assert!(report.table_differences.is_empty());
    assert_eq!(report.dropped.get("csi.csv"), Some(&1));
    assert_eq!(report.dropped.get("csi.parquet"), Some(&1));
    assert_eq!(report.dropped.len(), 4);
    assert!(!target.with_extension("zip.tmp").exists());

    let manifest = archive_manifest(&target).unwrap();
    assert_eq!(manifest["version"], 3);
    let names: Vec<&str> = manifest["members"]
        .as_array()
        .unwrap()
        .iter()
        .map(|m| m["name"].as_str().unwrap())
        .collect();
    assert!(names.iter().any(|n| n.ends_with("envelopes.bin.zst")));
    assert!(
        names
            .iter()
            .any(|n| n.ends_with("transport/gateway/00000000000000c1/events.jsonl.zst"))
    );
    assert!(names.contains(&"original/session.json"));
    assert!(
        names
            .iter()
            .all(|n| !n.contains("/receivers/") && !n.starts_with("tables/"))
    );
    assert!(verify_archive(&target).unwrap().is_empty());

    // The new archive reads like the old one: logical paths, no .zst suffix.
    let files = vfs::open(&target).unwrap().files().to_vec();
    assert!(
        files.contains(&"original/transport/gateway/00000000000000c1/envelopes.bin".to_string())
    );

    // Independent check of the gate: convert both and compare.
    let options = ConvertOptions {
        scope: FrameScope::Attempts,
        ..ConvertOptions::default()
    };
    let a = TempDir::new("mig-a");
    let b = TempDir::new("mig-b");
    convert_session(vfs::open(&zip).unwrap().as_ref(), a.path(), &options).unwrap();
    convert_session(vfs::open(&target).unwrap().as_ref(), b.path(), &options).unwrap();
    assert!(tables_differences(a.path(), b.path()).unwrap().is_empty());
}

#[test]
fn migration_refuses_to_overwrite_and_leaves_no_partial_file() {
    let (dir, zip) = old_layout_archive("mig-overwrite");
    let target = dir.path().join("new.zip");
    migrate_archive(&zip, &target, &MigrateOptions::default()).unwrap();
    let before = fs::read(&target).unwrap();
    assert!(migrate_archive(&zip, &target, &MigrateOptions::default()).is_err());
    assert_eq!(fs::read(&target).unwrap(), before);
    // A source that is not a session fails without creating the destination.
    let bogus = dir.path().join("bogus.zip");
    fs::write(&bogus, b"not a zip").unwrap();
    let other = dir.path().join("other.zip");
    assert!(migrate_archive(&bogus, &other, &MigrateOptions::default()).is_err());
    assert!(!other.exists());
}

#[test]
fn verify_detects_tampering_with_a_member() {
    let (dir, zip) = old_layout_archive("mig-tamper");
    let target = dir.path().join("new.zip");
    migrate_archive(&zip, &target, &MigrateOptions::default()).unwrap();
    let mut bytes = fs::read(&target).unwrap();
    let middle = bytes.len() / 3;
    bytes[middle] ^= 0xff;
    let tampered = dir.path().join("tampered.zip");
    fs::write(&tampered, bytes).unwrap();
    let outcome = verify_archive(&tampered);
    assert!(outcome.map(|problems| !problems.is_empty()).unwrap_or(true));
}

#[test]
fn tables_differences_reports_changed_rows() {
    let (dir, zip) = old_layout_archive("diff");
    let options = ConvertOptions {
        scope: FrameScope::All,
        ..ConvertOptions::default()
    };
    let attempts = ConvertOptions {
        scope: FrameScope::Attempts,
        ..ConvertOptions::default()
    };
    let a = TempDir::new("diff-a");
    let b = TempDir::new("diff-b");
    convert_session(vfs::open(&zip).unwrap().as_ref(), a.path(), &options).unwrap();
    convert_session(vfs::open(&zip).unwrap().as_ref(), b.path(), &attempts).unwrap();
    let differences = tables_differences(a.path(), b.path()).unwrap();
    assert!(
        !differences.is_empty(),
        "all-frames and attempts-only tables differ"
    );
    drop(dir);
}

fn session_directory(label: &str, journal: bool) -> TempDir {
    let source = TempDir::new(label);
    if journal {
        let spec = Run {
            run: 0xc1,
            era: Era::Python,
            start_ns: 2_000_000,
            batches: 6,
            width: 490,
            receivers: vec![RX1, RX2],
        };
        write_session_files(source.path(), capture_for(&spec, 1), capture_for(&spec, 9));
        write_run(source.path(), &spec);
    } else {
        write_session_files(source.path(), 1_000, 9_000);
    }
    let receiver = source
        .path()
        .join("trials/001_activity/attempt_01/receivers/rx-1");
    fs::create_dir_all(&receiver).unwrap();
    fs::write(receiver.join("csi.csv"), b"CSI_DATA,0\n".repeat(500)).unwrap();
    fs::write(source.path().join("video.mp4"), [7u8; 4096]).unwrap();
    source
}

#[test]
fn a_session_directory_is_archived_with_its_sidecars_and_proven_by_the_gate() {
    let dir = session_directory("arch-dir", true);
    let target = dir.path().join("out/session.zip");
    let report = write_archive(dir.path(), &target, &ArchiveOptions::default()).unwrap();
    assert!(report.dropped.is_empty());
    assert!(report.table_differences.is_empty());
    assert!(verify_archive(&target).unwrap().is_empty());
    let manifest = archive_manifest(&target).unwrap();
    assert_eq!(manifest["version"], 3);
    let names: Vec<&str> = manifest["members"]
        .as_array()
        .unwrap()
        .iter()
        .map(|m| m["name"].as_str().unwrap())
        .collect();
    assert!(names.contains(&"original/session.json"));
    assert!(names.contains(&"original/trials/001_activity/attempt_01/receivers/rx-1/csi.csv.zst"));
    assert!(names.contains(&"original/video.mp4"));
    assert!(names.iter().any(|n| n.ends_with("envelopes.bin.zst")));
    // Logical paths match the directory's, behind the `original/` wrapper.
    let files = vfs::open(&target).unwrap().files().to_vec();
    assert!(
        files.contains(
            &"original/trials/001_activity/attempt_01/receivers/rx-1/csi.csv".to_string()
        )
    );
    assert!(dir.path().join("trials").is_dir()); // the source is untouched
}

#[test]
fn dropping_derived_members_removes_only_the_sidecars() {
    let dir = session_directory("arch-drop", true);
    let target = dir.path().join("out/session.zip");
    let options = ArchiveOptions {
        drop_derived: true,
        ..ArchiveOptions::default()
    };
    let report = write_archive(dir.path(), &target, &options).unwrap();
    assert_eq!(report.dropped.get("csi.csv"), Some(&1));
    let files = vfs::open(&target).unwrap().files().to_vec();
    assert!(!files.iter().any(|f| f.contains("/receivers/")));
    assert!(files.contains(&"original/video.mp4".to_string()));
}

#[test]
fn a_session_without_journals_is_archived_without_the_table_gate() {
    let dir = session_directory("arch-nojournal", false);
    let target = dir.path().join("out/session.zip");
    let report = write_archive(dir.path(), &target, &ArchiveOptions::default()).unwrap();
    assert!(report.table_differences.is_empty());
    assert!(verify_archive(&target).unwrap().is_empty());
}

#[test]
fn extraction_restores_a_directory_the_converter_reads_identically() {
    let dir = session_directory("arch-extract", true);
    let target = dir.path().join("out/session.zip");
    write_archive(dir.path(), &target, &ArchiveOptions::default()).unwrap();
    let extracted = dir.path().join("out/extracted");
    let count = extract_archive(&target, &extracted).unwrap();
    assert!(count > 5);
    assert!(extracted.join("session.json").is_file());
    assert!(extracted.join("video.mp4").is_file());
    assert!(extract_archive(&target, &extracted).is_err()); // never overwrites
    let options = ConvertOptions::default();
    let a = TempDir::new("arch-extract-a");
    let b = TempDir::new("arch-extract-b");
    convert_session(vfs::open(dir.path()).unwrap().as_ref(), a.path(), &options).unwrap();
    convert_session(vfs::open(&extracted).unwrap().as_ref(), b.path(), &options).unwrap();
    assert!(tables_differences(a.path(), b.path()).unwrap().is_empty());
}

#[test]
fn a_damaged_archive_is_not_extracted() {
    let dir = session_directory("arch-damaged", false);
    let target = dir.path().join("out/session.zip");
    write_archive(dir.path(), &target, &ArchiveOptions::default()).unwrap();
    let mut bytes = fs::read(&target).unwrap();
    // Flip a byte inside the stored video member.
    let position = bytes.windows(8).position(|w| w == [7u8; 8]).unwrap();
    bytes[position] ^= 0xff;
    fs::write(&target, bytes).unwrap();
    let extracted = dir.path().join("out/extracted");
    assert!(extract_archive(&target, &extracted).is_err());
    assert!(!extracted.exists());
    assert!(!extracted.with_extension("extracting").exists());
}

#[test]
fn one_member_can_be_extracted_without_the_rest() {
    let dir = session_directory("arch-member", false);
    let target = dir.path().join("out/session.zip");
    write_archive(dir.path(), &target, &ArchiveOptions::default()).unwrap();
    let source = vfs::open(&target).unwrap();
    let clip = dir.path().join("cache/nested/video.mp4");
    let written = extract_session_file(source.as_ref(), "video.mp4", &clip).unwrap();
    assert_eq!(written, 4096);
    assert_eq!(fs::read(&clip).unwrap(), vec![7u8; 4096]);
    assert!(!clip.with_extension("mp4.part").exists());
    assert!(extract_session_file(source.as_ref(), "../video.mp4", &clip).is_err());
    let missing = dir.path().join("cache/absent.bin");
    assert!(extract_session_file(source.as_ref(), "absent.bin", &missing).is_err());
    assert!(!missing.exists() && !missing.with_extension("bin.part").exists());
    // Zstandard members decode on the way out.
    let log = dir.path().join("cache/csi.csv");
    extract_session_file(
        source.as_ref(),
        "trials/001_activity/attempt_01/receivers/rx-1/csi.csv",
        &log,
    )
    .unwrap();
    assert_eq!(fs::read(&log).unwrap(), b"CSI_DATA,0\n".repeat(500));
}
