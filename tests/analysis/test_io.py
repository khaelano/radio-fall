"""Atomic publication helpers keep previous files intact on failure."""

import pytest

from fall_detection.analysis._io import atomic_json


def test_atomic_json_failure_preserves_file_and_leaves_no_temporary(tmp_path):
    path = tmp_path / "manifest.json"
    atomic_json({"version": 1}, path)
    with pytest.raises(TypeError):
        atomic_json({"version": object()}, path)
    assert path.read_text() == '{\n  "version": 1\n}\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["manifest.json"]
