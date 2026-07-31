import os
import sys

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mTLSSaturation as S


def base_cfg(arm="pump"):
    return {
        "shots": 8,
        "saturation_arm": arm,
        "saturation_pump_us": 10.0,
        "saturation_probe_us": 5.0,
        "saturation_recovery_us": 3.0,
        "saturation_pump_gain": 6000,
        "saturation_pump_freq_mhz": 2230.0,
        "saturation_reset_thermalization_us": 0.0,
        "qubit_pi_freq": 2534.0,
        "qubit_pi_gain": 5500,
        "qubit_pulse_style": "arb",
        "res_ch": 0,
        "nqz": 2,
        "mixer_freq": 0.0,
        "ro_chs": [0],
        "qubit_ch": 1,
        "qubit_nqz": 1,
        "read_pulse_freq": 7249.0,
        "read_pulse_gain": 3500,
        "read_length": 15.0,
        "sigma": 0.1,
        "qubit_drag_beta": 0.0,
        "ff_ch": 3,
        "ff_nqz": 1,
        "ff_gain": 8000,
        "ff_park_gain": 0,
        "dt_pulseplay": 5.0,
        "ff_ramp_length": 0.5,
        "dt_pulsedef": 0.002,
        "flux_settle_time_us": 0.5,
        "reset_mode": "feedback",
        "reset_threshold_raw": 100,
        "reset_max_iters": 3,
        "rot_reset": {"c_int": 1, "s_int": 0, "excite_threshold": 100,
                      "max_iters": 3},
        "adc_trig_offset": 0.5,
        "relax_delay": 1500.0,
    }


def make_program(arm="pump"):
    events = []
    program = object.__new__(S.TLSSaturationProbeProgram)
    program.cfg = base_cfg(arm)
    program.saturation_arm = arm
    program.recovery_us = 3.0
    program.pump_tone_us = 11.0
    program.ff_settle_us = 0.5
    program.pump_segs = {"park": 0}
    program.probe_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.set_pulse_registers = lambda **kw: events.append(("register", kw))
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles=0: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    return program, events


def test_initialize_builds_pump_and_probe_excursions(monkeypatch):
    program = object.__new__(S.TLSSaturationProbeProgram)
    program.cfg = base_cfg()
    program.declare_gen = lambda **kw: None
    program.declare_readout = lambda **kw: None
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.set_pulse_registers = lambda **kw: None
    program.synci = lambda cycles: None
    monkeypatch.setattr(S, "add_qubit_gaussian", lambda prog, **kw: None)
    monkeypatch.setattr(S, "set_readout_pulse", lambda prog, *a, **kw: None)
    monkeypatch.setattr(S.ff_pulse, "declare_ff", lambda prog: None)
    monkeypatch.setattr(S.ff_pulse, "load_compensation", lambda cfg: None)
    monkeypatch.setattr(S.ff_pulse, "make_distortion_model", lambda prog: None)
    built = []

    def build(prog, **kw):
        built.append(kw)
        return {"park": 0}

    monkeypatch.setattr(S.ff_pulse, "build_ramp_hold_ramp", build)
    program.initialize()
    assert [item["hold_us"] for item in built] == [10.5, 5.5]
    assert [item["name_prefix"] for item in built] == [
        "saturation_pump", "saturation_probe"]
    assert np.isclose(program.pump_tone_us, 11.0)


def test_pump_and_no_pump_are_timing_matched(monkeypatch):
    gains = {}
    for arm in S.SATURATION_ARMS:
        program, events = make_program(arm)
        monkeypatch.setattr(S.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
        monkeypatch.setattr(S.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
        program._pump_excursion()
        gains[arm] = [event[1]["gain"] for event in events
                      if event[0] == "register"][0]
        assert len([event for event in events if event[0] == "pulse"]) == 1
    assert gains["no_pump"] == 0
    assert gains["pump"] == 6000


def test_body_resets_between_pump_and_probe(monkeypatch):
    program, events = make_program()
    monkeypatch.setattr(S.ff_pulse, "assert_park", lambda *a, **kw: None)
    program._pump_excursion = lambda: events.append(("pump",))
    program._reset_qubit = lambda: events.append(("reset",))
    program._probe_excursion = lambda: events.append(("probe",))
    program.body()
    names = [event[0] for event in events]
    assert names.index("pump") < names.index("reset") < names.index("probe")
    assert ("sync", 3.0) in events
    assert names[-1] == "measure"


def test_collect_shots_separates_reset_and_final_reads():
    program = object.__new__(S.TLSSaturationProbeProgram)
    program.cfg = dict(base_cfg(), reps=2, read_length=1.0)
    program.us2cycles = lambda value, **kw: value
    program.di_buf = [np.arange(8, dtype=float)]
    program.dq_buf = [np.arange(8, dtype=float) + 10]
    reset_i, reset_q, i, q = program.collect_shots()
    assert reset_i.shape == (2, 3)
    assert reset_q.shape == (2, 3)
    assert i.tolist() == [3.0, 7.0]
    assert q.tolist() == [13.0, 17.0]


def test_wrapper_classifies_population_and_reset_monitor(monkeypatch, tmp_path):
    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            n = int(self.cfg["shots"])
            reset = np.ones((n, 3))
            final = np.r_[np.ones(n // 2), -np.ones(n - n // 2)]
            return reset, np.zeros_like(reset), final, np.zeros(n)

    monkeypatch.setattr(S, "TLSSaturationProbeProgram", FakeProgram)
    exp = S.TLSSaturationProbe(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg=base_cfg(), ff_gain=8000, target_freq_mhz=2230.0,
        pump_gain=6000, pump_us=10.0, probe_us=5.0, recovery_us=2.0,
        arm="pump", shots=20,
        calib_params={"scale_factor": 1.0, "threshold": 0.0,
                      "read_theta": 0.0, "ground_threshold": -0.5},
        assignment_reference={"P_g": 0.1, "P_e": 0.9})
    exp.acquire()
    assert np.isclose(exp.metrics["P_excited"], 0.5)
    assert np.isclose(exp.metrics["population_corrected"], 0.5)
    assert np.isclose(exp.metrics["reset_last_P_excited"], 1.0)
    assert exp.raw["reset_i"].shape == (20, 3)
