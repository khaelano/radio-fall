"""Exercise data preparation and the notebook's visible training cells."""
import json
from pathlib import Path

import numpy as np
import polars as pl

from fall_detection.analysis.amplitude_pipeline import save_recording
from fall_detection.analysis.window_data import index_windows, pooled_input, save_manifest, split_attempts


def test_pooling_ignores_missing_and_exposes_coverage():
    values = np.array([[1.], [99.], [3.], [5.]], dtype=np.float32)
    mask = np.array([[1], [0], [1], [1]], dtype=bool)
    np.testing.assert_array_equal(pooled_input(values, mask, 2), [[1., 0.5], [4., 1.]])


def test_notebook_trains_each_model_on_grouped_synthetic_windows(tmp_path):
    root = tmp_path / 'windows'
    for duration in (2, 4, 6):
        for attempt in range(10):
            for receiver in ('rx-1', 'rx-2'):
                path = root / f'{duration}s' / f'trial{attempt}' / f'{receiver}.npz'
                data = np.random.default_rng(attempt).normal(size=(3, duration*80, 4)).astype('f4')
                save_recording(path, {'amplitude': data, 'valid': np.ones_like(data, dtype=bool),
                    'label': np.array(['preparation', 'action', 'resting']),
                    'provenance_json': np.asarray(json.dumps({'session_id': 'session', 'attempt_key': f'trial{attempt}', 'receiver_id': receiver}))})
    notebook = json.loads(Path('notebooks/latest/03_training.ipynb').read_text())
    cells = [''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code']
    namespace = {}
    exec(compile(cells[0], 'setup cell', 'exec'), namespace)
    index = split_attempts(index_windows(root), 42)
    assert index.group_by('group').agg(pl.col('split').n_unique().alias('n'))['n'].max() == 1
    save_manifest(index, tmp_path / 'results', {'split_seed': 42})
    namespace.update(index=index, RESULT_DIR=tmp_path / 'results', WINDOW_DURATIONS=(2,))
    metrics_cell = next(cell for cell in cells if cell.startswith('def metrics'))
    exec(compile(metrics_cell, 'metrics cell', 'exec'), namespace)
    for name, run_prefix in (
        ('CNN', 'cnn_results = []'), ('LSTM', 'lstm_results = []'),
        ('GRU', 'gru_results = []'), ('FOREST', 'forest_results = []'),
    ):
        config_cell = next(cell for cell in cells if cell.startswith(name + '_CONFIG ='))
        run_cell = next(cell for cell in cells if cell.startswith(run_prefix))
        exec(compile(config_cell, name + ' config', 'exec'), namespace)
        config = namespace[name + '_CONFIG']
        config.update(temporal_bins=4)
        if name == 'FOREST':
            config.update(n_estimators=2, n_jobs=1)
        else:
            config.update(epochs=1, batch_size=8, hidden_size=4)
            definition = next(cell for cell in cells if cell.startswith('class ' + name + 'Model'))
            exec(compile(definition, name + ' model', 'exec'), namespace)
        exec(compile(run_cell, name + ' training', 'exec'), namespace)
    results = namespace['cnn_results'] + namespace['lstm_results'] + namespace['gru_results'] + namespace['forest_results']
    assert len(results) == 4
    for result in results:
        assert sum(result['counts'].values()) == 60
        assert len(result['test']['confusion_matrix']) == 3
        assert (tmp_path / 'results' / '2s' / result['model'] / 'metrics.json').is_file()
        model_file = 'model.joblib' if result['model'] == 'random_forest' else 'model.pt'
        assert (tmp_path / 'results' / '2s' / result['model'] / model_file).is_file()
        load_cell = next(cell for cell in cells if cell.startswith('from fall_detection.analysis.window_data import pooled_input'))
        load_cell = load_cell.replace('LOAD_MODEL = "cnn"', 'LOAD_MODEL = "' + result['model'] + '"')
        exec(compile(load_cell, 'load saved model', 'exec'), namespace)
        assert 0 <= namespace['predicted_id'] < 3
    # The comparison must also work when the user runs only one model section.
    for name in ('lstm_results', 'gru_results', 'forest_results'):
        del namespace[name]
    comparison_cell = next(cell for cell in cells if cell.startswith('results = ['))
    exec(compile(comparison_cell, 'comparison cell', 'exec'), namespace)
    assert namespace['comparison'].height == 1
