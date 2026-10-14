"""Hardware-free tests for qicklab.runs.active_reset.calibrate_active_reset_readout (F22).

The calibration rotates ctx.config["res_phase"] in place and the rotated value persists in the
session, so repeated calibrations (ARV -> MR(use_active_reset) -> another MR in one regime-A
session) build on each other. The phase must stay wrapped into [0, 2^b_phase): unwrapped, the
third calibration pushed it past 2^33 and SingleShotProgram failed to compile ("Immediate values
are only 31 bits"). See docs/experiments/active_reset.md.

    python -m pytest tests/test_active_reset_calibration.py
"""

import numpy as np
import pytest

import qicklab.runs.active_reset as ar
from qicklab.experiments.single_shot import SingleShotProgram
from qicklab.hardware.board import BaseConfig
from tests.regression import capture
from tests.test_program_timing import _cfg

# residual g->e axis angle seen by each successive calibration (the finding's sequence)
RESIDUALS_DEG = [10.0, 2.0, 1.0]


class _Ctx:
    def __init__(self, soccfg, res_phase=0):
        self.soccfg = soccfg
        self.config = _cfg(BaseConfig, res_phase=res_phase)


def _fake_separator(residuals):
    """First call of each calibration: e rotated by the next residual; trial calls: aligned on I."""
    state = {"n": 0, "k": 0}

    def sep(ctx):
        n = state["n"]
        state["n"] += 1
        if n % 2 == 0:
            phi = np.radians(residuals[state["k"]])
            state["k"] += 1
            return {"g_center": np.zeros(2), "e_center": np.array([np.cos(phi), np.sin(phi)])}
        return {"g_center": np.zeros(2), "e_center": np.array([1.0, 0.0])}

    return sep


@pytest.mark.parametrize("start_phase", [0, -12345, 2**32 + 7])
def test_repeated_calibration_keeps_res_phase_in_range(monkeypatch, start_phase):
    soccfg = capture.FakeSocCfg("A")
    ctx = _Ctx(soccfg, res_phase=start_phase)
    res_ch = ctx.config["res_ch"]
    mod = 2 ** soccfg["gens"][res_ch]["b_phase"]
    monkeypatch.setattr(ar, "get_apriori_separator_from_singleshot", _fake_separator(RESIDUALS_DEG))

    expected = start_phase % mod
    for phi in RESIDUALS_DEG:
        out = ar.calibrate_active_reset_readout(ctx)
        expected = (expected + soccfg.deg2reg(-phi, gen_ch=res_ch)) % mod
        assert out["res_phase"] == ctx.config["res_phase"] == expected
        assert 0 <= ctx.config["res_phase"] < mod
        SingleShotProgram(soccfg, dict(ctx.config))  # the old unwrapped value raised on the 3rd


def test_unwrapped_phase_would_not_compile():
    """Guards the premise: an out-of-range phase (old 3rd-calibration value) breaks the compile."""
    soccfg = capture.FakeSocCfg("A")
    with pytest.raises(RuntimeError, match="31 bits"):
        SingleShotProgram(soccfg, _cfg(BaseConfig, res_phase=12729805847))
