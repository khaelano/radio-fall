mod support;

use arrow_array::{
    Array, BooleanArray, FixedSizeBinaryArray, Float32Array, Int64Array, RecordBatch, StringArray,
    UInt16Array, UInt32Array,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use radio_storage::{
    ConvertOptions, FrameQuery, FrameScope, convert_session, read_frames, verify_against_source,
    verify_dir, vfs,
};
use radio_transport::wire::{Batch, RawBatch};
use std::fs;
use std::path::Path;
use support::*;

fn all_frames() -> ConvertOptions {
    ConvertOptions {
        scope: FrameScope::All,
        ..ConvertOptions::default()
    }
}

fn run(id: u64, era: Era, start_ns: u64, batches: u32) -> Run {
    Run {
        run: id,
        era,
        start_ns,
        batches,
        width: 490,
        receivers: vec![RX1, RX2],
    }
}

fn read_all(path: &Path) -> RecordBatch {
    let reader = ParquetRecordBatchReaderBuilder::try_new(fs::File::open(path).unwrap())
        .unwrap()
        .build()
        .unwrap();
    let batches: Vec<RecordBatch> = reader.map(|b| b.unwrap()).collect();
    arrow_select::concat::concat_batches(&batches[0].schema(), &batches).unwrap()
}

fn column<'a, T: 'static>(batch: &'a RecordBatch, name: &str) -> &'a T {
    batch
        .column_by_name(name)
        .unwrap()
        .as_any()
        .downcast_ref::<T>()
        .unwrap()
}

fn session(label: &str, runs: &[Run]) -> TempDir {
    let dir = TempDir::new(label);
    write_session_files(dir.path(), 1_000_000, 9_000_000);
    for run in runs {
        write_run(dir.path(), run);
    }
    dir
}

fn convert(source: &Path, out: &Path) -> radio_storage::ConversionReport {
    let source = vfs::open(source).unwrap();
    convert_session(source.as_ref(), out, &all_frames()).unwrap()
}

#[test]
fn raw_parser_matches_the_full_decoder() {
    let frames = [Frame::new(RX1, 4, 490), Frame::new(RX1, 5, 490)];
    let bytes = envelope(5, 9, 77, 3, RX1, &frames);
    let raw = RawBatch::parse(&bytes).unwrap();
    let full = Batch::decode(&bytes).unwrap();
    assert_eq!(raw.run, full.run);
    assert_eq!(
        (raw.tx_boot, raw.rx_boot, raw.id),
        (full.tx_boot, full.rx_boot, full.id)
    );
    assert_eq!(raw.records.len(), full.records.len());
    for (a, b) in raw.records.iter().zip(&full.records) {
        assert_eq!(a.sequence(), b.sequence);
        assert_eq!(a.transport_sequence(), b.transport_sequence);
        assert_eq!(a.rx_radio_us(), b.timestamp);
        assert_eq!(a.rssi(), b.rssi);
        assert_eq!(a.noise_floor(), b.noise);
        assert_eq!(a.fields(), b.fields);
        assert_eq!(a.sig_len(), b.sig_len);
        assert_eq!(a.tx_enqueue_us(), b.tx_timestamp);
        assert_eq!(a.rx_callback_us(), b.callback);
        assert_eq!(a.payload(), &b.raw[..]);
    }
}

#[test]
fn raw_parser_rejects_corruption() {
    let frames = [Frame::new(RX1, 4, 490)];
    let mut bytes = envelope(5, 9, 77, 3, RX1, &frames);
    let last = bytes.len() - 6;
    bytes[last] ^= 0xff;
    assert!(RawBatch::parse(&bytes).is_err());
}

#[test]
fn python_era_session_round_trips() {
    let source = session(
        "py",
        &[
            run(0xaa, Era::Python, 2_000_000, 6),
            run(0xbb, Era::Python, 900_000_000, 3),
        ],
    );
    let out = TempDir::new("py-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.source_kind, "journal_python_era");
    assert_eq!(report.frames, (6 + 3) * 2 * 2);
    assert_eq!(report.payload_width, Some(490));
    let table = read_all(&out.path().join("frames.parquet"));
    assert_eq!(table.num_rows() as u64, report.frames);
    // Run-major, then receiver, then journal order.
    let run_index = column::<UInt16Array>(&table, "run_index");
    let receiver = column::<StringArray>(&table, "receiver_id");
    let sequence = column::<UInt32Array>(&table, "sequence");
    assert_eq!(run_index.value(0), 0);
    assert_eq!(receiver.value(0), "rx-1");
    assert_eq!(sequence.value(0), 0);
    assert_eq!(sequence.value(11), 11);
    assert_eq!(receiver.value(12), "rx-2");
    assert_eq!(run_index.value(table.num_rows() - 1), 1);
    // Capture time, uncertainty and payload come through unchanged.
    let capture = column::<Int64Array>(&table, "capture_time_ns");
    assert_eq!(
        capture.value(3),
        capture_for(&run(0xaa, Era::Python, 2_000_000, 6), 3)
    );
    assert_eq!(
        column::<Float32Array>(&table, "capture_uncertainty_us").value(0),
        1500.5
    );
    assert!(column::<BooleanArray>(&table, "timely").value(0));
    let csi = column::<FixedSizeBinaryArray>(&table, "csi");
    assert_eq!(csi.value(5), &Frame::new(RX1, 5, 490).payload[..]);
    let transmitter = column::<StringArray>(&table, "transmitter_mac");
    assert!((0..table.num_rows()).all(|i| transmitter.value(i) == mac_text(&TX)));
    let check = verify_dir(out.path()).unwrap();
    assert!(check.ok(), "{:?}", check.problems);
    let source_vfs = vfs::open(source.path()).unwrap();
    let again = verify_against_source(source_vfs.as_ref(), out.path(), &all_frames()).unwrap();
    assert!(again.ok(), "{:?}", again.problems);
}

#[test]
fn rust_era_session_uses_batch_acceptance() {
    let source = session("rs", &[run(0xcc, Era::Rust, 2_000_000, 4)]);
    let out = TempDir::new("rs-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.source_kind, "journal_rust_era");
    let table = read_all(&out.path().join("frames.parquet"));
    let capture = column::<Int64Array>(&table, "capture_time_ns");
    assert!(capture.is_null(0), "sequence 0 has no mapped capture time");
    assert!(!capture.is_null(1));
    assert_eq!(
        column::<Float32Array>(&table, "capture_uncertainty_us").value(2),
        250.0
    );
    assert!(column::<BooleanArray>(&table, "timely").is_null(0));
    assert_eq!(report.runs[0].frames_without_capture, 2); // one per receiver
}

#[test]
fn empty_runs_and_unrelated_events_are_tolerated() {
    let source = session("empty", &[run(0xdd, Era::Python, 2_000_000, 2)]);
    let empty = source.path().join("transport/gateway/00000000000000ee");
    fs::create_dir_all(&empty).unwrap();
    fs::write(empty.join("envelopes.bin"), b"").unwrap();
    fs::write(empty.join("events.jsonl"), b"").unwrap();
    let out = TempDir::new("empty-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.runs.len(), 2);
    assert!(
        report
            .runs
            .iter()
            .any(|r| r.run_index.is_none() && r.frames == 0)
    );
    assert_eq!(report.frames, 8);
    assert!(verify_dir(out.path()).unwrap().ok());
}

#[test]
fn session_without_frames_still_writes_tables() {
    let source = TempDir::new("none");
    write_session_files(source.path(), 10, 20);
    let out = TempDir::new("none-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.frames, 0);
    assert_eq!(report.source_kind, "journal_empty");
    assert!(verify_dir(out.path()).unwrap().ok());
}

#[test]
fn torn_tails_are_reported_not_fatal() {
    let source = session("torn", &[run(0xff, Era::Python, 2_000_000, 3)]);
    let dir = source.path().join("transport/gateway/00000000000000ff");
    let mut journal = fs::read(dir.join("envelopes.bin")).unwrap();
    journal.truncate(journal.len() - 40);
    fs::write(dir.join("envelopes.bin"), journal).unwrap();
    let mut events = fs::read(dir.join("events.jsonl")).unwrap();
    events.extend(b"{\"kind\":\"record\",\"seq"); // unterminated final line
    fs::write(dir.join("events.jsonl"), events).unwrap();
    let out = TempDir::new("torn-out");
    let report = convert(source.path(), out.path());
    assert!(report.runs[0].torn_journal);
    assert_eq!(report.runs[0].torn_event_lines, 1);
    assert_eq!(report.frames, 3 * 2 * 2 - 2); // last envelope (two frames) lost
    assert!(verify_dir(out.path()).unwrap().ok());
}

#[test]
fn corrupt_envelope_is_an_error() {
    let source = session("corrupt", &[run(0x11, Era::Python, 2_000_000, 2)]);
    let path = source
        .path()
        .join("transport/gateway/0000000000000011/envelopes.bin");
    let mut journal = fs::read(&path).unwrap();
    journal[40] ^= 0xff;
    fs::write(&path, journal).unwrap();
    let out = TempDir::new("corrupt-out");
    let source = vfs::open(source.path()).unwrap();
    assert!(convert_session(source.as_ref(), out.path(), &all_frames()).is_err());
}

#[test]
fn mismatched_acceptance_event_is_an_error() {
    let source = session("mismatch", &[run(0x22, Era::Rust, 2_000_000, 2)]);
    let path = source
        .path()
        .join("transport/gateway/0000000000000022/events.jsonl");
    let text = fs::read_to_string(&path)
        .unwrap()
        .replace("\"batch\":0", "\"batch\":9");
    fs::write(&path, text).unwrap();
    let out = TempDir::new("mismatch-out");
    let source = vfs::open(source.path()).unwrap();
    let error = convert_session(source.as_ref(), out.path(), &all_frames()).unwrap_err();
    assert!(error.0.contains("does not match envelope"), "{}", error.0);
}

#[test]
fn variable_payload_falls_back_to_binary() {
    let mut varied = run(0x33, Era::Python, 2_000_000, 2);
    let source = TempDir::new("var");
    write_session_files(source.path(), 1_000_000, 9_000_000);
    write_run(source.path(), &varied);
    // Rewrite the second run with a different payload width in the same session.
    varied.run = 0x34;
    varied.start_ns = 900_000_000;
    varied.width = 244;
    write_run(source.path(), &varied);
    let out = TempDir::new("var-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.payload_width, None);
    let table = read_all(&out.path().join("frames.parquet"));
    let csi = column::<arrow_array::BinaryArray>(&table, "csi");
    assert_eq!(csi.value(0).len(), 490);
    assert_eq!(csi.value(table.num_rows() - 1).len(), 244);
}

#[test]
fn backward_capture_steps_are_reported_but_not_failures() {
    let source = session("back", &[run(0x44, Era::Python, 2_000_000, 3)]);
    let path = source
        .path()
        .join("transport/gateway/0000000000000044/events.jsonl");
    let mut lines: Vec<String> = fs::read_to_string(&path)
        .unwrap()
        .lines()
        .map(String::from)
        .collect();
    // Move the capture time of one receiver-1 frame back by 50 ms.
    let target = lines
        .iter()
        .position(|l| l.contains("\"receiver_id\":\"rx-1\"") && l.contains("\"sequence\":3,"))
        .unwrap();
    let mut value: serde_json::Value = serde_json::from_str(&lines[target]).unwrap();
    let before = value["capture_host_ns"].as_i64().unwrap();
    value["capture_host_ns"] = (before - 50_000_000).into();
    lines[target] = value.to_string();
    fs::write(&path, lines.join("\n") + "\n").unwrap();
    let out = TempDir::new("back-out");
    let report = convert(source.path(), out.path());
    assert_eq!(report.runs[0].capture_backward_steps, 1);
    let check = verify_dir(out.path()).unwrap();
    assert!(check.ok(), "{:?}", check.problems);
    assert_eq!(check.capture_backward_steps, 1);
}

#[test]
fn verify_detects_tampering() {
    let source = session("tamper", &[run(0x55, Era::Python, 2_000_000, 2)]);
    let out = TempDir::new("tamper-out");
    convert(source.path(), out.path());
    let frames = out.path().join("frames.parquet");
    let mut bytes = fs::read(&frames).unwrap();
    let middle = bytes.len() / 2;
    bytes[middle] ^= 0x01;
    fs::write(&frames, bytes).unwrap();
    let outcome = verify_dir(out.path());
    assert!(outcome.map(|r| !r.ok()).unwrap_or(true));
}

#[test]
fn read_frames_filters_receiver_and_capture_range() {
    let spec = run(0x66, Era::Python, 2_000_000, 40);
    let source = session("read", std::slice::from_ref(&spec));
    let out = TempDir::new("read-out");
    let options = ConvertOptions {
        row_group_rows: 10,
        zstd_level: 3,
        scope: FrameScope::All,
    };
    let vfs_source = vfs::open(source.path()).unwrap();
    convert_session(vfs_source.as_ref(), out.path(), &options).unwrap();
    let path = out.path().join("frames.parquet");
    let low = capture_for(&spec, 20);
    let high = capture_for(&spec, 40);
    let query = FrameQuery {
        receiver_id: Some("rx-2".into()),
        capture_start_ns: Some(low),
        capture_end_ns: Some(high),
        columns: Some(vec!["sequence".into(), "receiver_id".into()]),
    };
    let batches = read_frames(&path, &query).unwrap();
    let rows: usize = batches.iter().map(|b| b.num_rows()).sum();
    assert_eq!(rows, 20);
    for batch in &batches {
        assert_eq!(batch.num_columns(), 2);
        let ids = column::<StringArray>(batch, "receiver_id");
        assert!((0..ids.len()).all(|i| ids.value(i) == "rx-2"));
        let seq = column::<UInt32Array>(batch, "sequence");
        assert!((0..seq.len()).all(|i| (20..40).contains(&seq.value(i))));
    }
    // No filter returns everything.
    let all = read_frames(&path, &FrameQuery::default()).unwrap();
    assert_eq!(all.iter().map(|b| b.num_rows()).sum::<usize>(), 40 * 2 * 2);
    // Unknown column is an error.
    assert!(
        read_frames(
            &path,
            &FrameQuery {
                columns: Some(vec!["nope".into()]),
                ..Default::default()
            }
        )
        .is_err()
    );
}

#[test]
fn attempts_and_phases_are_written() {
    let source = session("annot", &[run(0x77, Era::Python, 2_000_000, 2)]);
    let out = TempDir::new("annot-out");
    convert(source.path(), out.path());
    let attempts = read_all(&out.path().join("attempts.parquet"));
    assert_eq!(attempts.num_rows(), 1);
    assert_eq!(
        column::<StringArray>(&attempts, "activity_label").value(0),
        "non_fall"
    );
    assert_eq!(
        column::<Int64Array>(&attempts, "start_ns").value(0),
        1_000_000
    );
    assert_eq!(
        column::<Int64Array>(&attempts, "end_ns").value(0),
        9_000_000
    );
    let phases = read_all(&out.path().join("phases.parquet"));
    assert_eq!(phases.num_rows(), 3);
    let names = column::<StringArray>(&phases, "phase");
    assert_eq!(
        (names.value(0), names.value(1), names.value(2)),
        ("countdown", "action", "recovery")
    );
    let end = column::<Int64Array>(&phases, "end_ns");
    assert_eq!(end.value(0), 1_001_000); // ends where the next phase starts
    assert_eq!(end.value(1), 1_003_000);
    assert_eq!(end.value(2), 9_000_000); // last phase ends with the attempt
}

#[test]
fn zip_sources_match_directory_sources() {
    use std::io::Write;
    let spec = run(0x88, Era::Python, 2_000_000, 3);
    let source = session("zipsrc", std::slice::from_ref(&spec));
    let archive = TempDir::new("zip");
    let zip_path = archive.path().join("session.zip");
    {
        let file = fs::File::create(&zip_path).unwrap();
        let mut writer = zip::ZipWriter::new(file);
        let plain = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);
        let zstd = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Zstd);
        let mut stack = vec![source.path().to_path_buf()];
        while let Some(dir) = stack.pop() {
            for entry in fs::read_dir(&dir).unwrap() {
                let path = entry.unwrap().path();
                if path.is_dir() {
                    stack.push(path);
                    continue;
                }
                let relative = path
                    .strip_prefix(source.path())
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                let data = fs::read(&path).unwrap();
                if relative.ends_with("events.jsonl") && relative.contains("transport") {
                    // Zstandard members carry a .zst suffix and decode transparently.
                    writer
                        .start_file(format!("original/{relative}.zst"), zstd)
                        .unwrap();
                    writer
                        .write_all(&zstd::encode_all(&data[..], 3).unwrap())
                        .unwrap();
                } else {
                    writer
                        .start_file(format!("original/{relative}"), plain)
                        .unwrap();
                    writer.write_all(&data).unwrap();
                }
            }
        }
        writer.finish().unwrap();
    }
    let from_dir = TempDir::new("zip-dir-out");
    let from_zip = TempDir::new("zip-zip-out");
    convert(source.path(), from_dir.path());
    let report = convert(&zip_path, from_zip.path());
    assert_eq!(report.session_id, "20261113T000000000000Z");
    let a = read_all(&from_dir.path().join("frames.parquet"));
    let b = read_all(&from_zip.path().join("frames.parquet"));
    assert_eq!(a, b);
    assert!(verify_dir(from_zip.path()).unwrap().ok());
}

#[test]
fn spaced_json_events_are_still_matched() {
    for era in [Era::Python, Era::Rust] {
        let source = session("spaced", &[run(0x99, era, 2_000_000, 3)]);
        let path = source
            .path()
            .join("transport/gateway/0000000000000099/events.jsonl");
        let text = fs::read_to_string(&path)
            .unwrap()
            .replace("\":", "\": ")
            .replace(",\"", ", \"");
        fs::write(&path, text).unwrap();
        let out = TempDir::new("spaced-out");
        let report = convert(source.path(), out.path());
        let expected_missing = if era == Era::Rust { 2 } else { 0 };
        assert_eq!(report.runs[0].frames_without_capture, expected_missing);
        assert_eq!(report.frames, 3 * 2 * 2);
    }
}

fn windowed(label: &str, spec: &Run, from: u32, to: u32) -> TempDir {
    let dir = TempDir::new(label);
    write_session_files(dir.path(), capture_for(spec, from), capture_for(spec, to));
    write_run(dir.path(), spec);
    dir
}

#[test]
fn attempts_scope_keeps_only_frames_inside_windows() {
    for era in [Era::Python, Era::Rust] {
        let spec = run(0xa1, era, 2_000_000, 6); // sequences 0..12 per receiver
        let source = windowed("scope", &spec, 2, 6);
        let out = TempDir::new("scope-out");
        let vfs_source = vfs::open(source.path()).unwrap();
        let report =
            convert_session(vfs_source.as_ref(), out.path(), &ConvertOptions::default()).unwrap();
        assert_eq!(report.frame_scope, "attempts");
        assert_eq!(report.frames_in_journal, 24);
        assert_eq!(report.frames, 8); // sequences 2..6 on two receivers
        assert_eq!(report.runs[0].frames_excluded, 16);
        let table = read_all(&out.path().join("frames.parquet"));
        let sequence = column::<UInt32Array>(&table, "sequence");
        let values: Vec<u32> = (0..sequence.len()).map(|i| sequence.value(i)).collect();
        assert_eq!(values, vec![2, 3, 4, 5, 2, 3, 4, 5]);
        assert!(verify_dir(out.path()).unwrap().ok());
        // The window is half open: the end frame is excluded, the start included.
        assert!(!values.contains(&6));
    }
}

#[test]
fn attempts_scope_drops_frames_without_capture_time() {
    let spec = run(0xa2, Era::Rust, 2_000_000, 4); // sequence 0 has no capture time
    let source = windowed("scope-null", &spec, 0, 8);
    let out = TempDir::new("scope-null-out");
    let vfs_source = vfs::open(source.path()).unwrap();
    let report =
        convert_session(vfs_source.as_ref(), out.path(), &ConvertOptions::default()).unwrap();
    // Frames 0 lack a capture time on both receivers, so they cannot be placed.
    assert_eq!(report.frames_in_journal, 16);
    assert_eq!(report.frames, 14);
}

#[test]
fn sessions_without_attempts_keep_all_frames() {
    let source = TempDir::new("noattempts");
    fs::write(
        source.path().join("session.json"),
        r#"{"session_id":"s","protocol_hash":"p","environment":{"receiver_ids":{}}}"#,
    )
    .unwrap();
    write_run(source.path(), &run(0xa3, Era::Python, 2_000_000, 2));
    let out = TempDir::new("noattempts-out");
    let vfs_source = vfs::open(source.path()).unwrap();
    let report =
        convert_session(vfs_source.as_ref(), out.path(), &ConvertOptions::default()).unwrap();
    assert_eq!(report.frame_scope, "all");
    assert_eq!(report.frames, 8);
    assert_eq!(report.frames_excluded_total(), 0);
}

#[test]
fn directory_fingerprint_ignores_review_and_video_but_not_inputs() {
    let source = session("fingerprint", &[run(0xb1, Era::Python, 2_000_000, 2)]);
    let fingerprint = |dir: &Path| vfs::open(dir).unwrap().fingerprint().unwrap();
    let before = fingerprint(source.path());
    fs::write(
        source.path().join("session_review.json"),
        b"{\"revision\":1}",
    )
    .unwrap();
    fs::write(
        source
            .path()
            .join("trials/001_activity/attempt_01/camera.mp4"),
        b"video",
    )
    .unwrap();
    assert_eq!(fingerprint(source.path()), before);
    let manifest = source.path().join("session.json");
    let text = fs::read_to_string(&manifest)
        .unwrap()
        .replace("abc123", "abc124");
    fs::write(&manifest, text).unwrap();
    assert_ne!(fingerprint(source.path()), before);
}
