import hashlib
import json
from pathlib import Path

from fluxpred.run_offline import run


def test_frozen_offline_pipeline_reproduces_and_keeps_failed_gates(tmp_path):
    source = Path(__file__).resolve().parents[1]/'reports/neutral_flux/input_traces.json'
    before = source.read_bytes()
    first = run(source, tmp_path/'first')
    second = run(source, tmp_path/'second')
    assert source.read_bytes() == before
    assert first['snapshot_sha256'] == hashlib.sha256(before).hexdigest()
    assert not first['gates']['scientific_gate_pass']
    assert not first['gates']['hardware_ready']
    assert len(first['loao']) == 3
    assert first['loao'][1]['outside_training_hull'] is False
    assert set(first['training_ids']).isdisjoint(first['validation_ids'])
    assert all('nested_train_only_selection' in fold for fold in first['loao'])
    for path in (tmp_path/'first').glob('*.json'):
        assert path.read_bytes() == (tmp_path/'second'/path.name).read_bytes()
    candidate = json.loads((tmp_path/'first'/'conditioned_candidate.json').read_text())
    assert candidate['model']['resolution_ns'] == 4000
    assert min(candidate['model']['taus_ns']) >= 8000
