import os
import sys

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mSingleShot1Q as SS


def test_flux_ramp_initializes_park_pi_and_t1_matched_hold(monkeypatch):
    built = {}
    registers = []
    program = object.__new__(SS.SingleShotFluxRampProgram)
    program.cfg = {
        "shots": 8, "qubit_freq": 2000.0, "qubit_pi_freq": 2534.0,
        "qubit_pi_gain": 5500, "prep_excited": True,
        "qubit_pulse_style": "arb", "res_ch": 0, "nqz": 2,
        "mixer_freq": 0.0, "ro_chs": [0], "qubit_ch": 1,
        "qubit_nqz": 1, "read_pulse_freq": 7249.0, "read_length": 15.0,
        "sigma": 0.25, "ff_gain": 8000, "ff_park_gain": 0,
        "ss_flux_hold_us": 0.75, "dt_pulseplay": 5.0,
        "ff_ramp_length": 0.5, "dt_pulsedef": 0.002,
        "flux_settle_time_us": 0.5, "reset_mode": "passive",
    }
    program.declare_gen = lambda **kw: None
    program.declare_readout = lambda **kw: None
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.set_pulse_registers = lambda **kw: registers.append(kw)
    program.synci = lambda cycles: None
    monkeypatch.setattr(SS, "add_qubit_gaussian", lambda prog, **kw: None)
    monkeypatch.setattr(SS, "set_readout_pulse", lambda prog, *a, **kw: None)
    monkeypatch.setattr(SS.ff_pulse, "declare_ff", lambda prog: None)
    monkeypatch.setattr(SS.ff_pulse, "load_compensation", lambda cfg: None)
    monkeypatch.setattr(SS.ff_pulse, "make_distortion_model", lambda prog: None)

    def build(prog, **kw):
        built.update(kw)
        return {"park": 0}

    monkeypatch.setattr(SS.ff_pulse, "build_ramp_hold_ramp", build)
    program.initialize()
    assert registers[0]["freq"] == 2534.0
    assert registers[0]["gain"] == 5500
    assert built["ff_gain"] == 8000
    assert built["hold_us"] == 1.25


def test_flux_ramp_body_prepares_at_park_then_applies_excursion(monkeypatch):
    events = []
    program = object.__new__(SS.SingleShotFluxRampProgram)
    program.cfg = {
        "reset_mode": "passive", "qubit_ch": 1, "res_ch": 0,
        "ro_chs": [0], "adc_trig_offset": 0.5, "relax_delay": 25.0,
        "repeats": 2, "dt_pulseplay": 5.0, "flux_settle_time_us": 0.5,
        "prep_excited": True, "herald_delay": 8.0,
    }
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pi", ch))
    program.sync_all = lambda cycles: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    monkeypatch.setattr(SS.ff_pulse, "assert_park",
                        lambda prog, segs: events.append(("park", segs)))
    monkeypatch.setattr(SS.ff_pulse, "play_ramp_up_hold",
                        lambda prog, segs, dt_play_us: events.append(("ramp_up", segs)))
    monkeypatch.setattr(SS.ff_pulse, "play_ramp_down",
                        lambda prog, segs: events.append(("ramp_down", segs)))
    program.body()
    names = [row[0] for row in events]
    assert names == ["park", "measure", "pi", "sync", "pi", "sync",
                     "ramp_up", "sync", "ramp_down", "sync", "measure"]
    assert events[-1][1]["syncdelay"] == 25.0


def test_flux_ramp_ground_arm_skips_pi(monkeypatch):
    events = []
    program = object.__new__(SS.SingleShotFluxRampProgram)
    program.cfg = {
        "reset_mode": "passive", "qubit_ch": 1, "res_ch": 0,
        "ro_chs": [0], "adc_trig_offset": 0.5, "relax_delay": 25.0,
        "repeats": 1, "dt_pulseplay": 5.0, "flux_settle_time_us": 0.5,
        "prep_excited": False, "herald_delay": 8.0,
    }
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pi", ch))
    program.sync_all = lambda cycles: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    monkeypatch.setattr(SS.ff_pulse, "assert_park", lambda prog, segs: None)
    monkeypatch.setattr(SS.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
    monkeypatch.setattr(SS.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    assert not [event for event in events if event[0] == "pi"]
    assert len([event for event in events if event[0] == "measure"]) == 2


def test_flux_ramp_wrapper_acquires_matched_ground_and_excited_arms(monkeypatch,
                                                                    tmp_path):
    seen = []

    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg
            seen.append(dict(cfg))

        def acquire(self, soc, load_pulses=True, progress=False):
            value = 1.0 if self.cfg["prep_excited"] else -1.0
            n = int(self.cfg["shots"])
            return (np.zeros(n), np.zeros(n), np.full(n, value),
                    np.full(n, 2.0 * value))

    monkeypatch.setattr(SS, "SingleShotFluxRampProgram", FakeProgram)
    exp = SS.SingleShotFluxRamp(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg={"shots": 8, "qubit_freq": 2534.0, "qubit_pi_freq": 2534.0,
             "qubit_pi_gain": 5500},
        ff_gain=8000, flux_hold_us=0.75,
        save=False, plot=False)
    i, q = exp._acquire_shots()
    assert [row["prep_excited"] for row in seen] == [False, True]
    assert all(row["ff_gain"] == 8000 for row in seen)
    assert all(row["qubit_pi_freq"] == 2534.0 for row in seen)
    assert all(row["ss_flux_hold_us"] == 0.75 for row in seen)
    assert np.all(i[0] == -1.0) and np.all(i[1] == 1.0)
    assert np.all(q[0] == -2.0) and np.all(q[1] == 2.0)


def test_flux_ramp_requires_an_explicit_flux_target(tmp_path):
    try:
        SS.SingleShotFluxRamp(
            soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
            cfg={"qubit_freq": 2534.0, "qubit_pi_freq": 2534.0,
                 "qubit_pi_gain": 5500})
    except ValueError as exc:
        assert "ff_gain" in str(exc)
    else:
        raise AssertionError("missing flux target was accepted")
