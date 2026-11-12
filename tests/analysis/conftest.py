"""Load experiment definitions from their authoritative notebook cells."""

# These tests execute only trusted, repository-owned notebook cells.
# ruff: noqa: S102

import ast
import json
import os
from pathlib import Path

import numpy as np
import pytest

NOTEBOOKS = Path(__file__).resolve().parents[2] / "notebooks/latest"


def code_cells(name: str) -> dict[str, str]:
    notebook = json.loads((NOTEBOOKS / name).read_text())
    return {
        cell["id"]: "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    }


@pytest.fixture
def notebook_label_windows():
    tree = ast.parse(code_cells("02_preprocess.ipynb")["c6518ea1"])
    definition = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    namespace = {"np": np, "WINDOW_OVERLAP": 0.5}
    exec(
        compile(ast.Module([definition], []), "02_preprocess.ipynb", "exec"), namespace
    )
    return namespace["label_windows"]


@pytest.fixture
def training_notebook():
    pytest.importorskip("torch")
    namespace = {
        "Path": Path,
        "json": json,
        "os": os,
        "PROJECT_ROOT": NOTEBOOKS.parents[1],
    }
    import polars as pl

    from fall_detection.analysis.sequence_training_data import SegmentStore

    namespace.update(pl=pl, SegmentStore=SegmentStore)
    cells = code_cells("03_training.ipynb")
    for identifier in (
        "e1d34b7d",
        "dd512d89",
        "49721a0c",
        "cf18ef59",
        "b385170d",
        "2cb98c36",
        "fb056210",
    ):
        exec(compile(cells[identifier], "03_training.ipynb", "exec"), namespace)
    return namespace


@pytest.fixture
def summarize_phase_bursts():
    namespace = {}
    exec(
        compile(
            code_cells("01_02_phase_exp.ipynb")["burst-policy"],
            "01_02_phase_exp.ipynb",
            "exec",
        ),
        namespace,
    )
    return namespace["summarize_phase_bursts"]
