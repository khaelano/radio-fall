import json

import numpy as np
import pytest

from fall_detection import _radio_native as core
from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import encode_csi_datagram
from fall_detection.detection.model import ModelBundle, file_hash


@pytest.fixture
def native_record():
    def make(sequence=1, *, weak=False, bad=False, full=False):
        values = tuple(
            complex(10 + i % 23, 7 + i % 19) for i in range(256 if full else 245)
        )
        if weak:
            values = tuple(
                0j if i % 7 == 0 else value for i, value in enumerate(values)
            )
        record = CsiRecord(
            sequence,
            "1a:00:00:00:00:00",
            -40,
            -95,
            sequence,
            values,
            raw_csi=values,
            sig_mode=4,
            rx_state=int(bad),
            profile_fingerprint="0123456789abcdef",
        )
        encoded = encode_csi_datagram(
            record, receiver_mac="44:bd:8d:d0:b1:4c", transport_sequence=sequence
        )
        return core.decode_cnn_record(encoded), record

    return make


@pytest.fixture
def model_bundle(tmp_path, request):
    torch = pytest.importorskip("torch")
    nn = torch.nn
    phase = getattr(request, "param", "amplitude") == "phase_change"
    channels = 16 if phase else 8
    representation = "phase_change" if phase else "amplitude"
    directory = tmp_path / "model"
    directory.mkdir()
    normalization = "normalization.npz"
    np.savez(
        directory / normalization,
        mean=np.ones((1, 4, 1, 242), dtype="float32"),
        scale=np.full((1, 4, 1, 242), 2.0, dtype="float32"),
    )
    checkpoints = []
    for seed in [17, 29, 43]:
        torch.manual_seed(seed)
        model = nn.Module()
        model.network = nn.Sequential(
            nn.Conv2d(channels, 8, 5, stride=2, padding=2),
            nn.ReLU(),
            nn.Conv2d(8, 16, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.25),
            nn.Linear(32, 1),
        )
        name = f"seed{seed}.pt"
        torch.save(
            dict(
                state_dict=model.state_dict(),
                channels=channels,
                representation=representation,
                normalization="none" if phase else normalization,
            ),
            directory / name,
        )
        checkpoints.append(name)
    metadata = dict(
        schema_version=2 if phase else 1,
        architecture="small-cnn-v1",
        representation=representation,
        window_seconds=4,
        bin_hz=25,
        input_shape=[1, channels, 100, 242],
        minimum_coverage=0.7,
        threshold=0.5,
        receivers=[f"rx-{i}" for i in range(1, 5)],
        checkpoints=checkpoints,
        normalization="none" if phase else normalization,
        radio=dict(
            profile_fingerprint="0123456789abcdef",
            transmitter_mac="1a:00:00:00:00:00",
            receiver_macs=[f"00:00:00:00:00:0{i}" for i in range(1, 5)],
        ),
        sha256={
            name: file_hash(directory / name) for name in [normalization, *checkpoints]
        },
    )
    if phase:
        metadata.update(
            phase_preprocessing="calibrated-delta-sincos-v1",
            lag_seconds=0.1,
            maximum_lag_seconds=0.15,
            smoothing_bins=1,
        )
    (directory / "bundle.json").write_text(json.dumps(metadata))
    return ModelBundle.load(directory)
