"""Prepared state after Preparation, and the plain-language summary saved in the file."""
import json

import pytest

from Bob.blocks.registry import make_block
from Bob.config.resolver import Resolver
from Bob.config.settings import SweepAxis
from Bob.config.summary import prepared_states, state_counts, state_string, summarize
from Bob.core.params import Sweep, Value
from Bob.core.sequence import Sequence
from Bob.library import build_library

TEMPLATES = build_library.HERE / "templates"


def _seq_with(pulses, act="prep"):
    """One FF hold in `act` with pulses [(TYPE, qubit, phase)]."""
    s = Sequence()
    h = make_block("FFHold")
    h.act = act
    h.set_field("duration_us", Value(1.0))
    s.insert_segment(h)
    for t, q, ph in pulses:
        p = make_block(t)
        p.set_field("qubit", Value(q))
        p.set_field("phase", Value(ph))
        s.add_pulse(p, h.id)
    return s


def _states(seq):
    return prepared_states(seq)


@pytest.mark.parametrize("pulses, expected", [
    ([("PiPulse", 3, 0)], "00100000"),
    ([("PiPulse", 3, 0), ("PiPulse", 3, 0)], "00000000"),             # π then π: back to |0⟩
    ([("Pi2Pulse", 3, 0)], "00+00000"),
    ([("Pi2Pulse", 3, 0), ("Pi2Pulse", 3, 0)], "00100000"),           # two π/2 about the same axis = π
    ([("Pi2Pulse", 3, 0), ("Pi2Pulse", 3, 180)], "00000000"),         # opposite axis undoes it
    ([("Pi2Pulse", 3, 0), ("Pi2Pulse", 3, 90)], "00+00000"),          # orthogonal axis stays on the equator
    ([("Drive", 3, 0)], "00?00000"),
])
def test_ideal_rotations(pulses, expected):
    assert state_string(_states(_seq_with(pulses))) == expected


def test_only_preparation_pulses_count():
    s = _seq_with([("PiPulse", 2, 0)], act="dynamics")
    assert _states(s) == {}


def test_swept_gain_is_unknown():
    s = _seq_with([("PiPulse", 4, 0)])
    s.pulses[0].set_field("gain", Sweep("g"))
    assert _states(s)[4].kind == "?"


def test_swept_phase_uses_preview_point(station, calib):
    s = _seq_with([("Pi2Pulse", 3, 0), ("Pi2Pulse", 3, 0)])
    s.settings.sweeps.append(SweepAxis("phi", 0, 180, 3, "deg"))
    s.pulses[1].set_field("phase", Sweep("phi"))
    r = Resolver(station, calib)

    def at(k):
        return prepared_states(s, r.resolve(s, s.settings.point(k)))[3]
    assert at(0).kind == "1" and at(2).kind == "0" and at(1).kind == "+" and at(0).swept


def test_counts_text():
    st = _states(_seq_with([("PiPulse", 1, 0), ("PiPulse", 2, 0), ("Pi2Pulse", 3, 0), ("Drive", 4, 0)]))
    assert state_counts(st) == "2 excitations, 1 superposition, 1 unknown"


def test_mott_quench_template(station, calib):
    s = Sequence.load(TEMPLATES / "mott_quench.json")
    res = Resolver(station, calib).resolve(s)
    assert state_string(prepared_states(s, res)) == "00111+11"
    text = summarize(s, res)
    for part in ("Mott quench: 500 reps", "t_dyn", "(401 pts)", "π on Q3–Q5, Q7–Q8", "π/2 at 0° on Q6",
                 "Prepared state 00111+11", "5 excitations, 1 superposition", "π/2 at 0° on Q3–Q8",
                 "Measure: Q3–Q8 at readout_3800, reporting corrected populations"):
        assert part in text, part


def test_every_template_summarizes(station, calib):
    for path in TEMPLATES.glob("*.json"):
        s = Sequence.load(path)
        text = summarize(s, Resolver(station, calib).resolve(s))
        assert text.startswith(s.name) and "Measure" in text


def test_summary_round_trips_in_the_file(tmp_path):
    s = _seq_with([("PiPulse", 3, 0)])
    s.summary = "hello"
    s.save(tmp_path / "s.json")
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["summary"] == "hello"
    assert Sequence.load(tmp_path / "s.json").summary == "hello"
