import json

import pytest

from fluxpred.core import Command
from fluxpred.prepare import legacy_round_trip, compile_bank, prepare


def test_legacy_fallback_is_explicit_and_superposes_return_history():
    step = {'segment_edges_ns': [0, 8000, 20000], 'multipliers': [1.1, 1.03, 1]}
    cmd = legacy_round_trip(step, hold_ns=12000, recovery_ns=40000)
    pairs = list(zip(cmd.edges_ns[:-1], cmd.values))
    assert (12000, pytest.approx(-.07)) in pairs
    assert (20000, pytest.approx(-.03)) in pairs
    assert cmd.values[-1] == 0


def test_legacy_recovery_cannot_end_in_a_zero_gap_before_a_later_change():
    step = {'segment_edges_ns': [0, 100000], 'multipliers': [1, 1.03]}
    with pytest.raises(ValueError, match='horizon'):
        legacy_round_trip(step, hold_ns=10000, recovery_ns=20000)
    complete = legacy_round_trip(step, hold_ns=10000, recovery_ns=100000)
    assert complete.values[-1] == 0
    assert complete.edges_ns[-2] == 110000


def test_program_bank_counts_all_conditions_not_only_largest():
    cmds = [Command([0, 4000, 8000], [1, 0])]*3
    profiles = dict(backend='qick', park=0, scale=10000, clock_ns=4)
    with pytest.raises(ValueError, match='bank'):
        compile_bank(cmds, **profiles, max_instructions=300)
    assert len(compile_bank(cmds, **profiles, max_instructions=1000)) == 3


def test_failed_scientific_gate_allows_only_labelled_diagnostic_plan(tmp_path):
    from fluxpred.core import Filter
    model = Filter([8000], [1], [[.02]])
    doc = {'schema_version': 1, 'model': model.to_dict(),
           'coordinate': {'park': .18, 'scale': .24, 'unit': 'V'},
           'evidence': {'scientific_gate_pass': False, 'hardware_ready': False, 'emission_sample_ns': 2000}}
    path = tmp_path/'model.json'; path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='gate'):
        prepare(mode='neutral', model_path=path, backend='qua', park=.18, scale=.24,
                holds_ns=[12000], recovery_ns=200000, diagnostic=False)
    plan = prepare(mode='neutral', model_path=path, backend='qua', park=.18, scale=.24,
                   holds_ns=[12000], recovery_ns=200000, diagnostic=True)
    assert plan['hardware_ready'] is False
    assert plan['mode'] == 'neutral'
    assert plan['shots'][0]['normalized_command']['values'][-1] == 0
    assert plan['acquisition_performed'] is False


def test_uncorrected_fallback_does_not_require_candidate():
    plan = prepare(mode='uncorrected', backend='qick', park=-25146, scale=10396,
                   holds_ns=[12000], recovery_ns=200000, clock_ns=4, diagnostic=True)
    assert plan['shots'][0]['normalized_command']['values'] == [1.0, 0.0]
