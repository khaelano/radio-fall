"""The prune tool must never report a session that holds radio data as empty."""

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "processing" / "prune_data.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("prune_data", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_has_radio_data_counts_journals_and_compressed_sidecars(tool, tmp_path):
    receivers = tmp_path / "{}" / "trials/001_a/attempt_01/receivers/rx-1"
    journal = tmp_path / "journal" / "transport/gateway/run/envelopes.bin"
    _write(journal, b"\x00")
    _write(Path(str(receivers).format("zst")) / "csi.csv.zst", b"\x28\xb5")
    _write(Path(str(receivers).format("csv")) / "csi.csv", b"type,id\nCSI_DATA,1\n")
    _write(Path(str(receivers).format("header")) / "csi.csv", b"type,id\n")
    (tmp_path / "bare" / "trials").mkdir(parents=True)

    assert tool.has_radio_data(tmp_path / "journal")
    assert tool.has_radio_data(tmp_path / "zst")
    assert tool.has_radio_data(tmp_path / "csv")
    assert not tool.has_radio_data(tmp_path / "header")
    assert not tool.has_radio_data(tmp_path / "bare")
