"""Hardware-free contracts for lowering complete neutral commands to QICK."""

import importlib
from types import SimpleNamespace

import numpy as np
import pytest


def api():
    try:
        return importlib.import_module("fluxpred.qick")
    except ModuleNotFoundError as exc:
        pytest.fail(f"QICK command compiler is not available: {exc}")


def command(edges, values):
    # The compiler consumes this structural interface; core validates its own Command.
    return SimpleNamespace(edges_ns=np.asarray(edges, float), values=np.asarray(values, float))


def compile_plan(cmd, **kwargs):
    settings = dict(park_gain=100, scale_gain=-1000, clock_ns=4, max_gain=32767,
                    max_instructions=4096)
    settings.update(kwargs)
    return api().compile_command(cmd, **settings)


@pytest.mark.parametrize("hold_ns", [12, 20, 100, 1000])
def test_complete_return_history_is_preserved_for_each_hold(hold_ns):
    plan = compile_plan(command([0, hold_ns, hold_ns + 20, hold_ns + 40, hold_ns + 52],
                                [1.2, -0.2, -0.1, 0]))
    assert [seg.gain for seg in plan.segments] == [-1100, 300, 200, 100]
    assert [seg.cycles for seg in plan.segments] == [hold_ns // 4, 5, 5, 3]
    np.testing.assert_allclose(plan.normalized_command.values, [1.2, -0.2, -0.1, 0])
    np.testing.assert_array_equal(plan.normalized_command.edges_ns,
                                  [0, hold_ns, hold_ns + 20, hold_ns + 40, hold_ns + 52])


def test_quantizes_cumulative_boundaries_without_per_segment_drift():
    plan = compile_plan(command([0, 14, 28, 42, 56], [1, 0.5, -0.2, 0]))
    assert [seg.cycles for seg in plan.segments] == [4, 3, 3, 4]
    assert sum(seg.cycles for seg in plan.segments) == 14


def test_same_quantized_gain_can_merge_before_minimum_length_validation():
    plan = compile_plan(command([0, 4, 8, 16], [1, 1.0001, 1]))
    assert [(seg.gain, seg.cycles) for seg in plan.segments] == [(-900, 4)]


@pytest.mark.parametrize("edges", [[0, 4, 20], [0, 1, 20]])
def test_rejects_unrealizable_short_segment_instead_of_stretching(edges):
    with pytest.raises(ValueError, match="cycle|short"):
        compile_plan(command(edges, [1, 0]))


def test_long_segment_split_preserves_exact_total_and_minimum_chunk():
    plan = compile_plan(command([0, 260004], [1]))
    assert len(plan.segments) == 2
    assert sum(seg.cycles for seg in plan.segments) == 65001
    assert all(3 <= seg.cycles <= 65000 for seg in plan.segments)


def test_gain_quantization_is_nearest_integer():
    plan = compile_plan(command([0, 12, 24], [0.0104, 0.0116]))
    assert [seg.gain for seg in plan.segments] == [90, 88]


def test_exact_half_integer_gains_use_nearest_even_rounding():
    plan = compile_plan(command([0, 12, 24, 36], [2.5, 3.5, -2.5]),
                        park_gain=0, scale_gain=1)
    assert [seg.gain for seg in plan.segments] == [2, 4, -2]


@pytest.mark.parametrize("settings", [dict(scale_gain=30000), dict(park_gain=32760)])
def test_rejects_overrange_command_without_clipping(settings):
    with pytest.raises(ValueError, match="gain|range"):
        compile_plan(command([0, 12, 24], [1.5, -1.5]), **settings)


@pytest.mark.parametrize("settings", [dict(clock_ns=0), dict(clock_ns=np.nan),
    dict(scale_gain=0), dict(scale_gain=np.inf), dict(park_gain=np.nan),
    dict(max_gain=0), dict(max_gain=np.inf), dict(max_gain=32768),
    dict(max_instructions=0)])
def test_invalid_hardware_limits_fail_before_emission(settings):
    with pytest.raises(ValueError):
        compile_plan(command([0, 12], [0]), **settings)


def test_instruction_budget_rejects_large_unrolled_plan():
    with pytest.raises(ValueError, match="instruction"):
        compile_plan(command([0, 12, 24], [1, 0]), max_instructions=1)


def test_plan_reports_estimate_without_claiming_actual_qick_compilation():
    plan = compile_plan(command([0, 12, 24], [1, 0]))
    assert plan.instruction_estimate >= 2 * 24
    assert not plan.actual_compile_checked
    assert plan.waveform_samples == 0


class RecordingProgram:
    """Minimal external QICK boundary; compilation and scheduling remain production code."""
    cfg = {"ff_ch": 0, "ff_park_gain": 100}

    def __init__(self, clock_ns=4):
        self.clock_ns = clock_ns
        self.soccfg = {"gens": [{"f_fabric": 1000 / clock_ns, "maxv": 32767,
                                  "maxv_scale": 1.0}]}
        self.events = []

    def us2cycles(self, time_us, gen_ch=None):
        assert gen_ch == 0
        return round(time_us * 1000 / self.clock_ns)

    def set_pulse_registers(self, **kwargs):
        self.events.append(("registers", kwargs))

    def pulse(self, **kwargs):
        self.events.append(("pulse", kwargs))

    def sync_all(self, cycles):
        self.events.append(("sync", cycles))


def test_emission_queues_full_schedule_without_sync_or_extra_park_transition():
    plan = compile_plan(command([0, 12, 24, 36], [1, -0.2, 0]))
    prog = RecordingProgram()
    api().emit(plan, prog, channel=0)
    assert [event[0] for event in prog.events] == ["registers", "pulse"] * 3
    commands = [event[1] for event in prog.events if event[0] == "registers"]
    assert [value["gain"] for value in commands] == [-900, 300, 100]
    assert all(value["style"] == "const" and value["stdysel"] == "last"
               and value["length"] == 3 for value in commands)


def test_emission_rejects_clock_mismatch_before_register_write():
    prog = RecordingProgram(clock_ns=8)
    plan = compile_plan(command([0, 12], [0]))
    with pytest.raises(ValueError, match="clock"):
        api().emit(plan, prog, channel=0)
    assert prog.events == []


def test_emission_rechecks_actual_generator_headroom_before_register_write():
    prog = RecordingProgram()
    prog.soccfg["gens"][0]["maxv"] = 500
    plan = compile_plan(command([0, 12, 24], [1, 0]))
    with pytest.raises(ValueError, match="gain"):
        api().emit(plan, prog, channel=0)
    assert prog.events == []


def test_emission_rechecks_program_clock_conversion_before_register_write():
    prog = RecordingProgram()
    prog.us2cycles = lambda *args, **kwargs: 500
    plan = compile_plan(command([0, 12], [0]))
    with pytest.raises(ValueError, match="clock"):
        api().emit(plan, prog, channel=0)
    assert prog.events == []


def test_begin_schedule_requires_completed_reset_and_final_park_latch():
    helper = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.neutral_flux")
    plan = compile_plan(command([0, 12, 24], [1, 0]))
    prog = RecordingProgram()
    with pytest.raises(ValueError, match="reset"):
        helper.begin_schedule(plan, prog, channel=0, reset_completed_at_park=False)
    assert prog.events == []
    helper.begin_schedule(plan, prog, channel=0, reset_completed_at_park=True)
    assert prog.events[0] == ("sync", 0)
    assert [event[0] for event in prog.events].count("sync") == 1
    nonpark = compile_plan(command([0, 12], [1]))
    with pytest.raises(ValueError, match="park"):
        helper.begin_schedule(nonpark, RecordingProgram(), channel=0,
                              reset_completed_at_park=True)


def test_begin_schedule_does_not_reset_or_consume_inverse_history():
    helper = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.neutral_flux")
    plan = compile_plan(command([0, 12, 24, 36, 48], [1, -0.3, 0.2, 0]))
    prog = RecordingProgram()
    helper.begin_schedule(plan, prog, channel=0, reset_completed_at_park=True)
    assert [event[1]["gain"] for event in prog.events if event[0] == "registers"] == [
        -900, 400, -100, 100]
