import os
import sys

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mTLSMemory as M


def base_cfg(sequence="double"):
    return {
        "shots": 8,
        "memory_sequence": sequence,
        "memory_interaction_us": 1.0,
        "memory_storage_us": 2.0,
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
        "reset_mode": "passive",
        "adc_trig_offset": 0.5,
        "herald_delay": 8.0,
        "relax_delay": 1500.0,
    }


def make_body_program(sequence):
    events = []
    program = object.__new__(M.TLSMemoryProgram)
    program.cfg = base_cfg(sequence)
    program.memory_sequence = sequence
    program.memory_storage_us = 2.0
    program.excursion_total_us = 3.01
    program.ff_settle_us = 0.5
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    program._set_qubit_pulse = lambda *a, **kw: events.append(("register", a, kw))
    return program, events


def test_initialize_builds_one_reusable_interaction_waveform(monkeypatch):
    built = {}
    program = object.__new__(M.TLSMemoryProgram)
    program.cfg = base_cfg("double")
    program.declare_gen = lambda **kw: None
    program.declare_readout = lambda **kw: None
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.set_pulse_registers = lambda **kw: None
    program.synci = lambda cycles: None
    monkeypatch.setattr(M, "add_qubit_gaussian", lambda prog, **kw: None)
    monkeypatch.setattr(M, "set_readout_pulse", lambda prog, *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "declare_ff", lambda prog: None)
    monkeypatch.setattr(M.ff_pulse, "load_compensation", lambda cfg: None)
    monkeypatch.setattr(M.ff_pulse, "make_distortion_model", lambda prog: None)

    def build(prog, **kw):
        built.update(kw)
        return {"park": 0}

    monkeypatch.setattr(M.ff_pulse, "build_ramp_hold_ramp", build)
    program.initialize()
    assert built["ff_gain"] == 8000
    assert built["hold_us"] == 1.5
    assert np.isclose(program.excursion_total_us, 3.01)


def test_single_sequence_uses_one_excursion_and_matched_idle(monkeypatch):
    program, events = make_body_program("single")
    monkeypatch.setattr(M.ff_pulse, "assert_park", lambda *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "play_ramp_up_hold",
                        lambda *a, **kw: events.append(("ramp_up",)))
    monkeypatch.setattr(M.ff_pulse, "play_ramp_down",
                        lambda *a, **kw: events.append(("ramp_down",)))
    program.body()
    assert len([event for event in events if event[0] == "ramp_up"]) == 1
    assert len([event for event in events if event[0] == "ramp_down"]) == 1
    assert len([event for event in events if event[0] == "pulse"]) == 1
    assert ("sync", 3.01) in events
    assert len([event for event in events if event[0] == "measure"]) == 1


def test_double_sequence_uses_two_excursions(monkeypatch):
    program, events = make_body_program("double")
    monkeypatch.setattr(M.ff_pulse, "assert_park", lambda *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "play_ramp_up_hold",
                        lambda *a, **kw: events.append(("ramp_up",)))
    monkeypatch.setattr(M.ff_pulse, "play_ramp_down",
                        lambda *a, **kw: events.append(("ramp_down",)))
    program.body()
    assert len([event for event in events if event[0] == "ramp_up"]) == 2
    assert len([event for event in events if event[0] == "ramp_down"]) == 2
    assert len([event for event in events if event[0] == "pulse"]) == 1
    assert ("sync", 2.0) in events


def test_ground_double_has_no_microwave_pulse(monkeypatch):
    program, events = make_body_program("ground_double")
    monkeypatch.setattr(M.ff_pulse, "assert_park", lambda *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "play_ramp_up_hold",
                        lambda *a, **kw: events.append(("ramp_up",)))
    monkeypatch.setattr(M.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    assert len([event for event in events if event[0] == "ramp_up"]) == 2
    assert not [event for event in events if event[0] == "pulse"]


def test_feedback_uses_rotated_reset_block_and_restores_pi(monkeypatch):
    program, events = make_body_program("double")
    program.cfg.update({
        "reset_mode": "feedback",
        "reset_threshold_raw": 11177,
        "reset_pi_gain": 5400,
        "reset_pi_freq": 2533.5,
        "reset_max_iters": 3,
    })
    program._read_freq_reg = 7249.0
    monkeypatch.setattr(M, "set_readout_pulse", lambda *a, **kw: None)
    monkeypatch.setattr(M.active_reset, "active_reset_block",
                        lambda *a, **kw: events.append(("reset", kw["threshold_raw"])))
    monkeypatch.setattr(M.ff_pulse, "assert_park", lambda *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
    monkeypatch.setattr(M.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    registers = [event for event in events if event[0] == "register"]
    assert registers[0][2]["gain"] == 5400
    assert registers[0][2]["freq_mhz"] == 2533.5
    assert ("reset", 11177) in events
    assert registers[1][2] == {}


def test_collect_shots_without_herald_returns_final_readout():
    program = object.__new__(M.TLSMemoryProgram)
    program.cfg = dict(base_cfg(), reps=3, reset_mode="passive", read_length=1.0)
    program.us2cycles = lambda value, **kw: value
    program.di_buf = [np.array([1.0, 2.0, 3.0])]
    program.dq_buf = [np.array([4.0, 5.0, 6.0])]
    hi, hq, i, q = program.collect_shots()
    assert np.all(np.isnan(hi)) and np.all(np.isnan(hq))
    assert i.tolist() == [1.0, 2.0, 3.0]
    assert q.tolist() == [4.0, 5.0, 6.0]


def test_wrapper_classifies_and_corrects_population(monkeypatch, tmp_path):
    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            n = int(self.cfg["shots"])
            values = np.r_[np.ones(n // 2), -np.ones(n - n // 2)]
            empty = np.full(n, np.nan)
            return empty, empty.copy(), values, np.zeros(n)

    monkeypatch.setattr(M, "TLSMemoryProgram", FakeProgram)
    exp = M.TLSMemory(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg=base_cfg(), ff_gain=8000, interaction_us=1.0,
        storage_us=2.0, sequence="double", shots=20,
        calib_params={"scale_factor": 1.0, "threshold": 0.0,
                      "read_theta": 0.0, "ground_threshold": -0.5},
        assignment_reference={"P_g": 0.1, "P_e": 0.9})
    exp.acquire()
    assert np.isclose(exp.metrics["P_excited"], 0.5)
    assert np.isclose(exp.metrics["population_corrected"], 0.5)
    assert exp.raw["i"].size == 20
