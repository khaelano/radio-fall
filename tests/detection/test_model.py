import json
import time
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.detection.model import (
    ModelBundle,
    EnsembleWorker,
    load_ensemble,
    score_tensor,
    export_bundle,
    file_hash,
)


def test_saved_ensemble_has_deterministic_eval_scores_and_fixed_input_shape(
    model_bundle,
):
    models = load_ensemble(model_bundle, threads=1)
    values = np.random.default_rng(7).normal(size=(1, 8, 100, 242)).astype("float32")
    first, seeds = score_tensor(models, values.tobytes())
    second, _ = score_tensor(models, values.tobytes())
    assert first == second == np.array(seeds, dtype="float32").mean()
    assert all(not model.training for model in models)
    with pytest.raises(ValueError, match="tensor"):
        score_tensor(models, b"broken")


def test_bundle_rejects_changed_weights_and_path_traversal(model_bundle):
    directory = model_bundle.directory
    metadata = model_bundle.metadata.copy()
    metadata["normalization"] = "../outside.npz"
    (directory / "bundle.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="basenames"):
        ModelBundle.load(directory)
    (directory / "bundle.json").write_text(json.dumps(model_bundle.metadata))
    with (directory / model_bundle.metadata["checkpoints"][0]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        ModelBundle.load(directory)


def test_bundle_rejects_receiver_reordering_before_hardware(model_bundle):
    meta = model_bundle.metadata
    receivers = [
        SimpleNamespace(id=key, mac=mac)
        for key, mac in zip(
            meta["receivers"], meta["radio"]["receiver_macs"], strict=True
        )
    ]
    settings = SimpleNamespace(
        profile_fingerprint=meta["radio"]["profile_fingerprint"],
        inventory=SimpleNamespace(
            transmitter=SimpleNamespace(mac=meta["radio"]["transmitter_mac"]),
            receivers=receivers,
        ),
    )
    model_bundle.validate_radio(settings)
    settings.inventory.receivers = list(reversed(receivers))
    with pytest.raises(ValueError, match="ordered identities"):
        model_bundle.validate_radio(settings)


def test_scorer_process_initializes_scores_and_shuts_down(model_bundle):
    worker = EnsembleWorker(model_bundle, threads=1)
    try:
        worker.start()
        assert worker.submit(
            np.zeros((1, 8, 100, 242), dtype="float32").tobytes(),
            dict(generation=1, end_ns=10),
        )
        deadline = time.monotonic() + 15
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.poll()
            time.sleep(0.01)
        assert result["kind"] == "prediction"
        assert 0 <= result["probability"] <= 1
        assert result["generation"] == 1
    finally:
        worker.close()
    assert not worker.process.is_alive()


@pytest.mark.parametrize("model_bundle", ["phase_change"], indirect=True)
def test_phase_bundle_scores_16_channels_without_loading_a_scaler(model_bundle):
    # The artifact named by legacy fixtures is deliberately removed: phase loading
    # must not depend on a fitted normalization file.
    (model_bundle.directory / "normalization.npz").unlink()
    bundle = ModelBundle.load(model_bundle.directory)
    assert np.all(bundle.mean == 0) and np.all(bundle.scale == 1)
    models = load_ensemble(bundle, threads=1)
    probability, _ = score_tensor(
        models, np.zeros((1, 16, 100, 242), dtype="float32").tobytes()
    )
    assert 0 <= probability <= 1
    with pytest.raises(ValueError, match="tensor size"):
        score_tensor(models, np.zeros((1, 8, 100, 242), dtype="float32").tobytes())
    metadata = bundle.metadata.copy()
    metadata["lag_seconds"] = 0.2
    (bundle.directory / "bundle.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="phase-change contract"):
        ModelBundle.load(bundle.directory)


@pytest.mark.parametrize("model_bundle", ["phase_change"], indirect=True)
def test_export_phase_bundle_preserves_frozen_weights_without_scaler(
    model_bundle, tmp_path
):
    import shutil

    experiment = tmp_path / "experiment"
    models = experiment / "models"
    models.mkdir(parents=True)
    session = tmp_path / "recording"
    session.mkdir()
    radio = model_bundle.metadata["radio"]
    environment = dict(
        radio_profile_fingerprint=radio["profile_fingerprint"],
        radio_inventory=dict(
            transmitter=dict(mac=radio["transmitter_mac"]),
            receivers=[
                dict(id=key, mac=mac)
                for key, mac in zip(
                    model_bundle.metadata["receivers"],
                    radio["receiver_macs"],
                    strict=True,
                )
            ],
        ),
    )
    (session / "session.json").write_text(json.dumps(dict(environment=environment)))
    manifest = dict(
        raw_session=str(session),
        source_sha256={"session.json": file_hash(session / "session.json")},
    )
    (experiment / "manifest.json").write_text(json.dumps(manifest))
    names = []
    for seed, source in zip(
        [17, 29, 43], model_bundle.metadata["checkpoints"], strict=True
    ):
        name = f"random20__phase_change_seed{seed}.pt"
        shutil.copy2(model_bundle.directory / source, models / name)
        names.append(name)
    selection = dict(
        winner=dict(scheme="random20", representation="phase_change"),
        selected_by_scheme=dict(random20="phase_change"),
        normalization="none",
        threshold=0.5,
        config=dict(
            receivers=model_bundle.metadata["receivers"],
            training_seeds=[17, 29, 43],
            window_seconds=4,
            bin_hz=25,
            minimum_coverage=0.7,
            lag_seconds=0.1,
            smoothing_bins=1,
            normalization="none",
        ),
        versions={},
        manifest_sha256=file_hash(experiment / "manifest.json"),
        checkpoint_sha256={name: file_hash(models / name) for name in names},
    )
    (experiment / "selection.json").write_text(json.dumps(selection))
    bundle = export_bundle(experiment, tmp_path / "deployed")
    assert bundle.metadata["normalization"] == "none"
    assert bundle.metadata["input_shape"] == [1, 16, 100, 242]
    assert len(list(bundle.directory.iterdir())) == 4
    assert bundle.metadata["sha256"] == selection["checkpoint_sha256"]
    with (models / names[0]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="checkpoint changed"):
        export_bundle(experiment, tmp_path / "rejected")
