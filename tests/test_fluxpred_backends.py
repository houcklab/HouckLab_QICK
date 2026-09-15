import numpy as np
import pytest

from fluxpred.core import Command, Filter, geometric_schedule, render, render_on_schedule
from fluxpred import qick as qick_backend
from fluxpred import qua as qua_backend
from fluxpred import report

Q3_PARK_GAIN = -25146.0
Q3_TARGET_GAIN = -14750.0
Q3_SCALE_GAIN = Q3_TARGET_GAIN - Q3_PARK_GAIN
Q3_CLOCK_NS = 1000.0 / 430.08

Q5_PARK_V = 0.156232010522
Q5_TARGET_V = 0.387741615
Q5_SCALE_V = Q5_TARGET_V - Q5_PARK_V

TAUS_NS = np.array([8_000.0, 24_000.0, 64_000.0, 192_000.0])
COEFFICIENTS = np.array([0.06, -0.04, 0.03, -0.02])
PRODUCTION_HOLDS_NS = (2_000.0, 40_000.0, 80_000.0, 200_000.0)
RECOVERY_NS = 400_000.0


def model(resolution_ns=4000.0):
    return Filter(TAUS_NS, [1.0], [COEFFICIENTS], resolution_ns=resolution_ns)


class FakeGenerator(dict):
    pass


class FakeProgram:
    def __init__(self, fabric_mhz=430.08, maxv=32767, maxv_scale=1.0, channels=(6,)):
        self.soccfg = {"gens": [FakeGenerator({"f_fabric": fabric_mhz, "maxv": maxv,
                                               "maxv_scale": maxv_scale})
                                for _ in range(max(channels) + 1)]}
        self.gen_chs = {channel: {} for channel in channels}
        self.fabric_mhz = fabric_mhz
        self.emitted = []

    def us2cycles(self, value, gen_ch=None):
        return int(round(float(value) * self.fabric_mhz))

    def set_pulse_registers(self, **kwargs):
        self._pending = kwargs

    def pulse(self, ch):
        self.emitted.append(dict(self._pending, ch=ch))


class FakeQua:
    def __init__(self):
        self.calls = []

    def align(self, *elements):
        self.calls.append(("align", elements))

    def set_dc_offset(self, element, channel, value):
        self.calls.append(("set_dc_offset", element, channel, float(value)))

    def wait(self, duration, element):
        self.calls.append(("wait", int(duration), element))


def qua_config(filter_taps=None):
    analog = {"offset": 0.0}
    if filter_taps is not None:
        analog["filter"] = filter_taps
    return {"elements": {"flux_q5": {"singleInput": {"port": ("con1", 5)}}},
            "controllers": {"con1": {"analog_outputs": {5: analog}}}}


def production_command(hold_ns=200_000.0, recovery_ns=RECOVERY_NS, sample_ns=4000.0):
    command, _ = render(model(), [(1.0, hold_ns), (0.0, recovery_ns)], sample_ns=sample_ns)
    return Command(np.r_[command.edges_ns, command.edges_ns[-1] + 4000.0],
                   np.r_[command.values, 0.0])


def test_qua_lowering_preserves_park_and_target_voltages():
    plan = qua_backend.compile_command(production_command(), park_v=Q5_PARK_V, scale_v=Q5_SCALE_V)
    assert plan.commands_v[0] > Q5_TARGET_V
    assert plan.commands_v[-1] == pytest.approx(Q5_PARK_V, abs=plan.voltage_quantum_v)
    assert plan.max_timing_error_ns <= 2.0
    assert plan.max_voltage_error_v <= plan.voltage_quantum_v


def test_qua_rejects_a_nonempty_builtin_output_filter():
    plan = qua_backend.compile_command(production_command(), park_v=Q5_PARK_V, scale_v=Q5_SCALE_V)
    with pytest.raises(ValueError, match="empty OPX output filter"):
        qua_backend.emit(plan, "flux_q5", config=qua_config({"feedforward": [1.0, -0.9]}),
                         sync_elements=("q5", "r5"), qua=FakeQua())


def test_qua_accepts_an_absent_and_an_empty_output_filter():
    plan = qua_backend.compile_command(production_command(), park_v=Q5_PARK_V, scale_v=Q5_SCALE_V)
    for taps in (None, {}, {"feedforward": [], "feedback": []}):
        fake = FakeQua()
        qua_backend.emit(plan, "flux_q5", config=qua_config(taps),
                         sync_elements=("q5", "r5"), qua=fake)
        assert fake.calls[0][0] == "align"


def test_qua_emit_aligns_once_then_only_advances_flux():
    plan = qua_backend.compile_command(production_command(hold_ns=40_000.0),
                                       park_v=Q5_PARK_V, scale_v=Q5_SCALE_V)
    fake = FakeQua()
    qua_backend.emit(plan, "flux_q5", config=qua_config(), sync_elements=("q5", "r5"), qua=fake)
    assert sum(1 for call in fake.calls if call[0] == "align") == 1
    writes = [call for call in fake.calls if call[0] == "set_dc_offset"]
    waits = [call for call in fake.calls if call[0] == "wait"]
    assert len(writes) == len(waits) == len(plan.commands_v)
    assert all(call[3] == "flux_q5" if False else call[2] == "flux_q5" for call in waits)


def test_qua_clipping_fails_rather_than_saturating():
    command = Command([0.0, 100_000.0], [1.0])
    with pytest.raises(ValueError, match="output range"):
        qua_backend.compile_command(command, park_v=0.4, scale_v=0.4, output_limit_v=0.5)


def test_qua_rejects_a_segment_shorter_than_one_clock_quantum():
    command = Command([0.0, 2.0, 100_000.0], [1.0, 0.0])
    with pytest.raises(ValueError, match="clocks"):
        qua_backend.compile_command(command, park_v=Q5_PARK_V, scale_v=Q5_SCALE_V)


def test_qua_instruction_budget_is_enforced():
    with pytest.raises(ValueError, match="instruction budget"):
        qua_backend.compile_command(production_command(), park_v=Q5_PARK_V, scale_v=Q5_SCALE_V,
                                    max_instructions=8)


def test_qick_lowering_uses_the_supplied_fabric_clock():
    plan = qick_backend.compile_command(production_command(), park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS)
    assert plan.clock_ns == Q3_CLOCK_NS
    total = sum(segment.cycles for segment in plan.segments)
    assert total * Q3_CLOCK_NS == pytest.approx(production_command().edges_ns[-1], abs=Q3_CLOCK_NS)


def test_qick_validate_rejects_a_clock_that_disagrees_with_soccfg():
    plan = qick_backend.compile_command(production_command(), park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=4.0)
    with pytest.raises(ValueError, match="generator fabric clock"):
        qick_backend.validate_program_compatibility(plan, FakeProgram(), channel=6)


def test_qick_validate_accepts_the_actual_soccfg_clock():
    program = FakeProgram()
    plan = qick_backend.compile_command(production_command(), park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS)
    qick_backend.validate_program_compatibility(plan, program, channel=6)


def test_qick_validate_rejects_an_undeclared_generator_channel():
    program = FakeProgram(channels=(6,))
    plan = qick_backend.compile_command(production_command(), park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS)
    with pytest.raises(ValueError, match="declared"):
        qick_backend.validate_program_compatibility(plan, program, channel=0)


def test_qick_emit_queues_every_segment_with_a_persistent_final_level():
    program = FakeProgram()
    plan = qick_backend.compile_command(production_command(hold_ns=40_000.0),
                                        park_gain=Q3_PARK_GAIN, scale_gain=Q3_SCALE_GAIN,
                                        clock_ns=Q3_CLOCK_NS)
    qick_backend.emit(plan, program, channel=6)
    assert len(program.emitted) == len(plan.segments)
    assert all(call["stdysel"] == "last" for call in program.emitted)
    assert program.emitted[-1]["gain"] == int(round(Q3_PARK_GAIN))


def test_qick_clipping_fails_rather_than_saturating():
    command = Command([0.0, 100_000.0], [1.0])
    with pytest.raises(ValueError, match="clipping is forbidden"):
        qick_backend.compile_command(command, park_gain=30_000.0, scale_gain=10_000.0,
                                     clock_ns=Q3_CLOCK_NS)


def test_qick_merges_adjacent_equal_segments():
    command = Command([0.0, 10_000.0, 20_000.0, 30_000.0], [1.0, 1.0, 0.0])
    plan = qick_backend.compile_command(command, park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS)
    assert len(plan.segments) == 2


def test_qick_rejects_an_edge_that_vanishes_under_quantization():
    command = Command([0.0, 1.0, 30_000.0], [1.0, 0.0])
    with pytest.raises(ValueError, match="three fabric cycles"):
        qick_backend.compile_command(command, park_gain=Q3_PARK_GAIN,
                                     scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS)


def test_qick_instruction_budget_is_enforced():
    with pytest.raises(ValueError, match="instruction allowance"):
        qick_backend.compile_command(production_command(), park_gain=Q3_PARK_GAIN,
                                     scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS,
                                     max_instructions=64)


def test_cumulative_rounding_does_not_accumulate_duration_error():
    command, _ = render(model(), [(1.0, 200_000.0), (0.0, 800_000.0)], sample_ns=1234.0)
    plan = qua_backend.compile_command(command, park_v=Q5_PARK_V, scale_v=Q5_SCALE_V,
                                       max_instructions=100_000)
    total_clk = plan.edges_clk[-1] * plan.clock_ns
    assert abs(total_clk - command.edges_ns[-1]) <= plan.clock_ns
    plan = qick_backend.compile_command(command, park_gain=Q3_PARK_GAIN,
                                        scale_gain=Q3_SCALE_GAIN, clock_ns=Q3_CLOCK_NS,
                                        max_instructions=100_000)
    total_ns = sum(segment.cycles for segment in plan.segments) * Q3_CLOCK_NS
    assert abs(total_ns - command.edges_ns[-1]) <= Q3_CLOCK_NS


def test_both_backends_include_the_target_and_the_return_edge():
    command = production_command(hold_ns=80_000.0)
    qua_command = qua_backend.reconstruct_command(
        qua_backend.compile_command(command, park_v=Q5_PARK_V, scale_v=Q5_SCALE_V))
    qick_command = qick_backend.reconstruct_command(
        qick_backend.compile_command(command, park_gain=Q3_PARK_GAIN, scale_gain=Q3_SCALE_GAIN,
                                     clock_ns=Q3_CLOCK_NS))
    for reconstructed in (qua_command, qick_command):
        times, _ = report.transitions(reconstructed)
        assert times[0] == pytest.approx(0.0, abs=4.0) or times.size > 1
        assert np.any(np.abs(times - 80_000.0) <= 10.0)
        assert reconstructed.values[-1] == pytest.approx(0.0, abs=1e-3)


def test_cross_backend_commands_agree_within_the_declared_quantization():
    bank = report.condition_bank(model(), amplitude=1.0, holds_ns=PRODUCTION_HOLDS_NS,
                                 recovery_ns=1_600_000.0, schedule_first_ns=2000.0,
                                 schedule_max_ns=100_000.0, schedule_quantum_ns=1000.0)
    summary = report.cross_backend_report(
        bank, qua_park_v=Q5_PARK_V, qua_scale_v=Q5_SCALE_V, qick_park_gain=Q3_PARK_GAIN,
        qick_scale_gain=Q3_SCALE_GAIN, qick_clock_ns=Q3_CLOCK_NS,
        qua_max_instructions=10_000, qick_max_instructions=4096)
    assert len(summary["conditions"]) == len(PRODUCTION_HOLDS_NS)
    assert summary["all_conditions_within_edge_tolerance"]
    assert summary["worst_case"]["max_edge_time_error_ns"] <= 4.0
    assert summary["worst_case"]["rms"] < 1e-3
    assert summary["worst_case"]["integrated_abs_ns"] < 200.0
    assert "unmatched_transition_counts" not in summary["worst_case"]
    assert len(summary["report_sha256"]) == 64


def test_cross_backend_max_abs_is_only_the_sub_clock_edge_sliver():
    bank = report.condition_bank(model(), amplitude=1.0, holds_ns=(200_000.0,),
                                 recovery_ns=1_600_000.0, schedule_first_ns=2000.0,
                                 schedule_max_ns=100_000.0, schedule_quantum_ns=1000.0)
    summary = report.cross_backend_report(
        bank, qua_park_v=Q5_PARK_V, qua_scale_v=Q5_SCALE_V, qick_park_gain=Q3_PARK_GAIN,
        qick_scale_gain=Q3_SCALE_GAIN, qick_clock_ns=Q3_CLOCK_NS)
    difference = summary["conditions"][0]["normalized_difference"]
    assert difference["max_abs"] > 0.5
    assert difference["rms"] < 1e-3
    assert abs(difference["signed_area_ns"]) < difference["integrated_abs_ns"] + 1e-9


def test_cross_backend_report_flags_a_one_clock_displaced_full_amplitude_edge():
    a = Command([0.0, 100_000.0, 200_000.0], [1.0, 0.0])
    b = Command([0.0, 100_004.0, 200_000.0], [1.0, 0.0])
    edges = report.transition_report(a, b, tolerance_ns=2.0)
    assert not edges["within_tolerance"]
    assert edges["max_edge_time_error_ns"] == pytest.approx(4.0)
    assert edges["matched"]


def test_cross_backend_report_flags_a_differing_transition_count():
    a = Command([0.0, 100_000.0, 200_000.0], [1.0, 0.0])
    b = Command([0.0, 200_000.0], [1.0])
    edges = report.transition_report(a, b, tolerance_ns=4.0)
    assert not edges["matched"]
    assert not edges["within_tolerance"]
    assert edges["max_edge_time_error_ns"] is None


def test_condition_bank_covers_every_production_hold_with_its_own_return():
    bank = report.condition_bank(model(), amplitude=1.0, holds_ns=PRODUCTION_HOLDS_NS,
                                 recovery_ns=1_600_000.0, schedule_first_ns=2000.0,
                                 schedule_max_ns=100_000.0, schedule_quantum_ns=1000.0)
    returns = []
    for entry in bank:
        command = entry["command"]
        index = int(np.searchsorted(command.edges_ns, entry["hold_ns"], side="left"))
        returns.append(float(command.values[index]))
    assert len(set(returns)) == len(returns)
    assert all(value < 0.0 for value in returns)


def test_bank_instruction_budget_is_checked_across_every_condition():
    bank = report.condition_bank(model(), amplitude=1.0, holds_ns=PRODUCTION_HOLDS_NS,
                                 recovery_ns=1_600_000.0, schedule_first_ns=2000.0,
                                 schedule_max_ns=100_000.0, schedule_quantum_ns=1000.0)
    summary = report.cross_backend_report(
        bank, qua_park_v=Q5_PARK_V, qua_scale_v=Q5_SCALE_V, qick_park_gain=Q3_PARK_GAIN,
        qick_scale_gain=Q3_SCALE_GAIN, qick_clock_ns=Q3_CLOCK_NS,
        qua_max_instructions=10_000, qick_max_instructions=4096)
    assert summary["qua_instruction_total"] > 0
    assert summary["qick_instruction_total"] > 0
    assert max(c["qick_instruction_estimate"] for c in summary["conditions"]) <= 4096


def test_repeated_shots_converge_to_a_bounded_steady_state():
    result = report.repeated_shot_state(model(), amplitude=1.0, hold_ns=200_000.0,
                                        recovery_ns=1_600_000.0, repeats=6, sample_ns=4000.0)
    assert len(result["tail_bound_per_shot"]) == 6
    assert result["steady_state_tail_bound"] <= result["max_tail_bound"]
    assert result["steady_state_tail_bound"] < 1e-4


def test_repeated_shots_with_a_short_recovery_do_not_settle():
    result = report.repeated_shot_state(model(), amplitude=1.0, hold_ns=200_000.0,
                                        recovery_ns=40_000.0, repeats=6, sample_ns=4000.0)
    assert result["steady_state_tail_bound"] > 1e-3


def test_command_hash_changes_with_a_single_displaced_edge():
    a = Command([0.0, 100_000.0, 200_000.0], [1.0, 0.0])
    b = Command([0.0, 100_004.0, 200_000.0], [1.0, 0.0])
    assert report.command_hash(a) != report.command_hash(b)


def test_geometric_schedule_fits_a_full_shot_in_tproc_memory():
    schedule = geometric_schedule(1.0, 1_800_000.0, first_ns=2000.0, growth=1.35,
                                  max_ns=100_000.0, quantum_ns=1000.0)
    assert sum(duration for _, duration in schedule) == pytest.approx(1_800_000.0)
    assert len(schedule) * qick_backend.INSTRUCTIONS_PER_SEGMENT < 4096
    assert schedule[0][1] <= 2000.0
    widths = [duration for _, duration in schedule]
    assert all(np.diff(widths[:-1]) >= 0)


def test_geometric_schedule_respects_the_emission_quantum():
    schedule = geometric_schedule(1.0, 100_000.0, first_ns=4000.0, quantum_ns=4000.0)
    for _, duration in schedule[:-1]:
        assert duration % 4000.0 == pytest.approx(0.0)


def test_geometric_schedule_rejects_a_sub_quantum_first_segment():
    with pytest.raises(ValueError, match="one emission quantum"):
        geometric_schedule(1.0, 100_000.0, first_ns=1000.0, quantum_ns=4000.0)


def test_render_on_schedule_matches_uniform_render_state():
    uniform = render(model(), [(1.0, 40_000.0)], sample_ns=1000.0)[1]
    scheduled = render_on_schedule(model(), [(1.0, 10_000.0), (1.0, 30_000.0)])[1]
    assert uniform == pytest.approx(scheduled, abs=1e-12)


def test_render_on_schedule_emits_exactly_one_value_per_entry():
    schedule = geometric_schedule(1.0, 200_000.0, first_ns=2000.0, quantum_ns=1000.0)
    command, _ = render_on_schedule(model(), schedule)
    assert len(command.values) == len(schedule)


def test_shot_schedule_covers_hold_and_recovery_and_lands_on_the_target_edge():
    from fluxpred.validation import shot_schedule

    schedule = shot_schedule(amplitude=1.0, hold_ns=200_000.0, recovery_ns=1_600_000.0,
                             first_ns=2000.0, max_ns=100_000.0, quantum_ns=1000.0)
    hold_total = sum(d for level, d in schedule if level == 1.0)
    assert hold_total == pytest.approx(200_000.0)
    assert sum(d for _, d in schedule) == pytest.approx(1_800_000.0)


def test_scheduled_shot_reports_the_park_quantization_residual():
    bank = report.condition_bank(model(), amplitude=1.0, holds_ns=(200_000.0,),
                                 recovery_ns=1_600_000.0, schedule_first_ns=2000.0,
                                 schedule_max_ns=100_000.0, schedule_quantum_ns=1000.0)
    summary = report.cross_backend_report(
        bank, qua_park_v=Q5_PARK_V, qua_scale_v=Q5_SCALE_V, qick_park_gain=Q3_PARK_GAIN,
        qick_scale_gain=Q3_SCALE_GAIN, qick_clock_ns=Q3_CLOCK_NS)
    residual = summary["conditions"][0]["terminal_park_quantization"]
    assert abs(residual["qua_residual"]) <= residual["tolerance"]
    assert abs(residual["qick_residual"]) <= residual["tolerance"]
