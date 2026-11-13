mod support;

use radio_storage::vfs::read_file;
use std::fs;
use support::TempDir;

fn frame(data: &[u8]) -> Vec<u8> {
    zstd::encode_all(data, 3).unwrap()
}

#[test]
fn plain_and_compressed_files_read_alike() {
    let dir = TempDir::new("read-file");
    fs::write(dir.path().join("plain.jsonl"), b"one\n").unwrap();
    fs::write(dir.path().join("log.jsonl.zst"), frame(b"two\n")).unwrap();
    assert_eq!(
        read_file(&dir.path().join("plain.jsonl")).unwrap(),
        b"one\n"
    );
    // The logical name resolves to the `.zst` sibling.
    assert_eq!(read_file(&dir.path().join("log.jsonl")).unwrap(), b"two\n");
    assert_eq!(
        read_file(&dir.path().join("log.jsonl.zst")).unwrap(),
        b"two\n"
    );
}

#[test]
fn concatenated_frames_are_decoded_in_order() {
    let dir = TempDir::new("read-frames");
    let mut data = frame(b"one\n");
    data.extend(frame(b"two\n"));
    data.extend(frame(b"three\n"));
    fs::write(dir.path().join("events.jsonl.zst"), data).unwrap();
    assert_eq!(
        read_file(&dir.path().join("events.jsonl")).unwrap(),
        b"one\ntwo\nthree\n"
    );
}

#[test]
fn a_truncated_final_frame_is_an_error() {
    let dir = TempDir::new("read-truncated");
    let mut data = frame(b"one\n");
    data.extend(frame(b"two\n"));
    data.pop();
    fs::write(dir.path().join("events.jsonl.zst"), data).unwrap();
    assert!(read_file(&dir.path().join("events.jsonl")).is_err());
}

#[test]
fn a_missing_file_names_the_path() {
    let dir = TempDir::new("read-missing");
    let error = read_file(&dir.path().join("absent.jsonl")).unwrap_err();
    assert!(error.to_string().contains("absent.jsonl"), "{error}");
}
