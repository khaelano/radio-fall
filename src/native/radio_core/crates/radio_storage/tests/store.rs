mod support;

use radio_storage::{
    EnsureStage, FrameQuery, FrameStore, annotations_dir_for, ensure_frames, tables_current, vfs,
};
use std::fs;
use support::*;

fn session(label: &str) -> TempDir {
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
    source
}

#[test]
fn tables_are_converted_once_and_reused_until_the_source_changes() {
    let source = session("store-ensure");
    let out = TempDir::new("store-ensure-out");
    let mut conversions = 0usize;
    let open = || vfs::open(source.path()).unwrap();
    let (store, converted) = ensure_frames(open().as_ref(), out.path(), false, &mut |stage| {
        conversions += usize::from(stage == EnsureStage::Converting);
    })
    .unwrap();
    assert!(converted && store.session_id() == "20261113T000000000000Z");
    assert!(tables_current(out.path(), store.source_fingerprint()));

    let (_, converted) = ensure_frames(open().as_ref(), out.path(), false, &mut |stage| {
        conversions += usize::from(stage == EnsureStage::Converting);
    })
    .unwrap();
    assert!(!converted);
    let (_, rebuilt) = ensure_frames(open().as_ref(), out.path(), true, &mut |stage| {
        conversions += usize::from(stage == EnsureStage::Converting);
    })
    .unwrap();
    assert!(rebuilt);

    // A changed attempt manifest changes the fingerprint and forces a conversion.
    let attempt = source
        .path()
        .join("trials/001_activity/attempt_01/attempt.json");
    let text = fs::read_to_string(&attempt)
        .unwrap()
        .replace("non_fall", "walk");
    fs::write(&attempt, text).unwrap();
    let (_, converted) = ensure_frames(open().as_ref(), out.path(), false, &mut |stage| {
        conversions += usize::from(stage == EnsureStage::Converting);
    })
    .unwrap();
    assert!(converted);
    assert_eq!(conversions, 3);
}

#[test]
fn concurrent_conversions_of_one_session_are_serialised_by_the_lock() {
    let source = session("store-lock");
    let out = TempDir::new("store-lock-out");
    let frames_dir = out.path().join("tables");
    let outcomes: Vec<(String, bool, bool)> = std::thread::scope(|scope| {
        let workers: Vec<_> = (0..4)
            .map(|_| {
                scope.spawn(|| {
                    let mut waited = false;
                    let (store, converted) = ensure_frames(
                        vfs::open(source.path()).unwrap().as_ref(),
                        &frames_dir,
                        false,
                        &mut |stage| waited |= stage == EnsureStage::Waiting,
                    )
                    .unwrap();
                    // Every caller must be able to read what it was handed.
                    let (_, batches) = store.frames(&FrameQuery::default()).unwrap();
                    assert!(batches.iter().map(|b| b.num_rows()).sum::<usize>() > 0);
                    store.attempts().unwrap();
                    store.phases().unwrap();
                    (store.source_fingerprint().to_string(), converted, waited)
                })
            })
            .collect();
        workers.into_iter().map(|w| w.join().unwrap()).collect()
    });
    let fingerprint = vfs::open(source.path()).unwrap().fingerprint().unwrap();
    assert!(outcomes.iter().all(|(found, _, _)| *found == fingerprint));
    // Callers that waited re-check currency and reuse the published tables.
    assert_eq!(
        outcomes
            .iter()
            .filter(|(_, converted, _)| *converted)
            .count(),
        1
    );
    assert!(tables_current(&frames_dir, &fingerprint));
    let manifest = FrameStore::open(&frames_dir).unwrap().manifest;
    assert_eq!(
        manifest["source_fingerprint"].as_str(),
        Some(fingerprint.as_str())
    );
    assert!(out.path().join("tables.lock").is_file());
    assert!(!frames_dir.join("frames.parquet.tmp").exists());
}

#[test]
fn an_incomplete_conversion_is_not_current() {
    let source = session("store-incomplete");
    let out = TempDir::new("store-incomplete-out");
    let (store, _) = ensure_frames(
        vfs::open(source.path()).unwrap().as_ref(),
        out.path(),
        false,
        &mut |_| {},
    )
    .unwrap();
    let fingerprint = store.source_fingerprint().to_string();
    fs::remove_file(out.path().join("phases.parquet")).unwrap();
    assert!(!tables_current(out.path(), &fingerprint));
    assert!(!tables_current(&out.path().join("absent"), &fingerprint));
}

#[test]
fn attempt_frames_are_the_frames_inside_the_window() {
    let source = session("store-window");
    let out = TempDir::new("store-window-out");
    let (store, _) = ensure_frames(
        vfs::open(source.path()).unwrap().as_ref(),
        out.path(),
        false,
        &mut |_| {},
    )
    .unwrap();
    let (_, all) = store.frames(&FrameQuery::default()).unwrap();
    let total: usize = all.iter().map(|b| b.num_rows()).sum();
    let (_, inside) = store
        .attempt_frames(0, None, Some(vec!["receiver_id".into()]))
        .unwrap();
    assert_eq!(inside.iter().map(|b| b.num_rows()).sum::<usize>(), total);
    let (schema, one) = store
        .attempt_frames(0, Some("rx-1".into()), Some(vec!["sequence".into()]))
        .unwrap();
    assert_eq!(schema.fields().len(), 1);
    let rows: usize = one.iter().map(|b| b.num_rows()).sum();
    assert!(rows > 0 && rows < total);
    assert!(store.attempt_frames(1, None, None).is_err());
    let (_, attempts) = store.attempts().unwrap();
    assert_eq!(attempts.iter().map(|b| b.num_rows()).sum::<usize>(), 1);
}

#[test]
fn an_empty_directory_is_not_a_store() {
    let dir = TempDir::new("store-empty");
    assert!(FrameStore::open(dir.path()).is_err());
}

#[test]
fn annotations_are_implied_only_by_the_raw_sessions_layout() {
    let dir = TempDir::new("store-annot");
    let sessions = dir.path().join("data/raw/sessions");
    fs::create_dir_all(&sessions).unwrap();
    let archive = sessions.join("s.zip");
    fs::write(&archive, b"x").unwrap();
    let expected = dir.path().canonicalize().unwrap().join("data/annotations");
    assert_eq!(annotations_dir_for(&archive), Some(expected));
    let elsewhere = dir.path().join("loose.zip");
    fs::write(&elsewhere, b"x").unwrap();
    assert_eq!(annotations_dir_for(&elsewhere), None);
    assert_eq!(annotations_dir_for(&dir.path().join("absent")), None);
}
