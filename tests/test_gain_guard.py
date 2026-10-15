"""Hardware-free tests for the drive-gain guard (docs/concepts/timing_and_units.md#gains).

qick 0.2.334 compiles a DAC gain above 32767 without complaint and the signed 16-bit register
wraps it (40000 plays as -25536). Every experiment, the regime-A context and the runs that sweep a
gain must refuse such a value before any folder, program or hardware call; valid gains and
fast-flux entries pass untouched.

    python -m pytest tests/test_gain_guard.py
"""

import os
from types import SimpleNamespace

import numpy as np
import pytest
from qick import AveragerProgram

import qicklab.core.context as context_mod
import qicklab.runs.rabi as rabi_runs
import qicklab.runs.spectroscopy as spec_runs
from qicklab.core.config import GAIN_MAX, check_gain, validate_gains
from qicklab.core.experiment import ExperimentClass
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N
from qicklab.experiments.readout_optimize import ReadOpt_wSingleShotFF
from qicklab.experiments.zero_span_parity import ZeroSpanParity
from qicklab.hardware.board import FF_Qubits
from tests.regression.capture import FakeSocCfg


def test_qick_compiles_an_out_of_range_gain_unchecked():
    """The reason for the guard: qick writes 40000 into the gain register as is."""

    class _Prog(AveragerProgram):
        def initialize(self):
            self.declare_gen(ch=1, nqz=1)
            self.set_pulse_registers(ch=1, style="const", freq=0, phase=0, gain=40000, length=10)
            self.synci(200)

        def body(self):
            self.pulse(ch=1, t=0)

    listing = str(_Prog(FakeSocCfg(), {"reps": 1}))
    assert "40000" in listing


def test_check_gain_limits_and_message():
    assert GAIN_MAX == 32767
    for ok in (0, 1, 32767, 32767.0, np.int64(5000), [0, 32767], np.arange(0, 32001, 1000)):
        check_gain("g", ok)
    for skipped in (None, float("nan"), "800", True):
        check_gain("g", skipped)
    with pytest.raises(ValueError, match=r"pulse_gain = 40000 .*0\.\.32767.*-25536"):
        check_gain("pulse_gain", 40000)
    with pytest.raises(ValueError, match="32768"):
        check_gain("g", 32768)
    with pytest.raises(ValueError, match=r"g = -10 "):
        check_gain("g", -10)
    with pytest.raises(ValueError, match="40000"):
        check_gain("sweep_gains", [200, 5000, 40000])
    with pytest.raises(ValueError, match="70000"):
        check_gain("g", np.array([[100], [70000]]))


def _regime_a_cfg(**over):
    cfg = {
        "res_ch": 0,
        "qubit_ch": 1,
        "pulse_gain": 1500,
        "qubit_gain": 800,
        "pi2_gain": 2500,
        "start": 4000.0,  # a frequency sweep in most experiments: never a gain by default
        "step": 0.2,
        "expts": 201,
        "FF_Qubits": FF_Qubits,
    }
    cfg.update(over)
    return cfg


def test_validate_gains_checks_drive_keys_only():
    validate_gains(_regime_a_cfg())
    # fast-flux entries may be negative: never checked
    ff = {k: dict(v, Gain_Pulse=-20000, Gain_Readout=-32000) for k, v in FF_Qubits.items()}
    validate_gains(_regime_a_cfg(FF_Qubits=ff, ff_gain=-30000))
    for key in ("pulse_gain", "qubit_gain", "pi_gain", "pi2_gain", "gain_end", "cav_gain_Stop"):
        with pytest.raises(ValueError, match=rf"\['{key}'\] = 40000"):
            validate_gains(_regime_a_cfg(**{key: 40000}))
    with pytest.raises(ValueError, match="qubit_gains"):
        validate_gains(_regime_a_cfg(qubit_gains=[3000, 40000]))
    with pytest.raises(ValueError, match="qubit_gain_Start"):
        validate_gains(_regime_a_cfg(qubit_gain_Start=-1))


def test_validate_gains_register_sweep_endpoint():
    keys = ("start", "step", "expts")
    validate_gains({"start": 0, "step": 99, "expts": 101}, keys)  # last point 9900
    validate_gains({"start": 0, "step": 327, "expts": 101}, keys)  # last point 32700
    with pytest.raises(ValueError, match="last sweep point"):
        validate_gains({"start": 0, "step": 400, "expts": 101}, keys)  # last point 40000
    with pytest.raises(ValueError, match="first sweep point"):
        validate_gains({"start": 40000, "step": -400, "expts": 101}, keys)


def _ctor_kwargs(tmp_path, cfg):
    return dict(path="Gains", outerFolder=str(tmp_path) + os.sep, cfg=cfg, soccfg=FakeSocCfg())


def test_experiment_refuses_before_making_its_folder(tmp_path):
    with pytest.raises(ValueError, match=r"ExperimentClass cfg\['pulse_gain'\] = 40000"):
        ExperimentClass(**_ctor_kwargs(tmp_path, _regime_a_cfg(pulse_gain=40000)))
    assert not os.listdir(tmp_path)
    ExperimentClass(**_ctor_kwargs(tmp_path, _regime_a_cfg()))
    assert os.listdir(tmp_path)


def test_amplitude_rabi_classes_check_their_gain_sweep(tmp_path):
    # AmplitudeRabiFF: start/step/expts are gains (register sweep)
    good = _regime_a_cfg(start=0, step=99, expts=101)
    AmplitudeRabiFF(**_ctor_kwargs(tmp_path, good))
    with pytest.raises(ValueError, match=r"AmplitudeRabiFF cfg.*last sweep point"):
        AmplitudeRabiFF(**_ctor_kwargs(tmp_path, _regime_a_cfg(start=0, step=400, expts=101)))
    # the same keys are a frequency sweep elsewhere: an experiment without gain_sweep_keys ignores them
    ExperimentClass(**_ctor_kwargs(tmp_path, _regime_a_cfg(start=0, step=400, expts=101)))
    # AmplitudeRabiFF_N: np.linspace(gain_start, gain_end, n)
    with pytest.raises(ValueError, match=r"AmplitudeRabiFF_N cfg\['gain_end'\] = 40000"):
        AmplitudeRabiFF_N(**_ctor_kwargs(tmp_path, _regime_a_cfg(gain_start=0, gain_end=40000)))


def test_readout_optimize_gain_stop(tmp_path):
    cfg = _regime_a_cfg(cav_gain_Start=3000, cav_gain_Stop=40000, cav_gain_Points=7)
    with pytest.raises(ValueError, match=r"cav_gain_Stop'\] = 40000"):
        ReadOpt_wSingleShotFF(**_ctor_kwargs(tmp_path, cfg))


class _Ctx:
    """The fields run_amplitude_rabi / run_spec_gain_length_sweep read; working_config is fatal."""

    qubit_sigma, qubit_flattop, Qubit_Pulse, outerFolder = 0.05, None, 1, "unused"
    qubit_frequency_center = 4000.0
    soc = soccfg = None

    def working_config(self, *updates):
        raise AssertionError("the run must refuse before building its cfg")


def test_run_amplitude_rabi_refuses_max_gain():
    params = dict(max_gain=40000, number_of_steps=101, reps=1, rounds=1, qubit_freq=4000.0)
    params.update(relax_delay=100, fit=False)
    with pytest.raises(ValueError, match=r"Amplitude_Rabi_params\['max_gain'\] = 40000"):
        rabi_runs.run_amplitude_rabi(_Ctx(), params)


def test_run_spec_gain_length_sweep_refuses_before_the_first_point(monkeypatch):
    class _NeverBuilt:
        def __init__(self, *a, **k):
            raise AssertionError("no spectrum may run before the gain list is checked")

    monkeypatch.setattr(spec_runs, "QubitSpecSliceFF", _NeverBuilt)
    ctx = SimpleNamespace(working_config=dict)
    params = dict(sweep_lengths=[10], sweep_gains=[200, 5000, 40000], display=False)
    params.update(min_sep_MHz=1.0)
    with pytest.raises(ValueError, match=r"sweep_gains'\] = 40000"):
        spec_runs.run_spec_gain_length_sweep(ctx, params)


def test_zero_span_set_qubit_gain_refuses_and_leaves_cfg():
    exp = ZeroSpanParity.__new__(ZeroSpanParity)
    exp.cfg = {"mode": "strobe", "qubit_gain": 800}
    with pytest.raises(ValueError, match="set_qubit_gain gain = 40000"):
        exp.set_qubit_gain(40000)
    assert exp.cfg["qubit_gain"] == 800


def _qubit_parameters(readout_gain=1500, qubit_gain=5000, pi2_gain=2500):
    return {
        "1": {
            "Readout": {"Frequency": 6870.8, "Gain": readout_gain},
            "Qubit": {"Frequency": 4000.0, "Gain": qubit_gain, "pi2_Gain": pi2_gain},
        }
    }


@pytest.mark.parametrize(
    "over, name",
    [
        (dict(readout_gain=40000), r"\['Readout'\]\['Gain'\]"),
        (dict(qubit_gain=33000), r"\['Qubit'\]\['Gain'\]"),
        (dict(pi2_gain=-1), r"\['pi2_Gain'\]"),
    ],
)
def test_build_context_refuses_before_connecting(monkeypatch, over, name):
    def _no_hardware():
        raise AssertionError("build_context must check gains before makeProxy")

    monkeypatch.setattr(context_mod, "makeProxy", _no_hardware)
    with pytest.raises(ValueError, match=name):
        context_mod.build_context(
            _qubit_parameters(**over),
            1,
            1,
            0.0,
            Transmission_params={},
            Spec_relevant_params={"qubit_gain": 800},
            tl={},
            ts={},
            charge_params={},
        )
    with pytest.raises(ValueError, match=r"Spec_relevant_params\['qubit_gain'\] = 40000"):
        context_mod.build_context(
            _qubit_parameters(),
            1,
            1,
            0.0,
            Transmission_params={},
            Spec_relevant_params={"qubit_gain": 40000},
            tl={},
            ts={},
            charge_params={},
        )
