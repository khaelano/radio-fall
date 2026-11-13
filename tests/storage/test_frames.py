"""Typed frame tables, read through the Rust storage library."""

import json

import pytest

pa = pytest.importorskip("pyarrow")

from fall_detection._radio_native import (
    FrameStore,
    StorageError,
    storage_convert,
    storage_files,
    storage_read,
    storage_source_fingerprint,
    storage_verify,
)
from journal_builder import WIDTH, build_session, capture_ns, payload_for

convert_session = storage_convert
verify_session = storage_verify


@pytest.fixture(params=["python", "rust"])
def converted(tmp_path, request):
    source = build_session(tmp_path / "session", batches=8, era=request.param)
    out = tmp_path / "frames"
    report = convert_session(source, out)
    return source, out, report


def test_convert_reports_counts_and_era(converted):
    _, out, report = converted
    # The attempt window covers sequences 0..7 of the 16 journaled per receiver.
    assert report["frame_scope"] == "attempts"
    assert report["frames_in_journal"] == 32
    assert report["frames"] == 16
    assert report["receivers"] == {"rx-1": 8, "rx-2": 8}
    assert report["payload_width"] == WIDTH
    assert report["source_kind"].startswith("journal_")
    assert json.loads((out / "conversion.json").read_text())["frames"] == 16


def test_frames_keep_payload_and_capture_time(converted):
    _, out, _ = converted
    table = pa.table(
        FrameStore.open(out).frames(
            receiver_id="rx-2", columns=["sequence", "csi", "capture_time_ns"]
        )
    )
    assert table.num_rows == 8
    sequence = table.column("sequence").to_pylist()
    assert sequence == list(range(8))
    assert table.column("capture_time_ns").to_pylist() == [
        capture_ns(s) for s in sequence
    ]
    csi = table.column("csi").combine_chunks()
    assert csi[3].as_py() == payload_for(3)


def test_attempt_window_selects_by_capture_time(converted):
    _, out, _ = converted
    session = FrameStore.open(out)
    attempts = pa.table(session.attempts())
    assert attempts.num_rows == 1
    assert attempts.column("activity_label")[0].as_py() == "non_fall"
    inside = pa.table(
        session.attempt_frames(0, receiver_id="rx-1", columns=["sequence"])
    )
    # The window is [capture_ns(0), capture_ns(8)): sequences 0..7 per receiver.
    assert inside.column("sequence").to_pylist() == list(range(8))
    phases = pa.table(session.phases())
    assert phases.column("phase").to_pylist() == ["countdown", "action"]
    with pytest.raises(StorageError, match="out of range"):
        session.attempt_frames(3)


def test_all_scope_keeps_frames_between_attempts(tmp_path):
    source = build_session(tmp_path / "session", batches=8)
    report = convert_session(source, tmp_path / "all", scope="all")
    assert report["frame_scope"] == "all"
    assert report["frames"] == report["frames_in_journal"] == 32
    with pytest.raises(StorageError, match="scope"):
        convert_session(source, tmp_path / "bad", scope="everything")


def test_verify_reproduces_from_source_and_detects_changes(converted):
    source, out, _ = converted
    assert verify_session(out)["ok"]
    assert verify_session(out, source)["ok"]
    (out / "phases.parquet").write_bytes(b"corrupt")
    assert not verify_session(out)["ok"]


def test_missing_columns_and_missing_sessions_raise(tmp_path, converted):
    _, out, _ = converted
    with pytest.raises(StorageError):
        FrameStore.open(out).frames(columns=["no_such_column"])
    with pytest.raises(StorageError):
        FrameStore.open(tmp_path / "absent")


def test_ensure_frames_reuses_current_tables_and_reconverts_stale_ones(tmp_path):
    source = build_session(tmp_path / "session", batches=4)
    frames = tmp_path / "frames"
    messages: list[str] = []

    def ensure(**options):
        return FrameStore.ensure(
            str(source), str(frames), progress=messages.append, **options
        )

    first = ensure()
    stamp = (frames / "frames.parquet").stat().st_mtime_ns
    again = ensure()
    assert len(messages) == 1  # the second call converted nothing
    assert (frames / "frames.parquet").stat().st_mtime_ns == stamp
    assert again.source_fingerprint == first.source_fingerprint
    assert ensure(rebuild=True).manifest["frames"] == 8
    before = storage_source_fingerprint(str(source))
    (source / "session.json").write_text(
        (source / "session.json").read_text().replace("feedface", "deadbeef")
    )
    assert storage_source_fingerprint(str(source)) != before
    ensure()
    assert len(messages) == 3  # the rebuild above also announced itself
    assert FrameStore.open(frames).manifest["protocol_hash"] == "deadbeef"


def test_concurrent_ensure_from_two_processes_publishes_consistent_tables(tmp_path):
    import multiprocessing

    from ensure_worker import ensure_tables

    source = build_session(tmp_path / "session", batches=8)
    frames = tmp_path / "frames"
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    workers = [
        context.Process(
            target=ensure_tables, args=(str(source), str(frames), barrier, queue)
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=120) for _ in workers]
    for worker in workers:
        worker.join(timeout=60)
    assert [result.get("error") for result in results] == [None, None]
    assert all(worker.exitcode == 0 for worker in workers)

    fingerprint = storage_source_fingerprint(str(source))
    assert {result["fingerprint"] for result in results} == {fingerprint}
    assert all(result["frames"] == 16 for result in results)
    assert all(result["attempts"] == 1 for result in results)
    # Exactly one process converted; the other waited for it or found it done.
    converting = [
        message
        for result in results
        for message in result["messages"]
        if message.startswith("Converting")
    ]
    assert len(converting) == 1
    assert FrameStore.open(frames).source_fingerprint == fingerprint
    assert (tmp_path / "frames.lock").is_file()


def test_directory_and_archive_sources_look_the_same(tmp_path):
    import zipfile

    source = build_session(tmp_path / "session", batches=2)
    archive = tmp_path / "session.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                bundle.write(path, "original/" + path.relative_to(source).as_posix())
    assert storage_files(str(source)) == storage_files(str(archive))
    assert "trials/001_activity/attempt_01/attempt.json" in storage_files(str(archive))
    assert storage_read(str(archive), "session.json") == storage_read(
        str(source), "session.json"
    )
    with pytest.raises(StorageError):
        storage_read(str(archive), "../session.json")
    with pytest.raises(StorageError):
        storage_read(str(archive), "absent.json")
    one = convert_session(source, tmp_path / "from-dir")
    two = convert_session(archive, tmp_path / "from-zip")
    assert one["frames"] == two["frames"]
    assert one["source_fingerprint"] != two["source_fingerprint"]
