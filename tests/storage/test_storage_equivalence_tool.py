"""The CSV equivalence tool must not pass when it compared nothing."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("pyarrow")

from fall_detection._radio_native import storage_convert
from journal_builder import build_session

TOOL = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "processing"
    / "check_storage_equivalence.py"
)


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_storage_equivalence", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def converted(tmp_path):
    source = build_session(tmp_path / "session", batches=4, era="python")
    out = tmp_path / "frames"
    storage_convert(source, out)
    return Path(source), out / "frames.parquet"


def test_session_without_csv_rows_fails_instead_of_passing(tool, converted, capsys):
    source, frames = converted

    with pytest.raises(ValueError, match="no CSV rows were compared"):
        tool.check(source, frames)
    assert tool.main([str(source), str(frames)]) == 1
    assert "no CSV rows were compared" in capsys.readouterr().err


def test_manifest_without_csv_sidecars_fails(tool, converted, capsys):
    source, frames = converted
    manifest = source / "session.json"
    data = json.loads(manifest.read_text()) if manifest.exists() else {}
    data["environment"] = {**data.get("environment", {}), "csv_sidecars": False}
    manifest.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="csv_sidecars: false"):
        tool.check(source, frames)
    assert tool.main([str(source), str(frames)]) == 1
    assert "csv_sidecars: false" in capsys.readouterr().err
