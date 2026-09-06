import sys
import types

import numpy as np
import pytest


qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick


from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
    mCoherence as C,
    mRabiChevronIQ as R,
    mRabiChevronSS as RSS,
    mSingleShot1Q as SS,
    mTLSMemory as TM,
    mT1VsFlux as T1F,
    mTransmissionVsFlux as TVF,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import integration
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import PayloadRecord


class FakeProgram:
    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.events = []

    def us2cycles(self, value, **kwargs):
        return int(round(float(value) * 100))

    def sync_all(self, cycles):
        self.events.append(("sync", int(cycles)))

    def pulse(self, **kwargs):
        self.events.append(("pulse", kwargs.get("ch")))

    def measure(self, **kwargs):
        self.events.append(("measure", kwargs.get("pulse_ch")))


def test_build_park_hold_uses_config_in_dynamic_programs(monkeypatch):
    program = FakeProgram({"ff_ch": 3, "ff_park_gain": -7000})
    monkeypatch.setattr(
        ff_pulse,
        "build_ramp_hold_ramp",
        lambda prog, **kwargs: kwargs,
    )

    segments = ff_pulse.build_park_hold(program, hold_us=0.5)

    assert segments["ff_gain"] == -7000
    assert segments["park_gain"] == 0
    assert segments["hold_us"] == 0.5


def test_persistent_hard_park_is_asserted_once_outside_the_shot_body(monkeypatch):
    program = FakeProgram({
        "ff_ch": 3,
        "ff_park_gain": 29000,
        "opx_persistent_park": True,
        "opx_hard_flux_steps": True,
        "opx_park_preroll_us": 400.0,
    })
    monkeypatch.setattr(
        ff_pulse,
        "play_hard_step",
        lambda prog, gain: prog.events.append(("hard_step", int(gain))),
    )

    ff_pulse.begin_park_lifecycle(program, "park")
    ff_pulse.enter_park_for_shot(program, "park")
    ff_pulse.leave_park_for_shot(program, "park")

    assert program.events == [("hard_step", 29000), ("sync", 40000)]


def test_nonpersistent_park_still_brackets_each_shot(monkeypatch):
    program = FakeProgram({"ff_ch": 3, "ff_park_gain": 29000})
    monkeypatch.setattr(
        ff_pulse,
        "play_park_up",
        lambda prog, segs: prog.events.append(("park_up", segs)),
    )
    monkeypatch.setattr(
        ff_pulse,
        "play_park_down",
        lambda prog, segs: prog.events.append(("park_down", segs)),
    )

    ff_pulse.begin_park_lifecycle(program, "park")
    ff_pulse.enter_park_for_shot(program, "park")
    ff_pulse.leave_park_for_shot(program, "park")

    assert program.events == [("park_up", "park"), ("park_down", "park")]


def test_rabi_excursion_enters_park_before_payload_and_releases_after_readout(monkeypatch):
    cfg = {
        "reset_mode": "passive",
        "n_pulses": 1,
        "qubit_ch": 1,
        "res_ch": 0,
        "ro_chs": [0],
        "adc_trig_offset": 0.5,
        "readout_after_park": True,
        "relax_delay": 400.0,
        "flux_settle_time_us": 0.5,
    }
    program = FakeProgram(cfg)
    program.ff_park_segs = "park"
    program.ff_segs = "excursion"
    program.do_flux_hold = True
    monkeypatch.setattr(
        R.ff_pulse,
        "play_park_up",
        lambda prog, segs: prog.events.append(("park_up", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_park_down",
        lambda prog, segs: prog.events.append(("park_down", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_ramp_up_hold",
        lambda prog, segs, **kwargs: prog.events.append(("excursion_up", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_ramp_down",
        lambda prog, segs: prog.events.append(("excursion_down", segs)),
    )

    R.rabi_flux_body(program)

    names = [event[0] for event in program.events]
    assert names[0] == "park_up"
    assert names.index("park_up") < names.index("excursion_up")
    assert names.index("excursion_down") < names.index("measure")
    assert names.index("measure") < names.index("park_down")
    assert names[-1] == "sync"


def test_external_flux_transmission_bounds_static_rfsoc_park(monkeypatch):
    program = FakeProgram({
        "res_ch": 0,
        "ro_chs": [0],
        "adc_trig_offset": 0.5,
        "relax_delay": 400.0,
    })
    program.ff_park_segs = "park"
    monkeypatch.setattr(
        TVF.ff_pulse,
        "play_park_up",
        lambda prog, segs: prog.events.append(("park_up", segs)),
    )
    monkeypatch.setattr(
        TVF.ff_pulse,
        "play_park_down",
        lambda prog, segs: prog.events.append(("park_down", segs)),
    )

    TVF.TransmissionProgram.body(program)

    names = [event[0] for event in program.events]
    assert names == ["park_up", "measure", "park_down", "sync"]


def test_single_shot_dispatches_unbounded_reset_through_dmem(monkeypatch):
    experiment = object.__new__(SS.SingleShot1Q)
    experiment.cfg = {
        "reset_mode": "opx_unbounded",
        "shots": 3,
        "qubit_gain": 11000,
        "qubit_pi_freq": 4367.25,
        "qubit_freq": 4367.25,
    }
    experiment.soc = object()
    experiment.soccfg = object()
    experiment.repeats = 1
    calls = []

    def acquire(soc, soccfg, cfg, **kwargs):
        calls.append(kwargs)
        value = float(kwargs["gain"])
        return np.full(3, value), np.full(3, -value), {}

    monkeypatch.setattr(SS, "acquire_pulse_iq", acquire)

    shots_i, shots_q = experiment._acquire_shots()

    assert [call["gain"] for call in calls] == [0, 11000]
    assert shots_i.tolist() == [[0.0, 0.0, 0.0], [11000.0, 11000.0, 11000.0]]
    assert shots_q.tolist() == [[0.0, 0.0, 0.0], [-11000.0, -11000.0, -11000.0]]


def test_single_shot_unbounded_path_honors_physical_state_order(monkeypatch):
    experiment = object.__new__(SS.SingleShot1Q)
    experiment.cfg = {
        "reset_mode": "opx_unbounded",
        "single_shot_state_order": "eg",
        "shots": 2,
        "qubit_gain": 11000,
        "qubit_pi_freq": 4367.25,
        "qubit_freq": 4367.25,
    }
    experiment.soc = object()
    experiment.soccfg = object()
    experiment.repeats = 1
    calls = []

    def acquire(soc, soccfg, cfg, **kwargs):
        calls.append(kwargs["gain"])
        value = float(kwargs["gain"])
        return np.full(2, value), np.full(2, -value), {}

    monkeypatch.setattr(SS, "acquire_pulse_iq", acquire)

    shots_i, shots_q = experiment._acquire_shots()

    assert calls == [11000, 0]
    assert shots_i.tolist() == [[0.0, 0.0], [11000.0, 11000.0]]
    assert shots_q.tolist() == [[0.0, 0.0], [-11000.0, -11000.0]]


def test_single_shot_saves_qua_state_block_order():
    experiment = object.__new__(SS.SingleShot1Q)
    experiment.cfg = {"shots": 2, "single_shot_state_order": "ge"}
    experiment.repeats = 1
    experiment.save = False
    experiment.min_F = 0.0
    experiment._acquire_shots = lambda progress=False: (
        np.asarray([[1.0, 2.0], [3.0, 4.0]]),
        np.asarray([[5.0, 6.0], [7.0, 8.0]]),
    )
    experiment.analyze = lambda plotDisp=False: 0.9

    result = experiment.acquire()

    assert result["data"]["acquisition_order"] == "state_shot"
    assert result["data"]["state_order"] == ["ground", "excited"]


def test_rabi_ss_dispatches_unbounded_gain_sweep(monkeypatch):
    gains = np.asarray([1000, 2000, 3000])
    cfg = {
        "reset_mode": "opx_unbounded",
        "shots": 4,
        "n_pulses": 1,
        "rabi_drive_freq": 4367.25,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "sigma": 0.25,
        "read_length": 5.0,
        "adc_trig_offset": 0.5,
    }
    experiment = types.SimpleNamespace(soc=object(), soccfg=object())
    observed = {}

    def acquire(soc, soccfg, passed_cfg, **kwargs):
        observed.update(kwargs)
        i_values = np.asarray([
            np.full(4, -1.0),
            np.full(4, 1.0),
            np.full(4, 2.0),
        ])
        return i_values, np.zeros_like(i_values), {"read_length_cycles": 10}

    monkeypatch.setattr(RSS, "acquire_pulse_sweep_iq", acquire)
    monkeypatch.setattr(
        RSS,
        "classify_payload_iq",
        lambda cfg, i_values, q_values, read_length_cycles: np.asarray(i_values) > 0,
        raising=False,
    )
    monkeypatch.setattr(
        RSS,
        "discriminate_shots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(
            "OPX Rabi must use the timing-matched payload classifier"
        )),
    )
    populations = RSS.sweep_gain_populations(
        experiment,
        cfg,
        gains,
        {"read_theta": 0.0, "scale_factor": 1.0, "threshold": 0.0},
    )

    assert np.array_equal(observed["gains"], gains)
    assert observed["pulses"] == 1
    assert populations.tolist() == [0.0, 1.0, 1.0]


def test_rabi_ss_can_return_the_shots_used_for_population(monkeypatch):
    gains = np.asarray([1000, 2000])
    cfg = {
        "reset_mode": "opx_unbounded",
        "shots": 2,
        "n_pulses": 1,
        "rabi_drive_freq": 4367.25,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "sigma": 0.25,
        "read_length": 5.0,
        "adc_trig_offset": 0.5,
    }
    shots_i = np.asarray([[-1.0, 1.0], [2.0, 3.0]])
    shots_q = np.zeros_like(shots_i)

    monkeypatch.setattr(
        RSS,
        "acquire_pulse_sweep_iq",
        lambda *args, **kwargs: (
            shots_i,
            shots_q,
            {"read_length_cycles": 10},
        ),
    )
    monkeypatch.setattr(
        RSS,
        "classify_payload_iq",
        lambda cfg, i_values, q_values, read_length_cycles: np.asarray(i_values) > 0,
        raising=False,
    )
    populations, returned_i, returned_q = RSS.sweep_gain_populations(
        types.SimpleNamespace(soc=object(), soccfg=object()),
        cfg,
        gains,
        {"read_theta": 0.0, "scale_factor": 1.0, "threshold": 0.0},
        return_iq=True,
    )

    assert populations.tolist() == [0.5, 1.0]
    assert np.array_equal(returned_i, shots_i)
    assert np.array_equal(returned_q, shots_q)


def test_rabi_ss_opx_path_does_not_require_legacy_calibration(monkeypatch):
    def initialize(experiment, **kwargs):
        experiment.cfg = kwargs["cfg"]

    monkeypatch.setattr(RSS.ExperimentClass, "__init__", initialize)

    experiment = RSS.RabiChevronSS(
        soc=object(),
        soccfg=object(),
        path="q3",
        outerFolder="unused",
        cfg={"reset_mode": "opx_unbounded"},
        calib_params=None,
    )

    assert experiment.calib_params is None


def test_tls_memory_opx_path_uses_timing_matched_classifier(monkeypatch):
    def initialize(experiment, **kwargs):
        experiment.cfg = kwargs["cfg"]

    monkeypatch.setattr(TM.ExperimentClass, "__init__", initialize)
    monkeypatch.setattr(
        TM,
        "runtime_bundle",
        lambda cfg: types.SimpleNamespace(
            payload=types.SimpleNamespace(
                holdout={"false_pi": 0.05, "excited_fire": 0.85}
            )
        ),
        raising=False,
    )
    experiment = TM.TLSMemory(
        soc=object(),
        soccfg=object(),
        path="q3",
        outerFolder="unused",
        cfg={"reset_mode": "opx_unbounded"},
        ff_gain=-20000,
        interaction_us=4.0,
        storage_us=12.0,
        sequence="double",
        shots=4,
        calib_params=None,
        assignment_reference=None,
    )
    experiment.soc = object()
    experiment.soccfg = object()
    monkeypatch.setattr(
        TM,
        "acquire_tls_memory_iq",
        lambda *args, **kwargs: (
            np.asarray([[-1.0, 1.0, 2.0, -2.0]]),
            np.zeros((1, 4)),
            {"read_length_cycles": 10, "order": "shot_sequence"},
        ),
        raising=False,
    )
    monkeypatch.setattr(
        TM,
        "classify_payload_iq",
        lambda cfg, i_values, q_values, read_length_cycles: (
            np.asarray(i_values) > 0
        ),
        raising=False,
    )
    monkeypatch.setattr(
        TM,
        "discriminate_shots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(
            "OPX TLS memory must use the timing-matched payload classifier"
        )),
    )

    data = experiment.acquire()

    assert experiment.calib_params is None
    assert experiment.assignment_reference == {"P_g": 0.05, "P_e": 0.85}
    assert data["metrics"]["P_excited"] == pytest.approx(0.5)
    assert data["opx_reset_telemetry"]["order"] == "shot_sequence"


def test_rabi_ss_passive_sweep_derives_program_gain_registers(monkeypatch):
    gains = np.asarray([1000, 2000, 3000])
    cfg = {"reset_mode": "passive"}
    captured = {}

    class Program:
        def __init__(self, soccfg, passed_cfg):
            captured.update(passed_cfg)

        def acquire(self, soc, **kwargs):
            return (
                np.asarray([[-1.0], [1.0], [2.0]]),
                np.zeros((3, 1)),
            )

    monkeypatch.setattr(RSS, "RabiSSProgram", Program)
    populations = RSS.sweep_gain_populations(
        types.SimpleNamespace(soc=object(), soccfg=object()),
        cfg,
        gains,
        {"read_theta": 0.0, "scale_factor": 1.0, "threshold": 0.0},
    )

    assert captured["amp_start"] == 1000
    assert captured["amp_step"] == 1000
    assert captured["amp_expts"] == 3
    assert populations.tolist() == [0.0, 1.0, 1.0]


def test_compact_dmem_sweep_chunks_and_restores_gain_shape(monkeypatch):
    bundle = types.SimpleNamespace(payload=object(), loop=object())
    monkeypatch.setattr(integration, "runtime_bundle", lambda cfg: bundle)
    programs = []

    class Program:
        def __init__(self, soccfg, cfg, payload, loop):
            self.cfg = dict(cfg)
            self.reps = cfg["opx_payload_shots_per_expt"] * cfg["opx_payload_expts"]
            programs.append(self)

        def us2cycles(self, value, ro_ch=None):
            return 10

    def run(soc, program, **kwargs):
        shots = program.cfg["opx_payload_shots_per_expt"]
        expts = program.cfg["opx_payload_expts"]
        return [
            PayloadRecord(100 * expt + shot, -(100 * expt + shot))
            for shot in range(shots)
            for expt in range(expts)
        ]

    monkeypatch.setattr(integration, "OPXResetPulseSweepProgram", Program)
    monkeypatch.setattr(integration, "run_dmem_block", run)
    i_values, q_values, telemetry = integration.acquire_pulse_sweep_iq(
        object(),
        {"tprocs": [{"dmem_size": 64}]},
        {
            "shots": 7,
            "read_length": 5.0,
            "ro_chs": [0],
            "opx_record_base": 32,
        },
        gains=[1000, 2000, 3000],
        pulses=1,
        frequency_mhz=4367.25,
    )

    assert [program.cfg["opx_payload_shots_per_expt"] for program in programs] == [5, 2]
    assert i_values.shape == (3, 7)
    assert q_values.shape == (3, 7)
    assert i_values[2].tolist() == [20.0, 20.1, 20.2, 20.3, 20.4, 20.0, 20.1]
    assert telemetry == {
        "shots_per_point": 7,
        "points": 3,
        "blocks": 2,
        "records": 21,
        "read_length_cycles": 10,
    }


def test_compact_dmem_sweep_forwards_passive_reset_control(monkeypatch):
    bundle = types.SimpleNamespace(payload=object(), loop=object())
    monkeypatch.setattr(integration, "runtime_bundle", lambda cfg: bundle)
    captured = []

    class Program:
        def __init__(self, soccfg, cfg, payload, loop):
            self.cfg = dict(cfg)
            self.reps = cfg["opx_payload_shots_per_expt"] * cfg["opx_payload_expts"]
            captured.append(self.cfg)

        def us2cycles(self, value, ro_ch=None):
            return 10

    def run(soc, program, **kwargs):
        return [PayloadRecord(0, 0) for _ in range(program.reps)]

    monkeypatch.setattr(integration, "OPXResetPulseSweepProgram", Program)
    monkeypatch.setattr(integration, "run_dmem_block", run)
    integration.acquire_pulse_sweep_iq(
        object(),
        {"tprocs": [{"dmem_size": 64}]},
        {
            "shots": 2,
            "read_length": 5.0,
            "ro_chs": [0],
            "opx_record_base": 32,
        },
        gains=[1000, 2000],
        pulses=1,
        frequency_mhz=4367.25,
        reset_scheme="none",
    )

    assert captured[0]["opx_reset_scheme"] == "none"


def test_production_t1_opx_path_sweeps_all_delays_inside_each_shot(monkeypatch):
    experiment = object.__new__(C.T1)
    experiment.cfg = {
        "shots": 4,
        "coherence_rounds": 2,
        "read_length": 5.0,
        "ro_chs": [0],
        "reset_mode": "opx_unbounded",
    }
    experiment.reset_mode = "opx_unbounded"
    experiment.ff_gain = -20000.0
    experiment.t_vec_us = np.asarray([1.0, 35.0, 100.0])
    experiment.soc = object()
    experiment.soccfg = object()
    experiment.calib_params = {}
    experiment.opx_reset_telemetry = []
    experiment.acquisition_telemetry = []
    calls = []

    def acquire(soc, soccfg, cfg, **kwargs):
        calls.append(kwargs)
        return (
            np.asarray([
                [1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, -1.0, -1.0],
                [-1.0, -1.0, -1.0, -1.0],
            ]),
            np.zeros((3, 4)),
            {
                "order": "shot_delay",
                "shots_per_point": 4,
                "points": 3,
                "blocks": 1,
                "records": 12,
                "read_length_cycles": 10,
            },
        )

    monkeypatch.setattr(C, "acquire_t1_sweep_iq", acquire, raising=False)
    monkeypatch.setattr(
        C,
        "classify_payload_iq",
        lambda cfg, i_values, q_values, read_length_cycles: np.asarray(i_values) > 0,
        raising=False,
    )
    monkeypatch.setattr(
        C,
        "discriminate_shots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(
            "OPX T1 must use the timing-matched payload classifier"
        )),
    )

    populations = experiment._sweep(progress=False)

    assert len(calls) == 1
    assert calls[0]["shots"] == 4
    assert all(
        np.array_equal(call["delays_us"], experiment.t_vec_us)
        for call in calls
    )
    assert populations.tolist() == [1.0, 0.5, 0.0]
    assert experiment.point_visit_orders == [[0, 1, 2]]
    assert experiment.acquisition_order == "shot_delay"
    assert experiment.acquisition_telemetry[0]["records"] == 12


def test_production_t1_opx_path_does_not_require_legacy_calibration(monkeypatch):
    def initialize(experiment, **kwargs):
        experiment.cfg = kwargs["cfg"]

    monkeypatch.setattr(C.ExperimentClass, "__init__", initialize)

    experiment = C.T1(
        soc=object(),
        soccfg=object(),
        path="q3",
        outerFolder="unused",
        cfg={"reset_mode": "opx_unbounded"},
        calib_params=None,
        t_vec_us=[1.0, 10.0],
        reset_mode="opx_unbounded",
        ff_gain=-20000,
    )

    assert experiment.calib_params is None


def test_t1_vs_flux_opx_path_does_not_require_legacy_calibration(monkeypatch):
    def initialize(experiment, **kwargs):
        experiment.cfg = kwargs["cfg"]
        experiment.soc = kwargs["soc"]
        experiment.soccfg = kwargs["soccfg"]

    monkeypatch.setattr(T1F.ExperimentClass, "__init__", initialize)

    experiment = T1F._T1VsFluxBase(
        soc=None,
        soccfg=None,
        path="q3",
        outerFolder="unused",
        cfg={"reset_mode": "opx_unbounded", "ro_chs": [0]},
        calib_params=None,
        dc_vec=[-20000],
        shots=10,
        reset_mode="opx_unbounded",
    )

    assert experiment.calib_params is None


def test_t1_vs_flux_opx_point_uses_timing_matched_classifier(monkeypatch):
    experiment = object.__new__(T1F._T1VsFluxBase)
    experiment.cfg = {
        "shots": 2,
        "read_length": 5.0,
        "ro_chs": [0],
    }
    experiment.reset_mode = "opx_unbounded"
    experiment.soc = object()
    experiment.soccfg = object()
    experiment.calib_params = None
    experiment.opx_reset_telemetry = []
    experiment.data = {}
    monkeypatch.setattr(
        T1F,
        "acquire_t1_iq",
        lambda *args, **kwargs: (
            np.asarray([-1.0, 1.0]),
            np.zeros(2),
            {"read_length_cycles": 10},
        ),
    )
    monkeypatch.setattr(
        T1F,
        "classify_payload_iq",
        lambda cfg, i, q, cycles: np.asarray([0, 1]),
    )
    monkeypatch.setattr(
        T1F,
        "discriminate_shots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(
            "OPX Step 6 must not use the legacy classifier"
        )),
    )

    excited, kept = experiment._run_point_counts(-20000, 70.0)

    assert excited == 1.0
    assert kept == 2


def test_production_t1_decay_fit_remains_available():
    delays = np.asarray([1.0, 10.0, 50.0, 150.0, 500.0])
    populations = 0.04 + 0.82 * np.exp(-delays / 100.0)

    fit = C._fit_exp_decay(delays, populations)

    assert fit["tau_us"] == pytest.approx(100.0, rel=1e-3)
    assert fit["P0"] == pytest.approx(0.04, abs=1e-3)
    assert fit["P1"] == pytest.approx(0.86, abs=1e-3)


def test_gate_calibration_builds_opx_rabi_runtime_without_legacy_reset(
    monkeypatch,
):
    qick.QickConfig = type("QickConfig", (), {})
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        GateCalibration as runner,
    )

    calibration = {"schema_version": 1, "payload": {}, "loop": {}}
    monkeypatch.setattr(
        runner,
        "_RESET_SESSION",
        runner.ProductionResetSession.active(calibration, 4366.392029),
    )

    cfg = runner._base_cfg({"shots": 20})

    assert cfg["reset_mode"] == "opx_unbounded"
    assert cfg["opx_reset_calibration"] == calibration
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(10.0)
    assert cfg["opx_persistent_park"] is True
    assert cfg["opx_hard_flux_steps"] is True
    assert cfg["qubit_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["reset_pi_freq"] == pytest.approx(4366.392029)
    assert cfg["relax_delay"] == pytest.approx(10.0)
