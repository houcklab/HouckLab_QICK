"""Regenerate the template and preset JSON files in this folder.

    python -m Bob.library.build_library

Templates are written in code so they stay correct as block classes change; the JSON
files are what the GUI opens. Every template points at entries in qubit_parameters.json
by reference, so opening one later picks up the current calibration.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..blocks.registry import make_block
from ..config.settings import SweepAxis
from ..core.params import Ref, Sweep, Value, VectorSource
from ..core.sequence import Sequence

HERE = Path(__file__).resolve().parent
SAMPLES_PER_US = 3440.64


def _hold(name, act, duration, group="readout_3800"):
    b = make_block("FFHold", name=name, act=act)
    b.set_field("group", Value(group))
    b.set_field("duration_us", duration if not isinstance(duration, (int, float)) else Value(float(duration)))
    return b


def _pulse(kind, qubit, phase=None, gain=None, name=None):
    symbol = "π" if kind == "PiPulse" else "π/2"
    p = make_block(kind, name=name or f"{symbol} Q{qubit}")
    p.set_field("qubit", Value(qubit))
    if phase is not None:
        p.set_field("phase", phase)
    if gain is not None:
        p.set_field("gain", gain)
    return p


def _measure(qubits, mode="populations_corrected"):
    m = make_block("Measure")
    m.set_field("qubits", Value(list(qubits)))
    m.set_field("mode", Value(mode))
    return m


def rabi() -> Sequence:
    s = Sequence(name="Rabi", description="Amplitude Rabi on Q3: sweep the π-pulse gain.")
    init = _hold("Init", "prep", 0.2)
    s.insert_segment(init)
    s.add_pulse(_pulse("PiPulse", 3, gain=Sweep("gain"), name="Drive Q3"), init.id)
    s.set_measure(_measure([3], "iq"))
    s.settings.sweeps.append(SweepAxis("gain", 0, 20000, 41, "DAC"))
    return s


def t1() -> Sequence:
    s = Sequence(name="T1", description="π pulse on Q3, wait, measure.")
    init = _hold("Init", "prep", 0.2)
    s.insert_segment(init)
    s.add_pulse(_pulse("PiPulse", 3), init.id)
    s.insert_segment(_hold("Wait", "dynamics", Sweep("t_wait")))
    s.set_measure(_measure([3]))
    s.settings.sweeps.append(SweepAxis("t_wait", 0.0, 50.0, 26, "µs"))
    return s


def ramsey() -> Sequence:
    s = Sequence(name="Ramsey", description="π/2, wait, π/2 on Q3.")
    init = _hold("Init", "prep", 0.2)
    s.insert_segment(init)
    s.add_pulse(_pulse("Pi2Pulse", 3), init.id)
    s.insert_segment(_hold("Wait", "dynamics", Sweep("t_wait")))
    close = _hold("Close", "readout", 0.2)
    s.insert_segment(close)
    s.add_pulse(_pulse("Pi2Pulse", 3), close.id)
    s.set_measure(_measure([3]))
    s.settings.sweeps.append(SweepAxis("t_wait", 0.0, 5.0, 51, "µs"))
    return s


def mott_quench() -> Sequence:
    """Run_Experiments/mott_quench_basic.py: π on Q3,4,5,7,8 and π/2 on Q6 (pi2_init_index 3),
    jump to the 6Q_Pulse_init lattice point and hold, π/2 on every qubit, read out Q3 to Q8."""
    qubits = [3, 4, 5, 6, 7, 8]
    s = Sequence(name="Mott quench",
                 description="Prepare a Mott state with one superposition, quench, π/2 on all, read out.")
    init = _hold("Init", "prep", 0.8)
    s.insert_segment(init)
    for q in qubits:
        s.add_pulse(_pulse("Pi2Pulse" if q == 6 else "PiPulse", q), init.id)
    dyn = make_block("FFDynamics", name="Quench")
    dyn.set_field("gains", VectorSource(Ref("calib:ff_groups/ramp_groups/ramp_6Q/6Q_Pulse_init/FF_Expt")))
    dyn.set_field("duration_us", Sweep("t_dyn"))
    s.insert_segment(dyn)
    close = _hold("Measurement π/2", "readout", 0.8)
    s.insert_segment(close)
    for q in qubits:
        s.add_pulse(_pulse("Pi2Pulse", q, phase=Value(0.0)), close.id)
    s.set_measure(_measure(qubits))
    s.settings.sweeps.append(SweepAxis("t_dyn", 0.0, round(8000 / SAMPLES_PER_US, 4), 401, "µs"))
    s.settings.reps = 500
    return s


def bs_correlations() -> Sequence:
    """Run_Experiments/beamsplitter_clean_timing.py, 1234 correlations: init π pulses,
    ramp into the lattice, timed beamsplitter, MUX readout of Q1 to Q4."""
    s = Sequence(name="BS correlations",
                 description="π pulses, ramp to the 1234 lattice point, beamsplitter with swept swap time.")
    init = _hold("Init", "prep", 0.4)
    s.insert_segment(init)
    for q in (1, 3):
        s.add_pulse(_pulse("PiPulse", q), init.id)
    ramp = make_block("FFRamp", name="Ramp")
    ramp.set_field("ramp_group", Value("ramp_3800"))
    ramp.set_field("ramp_entry", Value("1234"))
    ramp.set_field("duration_us", Value(1.0))
    s.insert_segment(ramp)
    bs = make_block("Beamsplitter")
    bs.set_field("bs_entry", Value("1234_correlations"))
    bs.set_field("extra_samples", Sweep("bs_extra"))
    s.insert_segment(bs)
    s.set_measure(_measure([1, 2, 3, 4]))
    s.settings.sweeps.append(SweepAxis("bs_extra", 0, 100, 101, "samples"))
    return s


TEMPLATES = {"rabi": rabi, "t1": t1, "ramsey": ramsey, "mott_quench": mott_quench,
             "bs_correlations": bs_correlations}


def presets() -> dict:
    out = {}
    out["pi_Q3"] = [_pulse("PiPulse", 3)]
    out["pi2_Q3"] = [_pulse("Pi2Pulse", 3)]
    r = make_block("FFRamp", name="Ramp to 3800 lattice")
    out["ramp_3800_8Q"] = [r]
    b = make_block("Beamsplitter", name="BS 1234 correlations")
    out["bs_1234"] = [b]
    q = make_block("FFDynamics", name="Quench to resonant")
    out["quench_resonant"] = [q]
    return out


def main():
    tdir, pdir = HERE / "templates", HERE / "presets"
    tdir.mkdir(exist_ok=True)
    pdir.mkdir(exist_ok=True)
    for key, fn in TEMPLATES.items():
        fn().save(tdir / f"{key}.json")
    for key, blocks in presets().items():
        (pdir / f"{key}.json").write_text(json.dumps(
            {"bob_preset": 1, "name": blocks[0].name, "blocks": [b.to_dict() for b in blocks]}, indent=2),
            encoding="utf-8")
    print(f"wrote {len(TEMPLATES)} templates and {len(presets())} presets")


if __name__ == "__main__":
    main()
