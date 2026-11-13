mod support;

use radio_storage::{
    MigrateOptions, ReviewOrigin, migrate_archive, open_session, open_source, resolve_source,
};
use std::fs;
use std::path::{Path, PathBuf};
use support::*;

const SESSION: &str = "20261113T000000000000Z";
const KEY: &str = "trials/001_activity/attempt_01";

type Patch = Box<dyn Fn(&mut serde_json::Value)>;

fn review_json(patch: impl FnOnce(&mut serde_json::Value)) -> Vec<u8> {
    let mut value = serde_json::json!({
        "schema_version": 1,
        "session_id": SESSION,
        "protocol_hash": "abc123",
        "revision": 3,
        "updated_at_utc": "2026-11-13T00:00:00+00:00",
        "metadata": {"participant_id": "p-07"},
        "attempts": {KEY: {
            "activity_label": "fall",
            "inclusion": "include",
            "quality": "good",
            "notes": "clean"
        }},
        "history": [{"revision": 3, "changes": []}],
    });
    patch(&mut value);
    serde_json::to_vec_pretty(&value).unwrap()
}

fn session(label: &str) -> TempDir {
    let dir = TempDir::new(label);
    write_session_files(&dir.path().join("session"), 1_000, 9_000);
    dir
}

fn write(path: &Path, bytes: &[u8]) -> PathBuf {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
    path.to_path_buf()
}

#[test]
fn a_session_without_a_review_keeps_its_recorded_values() {
    let dir = session("review-none");
    let opened = open_source(&dir.path().join("session"), None).unwrap();
    assert!(opened.review.is_none());
    let attempt = &opened.attempts[0];
    assert_eq!(attempt.attempt_key, KEY);
    assert_eq!(attempt.activity_label, "non_fall");
    assert_eq!(attempt.original_activity_label, "non_fall");
    assert_eq!(attempt.inclusion, "unreviewed");
    assert_eq!(attempt.review_revision, 0);
}

#[test]
fn an_annotation_overrides_the_label_without_touching_the_recording() {
    let dir = session("review-apply");
    let source = dir.path().join("session");
    let before = fs::read(source.join(KEY).join("attempt.json")).unwrap();
    write(
        &dir.path().join(format!("a/{SESSION}/session_review.json")),
        &review_json(|_| {}),
    );
    let opened = open_source(&source, Some(&dir.path().join("a"))).unwrap();
    let attempt = &opened.attempts[0];
    assert_eq!(attempt.activity_label, "fall");
    assert_eq!(attempt.original_activity_label, "non_fall");
    assert_eq!(attempt.inclusion, "include");
    assert_eq!(attempt.quality, "good");
    assert_eq!(attempt.notes, "clean");
    assert_eq!(attempt.review_revision, 3);
    let review = opened.review.unwrap();
    assert_eq!(review.origin, ReviewOrigin::Annotations);
    assert_eq!(review.review.metadata["participant_id"], "p-07");
    assert_eq!(
        fs::read(source.join(KEY).join("attempt.json")).unwrap(),
        before
    );
}

#[test]
fn the_source_fingerprint_ignores_the_review_but_the_review_hash_does_not() {
    let dir = session("review-hash");
    let source = dir.path().join("session");
    let path = write(
        &dir.path().join(format!("a/{SESSION}/session_review.json")),
        &review_json(|_| {}),
    );
    let first = open_source(&source, Some(&dir.path().join("a"))).unwrap();
    fs::write(
        &path,
        review_json(|v| v["attempts"][KEY]["quality"] = "bad".into()),
    )
    .unwrap();
    let second = open_source(&source, Some(&dir.path().join("a"))).unwrap();
    assert_eq!(first.source_fingerprint, second.source_fingerprint);
    assert_ne!(
        first.review.unwrap().review.content_sha256,
        second.review.unwrap().review.content_sha256
    );
}

#[test]
fn an_embedded_review_is_used_unless_an_annotation_exists() {
    let dir = session("review-embedded");
    let source = dir.path().join("session");
    write(&source.join("session_review.json"), &review_json(|_| {}));
    let embedded = open_source(&source, None).unwrap();
    let review = embedded.review.unwrap();
    assert_eq!(review.origin, ReviewOrigin::Embedded);
    assert!(review.path.is_none());

    let missing = dir.path().join("absent");
    let fallback = open_source(&source, Some(&missing)).unwrap();
    assert_eq!(fallback.review.unwrap().origin, ReviewOrigin::Embedded);

    write(
        &dir.path().join(format!("a/{SESSION}/session_review.json")),
        &review_json(|v| v["attempts"][KEY]["activity_label"] = "walk".into()),
    );
    let preferred = open_source(&source, Some(&dir.path().join("a"))).unwrap();
    assert_eq!(preferred.attempts[0].activity_label, "walk");
    assert_eq!(preferred.review.unwrap().origin, ReviewOrigin::Annotations);
}

#[test]
fn archives_and_directories_resolve_the_same_attempts() {
    let dir = session("review-archive");
    let source = dir.path().join("session");
    let zip = dir.path().join("s.zip");
    let review = review_json(|_| {});
    zip_session(&source, &zip, &[("original/session_review.json", &review)]);
    let from_zip = open_source(&zip, None).unwrap();
    write(&source.join("session_review.json"), &review);
    let from_dir = open_source(&source, None).unwrap();
    assert_eq!(from_zip.attempts, from_dir.attempts);
    assert_eq!(from_zip.session_id, SESSION);
}

#[test]
fn a_review_for_another_recording_is_rejected_not_ignored() {
    let dir = session("review-reject");
    let source = dir.path().join("session");
    let path = dir.path().join(format!("a/{SESSION}/session_review.json"));
    let cases: Vec<(&str, Patch)> = vec![
        (
            "belongs to session",
            Box::new(|v| v["session_id"] = "other".into()),
        ),
        (
            "protocol hash",
            Box::new(|v| v["protocol_hash"] = "zzz".into()),
        ),
        (
            "unknown attempt",
            Box::new(|v| {
                let entry = v["attempts"][KEY].clone();
                v["attempts"] = serde_json::json!({"trials/009_x/attempt_01": entry});
            }),
        ),
        ("unknown field", Box::new(|v| v["extra"] = 1.into())),
        (
            "invalid inclusion",
            Box::new(|v| v["attempts"][KEY]["inclusion"] = "maybe".into()),
        ),
        (
            "non-empty",
            Box::new(|v| v["attempts"][KEY]["activity_label"] = "  ".into()),
        ),
        (
            "invalid attempt key",
            Box::new(|v| {
                let entry = v["attempts"][KEY].clone();
                v["attempts"] = serde_json::json!({"trials/../x": entry});
            }),
        ),
        (
            "schema version",
            Box::new(|v| v["schema_version"] = 2.into()),
        ),
    ];
    for (needle, patch) in cases {
        write(&path, &review_json(|v| patch(v)));
        let error = open_source(&source, Some(&dir.path().join("a")))
            .unwrap_err()
            .to_string();
        assert!(error.contains(needle), "{needle}: {error}");
    }
}

fn old_layout_archive(root: &Path) -> PathBuf {
    let spec = Run {
        run: 0xc1,
        era: Era::Python,
        start_ns: 2_000_000,
        batches: 6,
        width: 490,
        receivers: vec![RX1, RX2],
    };
    let source = root.join("scratch");
    write_session_files(&source, capture_for(&spec, 1), capture_for(&spec, 9));
    write_run(&source, &spec);
    let zip = root.join(format!("data/old_raw/sessions/{SESSION}.zip"));
    fs::create_dir_all(zip.parent().unwrap()).unwrap();
    zip_session(
        &source,
        &zip,
        &[("manifest.json", b"{\"format\":\"old\",\"version\":2}")],
    );
    zip
}

#[test]
fn open_session_finds_the_archive_review_and_checks_the_predecessor() {
    let dir = TempDir::new("review-root");
    let root = dir.path();
    let predecessor = old_layout_archive(root);
    let current = root.join(format!("data/raw/sessions/{SESSION}.zip"));
    fs::create_dir_all(current.parent().unwrap()).unwrap();
    migrate_archive(&predecessor, &current, &MigrateOptions::default()).unwrap();
    write(
        &root.join(format!("data/annotations/{SESSION}/session_review.json")),
        &review_json(|_| {}),
    );

    assert_eq!(
        resolve_source(root, SESSION).unwrap(),
        (current.clone(), Some(3))
    );
    let opened = open_session(root, SESSION).unwrap();
    assert_eq!(opened.archive_version, Some(3));
    assert_eq!(opened.source, current);
    assert_eq!(opened.attempts[0].activity_label, "fall");
    assert_eq!(opened.review.unwrap().origin, ReviewOrigin::Annotations);

    // A changed predecessor no longer matches the recorded provenance.
    fs::remove_file(&predecessor).unwrap();
    zip_session(
        &root.join("scratch"),
        &predecessor,
        &[
            ("manifest.json", b"{\"format\":\"old\",\"version\":2}"),
            ("original/extra.txt", b"changed"),
        ],
    );
    let error = open_session(root, SESSION).unwrap_err().to_string();
    assert!(
        error.contains("source differs") || error.contains("zip"),
        "{error}"
    );
}

#[test]
fn open_session_rejects_identifiers_that_leave_the_data_directory() {
    let dir = TempDir::new("review-ids");
    for id in ["", ".", "..", "../x", "a/b"] {
        assert!(open_session(dir.path(), id).is_err(), "{id:?}");
    }
    assert!(open_session(dir.path(), SESSION).is_err()); // nothing there
}
