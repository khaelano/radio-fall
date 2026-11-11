"""Keep display work independent of full-recording reads and repeated rendering."""

from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import numpy as np
import polars as pl
import pytest

from fall_detection.analysis import sequence_reporting as reporting


@pytest.fixture
def workflow(tmp_path):
    n = 257
    amplitude = np.full((n, 4, 245), 20.0, dtype=np.float64)
    amplitude[1] = np.nan
    amplitude[17, 0, 152] = np.nan
    path = tmp_path / "representative.npz"
    np.savez(
        path,
        amplitude=amplitude,
        filtered_amplitude=amplitude,
        squared_difference=np.zeros_like(amplitude),
        valid=np.isfinite(amplitude),
        hampel_replaced=np.zeros_like(amplitude, dtype=bool),
        time_ns=np.arange(n, dtype=np.int64) * 10_416_667,
        subcarriers=np.arange(-122, 123),
        unrelated=np.ones(1),
    )
    np.savez(
        tmp_path / "shard.npz", amplitude=amplitude[None, :192], target=np.array([0])
    )
    frame = pl.DataFrame(
        {
            "receiver": ["rx-1", "rx-2", "rx-3", "rx-4"],
            "replaced": [0] * 4,
            "valid": [100] * 4,
        }
    )
    return SimpleNamespace(
        name="test",
        output=tmp_path,
        segments=pl.DataFrame(
            [
                dict(
                    path=str(path),
                    segment_id="s",
                    samples=n,
                    activity_label="non_fall",
                    attempt_key="attempt",
                )
            ]
        ),
        index=pl.DataFrame(
            [
                dict(
                    duration=d,
                    segment_id="s",
                    shard="shard.npz",
                    shard_row=0,
                    start_ns=i * 1_000_000,
                    coverage=0.8,
                    target=0,
                )
                for d in (2, 4, 6)
                for i in range(100)
            ]
        ),
        shards=pl.DataFrame([dict(duration=2, shape=[1, 192, 4, 245], bytes=1000)]),
        timings={"load": 0.1},
        hampel=frame,
        alignment=pl.DataFrame({"gap_rounds": [[1]], "gap_counts": [[10]]}),
    )


def test_export_display_never_reads_representative(workflow, monkeypatch):
    @contextmanager
    def forbidden(path):
        pytest.fail("export display read unrelated representative tensors")
        yield

    monkeypatch.setattr(reporting, "read_segment", forbidden)
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    assert reporting.plot_stage(workflow, "export").is_file()


def test_hampel_display_does_not_decode_unused_arrays(workflow, monkeypatch):
    original = reporting.read_segment
    requested = []

    class Guarded(Mapping):
        def __init__(self, data):
            self.data = data

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

        def __getitem__(self, key):
            assert key not in {"squared_difference", "valid", "unrelated"}, (
                f"unused array read: {key}"
            )
            requested.append(key)
            return self.data[key]

    @contextmanager
    def guarded(path):
        with original(path) as data:
            yield Guarded(data)

    monkeypatch.setattr(reporting, "read_segment", guarded)
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    reporting.plot_stage(workflow, "hampel")
    assert "amplitude" in requested


def test_cached_plot_has_no_tensor_reads_or_render(workflow, monkeypatch):
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    first = reporting.plot_stage(workflow, "align", max_points=16, dpi=40)
    modified = first.stat().st_mtime_ns

    def forbidden(*args, **kwargs):
        pytest.fail("cached display did I/O or rendering work")

    with monkeypatch.context() as patch:
        patch.setattr(reporting.np, "load", forbidden)
        patch.setattr(reporting.plt, "subplots", forbidden)
        patch.setattr(reporting, "read_segment", forbidden)
        patch.setattr(reporting.plt, "show", forbidden)
        assert reporting.plot_stage(workflow, "align", max_points=16, dpi=40) == first
    assert first.stat().st_mtime_ns == modified


def test_previews_preserve_selected_missing_values_and_bound_artists(
    workflow, monkeypatch
):
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    original = reporting.plt.subplots
    figures = []

    def capture(*a, **k):
        result = original(*a, **k)
        figures.append(result)
        return result

    monkeypatch.setattr(reporting.plt, "subplots", capture)
    monkeypatch.setattr(
        reporting.plt, "show", lambda *a, **k: pytest.fail("duplicate inline render")
    )
    reporting.plot_stage(workflow, "align", max_points=16, dpi=40)
    image = figures[-1][1][1, 0].images[0].get_array()
    assert image.shape == (245, 16)
    assert image.mask[152, 1]
    reporting.plot_stage(
        workflow, "windows", max_points=16, max_window_overlays=5, dpi=40
    )
    for ax in figures[-1][1][:, 0]:
        assert len(ax.lines) <= 1 + 2 * 5
        assert len(ax.lines[0].get_xdata()) <= 16


def test_plot_cache_invalidates_changed_options_and_metadata(workflow, monkeypatch):
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    original = reporting.plt.subplots
    count = []

    def tracked(*a, **k):
        count.append(1)
        return original(*a, **k)

    monkeypatch.setattr(reporting.plt, "subplots", tracked)
    reporting.plot_stage(workflow, "windows", max_points=16, dpi=40)
    reporting.plot_stage(workflow, "windows", max_points=17, dpi=40)
    workflow.index = workflow.index.with_columns(pl.lit(0.5).alias("coverage"))
    reporting.plot_stage(workflow, "windows", max_points=17, dpi=40)
    assert len(count) == 3


def test_shared_scales_cache_avoids_loading_again(workflow, monkeypatch):
    scales = reporting.comparison_scales([workflow], max_points=16)
    monkeypatch.setattr(
        reporting,
        "read_segment",
        lambda *a, **k: pytest.fail("cached scales loaded data"),
    )
    assert reporting.comparison_scales([workflow], max_points=16) == scales


def test_array_preview_reused_across_stages(workflow, monkeypatch):
    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    reporting.comparison_scales([workflow], max_points=16)
    original = reporting.read_segment

    @contextmanager
    def guarded(path):
        with original(path) as data:

            class OnlyNeeded(Mapping):
                def __iter__(self):
                    return iter(data)

                def __len__(self):
                    return len(data)

                def __getitem__(self, key):
                    assert key != "amplitude", "reloaded a shared amplitude preview"
                    return data[key]

            yield OnlyNeeded()

    monkeypatch.setattr(reporting, "read_segment", guarded)
    reporting.plot_stage(workflow, "hampel", max_points=16, dpi=40)


def test_availability_bins_include_short_gaps(workflow):
    values = reporting._preview(workflow.segments["path"][0], "availability", 16)
    assert values.shape == (16, 4)
    assert (values[0] < 1).all() and (values[0] > 0).all()


def test_plot_cache_invalidates_changed_signal_file(workflow, monkeypatch):
    import os

    monkeypatch.setattr("IPython.display.display", lambda *a, **k: None)
    original = reporting.plt.subplots
    renders = []

    def tracked(*a, **k):
        renders.append(1)
        return original(*a, **k)

    monkeypatch.setattr(reporting.plt, "subplots", tracked)
    reporting.plot_stage(workflow, "windows", max_points=16, dpi=40)
    source = Path(workflow.segments["path"][0])
    before = source.stat()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1))
    reporting.plot_stage(workflow, "windows", max_points=16, dpi=40)
    assert len(renders) == 2
