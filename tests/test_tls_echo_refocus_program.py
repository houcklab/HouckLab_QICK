import math

import pytest


def module():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSEchoRefocusProgram
    return TLSEchoRefocusProgram


class Clock:
    cfg = {"qubit_ch": 1, "ff_ch": 3}

    def us2cycles(self, value, gen_ch=None):
        return round(value * 430.08)

    def cycles2us(self, value, gen_ch=None):
        return value / 430.08


@pytest.mark.parametrize("requested,elapsed", [(.35, 152), (.455, 196),
                                               (.65, 280), (.95, 408), (1.35, 580)])
@pytest.mark.parametrize("sequence", ["hahn_x", "hahn_y", "cpmg2_y"])
def test_elapsed_centers_and_whole_window_match_for_every_sequence(requested, elapsed, sequence):
    timing = module().timing_report(Clock(), requested, sequence, phase_deg=270)
    assert timing["elapsed_cycles"] == elapsed
    assert timing["elapsed_us"] == pytest.approx(elapsed / 430.08)
    assert timing["window_cycles"] == elapsed + 23
    assert timing["window_us"] <= 1.4107
    assert timing["pulse_starts_cycles"][0] == 0
    assert timing["pulse_starts_cycles"][-1] == elapsed
    assert timing["pulse_centers_cycles"][0] == 9.5
    assert timing["pulse_centers_cycles"][-1] == elapsed + 9.5
    assert timing["gaps_cycles"] == timing["gaps_cycles"][::-1]
    assert min(timing["gaps_cycles"]) >= 4
    assert timing["final_guard_cycles"] == 4


@pytest.mark.parametrize("sequence,starts,lengths,phases,gaps", [
    ("hahn_x", [0, 66, 152], [19, 39, 19], [0, 0, 180], [47, 47]),
    ("hahn_y", [0, 66, 152], [19, 39, 19], [0, 90, 180], [47, 47]),
    ("cpmg2_y", [0, 28, 104, 152], [19, 39, 39, 19], [0, 90, 90, 180], [9, 37, 9]),
])
def test_finite_pulse_positions_and_rotation_axes(sequence, starts, lengths, phases, gaps):
    timing = module().timing_report(Clock(), .35, sequence, phase_deg=180)
    assert timing["pulse_starts_cycles"] == starts
    assert timing["pulse_lengths_cycles"] == lengths
    assert timing["pulse_phases_deg"] == phases
    assert timing["gaps_cycles"] == gaps


@pytest.mark.parametrize("elapsed", [0, -.1, math.nan, math.inf, .08, .2, 1.5])
def test_rejects_infeasible_or_unbounded_elapsed_time(elapsed):
    with pytest.raises(ValueError):
        module().timing_report(Clock(), elapsed, "cpmg2_y")


def test_rejects_unknown_sequence_phase_or_nonmatching_clocks():
    refocus = module()
    with pytest.raises(ValueError):
        refocus.timing_report(Clock(), .35, "ramsey")
    with pytest.raises(ValueError):
        refocus.timing_report(Clock(), .35, "hahn_x", phase_deg=45)

    class OtherClock(Clock):
        def cycles2us(self, value, gen_ch=None):
            return value / (384. if gen_ch == 3 else 430.08)

    with pytest.raises(ValueError, match="clock"):
        refocus.timing_report(OtherClock(), .35, "hahn_x")


def test_clock_grid_boundaries_and_all_feasible_cpmg_centers():
    refocus = module()
    program = Clock()
    for elapsed in range(132, 581, 4):
        timing = refocus.timing_report(program, elapsed / 430.08, "cpmg2_y")
        centers = timing["pulse_centers_cycles"]
        assert centers[1] - centers[0] == elapsed / 4
        assert centers[2] - centers[0] == 3 * elapsed / 4
        assert centers[3] - centers[0] == elapsed
        assert min(timing["gaps_cycles"]) >= 4
    assert refocus.timing_report(program, 132 / 430.08, "cpmg2_y")["gaps_cycles"] == [4, 27, 4]
    for elapsed in (128, 584):
        with pytest.raises(ValueError):
            refocus.timing_report(program, elapsed / 430.08, "cpmg2_y")
    # A quarter-period conversion must avoid double-rounding the full interval.
    assert refocus.timing_report(program, 133.6 / 430.08, "cpmg2_y")["elapsed_cycles"] == 132
    assert program.cfg == {"qubit_ch": 1, "ff_ch": 3}


class Recorder(Clock):
    """Only replace the unavailable QICK instruction sink, not flux helpers."""

    def __init__(self, sequence="hahn_x", elapsed=.35, phase=0, edge=32.):
        self.cfg = {"qubit_ch": 1, "ff_ch": 3, "ff_park_gain": -25146,
                    "ff_gain": -20130, "opx_resident_pre_us": 30.,
                    "opx_resident_post_us": .1, "opx_resident_freq_mhz": 4290.5,
                    "refocus_sequence": sequence, "refocus_elapsed_us": elapsed,
                    "echo_phase_deg": phase}
        self._t1_ff_compensation = {
            "segment_edges_ns": [0., 30000., edge * 1000., 40000., 80000.],
            "multipliers": [1.03, 1.02, 1.01, 1., 1.]}
        self._t1_ff_settle_us = .5
        self._t1_ff_predistortion_recovery_us = 40.
        self.registers = {}
        self.time = 0
        self.ends = {1: 0, 3: 0}
        self.pulses = []
        self.waits = []

    def freq2reg(self, value, gen_ch):
        return value

    def deg2reg(self, value, gen_ch):
        return value

    def set_pulse_registers(self, **kwargs):
        self.registers[kwargs["ch"]] = kwargs

    def pulse(self, ch):
        register = dict(self.registers[ch])
        start = self.time + self.ends[ch]
        self.pulses.append({**register, "start": start})
        self.ends[ch] += register["length"]

    def sync_all(self, value):
        self.waits.append(value)
        self.time += max(self.ends.values()) + value
        self.ends = {1: 0, 3: 0}


@pytest.fixture
def qick_sink(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import PulseFunctions
    monkeypatch.setattr(PulseFunctions, "ff_maxv", lambda *_args, **_kwargs: 32766)


@pytest.mark.parametrize("elapsed", [.35, .455, .65, .95, 1.35])
@pytest.mark.parametrize("phase", [0, 90, 180, 270])
def test_emitted_pulses_waits_and_flux_envelope_match_saved_timing(elapsed, phase, qick_sink):
    refocus = module()
    envelopes = []
    for sequence in refocus.SEQUENCES:
        program = refocus.make_program(Recorder)(sequence, elapsed, phase)
        program._resident_excursion()
        timing = program.cfg["refocus_timing"]
        pulses = [pulse for pulse in program.pulses if pulse["ch"] == 1]
        first = pulses[0]["start"]
        assert [pulse["start"] - first for pulse in pulses] == timing["pulse_starts_cycles"]
        assert [pulse["length"] for pulse in pulses] == timing["pulse_lengths_cycles"]
        assert [pulse["phase"] for pulse in pulses] == timing["pulse_phases_deg"]
        assert program.waits[1:-1] == timing["gaps_cycles"] + [4]
        assert all(value >= 0 for value in program.waits)
        assert all(pulse["gain"] == 30000 and pulse["freq"] == 4290.5 for pulse in pulses)
        flux = [pulse for pulse in program.pulses if pulse["ch"] == 3]
        envelopes.append((flux, program.time))
        assert timing["science_end_us"] <= 31.9107
        assert timing["held_coefficient"] == 1.02
    assert envelopes[0] == envelopes[1] == envelopes[2]


def test_strict_flat_science_window_rejects_even_tiny_correction_edge(qick_sink):
    program = module().make_program(Recorder)("cpmg2_y", 1.35, edge=31.8)
    program._t1_ff_compensation["multipliers"][2] = 1.02000001
    with pytest.raises(ValueError, match="constant"):
        program._resident_excursion()
    assert program.pulses == []


def test_missing_correction_or_target_excursion_is_rejected(qick_sink):
    for missing in ("correction", "target"):
        program = module().make_program(Recorder)()
        if missing == "correction":
            program._t1_ff_compensation = None
        else:
            program.cfg["ff_gain"] = program.cfg["ff_park_gain"]
        with pytest.raises(ValueError):
            program._resident_excursion()
        assert program.pulses == []
