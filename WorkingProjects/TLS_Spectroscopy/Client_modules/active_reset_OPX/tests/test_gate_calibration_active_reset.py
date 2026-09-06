import sys
import types

import numpy as np


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


def test_gate_runner_prepares_active_session_for_rabi_iq(monkeypatch):
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
    monkeypatch.setitem(GateCalibration.P_RABI_CHEVRON_IQ, "run", True)

    GateCalibration.main()

    assert prepared == ["GateCalibration"]
