"""Compact device-resident segments for the notebook's sequence experiment."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import polars as pl
import torch

from .sequence_training_data import SequenceDataset, prefetched_batches


class DeviceSequenceDataset:
    """Keep each covered segment span once; gather overlapping windows on device.

    Signal channels stay float32 and masks stay boolean until a batch is built.
    Construction and iteration run on the consumer's stream, without a CUDA
    producer thread. The supplied normalizer must already be fitted on training.
    """

    def __init__(self, dataset: SequenceDataset, device: torch.device) -> None:
        self.dataset = dataset
        self.device = device
        self.values: torch.Tensor
        self.valid: torch.Tensor
        self.presence: torch.Tensor | None = None
        self.offsets: dict[str, int] = {}
        self.window_size = 0

    @property
    def frame(self) -> pl.DataFrame:
        """Return unchanged labels and provenance."""
        return self.dataset.frame

    @property
    def prepared_bytes(self) -> int:
        """Return zero: this path does not prepare a RAM window cache."""
        return 0

    @property
    def device_bytes(self) -> int:
        """Return resident tensor bytes, excluding transient gathered batches."""
        return sum(
            tensor.numel() * tensor.element_size()
            for tensor in (self.values, self.valid, self.presence)
            if tensor is not None
        )

    def __len__(self) -> int:
        return len(self.dataset)

    def batches(
        self, batch_size: int, seed: int | None = None
    ) -> Iterator[tuple[torch.Tensor, list[dict]]]:
        """Build float32 model inputs on the caller's current device stream."""
        steps = torch.arange(self.window_size, device=self.device)
        for rows in self.dataset.batch_rows(batch_size, seed):
            starts = torch.tensor(
                [self.offsets[row["path"]] + row["start"] for row in rows],
                device=self.device,
            )
            indices = starts[:, None] + steps
            channels = [self.values[indices], self.valid[indices].float()]
            if self.presence is not None:
                channels.append(self.presence[indices].float())
            yield torch.cat(channels, dim=-1), rows


def prepare_device_dataset(
    dataset: SequenceDataset, device: torch.device, max_bytes: int
) -> DeviceSequenceDataset | None:
    """Prepare complete compact segments within budget, or return a fallback.

    Budget refusal and CUDA allocation failure return None. Invalid data raises
    rather than silently bypassing validation. CPU devices support parity tests;
    the notebook selects this path only for CUDA. Budgets exclude model state,
    activations, batch assembly, and allocator overhead.

    Args:
        dataset: One partition with fixed duration, rate, and fitted normalizer.
        device: Device on which to store segments and gather batches.
        max_bytes: Maximum persistent signal/mask tensor bytes.

    Returns:
        Prepared device inputs, or None when the budget/allocation cannot fit.
    """
    if max_bytes < 0:
        raise ValueError("Device cache budget must be nonnegative")
    if not len(dataset):
        return None
    layouts = {
        (row["duration"], row.get("rate_hz", 96))
        for _, rows in dataset.parts
        for row in rows
    }
    if len(layouts) != 1:
        raise ValueError("Device cache requires one duration and sample rate")
    duration, rate = next(iter(layouts))
    size = duration * rate
    features = len(dataset.normalizer.mean)
    spans = []
    for path, rows in dataset.parts:
        begin = min(row["start"] for row in rows)
        end = max(row["stop"] for row in rows)
        if begin < 0 or any(row["stop"] - row["start"] != size for row in rows):
            raise ValueError(f"Window bounds differ: {path}")
        spans.append((path, begin, end))
    samples = sum(end - begin for _, begin, end in spans)
    required = samples * (features * 5 + (4 if rate == 120 else 0))
    if required > max_bytes:
        return None
    try:
        return _prepare(dataset, device, spans, samples, size, rate)
    except torch.cuda.OutOfMemoryError:
        # The failed helper's partial tensors are released on return.
        return None


def _prepare(
    dataset: SequenceDataset,
    device: torch.device,
    spans: list[tuple[str, int, int]],
    samples: int,
    size: int,
    rate: int,
) -> DeviceSequenceDataset:
    result = DeviceSequenceDataset(dataset, device)
    features = len(dataset.normalizer.mean)
    result.window_size = size
    result.values = torch.empty((samples, features), dtype=torch.float32, device=device)
    result.valid = torch.empty((samples, features), dtype=torch.bool, device=device)
    if rate == 120:
        result.presence = torch.empty((samples, 4), dtype=torch.bool, device=device)
    offset = 0
    for path, begin, end in spans:
        signal = dataset.store.read(path)
        if end > len(signal) or features != 980:
            raise ValueError(f"Window bounds or feature layout differ: {path}")
        presence = None
        if rate == 120:
            presence = np.load(
                Path(path).with_suffix(".presence.npy"),
                mmap_mode="r",
                allow_pickle=False,
            )
            if presence.dtype != bool or presence.shape != (len(signal), 4):
                raise ValueError(f"Invalid presence mask: {path}")
        result.offsets[path] = offset - begin
        # Bounded CPU normalization preserves NumPy rounding exactly.
        for start in range(begin, end, 4096):
            stop = min(start + 4096, end)
            values = np.asarray(signal[start:stop]).reshape(stop - start, features)
            valid = np.isfinite(values)
            scaled = np.where(
                valid,
                (np.where(valid, values, 0) - dataset.normalizer.mean)
                / dataset.normalizer.scale,
                0,
            ).astype(np.float32, copy=False)
            target = slice(offset + start - begin, offset + stop - begin)
            result.values[target].copy_(torch.from_numpy(scaled))
            result.valid[target].copy_(torch.from_numpy(valid))
            if presence is not None:
                result.presence[target].copy_(
                    torch.from_numpy(presence[start:stop].copy())
                )
        offset += end - begin
    return result


def training_batches(
    dataset: SequenceDataset | DeviceSequenceDataset,
    batch_size: int,
    seed: int | None = None,
) -> Iterator[tuple[np.ndarray | torch.Tensor, list[dict]]]:
    """Use the consumer stream for device inputs and a prefetch thread for RAM."""
    if isinstance(dataset, DeviceSequenceDataset):
        yield from dataset.batches(batch_size, seed)
    else:
        yield from prefetched_batches(dataset, batch_size, seed)
