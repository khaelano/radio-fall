"""Bounded, full-resolution inputs for the binary sequence-window experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

LABELS = ("non_fall", "fall")


def load_sequence_index(
    root: Path, *, datasets: tuple[str, ...], durations: tuple[int, ...]
) -> tuple[pl.DataFrame, dict]:
    """Read completed export metadata without materializing signal tensors.

    Args:
        root: Directory containing the selected amplitude-sequence exports.
        datasets: Dataset directory names selected by the experiment.
        durations: Window durations required by the experiment.

    Returns:
        Window index and source metadata, including declared signal hashes.
    """
    frames, sources = [], {}
    for name in datasets:
        folder = root / name
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest["schema"] != "amplitude_sequence":
            raise ValueError(f"Unsupported export schema: {folder}")
        if manifest["coordinates"] != {
            "receivers": [f"rx-{i}" for i in range(1, 5)],
            "subcarriers": list(range(-122, 123)),
        }:
            raise ValueError(f"Unexpected feature coordinates: {folder}")
        index_path = folder / "window_index.parquet"
        shard_path = folder / "signals.parquet"
        for filename in ("window_index.parquet", "segments.parquet", "signals.parquet"):
            if (
                hashlib.sha256((folder / filename).read_bytes()).hexdigest()
                != manifest["metadata_sha256"][filename]
            ):
                raise ValueError(f"Metadata hash differs: {folder / filename}")
        index = pl.read_parquet(index_path)
        shards = pl.read_parquet(shard_path)
        if (
            len(shards) != manifest["counts"]["segments"]
            or len(index) != manifest["counts"]["windows"]
        ):
            raise ValueError(f"Export counts differ: {folder}")
        if set(index["signal"]) != set(shards["signal"]):
            raise ValueError(f"Signal ledger differs: {folder}")
        for row in shards.iter_rows(named=True):
            path = (folder / row["signal"]).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError("Signal path escapes dataset directory")
            if path.stat().st_size != row["bytes"]:
                raise ValueError(f"Signal size differs: {path}")
            if manifest["parameters"]["target_hz"] == 120:
                presence_path = folder / row["presence"]
                if (
                    hashlib.sha256(presence_path.read_bytes()).hexdigest()
                    != row["presence_sha256"]
                ):
                    raise ValueError(f"Presence mask differs: {presence_path}")
        frames.append(
            index.with_columns(
                pl.lit(name).alias("dataset"),
                pl.lit(manifest["parameters"]["target_hz"]).alias("rate_hz"),
                pl.col("signal")
                .map_elements(
                    lambda p, folder=folder: str((folder / p).resolve()),
                    return_dtype=pl.String,
                )
                .alias("path"),
            )
        )
        sources[name] = {
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
            "signals_sha256": hashlib.sha256(shard_path.read_bytes()).hexdigest(),
            "source": manifest["source"],
            "parameters": manifest["parameters"],
            "signals": shards.to_dicts(),
        }
    index = pl.concat(frames).sort("dataset", "duration", "signal", "start")
    if not set(index["target"].unique()) <= {0, 1}:
        raise ValueError("Expected binary targets")
    if set(index["duration"].unique()) != set(durations):
        raise ValueError("Export window durations differ from the experiment")
    if (
        index.select("dataset", "segment_id", "duration", "start").unique().height
        != index.height
    ):
        raise ValueError("Duplicate window bounds")
    return index.with_row_index("window_id"), sources


def split_sequence_attempts(
    index: pl.DataFrame, *, seed: int, test_fraction: float, validation_fraction: float
) -> pl.DataFrame:
    """Assign stratified attempt groups consistently across all input durations."""
    if not (0 < test_fraction < 1 and 0 < validation_fraction < 1 - test_fraction):
        raise ValueError(
            "Split fractions must leave nonempty train/validation/test sets"
        )
    groups = index.select("group", "dataset", "activity_label").unique().sort("group")
    if groups["group"].n_unique() != len(groups):
        raise ValueError("An attempt has conflicting dataset/activity metadata")
    strata = [f"{r['dataset']}::{r['activity_label']}" for r in groups.to_dicts()]
    train_val, test = train_test_split(
        np.arange(len(groups)),
        test_size=test_fraction,
        random_state=seed,
        stratify=strata,
    )
    train, validation = train_test_split(
        train_val,
        test_size=validation_fraction / (1 - test_fraction),
        random_state=seed + 1,
        stratify=np.asarray(strata)[train_val],
    )
    mapping = {
        groups["group"][int(i)]: label
        for label, members in (
            ("train", train),
            ("validation", validation),
            ("test", test),
        )
        for i in members
    }
    result = index.with_columns(pl.col("group").replace_strict(mapping).alias("split"))
    for duration in sorted(index["duration"].unique()):
        for label in ("train", "validation", "test"):
            subset = result.filter(
                (pl.col("duration") == duration) & (pl.col("split") == label)
            )
            if set(subset["target"].unique()) != {0, 1}:
                raise ValueError(f"Both classes required in {duration}s {label}")
    return result


class SegmentStore:
    """Map segment NPY files without a second Python signal cache."""

    def __init__(self) -> None:
        self.coordinates = (
            np.asarray([f"rx-{i}" for i in range(1, 5)]),
            np.arange(-122, 123),
        )

    def read(self, path: str) -> np.memmap:
        """Map one segment; the operating system owns the page cache."""
        signal = np.load(path, mmap_mode="r", allow_pickle=False)
        if (
            signal.dtype != np.float32
            or signal.ndim != 3
            or signal.shape[1:] != (4, 245)
        ):
            raise ValueError(f"Invalid segment signal: {path}")
        return signal

    def clear(self) -> None:
        """No Python tensor cache is retained."""


@dataclass
class Normalizer:
    """Per-feature log1p mean and scale fitted on valid training samples."""

    mean: np.ndarray
    scale: np.ndarray
    count: np.ndarray

    def transform(self, values: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Standardize valid samples and append unscaled validity channels."""
        scaled = np.where(mask, (values - self.mean) / self.scale, 0)
        return np.concatenate((scaled, mask), axis=-1).astype(np.float32, copy=False)

    def save(self, path: Path) -> None:
        """Save statistics without pickle."""
        np.savez(path, mean=self.mean, scale=self.scale, count=self.count)

    @classmethod
    def load(cls, path: Path) -> Normalizer:
        """Load saved training statistics."""
        with np.load(path, allow_pickle=False) as data:
            return cls(*(data[k].copy() for k in ("mean", "scale", "count")))


def _selected(
    store: SegmentStore, path: str, rows: list[dict]
) -> tuple[np.ndarray, np.ndarray]:
    signal = store.read(path)
    if any(
        r["stop"] > len(signal)
        or r["start"] < 0
        or r["stop"] - r["start"] != r["duration"] * r.get("rate_hz", 96)
        for r in rows
    ):
        raise ValueError(f"Window bounds differ: {path}")
    values = np.stack([signal[r["start"] : r["stop"]] for r in rows]).reshape(
        len(rows), rows[0]["duration"] * rows[0].get("rate_hz", 96), -1
    )
    mask = np.isfinite(values)
    return np.where(mask, values, 0), mask


def fit_normalizer(frame: pl.DataFrame, store: SegmentStore) -> Normalizer:
    """Accumulate statistics exclusively from the training partition."""
    train = frame.filter(pl.col("split") == "train")
    if train.is_empty():
        raise ValueError("Training partition is empty")
    total = square = count = None
    for part in train.partition_by("path", maintain_order=True):
        ordered = part.sort("start")
        for chunk in ordered.iter_slices(32):
            values, mask = _selected(store, part["path"][0], chunk.to_dicts())
            values = values.astype(np.float64)
            if total is None:
                total = np.zeros(values.shape[-1])
                square = np.zeros_like(total)
                count = np.zeros(values.shape[-1], dtype=np.int64)
            total += np.where(mask, values, 0).sum(axis=(0, 1))
            square += np.where(mask, values * values, 0).sum(axis=(0, 1))
            count += mask.sum(axis=(0, 1))
    mean = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    variance = (
        np.divide(square, count, out=np.zeros_like(square), where=count > 0) - mean**2
    )
    scale = np.sqrt(np.maximum(variance, 0))
    scale[(scale < 1e-6) | (count == 0)] = 1
    return Normalizer(mean.astype(np.float32), scale.astype(np.float32), count)


class SequenceDataset:
    """Stream complete windows and preserve row identities through shuffling."""

    def __init__(
        self,
        frame: pl.DataFrame,
        normalizer: Normalizer,
        store: SegmentStore,
    ):
        self.frame, self.normalizer, self.store = frame, normalizer, store
        self.parts = [
            (
                p["path"][0],
                p.sort("start").to_dicts(),
            )
            for p in frame.partition_by("path", maintain_order=True)
        ]
        self._prepared: np.ndarray | None = None
        self._positions: dict[int, int] = {}

    @property
    def prepared_bytes(self) -> int:
        """Return resident prepared-input bytes, excluding transient batches."""
        return 0 if self._prepared is None else self._prepared.nbytes

    def prepare(self, max_bytes: int) -> bool:
        """Cache normalized windows once if they fit the supplied RAM budget.

        Returns False without reading signals when the complete cache cannot fit.
        Existing streaming behavior remains available for oversized datasets.
        Call before starting any batch producer; keep the frame and normalizer
        unchanged for this dataset's lifetime.
        """
        if max_bytes < 0:
            raise ValueError("Cache budget must be nonnegative")
        if self._prepared is not None:
            return self.prepared_bytes <= max_bytes
        if not len(self):
            return False
        shapes = {
            (
                row["duration"] * row.get("rate_hz", 96),
                len(self.normalizer.mean) * 2 + (4 if row.get("rate_hz") == 120 else 0),
            )
            for _, rows in self.parts
            for row in rows
        }
        if len(shapes) != 1:
            raise ValueError("Prepared inputs require one duration and feature layout")
        shape = (len(self), *next(iter(shapes)))
        required = int(np.prod(shape)) * np.dtype(np.float32).itemsize
        if required > max_bytes:
            return False
        prepared = np.empty(shape, dtype=np.float32)
        positions = {}
        offset = 0
        for values, rows in self.batches(16):
            prepared[offset : offset + len(rows)] = values
            positions.update((id(row), offset + i) for i, row in enumerate(rows))
            offset += len(rows)
        prepared.flags.writeable = False
        self._positions = positions
        self._prepared = prepared
        return True

    def __len__(self) -> int:
        return len(self.frame)

    def _ordered_groups(self, seed: int | None) -> Iterator[tuple[str, list[dict]]]:
        rng = np.random.default_rng(seed)
        groups = [
            (path, rows[offset : offset + 16])
            for path, rows in self.parts
            for offset in range(0, len(rows), 16)
        ]
        paths = np.arange(len(groups))
        if seed is not None:
            rng.shuffle(paths)
        for i in paths:
            path, original = groups[int(i)]
            rows = original.copy()
            if seed is not None:
                rng.shuffle(rows)
            yield path, rows

    def batch_rows(
        self, batch_size: int, seed: int | None = None
    ) -> Iterator[list[dict]]:
        """Yield metadata in the same seeded order as streamed input batches."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        pending = []
        for _, rows in self._ordered_groups(seed):
            pending.extend(rows)
            while len(pending) >= batch_size:
                yield pending[:batch_size]
                pending = pending[batch_size:]
        if pending:
            yield pending

    def batches(
        self, batch_size: int, seed: int | None = None
    ) -> Iterator[tuple[np.ndarray, list[dict]]]:
        """Yield contiguous float32 batches; shuffle only when a seed is given."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self._prepared is not None:
            for rows in self.batch_rows(batch_size, seed):
                yield self._prepared[[self._positions[id(row)] for row in rows]], rows
            return
        batch, batch_masks, batch_presence, metadata = [], [], [], []
        for path, rows in self._ordered_groups(seed):
            values, masks = _selected(self.store, path, rows)
            presence = None
            if rows[0].get("rate_hz") == 120:
                presence_path = Path(path).with_name(Path(path).stem + ".presence.npy")
                present = np.load(presence_path, mmap_mode="r", allow_pickle=False)
                presence = np.stack(
                    [present[row["start"] : row["stop"]] for row in rows]
                )
            for position, (value, mask, row) in enumerate(zip(values, masks, rows)):
                batch.append(value)
                batch_masks.append(mask)
                if presence is not None:
                    batch_presence.append(presence[position])
                metadata.append(row)
                if len(batch) == batch_size:
                    transformed = self.normalizer.transform(
                        np.stack(batch), np.stack(batch_masks)
                    )
                    if batch_presence:
                        transformed = np.concatenate(
                            (transformed, np.stack(batch_presence)), axis=-1
                        )
                    yield (
                        transformed,
                        metadata,
                    )
                    batch, batch_masks, batch_presence, metadata = [], [], [], []
        if batch:
            transformed = self.normalizer.transform(
                np.stack(batch), np.stack(batch_masks)
            )
            if batch_presence:
                transformed = np.concatenate(
                    (transformed, np.stack(batch_presence)), axis=-1
                )
            yield (
                transformed,
                metadata,
            )


def prefetched_batches(
    dataset: SequenceDataset, batch_size: int, seed: int | None = None
) -> Iterator[tuple[np.ndarray, list[dict]]]:
    """Overlap decoding/normalization and GPU work with one ready batch.

    Only the producer touches the shard cache. Iteration order and input values
    match synchronous loading. Exceptions propagate and early closure joins the
    producer, so validation cannot race it for the shared cache.
    """
    queue: Queue = Queue(maxsize=1)
    stop = Event()
    finished = object()

    def put(value: object) -> bool:
        while not stop.is_set():
            try:
                queue.put(value, timeout=0.1)
                return True
            except Full:
                pass
        return False

    def produce() -> None:
        try:
            for batch in dataset.batches(batch_size, seed):
                if not put(batch):
                    break
        except BaseException as error:  # noqa: BLE001 — propagate worker failures
            put(error)
        finally:
            put(finished)

    producer = Thread(target=produce, name="sequence-prefetch", daemon=True)
    producer.start()
    try:
        while True:
            try:
                batch = queue.get(timeout=0.1)
            except Empty:
                continue
            if batch is finished:
                break
            if isinstance(batch, BaseException):
                raise batch
            yield batch
    finally:
        stop.set()
        producer.join()
