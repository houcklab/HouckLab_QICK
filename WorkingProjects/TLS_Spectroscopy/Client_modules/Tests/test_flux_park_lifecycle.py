import sys
import types

import numpy as np


qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick


from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
    mRabiChevronIQ as R,
    mRabiChevronSS as RSS,
    mSingleShot1Q as SS,
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
        return i_values, np.zeros_like(i_values), {}

    monkeypatch.setattr(RSS, "acquire_pulse_sweep_iq", acquire)
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
        lambda *args, **kwargs: (shots_i, shots_q, {}),
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
            for expt in range(expts)
            for shot in range(shots)
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
