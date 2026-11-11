"""Bounded, full-resolution inputs for the binary sequence-window experiment."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Iterator

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

DATASET_NAMES = ("khaelano", "akmal", "continuous_non_fall")
DURATIONS = (2, 4, 6)
LABELS = ("non_fall", "fall")


def load_sequence_index(root: Path) -> tuple[pl.DataFrame, dict]:
    """Read completed export metadata without materializing signal tensors.

    Args:
        root: Directory containing the three amplitude_sequence_v2 datasets.

    Returns:
        Window index and source metadata, including declared signal hashes.
    """
    frames, sources = [], {}
    for name in DATASET_NAMES:
        folder = root / name
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest["schema"] != "amplitude_sequence_v2":
            raise ValueError(f"Unsupported export schema: {folder}")
        if manifest["coordinates"] != {
            "receivers": [f"rx-{i}" for i in range(1, 5)],
            "subcarriers": list(range(-122, 123)),
        }:
            raise ValueError(f"Unexpected feature coordinates: {folder}")
        index_path = folder / "window_index.parquet"
        shard_path = folder / "signals.parquet"
        for filename in ("window_index.parquet", "segments.parquet", "signals.parquet"):
            if hashlib.sha256((folder / filename).read_bytes()).hexdigest() != manifest["metadata_sha256"][filename]:
                raise ValueError(f"Metadata hash differs: {folder / filename}")
        index = pl.read_parquet(index_path)
        shards = pl.read_parquet(shard_path)
        if len(shards) != manifest["counts"]["segments"] or len(index) != manifest["counts"]["windows"]:
            raise ValueError(f"Export counts differ: {folder}")
        if set(index["signal"]) != set(shards["signal"]):
            raise ValueError(f"Signal ledger differs: {folder}")
        for row in shards.iter_rows(named=True):
            path = (folder / row["signal"]).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError("Signal path escapes dataset directory")
            if path.stat().st_size != row["bytes"]:
                raise ValueError(f"Signal size differs: {path}")
        frames.append(
            index.with_columns(
                pl.lit(name).alias("dataset"),
                pl.col("signal")
                .map_elements(
                    lambda p: str((folder / p).resolve()), return_dtype=pl.String
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
    if set(index["duration"].unique()) != set(DURATIONS):
        raise ValueError("Expected 2/4/6-second windows")
    if index.select("dataset", "segment_id", "duration", "start").unique().height != index.height:
        raise ValueError("Duplicate window bounds")
    return index.with_row_index("window_id"), sources


def split_sequence_attempts(index: pl.DataFrame, seed: int = 42) -> pl.DataFrame:
    """Assign stratified 60/20/20 attempt groups once for every duration."""
    groups = index.select("group", "dataset", "activity_label").unique().sort("group")
    if groups["group"].n_unique() != len(groups):
        raise ValueError("An attempt has conflicting dataset/activity metadata")
    strata = [f"{r['dataset']}::{r['activity_label']}" for r in groups.to_dicts()]
    train_val, test = train_test_split(
        np.arange(len(groups)), test_size=0.2, random_state=seed, stratify=strata
    )
    train, validation = train_test_split(
        train_val,
        test_size=0.25,
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
    for duration in DURATIONS:
        for label in ("train", "validation", "test"):
            subset = result.filter(
                (pl.col("duration") == duration) & (pl.col("split") == label)
            )
            if set(subset["target"].unique()) != {0, 1}:
                raise ValueError(f"Both classes required in {duration}s {label}")
    return result


class ShardStore:
    """Cache only log-transformed differences and masks within a byte budget."""

    def __init__(self, max_bytes: int = 512 * 1024**2):
        self.max_bytes = max_bytes
        self.cache: OrderedDict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = (
            OrderedDict()
        )
        self.bytes = 0
        self.coordinates: tuple[np.ndarray, np.ndarray] | None = None

    def clear(self) -> None:
        """Release cached signals while retaining coordinate validation."""
        self.cache.clear()
        self.bytes = 0

    def read(self, path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Read one shard; invalid values become zero before log1p."""
        if path in self.cache:
            self.cache.move_to_end(path)
            return self.cache[path]
        with np.load(path, allow_pickle=False) as archive:
            raw = archive["squared_difference"]
            mask = archive["difference_valid"].astype(bool)
            targets = archive["target"].copy()
            coordinates = (archive["receivers"].copy(), archive["subcarriers"].copy())
        if raw.ndim != 4 or raw.shape != mask.shape or len(raw) != len(targets):
            raise ValueError(f"Invalid signal/mask/target shapes: {path}")
        if self.coordinates is None:
            self.coordinates = coordinates
        elif any(
            not np.array_equal(a, b) for a, b in zip(self.coordinates, coordinates)
        ):
            raise ValueError(f"Receiver/subcarrier order differs: {path}")
        mask &= np.isfinite(raw)
        if np.any(raw[mask] < 0):
            raise ValueError(f"Negative squared difference: {path}")
        values = np.log1p(np.where(mask, raw, 0)).astype(np.float32)
        values = values.reshape(*values.shape[:2], -1)
        mask = mask.reshape(*mask.shape[:2], -1)
        item = (values, mask, targets)
        size = sum(a.nbytes for a in item)
        while self.cache and self.bytes + size > self.max_bytes:
            _, previous = self.cache.popitem(last=False)
            self.bytes -= sum(a.nbytes for a in previous)
        if size <= self.max_bytes:
            self.cache[path] = item
            self.bytes += size
        return item


class SegmentStore:
    """Map segment NPY files without a second Python signal cache."""

    def __init__(self) -> None:
        self.coordinates = (np.asarray([f"rx-{i}" for i in range(1, 5)]),
                            np.arange(-122, 123))

    def read(self, path: str) -> np.memmap:
        """Map one segment; the operating system owns the page cache."""
        signal = np.load(path, mmap_mode="r", allow_pickle=False)
        if signal.dtype != np.float32 or signal.ndim != 3 or signal.shape[1:] != (4, 245):
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
    store: ShardStore | SegmentStore, path: str, rows: list[dict]
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(store, SegmentStore):
        signal = store.read(path)
        if any(r["stop"] > len(signal) or r["start"] < 0 or
               r["stop"] - r["start"] != r["duration"] * 96 for r in rows):
            raise ValueError(f"Window bounds differ: {path}")
        values = np.stack([signal[r["start"]:r["stop"]] for r in rows]).reshape(
            len(rows), rows[0]["duration"] * 96, -1
        )
        mask = np.isfinite(values)
        return np.where(mask, values, 0), mask
    values, mask, targets = store.read(path)
    positions = np.asarray([r["shard_row"] for r in rows])
    if not np.array_equal(targets[positions], [r["target"] for r in rows]):
        raise ValueError(f"Index/shard targets differ: {path}")
    if any(values.shape[1] != r["duration"] * 96 for r in rows):
        raise ValueError(f"Window length differs: {path}")
    return values[positions], mask[positions]


def fit_normalizer(frame: pl.DataFrame, store: ShardStore | SegmentStore) -> Normalizer:
    """Accumulate statistics exclusively from the training partition."""
    train = frame.filter(pl.col("split") == "train")
    if train.is_empty():
        raise ValueError("Training partition is empty")
    total = square = count = None
    for part in train.partition_by("path", maintain_order=True):
        ordered = part.sort("start") if "start" in part.columns else part
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

    def __init__(self, frame: pl.DataFrame, normalizer: Normalizer,
                 store: ShardStore | SegmentStore):
        self.frame, self.normalizer, self.store = frame, normalizer, store
        self.parts = [
            (p["path"][0], p.sort("start").to_dicts() if "start" in p.columns else p.to_dicts())
            for p in frame.partition_by("path", maintain_order=True)
        ]

    def __len__(self) -> int:
        return len(self.frame)

    def batches(
        self, batch_size: int, seed: int | None = None
    ) -> Iterator[tuple[np.ndarray, list[dict]]]:
        """Yield contiguous float32 batches; shuffle only when a seed is given."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        rng = np.random.default_rng(seed)
        groups = [
            (path, rows[offset:offset + 16])
            for path, rows in self.parts
            for offset in range(0, len(rows), 16)
        ] if isinstance(self.store, SegmentStore) else self.parts
        paths = np.arange(len(groups))
        if seed is not None:
            rng.shuffle(paths)
        batch, batch_masks, metadata = [], [], []
        for i in paths:
            path, original = groups[int(i)]
            rows = original.copy()
            if seed is not None:
                rng.shuffle(rows)
            values, masks = _selected(self.store, path, rows)
            for value, mask, row in zip(values, masks, rows):
                batch.append(value)
                batch_masks.append(mask)
                metadata.append(row)
                if len(batch) == batch_size:
                    yield (
                        self.normalizer.transform(
                            np.stack(batch), np.stack(batch_masks)
                        ),
                        metadata,
                    )
                    batch, batch_masks, metadata = [], [], []
        if batch:
            yield (
                self.normalizer.transform(np.stack(batch), np.stack(batch_masks)),
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
        except BaseException as error:
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
