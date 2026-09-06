import sys
import types

import numpy as np
import pytest


qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    sys.modules["qick"] = qick
for name in ("AveragerProgram", "RAveragerProgram", "QickProgram", "QickConfig"):
    if not hasattr(qick, name):
        setattr(qick, name, type(name, (), {}))


def test_rabi_iq_qua_grid_uses_unbounded_reset_when_session_is_active(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mRabiChevronIQ

    observed = {}

    def acquire(soc, soccfg, cfg, **kwargs):
        observed.update(kwargs)
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(kwargs["shots"]),
        )
        values = np.arange(np.prod(shape), dtype=float).reshape(shape)
        return values, values / 2.0, {"order": "shot_frequency_gain"}

    monkeypatch.setattr(mRabiChevronIQ, "acquire_pulse_grid_iq", acquire)
    cfg = {
        "shots": 3,
        "amp_start": 1000,
        "amp_stop": 3000,
        "amp_expts": 3,
        "freq_span": 2.0,
        "freq_points": 3,
        "qubit_pi_freq": 4367.25,
        "qubit_freq": 4367.25,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "sigma": 0.25,
        "read_length": 5.0,
        "adc_trig_offset": 0.5,
        "reset_mode": "opx_unbounded",
        "qua_shot_order": True,
        "remeasure_outliers": False,
    }
    experiment = mRabiChevronIQ.RabiChevronIQ(
        soc=object(),
        soccfg={},
        path="q3",
        outerFolder=tmp_path,
        cfg=cfg,
        num_pi_pulses=1,
        pulse_type="X180",
        save=False,
    )

    experiment.acquire(progress=False, plotDisp=False)

    assert observed["reset_scheme"] == "opx_unbounded"


def test_rabi_iq_qua_grid_reports_outer_shot_progress(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mRabiChevronIQ

    updates = []

    def acquire(soc, soccfg, cfg, **kwargs):
        kwargs["progress"](2, 3)
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(kwargs["shots"]),
        )
        values = np.zeros(shape, dtype=float)
        return values, values, {"order": "shot_frequency_gain"}

    monkeypatch.setattr(mRabiChevronIQ, "acquire_pulse_grid_iq", acquire)
    monkeypatch.setattr(
        mRabiChevronIQ,
        "progress_counter",
        lambda iteration, total, **kwargs: updates.append(
            (iteration, total, kwargs["label"])
        ),
    )
    cfg = {
        "shots": 3,
        "amp_start": 1000,
        "amp_stop": 3000,
        "amp_expts": 3,
        "freq_span": 2.0,
        "freq_points": 3,
        "qubit_pi_freq": 4367.25,
        "qubit_freq": 4367.25,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "sigma": 0.25,
        "read_length": 5.0,
        "adc_trig_offset": 0.5,
        "reset_mode": "passive",
        "qua_shot_order": True,
        "remeasure_outliers": False,
    }
    experiment = mRabiChevronIQ.RabiChevronIQ(
        soc=object(),
        soccfg={},
        path="q3",
        outerFolder=tmp_path,
        cfg=cfg,
        save=False,
    )

    experiment.acquire(progress=True, plotDisp=False)

    assert updates == [(1, 3, "Rabi chevron IQ")]


def test_rabi_ss_qua_grid_reports_outer_shot_progress(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mRabiChevronSS

    updates = []

    def acquire(soc, soccfg, cfg, **kwargs):
        kwargs["progress"](3, 3)
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(kwargs["shots"]),
        )
        values = np.zeros(shape, dtype=float)
        return values, values, {"order": "shot_frequency_gain"}

    monkeypatch.setattr(mRabiChevronSS, "acquire_pulse_grid_iq", acquire)
    monkeypatch.setattr(
        mRabiChevronSS,
        "discriminate_shots",
        lambda i_values, q_values, calib_params: np.zeros_like(i_values),
    )
    monkeypatch.setattr(
        mRabiChevronSS,
        "progress_counter",
        lambda iteration, total, **kwargs: updates.append(
            (iteration, total, kwargs["label"])
        ),
    )
    cfg = {
        "shots": 3,
        "amp_start": 1000,
        "amp_stop": 3000,
        "amp_expts": 3,
        "freq_span": 2.0,
        "freq_points": 3,
        "qubit_pi_freq": 4367.25,
        "qubit_freq": 4367.25,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "sigma": 0.25,
        "read_length": 5.0,
        "adc_trig_offset": 0.5,
        "relax_delay": 10.0,
        "reset_mode": "passive",
        "qua_shot_order": True,
        "remeasure_outliers": False,
    }
    experiment = mRabiChevronSS.RabiChevronSS(
        soc=object(),
        soccfg={},
        path="q3",
        outerFolder=tmp_path,
        cfg=cfg,
        calib_params={},
        save=False,
    )

    experiment.acquire(progress=True, plotDisp=False)

    assert updates == [(2, 3, "Rabi chevron SS")]


def test_gate_runner_applies_active_session_to_rabi_iq(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    observed = {}

    class Experiment:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def acquire(self, **kwargs):
            return None

    monkeypatch.setattr(GateCalibration, "RabiChevronIQ", Experiment)
    monkeypatch.setattr(GateCalibration.plt, "close", lambda *args, **kwargs: None)
    monkeypatch.setattr(GateCalibration.gc, "collect", lambda: None)
    monkeypatch.setattr(
        GateCalibration,
        "_RESET_SESSION",
        ProductionResetSession.active(
            calibration={"schema_version": 1, "payload": {}, "loop": {}},
            method_frequency_mhz=4366.392029,
        ),
    )

    GateCalibration.run_rabi_chevron_iq(tmp_path, object(), {})

    assert observed["cfg"]["reset_mode"] == "opx_unbounded"


@pytest.mark.parametrize(
    "enabled_name",
    ["P_RABI_CHEVRON_IQ", "P_QUBIT_SPEC", "P_QUBIT_SPEC_SWEEP"],
)
def test_gate_runner_prepares_active_session_for_qubit_drive(monkeypatch, enabled_name):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    active = ProductionResetSession.active(
        calibration={"schema_version": 1, "payload": {}, "loop": {}},
        method_frequency_mhz=4366.392029,
    )
    prepared = []
    monkeypatch.setattr(GateCalibration, "makeProxy", lambda: (object(), {}))
    monkeypatch.setattr(
        GateCalibration,
        "_RESET_SESSION",
        ProductionResetSession.passive(),
    )
    monkeypatch.setattr(
        GateCalibration,
        "prepare_reset_session",
        lambda *args, **kwargs: prepared.append(kwargs["purpose"]) or active,
    )
    monkeypatch.setattr(GateCalibration, "run_rabi_chevron_iq", lambda *args: None)
    monkeypatch.setattr(GateCalibration, "run_qubit_spec", lambda *args: None)
    monkeypatch.setattr(GateCalibration, "run_qubit_spec_sweep", lambda *args: None)
    for params in (
        GateCalibration.P_TRANSMISSION,
        GateCalibration.P_TRANSMISSION_SWEEP,
        GateCalibration.P_QUBIT_SPEC,
        GateCalibration.P_QUBIT_SPEC_SWEEP,
        GateCalibration.P_SS_CAL,
        GateCalibration.P_RABI_CHEVRON_IQ,
        GateCalibration.P_RABI_CHEVRON_SS,
        GateCalibration.P_READOUT_OPT,
        GateCalibration.P_QUBIT_OPT,
    ):
        monkeypatch.setitem(params, "run", False)
    monkeypatch.setitem(getattr(GateCalibration, enabled_name), "run", True)

    GateCalibration.main()

    assert prepared == ["GateCalibration"]


def test_qubit_spec_uses_active_pulse_grid_for_an_active_session(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mQubitSpec

    observed = []

    def active(soc, soccfg, cfg, **kwargs):
        observed.append(kwargs["reset_scheme"])
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(cfg["shots"]),
        )
        values = np.arange(np.prod(shape), dtype=float).reshape(shape)
        return values, values / 2.0, {"order": "shot_frequency_gain"}

    def passive(soc, soccfg, cfg, **kwargs):
        observed.append("passive")
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(cfg["shots"]),
        )
        values = np.arange(np.prod(shape), dtype=float).reshape(shape)
        return values, values / 2.0, {"order": "shot_frequency_gain"}

    monkeypatch.setattr(mQubitSpec, "acquire_pulse_grid_iq", active, raising=False)
    monkeypatch.setattr(mQubitSpec, "acquire_passive_pulse_grid", passive)
    monkeypatch.setattr(mQubitSpec, "_feature_freq", lambda frequencies, magnitude: frequencies[0])
    cfg = {
        "shots": 3,
        "qubit_freq_start": 4360.0,
        "qubit_freq_stop": 4362.0,
        "qubit_freq_expts": 3,
        "qubit_gain": 15000,
        "reset_mode": "opx_unbounded",
        "qua_shot_order": True,
    }
    experiment = mQubitSpec.QubitSpec(
        soc=object(),
        soccfg={},
        path="q3",
        outerFolder=tmp_path,
        cfg=cfg,
        save=False,
    )

    experiment.acquire(progress=False, plotDisp=False)

    assert observed == ["opx_unbounded"]


def test_qubit_spec_active_grid_reports_outer_shot_progress(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mQubitSpec

    updates = []

    def active(soc, soccfg, cfg, **kwargs):
        kwargs["progress"](2, 3)
        shape = (
            len(kwargs["frequencies_mhz"]),
            len(kwargs["gains"]),
            int(cfg["shots"]),
        )
        values = np.zeros(shape, dtype=float)
        return values, values, {"order": "shot_frequency_gain"}

    monkeypatch.setattr(mQubitSpec, "acquire_pulse_grid_iq", active, raising=False)
    monkeypatch.setattr(mQubitSpec, "_feature_freq", lambda frequencies, magnitude: frequencies[0])
    monkeypatch.setattr(
        mQubitSpec,
        "progress_counter",
        lambda iteration, total, **kwargs: updates.append(
            (iteration, total, kwargs["label"])
        ),
    )
    cfg = {
        "shots": 3,
        "qubit_freq_start": 4360.0,
        "qubit_freq_stop": 4362.0,
        "qubit_freq_expts": 3,
        "qubit_gain": 15000,
        "reset_mode": "opx_unbounded",
        "qua_shot_order": True,
    }
    experiment = mQubitSpec.QubitSpec(
        soc=object(),
        soccfg={},
        path="q3",
        outerFolder=tmp_path,
        cfg=cfg,
        save=False,
    )

    experiment.acquire(progress=True, plotDisp=False)

    assert updates == [(1, 3, "qubit spec")]


def test_t1_qua_sweep_reports_outer_shot_progress(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mCoherence

    updates = []

    def acquire(soc, soccfg, cfg, **kwargs):
        kwargs["progress"](2, 3)
        values = np.zeros((len(kwargs["delays_us"]), kwargs["shots"]), dtype=float)
        return values, values, {
            "order": "shot_delay",
            "read_length_cycles": 10,
        }

    monkeypatch.setattr(mCoherence, "acquire_t1_sweep_iq", acquire)
    monkeypatch.setattr(
        mCoherence,
        "discriminate_shots",
        lambda i_values, q_values, calib_params: np.zeros_like(i_values),
    )
    monkeypatch.setattr(
        mCoherence,
        "progress_counter",
        lambda iteration, total, **kwargs: updates.append(
            (iteration, total, kwargs["label"])
        ),
    )
    experiment = object.__new__(mCoherence.T1)
    experiment.cfg = {"shots": 3}
    experiment.t_vec_us = np.asarray([1.0, 10.0, 100.0])
    experiment.ff_gain = 0.0
    experiment.reset_mode = "passive"
    experiment.soc = object()
    experiment.soccfg = {}
    experiment.calib_params = {}
    experiment.suffix = "T1"
    experiment.acquisition_telemetry = []
    experiment.opx_reset_telemetry = []

    experiment._sweep_qua_order(progress=True)

    assert updates == [(1, 3, "T1")]


def test_gate_runner_applies_active_session_to_qubit_spec(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    observed = {}

    class Experiment:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def acquire(self, **kwargs):
            return None

    monkeypatch.setattr(GateCalibration, "QubitSpec", Experiment)
    monkeypatch.setattr(GateCalibration.plt, "close", lambda *args, **kwargs: None)
    monkeypatch.setattr(GateCalibration.gc, "collect", lambda: None)
    monkeypatch.setattr(
        GateCalibration,
        "_RESET_SESSION",
        ProductionResetSession.active(
            calibration={"schema_version": 1, "payload": {}, "loop": {}},
            method_frequency_mhz=4366.392029,
        ),
    )

    GateCalibration.run_qubit_spec(tmp_path, object(), {})

    assert observed["cfg"]["reset_mode"] == "opx_unbounded"


def test_gate_qubit_spec_gain_sweep_uses_a_uniform_integer_dac_axis(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    observed = {}

    class Experiment:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def acquire(self, **kwargs):
            return None

    monkeypatch.setattr(GateCalibration, "QubitSpecGainSweep", Experiment)
    monkeypatch.setattr(GateCalibration.plt, "close", lambda *args, **kwargs: None)
    monkeypatch.setattr(GateCalibration.gc, "collect", lambda: None)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_min", 200)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_max", 10000)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_points", 12)
    monkeypatch.setattr(
        GateCalibration,
        "_RESET_SESSION",
        ProductionResetSession.active(
            calibration={"schema_version": 1, "payload": {}, "loop": {}},
            method_frequency_mhz=4366.392029,
        ),
    )

    GateCalibration.run_qubit_spec_sweep(tmp_path, object(), {})

    gains = np.asarray(observed["gains"])
    assert np.issubdtype(gains.dtype, np.integer)
    assert np.unique(np.diff(gains)).size == 1


def test_gate_qubit_spec_gain_sweep_preserves_passive_axis(tmp_path, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        ProductionResetSession,
    )

    observed = {}

    class Experiment:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def acquire(self, **kwargs):
            return None

    monkeypatch.setattr(GateCalibration, "QubitSpecGainSweep", Experiment)
    monkeypatch.setattr(GateCalibration.plt, "close", lambda *args, **kwargs: None)
    monkeypatch.setattr(GateCalibration.gc, "collect", lambda: None)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_min", 200)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_max", 10000)
    monkeypatch.setitem(GateCalibration.P_QUBIT_SPEC_SWEEP, "gain_points", 12)
    monkeypatch.setattr(
        GateCalibration,
        "_RESET_SESSION",
        ProductionResetSession.passive(),
    )

    GateCalibration.run_qubit_spec_sweep(tmp_path, object(), {})

    gains = np.asarray(observed["gains"])
    assert gains.dtype == np.dtype(float)
    assert gains[0] == 200.0
    assert gains[-1] == 10000.0
