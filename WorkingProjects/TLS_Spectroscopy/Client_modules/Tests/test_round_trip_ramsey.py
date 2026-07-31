import os
import sys

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mRoundTripRamsey as R


def base_cfg(arm="i"):
    return {
        "shots": 8,
        "ramsey_arm": arm,
        "qubit_pi_freq": 2534.0,
        "qubit_pi_gain": 5500,
        "qubit_pi2_gain": 2750,
        "qubit_pulse_style": "arb",
        "res_ch": 0,
        "nqz": 2,
        "mixer_freq": 0.0,
        "ro_chs": [0],
        "qubit_ch": 1,
        "qubit_nqz": 1,
        "read_pulse_freq": 7249.0,
        "read_length": 15.0,
        "sigma": 0.25,
        "ff_gain": 8000,
        "ff_park_gain": 0,
        "ramsey_flux_hold_us": 1.0,
        "dt_pulseplay": 5.0,
        "ff_ramp_length": 0.5,
        "dt_pulsedef": 0.002,
        "flux_settle_time_us": 0.5,
        "reset_mode": "passive",
        "adc_trig_offset": 0.5,
        "herald_delay": 8.0,
        "relax_delay": 25.0,
    }


def test_initialize_uses_only_park_microwave_frequency(monkeypatch):
    built = {}
    registers = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = base_cfg("i")
    program.declare_gen = lambda **kw: None
    program.declare_readout = lambda **kw: None
    program.us2cycles = lambda value, **kw: value
    program.freq2reg = lambda value, **kw: value
    program.deg2reg = lambda value, **kw: value
    program.set_pulse_registers = lambda **kw: registers.append(kw)
    program.synci = lambda cycles: None
    monkeypatch.setattr(R, "add_qubit_gaussian", lambda prog, **kw: None)
    monkeypatch.setattr(R, "set_readout_pulse", lambda prog, *a, **kw: None)
    monkeypatch.setattr(R.ff_pulse, "declare_ff", lambda prog: None)
    monkeypatch.setattr(R.ff_pulse, "load_compensation", lambda cfg: None)
    monkeypatch.setattr(R.ff_pulse, "make_distortion_model", lambda prog: None)

    def build(prog, **kw):
        built.update(kw)
        return {"park": 0}

    monkeypatch.setattr(R.ff_pulse, "build_ramp_hold_ramp", build)
    program.initialize()
    qubit_registers = [row for row in registers if row.get("ch") == 1]
    assert len(qubit_registers) == 1
    assert qubit_registers[0]["freq"] == 2534.0
    assert qubit_registers[0]["gain"] == 2750
    assert built["ff_gain"] == 8000
    assert built["hold_us"] == 1.5


def test_q_arm_prepares_x90_and_analyzes_at_phase_90(monkeypatch):
    events = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = base_cfg("q")
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    program._set_qubit_pulse = lambda gain, phase, *a, **kw: events.append(
        ("register", gain, phase))
    monkeypatch.setattr(R.ff_pulse, "assert_park",
                        lambda prog, segs: events.append(("park", segs)))
    monkeypatch.setattr(R.ff_pulse, "play_ramp_up_hold",
                        lambda prog, segs, dt_play_us: events.append(("ramp_up", segs)))
    monkeypatch.setattr(R.ff_pulse, "play_ramp_down",
                        lambda prog, segs: events.append(("ramp_down", segs)))
    program.body()
    assert len([row for row in events if row[0] == "pulse"]) == 2
    assert len([row for row in events if row[0] == "measure"]) == 1
    assert ("register", 2750, 90.0) in events
    names = [row[0] for row in events]
    assert names.index("ramp_down") < names.index("register")
    assert names[-1] == "measure"


def test_ground_arm_has_no_microwave_pulses(monkeypatch):
    events = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = base_cfg("g")
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles: None
    program.measure = lambda **kw: events.append(("measure", kw))
    monkeypatch.setattr(R.ff_pulse, "assert_park", lambda prog, segs: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    assert not [row for row in events if row[0] == "pulse"]
    assert len([row for row in events if row[0] == "measure"]) == 1


def test_park_idle_mode_skips_flux_waveforms(monkeypatch):
    events = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = dict(base_cfg("i"), ramsey_park_idle_only=True,
                       ramsey_flux_hold_us=0.75)
    program.ff_segs = None
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles: events.append(("sync", cycles))
    program.measure = lambda **kw: events.append(("measure", kw))
    program._set_qubit_pulse = lambda gain, phase, *a, **kw: events.append(
        ("register", gain, phase))
    monkeypatch.setattr(
        R.ff_pulse, "play_ramp_up_hold",
        lambda *a, **kw: events.append(("unexpected_ramp_up",)))
    monkeypatch.setattr(
        R.ff_pulse, "play_ramp_down",
        lambda *a, **kw: events.append(("unexpected_ramp_down",)))
    program.body()
    assert ("sync", 0.75) in events
    assert not [row for row in events if row[0].startswith("unexpected")]
    assert len([row for row in events if row[0] == "pulse"]) == 2


def test_herald_mode_retains_the_initial_measurement(monkeypatch):
    events = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = dict(base_cfg("g"), reset_mode="active")
    program.ff_segs = {"park": 0}
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: events.append(("pulse", ch))
    program.sync_all = lambda cycles: None
    program.measure = lambda **kw: events.append(("measure", kw))
    monkeypatch.setattr(R.ff_pulse, "assert_park", lambda prog, segs: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    assert len([row for row in events if row[0] == "measure"]) == 2


def test_collect_shots_without_herald_returns_only_final_readout():
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = dict(base_cfg("g"), reps=3, reset_mode="passive",
                       read_length=1.0)
    program.us2cycles = lambda value, **kw: value
    program.di_buf = [np.array([1.0, 2.0, 3.0])]
    program.dq_buf = [np.array([4.0, 5.0, 6.0])]
    hi, hq, i, q = program.collect_shots()
    assert np.all(np.isnan(hi)) and np.all(np.isnan(hq))
    assert i.tolist() == [1.0, 2.0, 3.0]
    assert q.tolist() == [4.0, 5.0, 6.0]


def test_collect_shots_with_herald_preserves_both_readouts():
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = dict(base_cfg("g"), reps=2, reset_mode="active",
                       read_length=1.0)
    program.us2cycles = lambda value, **kw: value
    program.di_buf = [np.array([1.0, 2.0, 3.0, 4.0])]
    program.dq_buf = [np.array([5.0, 6.0, 7.0, 8.0])]
    hi, hq, i, q = program.collect_shots()
    assert hi.tolist() == [1.0, 3.0]
    assert hq.tolist() == [5.0, 7.0]
    assert i.tolist() == [2.0, 4.0]
    assert q.tolist() == [6.0, 8.0]


def test_feedback_reset_uses_reset_frequency_then_restores_arm(monkeypatch):
    events = []
    program = object.__new__(R.RoundTripRamseyProgram)
    program.cfg = dict(base_cfg("i"), reset_mode="feedback",
                       reset_threshold_raw=11177, reset_pi_freq=2533.5,
                       reset_pi_gain=5400, reset_max_iters=3)
    program.ff_segs = {"park": 0}
    program._read_freq_reg = 7249.0
    program.us2cycles = lambda value, **kw: value
    program.pulse = lambda ch: None
    program.sync_all = lambda cycles: None
    program.measure = lambda **kw: None
    program._set_qubit_pulse = lambda gain, phase, waveform="qubit", freq_mhz=None: \
        events.append((gain, phase, waveform, freq_mhz))
    monkeypatch.setattr(R, "set_readout_pulse", lambda *a, **kw: None)
    monkeypatch.setattr(R.active_reset, "active_reset_block",
                        lambda *a, **kw: events.append(("reset", kw["threshold_raw"])))
    monkeypatch.setattr(R.ff_pulse, "assert_park", lambda *a, **kw: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_up_hold", lambda *a, **kw: None)
    monkeypatch.setattr(R.ff_pulse, "play_ramp_down", lambda *a, **kw: None)
    program.body()
    assert events[0] == (5400, 0.0, "qubit_reset", 2533.5)
    assert events[1] == ("reset", 11177)
    assert events[2] == (2750, 0.0, "qubit", None)
    assert events[-1] == (2750, 0.0, "qubit", None)


def test_wrapper_balances_arms_and_computes_complex_response(monkeypatch, tmp_path):
    seen = []
    counts = {"g": 1, "e": 8, "i": 6, "q": 5}

    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = dict(cfg)
            seen.append((cfg["ramsey_arm"], cfg["shots"], cfg["reset_mode"]))

        def acquire(self, soc, load_pulses=True, progress=False):
            n = int(self.cfg["shots"])
            excited = counts[self.cfg["ramsey_arm"]]
            final = np.r_[np.ones(excited), -np.ones(n - excited)]
            return np.full(n, -1.0), np.zeros(n), final, np.zeros(n)

    monkeypatch.setattr(R, "RoundTripRamseyProgram", FakeProgram)
    exp = R.RoundTripRamsey(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg=dict(base_cfg(), reset_mode="feedback"), ff_gain=8000,
        flux_hold_us=1.0, shots=20, rounds=2,
        calib_params={"scale_factor": 1.0, "threshold": 0.0,
                      "read_theta": 0.0, "ground_threshold": -0.5},
        assignment_reference={"P_g": 0.1, "P_e": 0.8})
    exp.acquire()
    assert [row[0] for row in seen] == ["g", "e", "i", "q", "q", "i", "e", "g"]
    assert all(row[1] == 10 for row in seen)
    assert all(row[2] == "feedback" for row in seen)
    assert np.isclose(exp.metrics["P_g"], 0.1)
    assert np.isclose(exp.metrics["P_e"], 0.8)
    assert np.isclose(exp.metrics["P_i"], 0.6)
    assert np.isclose(exp.metrics["P_q"], 0.5)
    assert np.isclose(exp.metrics["ramsey_i"], 3.0 / 7.0)
    assert np.isclose(exp.metrics["ramsey_q"], 1.0 / 7.0)
    assert all(exp.raw[arm]["i"].size == 20 for arm in R.RAMSEY_ARMS)


def test_local_reference_collapse_does_not_renormalize_ramsey_metrics(monkeypatch,
                                                                      tmp_path):
    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            n = int(self.cfg["shots"])
            return np.zeros(n), np.zeros(n), np.ones(n), np.zeros(n)

    monkeypatch.setattr(R, "RoundTripRamseyProgram", FakeProgram)
    exp = R.RoundTripRamsey(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg=base_cfg(), ff_gain=8000, shots=8, rounds=2,
        calib_params={"scale_factor": 1.0, "threshold": 0.0,
                      "read_theta": 0.0, "ground_threshold": -0.5},
        assignment_reference={"P_g": 0.1, "P_e": 0.8})
    exp.acquire()
    assert exp.metrics["local_reference_valid"] == 0.0
    assert exp.metrics["valid"] == 1.0
    assert np.isfinite(exp.metrics["coherence_magnitude"])


def test_invalid_assignment_reference_masks_ramsey_metrics(monkeypatch, tmp_path):
    class FakeProgram:
        def __init__(self, soccfg, cfg):
            self.cfg = cfg

        def acquire(self, soc, load_pulses=True, progress=False):
            n = int(self.cfg["shots"])
            return np.zeros(n), np.zeros(n), np.ones(n), np.zeros(n)

    monkeypatch.setattr(R, "RoundTripRamseyProgram", FakeProgram)
    exp = R.RoundTripRamsey(
        soc=None, soccfg=None, path="q4", outerFolder=str(tmp_path),
        cfg=base_cfg(), ff_gain=8000, shots=8, rounds=2,
        calib_params={"scale_factor": 1.0, "threshold": 0.0,
                      "read_theta": 0.0, "ground_threshold": -0.5},
        assignment_reference={"P_g": 0.48, "P_e": 0.50})
    exp.acquire()
    assert exp.metrics["valid"] == 0.0
    assert np.isnan(exp.metrics["coherence_magnitude"])
