"""Index, split and load the preprocessed window dataset."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.model_selection import GroupShuffleSplit

LABELS = ("preparation", "action", "resting")

def index_windows(root: str | Path, max_files_per_variant: int | None = None) -> pl.DataFrame:
    """Index labeled windows without loading their full signal matrices."""
    rows = []
    for duration in (2, 4, 6):
        files = sorted((Path(root) / f"{duration}s").rglob("*.npz"))
        if max_files_per_variant is not None:
            files = files[:max_files_per_variant]
        if not files:
            raise ValueError(f"No {duration}s window files in {root}")
        for path in files:
            with np.load(path, allow_pickle=False) as data:
                info = json.loads(str(data["provenance_json"]))
                labels = data["label"]
                shape = data["amplitude"].shape
            if len(shape) != 3 or shape[0] != len(labels) or shape[1] != duration * 80:
                raise ValueError(f"Invalid window shape: {path}")
            for index, label in enumerate(labels):
                if label in LABELS:
                    rows.append({"duration": duration, "path": str(path.resolve()),
                        "index": index, "label": str(label),
                        "group": f"{info['session_id']}::{info['attempt_key']}",
                        "session": info['session_id'], "attempt": info['attempt_key'],
                        "receiver": info['receiver_id']})
    return pl.DataFrame(rows)


def split_attempts(index: pl.DataFrame, seed: int) -> pl.DataFrame:
    """Split attempts once, so all receiver views and durations share a partition."""
    groups = np.array(sorted(index['group'].unique().to_list()))
    if len(groups) < 5:
        raise ValueError("At least five independent attempts are required for train/validation/test")
    train_val, test = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(groups, groups=groups))
    train, val = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed+1).split(groups[train_val], groups=groups[train_val]))
    mapping = {**{g: 'train' for g in groups[train_val[train]]},
               **{g: 'validation' for g in groups[train_val[val]]},
               **{g: 'test' for g in groups[test]}}
    return index.with_columns(pl.col('group').replace_strict(mapping).alias('split'))


def pooled_input(amplitude: np.ndarray, valid: np.ndarray, bins: int) -> np.ndarray:
    """Pool to common temporal bins; retain observed fractions as mask channels."""
    if amplitude.shape != valid.shape or amplitude.ndim != 2 or bins > len(amplitude):
        raise ValueError("Invalid window shape or temporal bin count")
    mask = valid & np.isfinite(amplitude)
    chunks = np.array_split(np.arange(len(amplitude)), bins)
    means, coverage = [], []
    for chunk in chunks:
        present = mask[chunk]
        count = present.sum(axis=0)
        total = np.where(present, amplitude[chunk], 0).sum(axis=0)
        means.append(np.divide(total, count, out=np.zeros_like(total, dtype=np.float32), where=count > 0))
        coverage.append(count / len(chunk))
    return np.concatenate((np.asarray(means), np.asarray(coverage)), axis=1).astype(np.float32)


class WindowDataset:
    """Load individual window archives lazily with a small bounded cache."""
    def __init__(self, frame: pl.DataFrame, bins: int):
        self.rows = frame.select('path', 'index', 'label').iter_rows()
        self.rows = list(self.rows)
        self.bins = bins
        self.cache = OrderedDict()

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        path, window, label = self.rows[index]
        if path not in self.cache:
            with np.load(path, allow_pickle=False) as data:
                amplitude, valid = data['amplitude'], data['valid']
            self.cache[path] = np.stack([
                pooled_input(amplitude[j], valid[j], self.bins)
                for j in range(len(amplitude))
            ])
            # Pooled archives are much smaller than raw windows. Retaining them
            # avoids decompressing the same recording in every training epoch.
            if len(self.cache) > 1024:
                self.cache.popitem(last=False)
        self.cache.move_to_end(path)
        return self.cache[path][window], LABELS.index(label)


class FileBatchSampler:
    """Shuffle archives per epoch while keeping each compressed file local."""
    def __init__(self, dataset: WindowDataset, batch_size: int, seed: int):
        self.groups = {}
        for index, (path, _, _) in enumerate(dataset.rows):
            self.groups.setdefault(path, []).append(index)
        self.batch_size = batch_size
        self.seed = seed
        self.epoch = 0

    def __iter__(self):
        rng = np.random.default_rng(self.seed + self.epoch)
        self.epoch += 1
        paths = list(self.groups)
        rng.shuffle(paths)
        for path in paths:
            indices = self.groups[path].copy()
            rng.shuffle(indices)
            for offset in range(0, len(indices), self.batch_size):
                yield indices[offset:offset + self.batch_size]

    def __len__(self):
        return sum((len(group) + self.batch_size - 1) // self.batch_size
                   for group in self.groups.values())


def save_manifest(index: pl.DataFrame, output: str | Path, config: dict) -> None:
    """Save split membership, source file fingerprints and experimental settings."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    index.write_parquet(output / 'window_split.parquet')
    files = []
    for path in sorted(index['path'].unique().to_list()):
        stat = Path(path).stat()
        files.append({'path': path, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps({'config': config, 'labels': LABELS,
        'source': 'amplitude_windows_v1', 'file_metadata_sha256': fingerprint,
        'files': files, 'split_unit': 'session_id + attempt_key',
        'limitation': 'attempt-level split does not test participant or session generalization; whole-recording scaling and centered filtering use future samples'}, indent=2))
