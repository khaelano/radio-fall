"""Analysis view of a session, built from the typed frame tables.

The Rust storage crate converts raw journals into ``frames.parquet``. This
module adds the analysis-level context on top of those tables: attempt and phase
annotations with review decisions, and per-recording packet tables with the
columns that preprocessing expects. Nothing here parses CSV text.

The attempt window rule, the capture-time sort, the single-epoch check, and the
``is_sensing`` definition follow the loader that this module replaces.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from .._radio_native import (
    FrameStore,
    storage_files,
    storage_open_source,
    storage_read,
)
from ..session_inspector.models import SessionBundle, load_session

ANALYSIS_SCHEMA_VERSION = 1
"""Version of the attempt, phase, and packet semantics defined in this module."""

PHASE_NAMES = {"countdown": "preparation", "action": "action", "recovery": "resting"}
TIME_SOURCE = "gateway capture clock mapping"
ANNOTATION_SOURCE = "collection_cue"

_MANIFESTS = {"session.json", "protocol.json", "events.jsonl", "session_review.json"}
_ATTEMPT_COLUMNS = [
    "session_id",
    "participant_id",
    "attempt_key",
    "attempt_id",
    "trial_ordinal",
    "attempt",
    "repetition",
    "scenario_id",
    "activity_label",
    "original_activity_label",
    "status",
    "inclusion",
    "quality",
    "review_revision",
    "start_direction",
    "end_direction",
    "started_monotonic_ns",
    "ended_monotonic_ns",
    "receiver_ids",
]
_PHASE_COLUMNS = [
    "session_id",
    "attempt_key",
    "trial_ordinal",
    "attempt",
    "scenario_id",
    "phase",
    "collection_phase",
    "start_ns",
    "end_ns",
    "annotation_source",
    "review_revision",
]
_ATTEMPT_CONSTANTS = [
    name
    for name in _ATTEMPT_COLUMNS
    if name not in {"receiver_ids", "started_monotonic_ns", "ended_monotonic_ns"}
]
_HEADER_COLUMNS = (
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "ant",
    "rx_state",
)
_STRING_ATTEMPT_COLUMNS = {
    "session_id",
    "participant_id",
    "attempt_key",
    "attempt_id",
    "scenario_id",
    "activity_label",
    "original_activity_label",
    "status",
    "inclusion",
    "quality",
    "start_direction",
    "end_direction",
}


_INT_COLUMNS = (
    "trial_ordinal",
    "attempt",
    "repetition",
    "review_revision",
    "source_row",
    "id",
    "sequence",
    "transport_sequence",
    "rssi",
    "noise_floor",
    "sig_len",
    "len",
    "first_word",
    "local_timestamp",
    "rx_radio_timestamp_us",
    "tx_enqueue_timestamp_us",
    "rx_callback_timestamp_us",
    "host_receive_monotonic_ns",
    "capture_time_ns",
    "attempt_started_monotonic_ns",
    "attempt_ended_monotonic_ns",
    *_HEADER_COLUMNS,
    "sig_mode",
    "mcs",
)
_STRING_COLUMNS = (
    *sorted(_STRING_ATTEMPT_COLUMNS),
    "receiver_id",
    "phase",
    "collection_phase",
    "annotation_source",
    "type",
    "mac",
    "receiver_mac",
    "time_source",
    "run_id",
    "transmitter_boot_id",
    "receiver_boot_id",
)
PACKET_TYPES: dict[str, pa.DataType] = {
    **dict.fromkeys(_STRING_COLUMNS, pa.string()),
    **dict.fromkeys(_INT_COLUMNS, pa.int64()),
    **dict.fromkeys(
        ("time_seconds", "clock_uncertainty_us", "nominal_rate_hz"), pa.float64()
    ),
    "is_sensing": pa.bool_(),
    "driver_valid": pa.bool_(),
    "csi_i": pa.list_(pa.int16()),
    "csi_q": pa.list_(pa.int16()),
}
"""Canonical Arrow type of every packet column, so empty recordings agree."""


@contextlib.contextmanager
def _manifest_root(source: Path) -> Iterator[Path]:
    """Yield a directory holding only the small manifests of a session.

    The library decodes archive members and compressed streams, so directories
    and archives are handled alike and no receiver data is copied.
    """
    with tempfile.TemporaryDirectory(prefix=".manifests-") as temporary:
        root = Path(temporary) / "session"
        for name in storage_files(str(source)):
            if name in _MANIFESTS or (
                name.startswith("trials/") and name.endswith("/attempt.json")
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(storage_read(str(source), name))
        yield root


def _attempt_table(
    session: SessionBundle,
    frames: FrameStore,
    indices: dict[tuple[int, int], int],
    opened: dict[str, Any],
) -> pd.DataFrame:
    """Join recorded attempts with the effective review decisions.

    Label, inclusion, quality and revision come from the shared storage library
    (``opened``), so every consumer applies a review the same way.
    """
    effective = {item["attempt_key"]: item for item in opened["attempts"]}
    metadata = opened["review"]["metadata"] if opened["review"] else {}
    trials = {trial.ordinal: trial for trial in session.trials}
    rows = []
    for attempt in session.attempts:
        decision = effective[attempt.key]
        trial = trials.get(attempt.trial_ordinal)
        attributes = trial.attributes if trial else {}
        index = indices.get((attempt.trial_ordinal, attempt.attempt_number))
        receivers: list[str] = []
        if index is not None:
            seen = pa.table(frames.attempt_frames(index, columns=["receiver_id"]))
            receivers = sorted(set(seen.column("receiver_id").to_pylist()))
        rows.append(
            {
                "session_id": session.session_id,
                "participant_id": metadata.get(
                    "participant_id", session.manifest.get("participant_id")
                ),
                "attempt_key": attempt.key,
                "attempt_id": f"{attempt.trial_ordinal:03d}/{attempt.attempt_number:02d}",
                "trial_ordinal": attempt.trial_ordinal,
                "attempt": attempt.attempt_number,
                "repetition": attempt.repetition,
                "scenario_id": attempt.scenario_id,
                "activity_label": decision["activity_label"],
                "original_activity_label": decision["original_activity_label"],
                "status": attempt.status,
                "inclusion": decision["inclusion"],
                "quality": decision["quality"],
                "review_revision": decision["review_revision"],
                "start_direction": attributes.get("start_direction"),
                "end_direction": attributes.get("end_direction"),
                "started_monotonic_ns": attempt.metadata.get("started_monotonic_ns"),
                "ended_monotonic_ns": attempt.metadata.get("ended_monotonic_ns"),
                "receiver_ids": receivers,
            }
        )
    return pd.DataFrame(rows, columns=_ATTEMPT_COLUMNS)


def _phase_table(session: SessionBundle, attempts: pd.DataFrame) -> pd.DataFrame:
    transitions: dict[tuple[int, int], list[dict]] = {}
    events_path = session.path / "events.jsonl"
    if events_path.exists():
        with events_path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("kind") == "phase_changed":
                    key = (int(event["trial_ordinal"]), int(event["attempt"]))
                    transitions.setdefault(key, []).append(event)
    rows = []
    for attempt in attempts.to_dict("records"):
        events = sorted(
            transitions.get((attempt["trial_ordinal"], attempt["attempt"]), []),
            key=lambda event: event["monotonic_ns"],
        )
        states = [event["state"] for event in events]
        ranks = [
            list(PHASE_NAMES).index(state) if state in PHASE_NAMES else -1
            for state in states
        ]
        if ranks and (ranks[0] != 0 or ranks != sorted(set(ranks))):
            raise ValueError(
                f"Invalid collection phase sequence: {attempt['attempt_key']}"
            )
        for index, event in enumerate(events):
            start = int(event["monotonic_ns"])
            stop = (
                int(events[index + 1]["monotonic_ns"])
                if index + 1 < len(events)
                else attempt["ended_monotonic_ns"]
            )
            if pd.isna(stop) or pd.isna(attempt["started_monotonic_ns"]):
                raise ValueError(f"Unbounded phase: {attempt['attempt_key']}")
            if (
                start < attempt["started_monotonic_ns"]
                or stop < start
                or stop > attempt["ended_monotonic_ns"]
            ):
                raise ValueError(f"Invalid phase bounds: {attempt['attempt_key']}")
            rows.append(
                {
                    **{
                        name: attempt[name]
                        for name in (
                            "session_id",
                            "attempt_key",
                            "trial_ordinal",
                            "attempt",
                            "scenario_id",
                            "review_revision",
                        )
                    },
                    "phase": PHASE_NAMES[event["state"]],
                    "collection_phase": event["state"],
                    "start_ns": start,
                    "end_ns": int(stop),
                    "annotation_source": ANNOTATION_SOURCE,
                }
            )
    return pd.DataFrame(rows, columns=_PHASE_COLUMNS)


def _payload_bytes(column: pa.ChunkedArray | pa.Array) -> tuple[np.ndarray, np.ndarray]:
    """Return the payload bytes of every row as one flat int8 array plus offsets.

    Works for fixed-size and variable-length binary columns, so recordings with
    payload widths that differ between frames are supported.
    """
    array = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    count = len(array)
    if pa.types.is_fixed_size_binary(array.type):
        width = array.type.byte_width
        start = array.offset * width
        values = np.frombuffer(array.buffers()[1], dtype=np.int8)[
            start : start + count * width
        ]
        return values, np.arange(0, (count + 1) * width, width, dtype=np.int64)
    offsets = np.frombuffer(array.buffers()[1], dtype=np.int32)[
        array.offset : array.offset + count + 1
    ].astype(np.int64)
    data = np.frombuffer(array.buffers()[2], dtype=np.int8)
    return data[offsets[0] : offsets[-1]], offsets - offsets[0]


def _int16_lists(values: np.ndarray, offsets: np.ndarray) -> pa.Array:
    """Build a list-of-int16 array from flat values and row offsets."""
    return pa.ListArray.from_arrays(
        pa.array(offsets.astype(np.int32)),
        pa.array(values.astype(np.int16, copy=False)),
    )


@dataclass(frozen=True)
class AnalysisSession:
    """Annotated session tables plus selective access to per-recording packets.

    Attributes:
        path: Directory of the converted frame tables.
        manifest: Source identity and counts; ``source_fingerprint`` changes
            whenever the raw data, the review overlay, the protocol, or the
            analysis semantics change.
        attempts: One row per attempt, with review decisions applied.
        phases: Collection-cue phase intervals ``[start_ns, end_ns)``.
        frames: The converted frame tables.
    """

    path: Path
    manifest: dict[str, Any]
    attempts: pd.DataFrame
    phases: pd.DataFrame
    frames: FrameStore
    transmitter_mac: str
    nominal_rate_hz: float
    attempt_indices: dict[str, int]

    def packets(
        self,
        attempt_key: str,
        receiver_id: str,
        columns: Sequence[str] | None = None,
    ) -> pa.Table:
        """Return the enriched packets of one attempt and receiver.

        Rows are sorted by capture time, as transport delivery can reorder
        records. ``source_row`` is the position in journal (delivery) order.

        Args:
            attempt_key: Attempt identifier from :attr:`attempts`.
            receiver_id: Receiver identifier such as ``"rx-1"``.
            columns: Column names to build; all columns when omitted. I/Q lists
                are only built when requested.

        Returns:
            An Arrow table, empty when the receiver has no frames in the window.

        Raises:
            KeyError: If the attempt is unknown.
            ValueError: If the recording mixes transmitter epochs.
        """
        row = self.attempts.loc[self.attempts["attempt_key"] == attempt_key]
        if row.empty:
            raise KeyError(attempt_key)
        if not self.transmitter_mac:
            raise ValueError("Session radio inventory must specify a transmitter MAC")
        if self.nominal_rate_hz <= 0:
            raise ValueError("A positive nominal sampling rate is required")
        attempt = row.iloc[0].to_dict()
        table = pa.table(
            self.frames.attempt_frames(
                self.attempt_indices[attempt_key], receiver_id=receiver_id
            )
        )
        if table.num_rows == 0:
            names = list(columns) if columns is not None else list(PACKET_TYPES)
            unknown = [name for name in names if name not in PACKET_TYPES]
            if unknown:
                raise KeyError(f"unknown packet columns: {unknown}")
            return pa.table({n: pa.array([], type=PACKET_TYPES[n]) for n in names})
        table = table.append_column("source_row", pa.array(np.arange(table.num_rows)))
        table = table.take(
            pc.sort_indices(table, sort_keys=[("capture_time_ns", "ascending")])
        )
        if (
            len(pc.unique(table.column("run_id"))) != 1
            or len(pc.unique(table.column("tx_boot_id"))) != 1
        ):
            raise ValueError("Gateway attempt mixes transmitter epochs")
        return self._enrich(table, attempt, receiver_id, columns)

    def _enrich(
        self,
        table: pa.Table,
        attempt: dict[str, Any],
        receiver_id: str,
        columns: Sequence[str] | None,
    ) -> pa.Table:
        count = table.num_rows
        started = int(attempt["started_monotonic_ns"])
        capture = table.column("capture_time_ns").to_numpy()
        payload, byte_offsets = _payload_bytes(table.column("csi"))
        widths = np.diff(byte_offsets)
        rows = self.phases.loc[self.phases["attempt_key"] == attempt["attempt_key"]]
        phase = np.full(count, "unassigned", dtype=object)
        collection = np.full(count, "unassigned", dtype=object)
        source = np.full(count, "unassigned", dtype=object)
        for interval in rows.itertuples(index=False):
            selected = (capture >= interval.start_ns) & (capture < interval.end_ns)
            phase[selected] = interval.phase
            collection[selected] = interval.collection_phase
            source[selected] = interval.annotation_source
        sig_mode = table.column("sig_mode").to_numpy()
        mcs = table.column("mcs").to_numpy()
        bandwidth = table.column("bandwidth").to_numpy()
        transmitter = table.column("transmitter_mac")
        derived: dict[str, Callable[[], Any]] = {
            "type": lambda: np.full(count, "CSI_DATA", dtype=object),
            "id": lambda: table.column("sequence").to_numpy(),
            "mac": lambda: transmitter.combine_chunks(),
            "receiver_mac": lambda: np.full(count, "", dtype=object),
            "len": lambda: widths.astype(np.int64),
            "first_word": lambda: (
                table.column("first_word_invalid")
                .to_numpy(zero_copy_only=False)
                .astype(np.int64)
            ),
            "local_timestamp": lambda: table.column("rx_radio_us").to_numpy(),
            "rx_radio_timestamp_us": lambda: table.column("rx_radio_us").to_numpy(),
            "tx_enqueue_timestamp_us": lambda: table.column("tx_enqueue_us").to_numpy(),
            "rx_callback_timestamp_us": lambda: table.column(
                "rx_callback_us"
            ).to_numpy(),
            "host_receive_monotonic_ns": lambda: table.column(
                "host_arrival_ns"
            ).to_numpy(),
            "clock_uncertainty_us": lambda: (
                table.column("capture_uncertainty_us")
                .to_numpy(zero_copy_only=False)
                .astype(np.float64)
            ),
            "run_id": lambda: pc.cast(
                table.column("run_id"), pa.string()
            ).combine_chunks(),
            "transmitter_boot_id": lambda: pc.cast(
                table.column("tx_boot_id"), pa.string()
            ).combine_chunks(),
            "receiver_boot_id": lambda: pc.cast(
                table.column("rx_boot_id"), pa.string()
            ).combine_chunks(),
            "time_seconds": lambda: (capture - started) / 1e9,
            "time_source": lambda: np.full(count, TIME_SOURCE, dtype=object),
            "attempt_id": lambda: np.full(count, attempt["attempt_id"], dtype=object),
            "attempt_key": lambda: np.full(count, attempt["attempt_key"], dtype=object),
            "receiver_id": lambda: np.full(count, receiver_id, dtype=object),
            "attempt_started_monotonic_ns": lambda: np.full(count, started),
            "attempt_ended_monotonic_ns": lambda: np.full(
                count, int(attempt["ended_monotonic_ns"])
            ),
            "nominal_rate_hz": lambda: np.full(count, self.nominal_rate_hz),
            "is_sensing": lambda: (
                pc.equal(transmitter, self.transmitter_mac).to_numpy(
                    zero_copy_only=False
                )
                & (sig_mode == 4)
                & (mcs == 0)
                & (bandwidth == 0)
            ),
            "driver_valid": lambda: table.column("rx_state").to_numpy() == 0,
            "phase": lambda: phase,
            "collection_phase": lambda: collection,
            "annotation_source": lambda: source,
            "csi_i": lambda: _int16_lists(payload[1::2], byte_offsets // 2),
            "csi_q": lambda: _int16_lists(payload[0::2], byte_offsets // 2),
        }
        for name in _HEADER_COLUMNS + ("sig_mode", "mcs"):
            derived.setdefault(name, lambda n=name: table.column(n).to_numpy())
        for name in ("rssi", "noise_floor", "sig_len", "transport_sequence"):
            derived.setdefault(name, lambda n=name: table.column(n).to_numpy())
        derived["sequence"] = lambda: table.column("sequence").to_numpy()
        derived["source_row"] = lambda: table.column("source_row").to_numpy()
        derived["capture_time_ns"] = lambda: capture
        for name in _ATTEMPT_CONSTANTS:
            derived.setdefault(name, lambda n=name: _constant(attempt[n], count, n))
        names = list(columns) if columns is not None else list(PACKET_TYPES)
        unknown = [name for name in names if name not in derived]
        if unknown:
            raise KeyError(f"unknown packet columns: {unknown}")
        arrays = {}
        for name in names:
            value = derived[name]()
            kind = PACKET_TYPES[name]
            arrays[name] = (
                pc.cast(value, kind)
                if isinstance(value, pa.Array)
                else pa.array(value, type=kind, from_pandas=True)
            )
        return pa.table(arrays)

    def recording_summary(
        self, attempt_keys: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """Summarize sensing-link packets of every attempt and receiver at once.

        One pass over a few frame columns replaces a read of each recording.

        Args:
            attempt_keys: Attempts to include; all attempts when omitted.

        Returns:
            One row per recording that has sensing packets, with ``attempt_key``,
            ``receiver_id``, ``packets``, ``driver_valid_packets``, ``first_ns``
            and ``last_ns`` (capture times of the first and last sensing packet).
        """
        selected = self.attempts
        if attempt_keys is not None:
            selected = selected.loc[selected["attempt_key"].isin(list(attempt_keys))]
        table = pa.table(
            self.frames.frames(
                columns=[
                    "receiver_id",
                    "transmitter_mac",
                    "sig_mode",
                    "mcs",
                    "bandwidth",
                    "rx_state",
                    "capture_time_ns",
                ]
            )
        )
        sensing = pc.and_(
            pc.and_(
                pc.equal(table.column("transmitter_mac"), self.transmitter_mac),
                pc.equal(table.column("sig_mode"), 4),
            ),
            pc.and_(
                pc.equal(table.column("mcs"), 0),
                pc.equal(table.column("bandwidth"), 0),
            ),
        )
        table = table.filter(sensing)
        receivers = table.column("receiver_id").to_numpy(zero_copy_only=False)
        capture = table.column("capture_time_ns").to_numpy()
        valid = table.column("rx_state").to_numpy() == 0
        rows = []
        for receiver in sorted(set(receivers.tolist())):
            mine = receivers == receiver
            order = np.argsort(capture[mine], kind="stable")
            times = capture[mine][order]
            cumulative = np.concatenate(([0], np.cumsum(valid[mine][order])))
            for attempt in selected.itertuples(index=False):
                start = int(attempt.started_monotonic_ns)
                end = int(attempt.ended_monotonic_ns)
                low, high = np.searchsorted(times, [start, end], side="left")
                if high > low:
                    rows.append(
                        {
                            "attempt_key": attempt.attempt_key,
                            "receiver_id": receiver,
                            "packets": int(high - low),
                            "driver_valid_packets": int(
                                cumulative[high] - cumulative[low]
                            ),
                            "first_ns": int(times[low]),
                            "last_ns": int(times[high - 1]),
                        }
                    )
        return pd.DataFrame(
            rows,
            columns=[
                "attempt_key",
                "receiver_id",
                "packets",
                "driver_valid_packets",
                "first_ns",
                "last_ns",
            ],
        )

    def read_packets(
        self,
        *,
        filters: Sequence[tuple[str, str, Any]] | None = None,
        columns: Sequence[str] | None = None,
        arrow_backed: bool = False,
        attempt_key: str | None = None,
        receiver_id: str | None = None,
        phase: str | None = None,
    ) -> pd.DataFrame:
        """Read enriched packets of selected recordings as a pandas frame.

        Filters on attempt-level columns (for example ``attempt``, ``status`` or
        ``scenario_id``) and on ``receiver_id`` choose which recordings are read
        at all; the remaining filters are applied to the packet rows.

        Args:
            filters: ANDed ``(column, operator, value)`` tuples with the
                operators ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``in``
                and ``not in``, as accepted by ``pandas.read_parquet``.
            columns: Column names; all columns when omitted.
            arrow_backed: Return Arrow-backed pandas dtypes.
            attempt_key: Shortcut for an ``attempt_key == value`` filter.
            receiver_id: Shortcut for a ``receiver_id == value`` filter.
            phase: Shortcut for a ``phase == value`` filter.

        Returns:
            Rows in attempt order, then receiver, then capture time.
        """
        conditions = list(filters or [])
        for name, value in (
            ("attempt_key", attempt_key),
            ("receiver_id", receiver_id),
            ("phase", phase),
        ):
            if value is not None:
                conditions.append((name, "==", value))
        attempt_level = [c for c in conditions if c[0] in self.attempts.columns]
        receiver_level = [c for c in conditions if c[0] == "receiver_id"]
        packet_level = [
            c for c in conditions if c not in attempt_level and c not in receiver_level
        ]
        attempts = self.attempts
        for name, operator, value in attempt_level:
            attempts = attempts.loc[_compare(attempts[name], operator, value)]
        wanted = list(columns) if columns is not None else None
        fetched = wanted
        if wanted is not None:
            extra = [c[0] for c in packet_level if c[0] not in wanted]
            fetched = [*wanted, *dict.fromkeys(extra)]
        frames = []
        for attempt in attempts.itertuples(index=False):
            for receiver in attempt.receiver_ids:
                if any(
                    not _compare(pd.Series([receiver]), op, value).iloc[0]
                    for _, op, value in receiver_level
                ):
                    continue
                table = self.packets(attempt.attempt_key, receiver, fetched)
                if table.num_rows:
                    frames.append(table.to_pandas())
        result = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=fetched)
        )
        for name, operator, value in packet_level:
            result = result.loc[_compare(result[name], operator, value)]
        if wanted is not None:
            result = result[wanted]
        if arrow_backed:
            result = pa.Table.from_pandas(result, preserve_index=False).to_pandas(
                types_mapper=pd.ArrowDtype
            )
        return result


def _compare(values: pd.Series, operator: str, target: Any) -> pd.Series:
    """Evaluate one ``pandas.read_parquet``-style comparison on a column."""
    if operator in {"==", "="}:
        return values == target
    if operator == "!=":
        return values != target
    if operator == "<":
        return values < target
    if operator == "<=":
        return values <= target
    if operator == ">":
        return values > target
    if operator == ">=":
        return values >= target
    if operator == "in":
        return values.isin(list(target))
    if operator == "not in":
        return ~values.isin(list(target))
    raise ValueError(f"unsupported filter operator: {operator!r}")


def _constant(value: Any, count: int, name: str) -> pa.Array:
    if name in _STRING_ATTEMPT_COLUMNS:
        return pa.array([value] * count, type=pa.string())
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pa.array([None] * count, type=pa.int64())
    return pa.array([value] * count)


def _identity(frames: FrameStore, bundle: SessionBundle, opened: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(frames.source_fingerprint.encode())
    digest.update(str(frames.manifest.get("converter_version")).encode())
    digest.update(str(frames.manifest.get("frame_scope")).encode())
    digest.update(bundle.protocol_hash.encode())
    digest.update(str(ANALYSIS_SCHEMA_VERSION).encode())
    review = opened["review"]
    digest.update((review["content_sha256"] if review else "").encode())
    return digest.hexdigest()


def load_analysis_session(
    source: str | Path,
    frames_dir: str | Path,
    *,
    annotations_dir: str | Path | None = None,
    rebuild: bool = False,
    progress: Callable[[str], None] | None = None,
) -> AnalysisSession:
    """Open a session for analysis, converting its journals when needed.

    Args:
        source: Raw session archive or directory with journals.
        frames_dir: Directory for the converted tables; it must be outside the
            raw data tree.
        annotations_dir: Directory of reviews, one folder per session id. By
            default ``data/annotations`` beside a source in
            ``data/raw/sessions``; any other source uses only a review stored
            inside it.
        rebuild: Convert again even when the tables are current.
        progress: Optional callback receiving status messages.

    Returns:
        The annotated analysis session.

    Raises:
        ValueError: If ``frames_dir`` is inside raw data, the session is still
            active, or its manifests are inconsistent.
    """
    source, frames_dir = Path(source).resolve(), Path(frames_dir).resolve()
    raw_root = source.parent.parent if source.parent.name == "sessions" else source
    if frames_dir.is_relative_to(raw_root):
        raise ValueError("Place derived tables outside raw session data")
    # Without an explicit directory the library implies data/annotations beside
    # a source in data/raw/sessions.
    opened = storage_open_source(
        str(source), None if annotations_dir is None else str(annotations_dir)
    )
    frames = FrameStore.ensure(str(source), str(frames_dir), rebuild, progress)
    with _manifest_root(source) as root:
        bundle = load_session(root)
        if bundle.active:
            raise ValueError("Analysis requires a closed session")
        window_index = {
            (int(row["trial_ordinal"]), int(row["attempt"])): index
            for index, row in enumerate(pa.table(frames.attempts()).to_pylist())
        }
        attempts = _attempt_table(bundle, frames, window_index, opened)
        phases = _phase_table(bundle, attempts)
        environment = bundle.manifest.get("environment", {})
        transmitter = (
            environment.get("radio_inventory", {})
            .get("transmitter", {})
            .get("mac", "")
            .lower()
        )
        rate = environment.get("nominal_rate_hz") or environment.get(
            "radio_profile", {}
        ).get("nominal_rate_hz")
        manifest = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "session_id": bundle.session_id,
            "source_directory": str(source),
            "source_fingerprint": _identity(frames, bundle, opened),
            "frames_fingerprint": frames.source_fingerprint,
            "review": opened["review"],
            "protocol_hash": bundle.protocol_hash,
            "source_manifest": bundle.manifest,
            "packet_count": int(frames.manifest["frames"]),
            "recording_count": int(sum(len(r) for r in attempts["receiver_ids"])),
            "phase_names": PHASE_NAMES,
            "phase_interval": "[start_ns, end_ns)",
            "annotation_source": ANNOTATION_SOURCE,
            "csi_layout": "raw slots; I=real, Q=imaginary; no aggregation",
        }
        keys = {
            row.attempt_key: window_index[(row.trial_ordinal, row.attempt)]
            for row in attempts.itertuples(index=False)
            if (row.trial_ordinal, row.attempt) in window_index
        }
        return AnalysisSession(
            frames_dir,
            manifest,
            attempts,
            phases,
            frames,
            transmitter,
            float(rate) if rate else 0.0,
            keys,
        )
