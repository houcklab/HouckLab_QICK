import json

import numpy as np
import pytest
from numpy.testing import assert_allclose

from fluxpred.core import Command, Filter, compare_commands, render, tail_bound


def example():
    return Filter(taus_ns=[8000, 64000], amplitudes=[1.0], coefficients=[[0.04, -0.02]])


def test_exact_state_average_and_round_trip_superposition():
    model = example()
    command, state = render(model, [(1, 12000), (0, 16000)])
    tau = np.array(model.taus_ns)
    c = np.array(model.coefficients[0])
    for start, stop, actual in zip(command.edges_ns[:-1], command.edges_ns[1:], command.values):
        def integral(edge, amplitude):
            a, b = max(start-edge, 0), max(stop-edge, 0)
            return amplitude * ((b-a) + np.sum(c*tau*(np.exp(-a/tau)-np.exp(-b/tau))))
        expected = (integral(0, 1) + integral(12000, -1)) / (stop-start)
        assert actual == pytest.approx(expected, abs=1e-14)
    assert_allclose(state, c*(1-np.exp(-12000/tau))*np.exp(-16000/tau))
    assert tail_bound(state) >= abs(command.values[-1]) * 0.9


def test_streaming_preserves_history_and_does_not_mutate_input_state():
    model = example()
    full, final = render(model, [(1, 8000), (0, 8000), (0.7, 12000)])
    first, state = render(model, [(1, 8000), (0, 8000)])
    original = state.copy()
    second, second_final = render(model, [(0.7, 12000)], initial_state=state)
    assert_allclose(full.values, np.r_[first.values, second.values])
    assert_allclose(final, second_final)
    assert_allclose(state, original)


def test_conditioned_potential_retains_outbound_history_on_return():
    model = Filter([8000], [0.5, 1], [[0.02], [0.08]])
    assert_allclose(model.potential(0.75), [0.75*0.05])
    assert_allclose(model.potential(0), [0])
    _, state = render(model, [(0.75, 12000)])
    recovery, final = render(model, [(0, 4000)], initial_state=state)
    assert recovery.values[0] == pytest.approx(-state[0]*2*(1-np.exp(-0.5)))
    assert final[0] == pytest.approx(state[0]*np.exp(-0.5))
    with pytest.raises(ValueError, match="amplitude"):
        render(model, [(1.01, 4000)])
    with pytest.raises(ValueError, match="amplitude"):
        render(model, [(-0.5, 4000)])


def test_causality_and_arbitrary_hold_edges():
    model = example()
    a, _ = render(model, [(1, 13000), (0, 17000)])
    b, _ = render(model, [(1, 13000), (0.5, 17000)])
    assert_allclose(a.values[:4], b.values[:4])
    assert 13000 in a.edges_ns
    assert a.edges_ns[-1] == 30000
    assert_allclose(render(model, [(0, 4000)])[0].values, 0)


def test_serialization_is_strict_and_roundtrips():
    original = example()
    doc = json.loads(json.dumps(original.to_dict(), allow_nan=False))
    assert Filter.from_dict(doc).to_dict() == original.to_dict()
    for bad in [dict(doc, schema_version=2), dict(doc, algorithm="piecewise"), dict(doc, unexpected=1),
                dict(doc, coefficients=[[float('nan'), 0]]), dict(doc, taus_ns=[1000, 64000])]:
        with pytest.raises(ValueError):
            Filter.from_dict(bad)


@pytest.mark.parametrize("kwargs", [dict(taus_ns=[0]), dict(taus_ns=[float('inf')]),
    dict(coefficients=[[0.3]]), dict(amplitudes=[1, 0.5]), dict(resolution_ns=0)])
def test_rejects_unstable_or_unbounded_filter(kwargs):
    args = dict(taus_ns=[8000], amplitudes=[1], coefficients=[[0.02]])
    args.update(kwargs)
    with pytest.raises(ValueError):
        Filter(**args)


@pytest.mark.parametrize("edges,values", [([1, 2], [1]), ([0, 2, 1], [1, 2]),
    ([0, 1], [float('nan')]), ([0, 1], []), ([0, float('inf')], [1])])
def test_command_schema(edges, values):
    with pytest.raises(ValueError):
        Command(edges, values)


def test_comparison_integrates_on_union_of_edges_not_sample_points():
    a = Command([0, 100, 200], [1, 0])
    b = Command([0, 110, 200], [1, 0])
    metrics = compare_commands(a, b)
    assert metrics['max_abs'] == 1
    assert metrics['rms'] == pytest.approx(np.sqrt(10/200))
    assert metrics['integrated_abs_ns'] == 10
    with pytest.raises(ValueError):
        compare_commands(a, Command([0, 210], [0]))


def test_comparison_handles_floating_point_endpoint_epsilon():
    a = Command([0, 100], [1])
    b = Command([0, 100+5e-7], [1])
    assert compare_commands(a, b)['rms'] == 0


def test_fail_before_allocating_excessive_command():
    with pytest.raises(ValueError, match="segment"):
        render(example(), [(1, 1e12)], max_segments=100)
    with pytest.raises(ValueError):
        render(example(), [(1, -1)])
    with pytest.raises(ValueError):
        render(example(), [(1, 4000)], initial_state=[float('nan'), 0])
    for limit in [float('nan'), float('inf'), 1.5, True]:
        with pytest.raises(ValueError):
            render(example(), [(1, 4000)], max_segments=limit)
