"""T2E step quantisation reads the tProc cycle from soccfg (F83).

The step used to be built from a hard-coded 0.00232515 us (1/430.08 MHz). On a board
with another tProc clock the per-wait register increment us2cycles(step/(n+1)) then
rounds to a different number of cycles than the x axis (i * step) assumes, scaling the
T2E axis by about 1-2 % (all n + 1 waits share r_wait, so they stay equal). No hardware:
programs compile against a real QickConfig over the synthetic board.
"""

import copy
import types

import pytest
from qick import QickConfig

from tests.regression import capture
from tests.test_program_timing import _cfg

OLD_CYCLE_US = 0.00232515  # the constant this replaced


def _soccfg(f_time):
    board = copy.deepcopy(capture.BOARDS["A"])
    board["tprocs"][0]["f_time"] = f_time
    return QickConfig(board)


def _wait_increment(soccfg, step, n):
    """The r_wait increment (tProc cycles) the compiled T2E program adds per point."""
    from qicklab.experiments.t2_echo import T2EProgram
    from qicklab.hardware.board import BaseConfig

    cfg = _cfg(BaseConfig, start=0, step=step, expts=121, num_pi_pulses=n)
    prog = T2EProgram(soccfg, cfg)
    (inc,) = [x["args"][4] for x in prog.prog_list if x["name"] == "mathi" and x["args"][1] == 3]
    return inc


@pytest.mark.parametrize("f_time", [430.08, 409.6, 384.0, 350.0])
def test_tproc_cycle_is_read_from_soccfg(f_time):
    from qicklab.core.schedule import tproc_cycle_us

    assert tproc_cycle_us(_soccfg(f_time)) == 1 / f_time


def test_lab_clock_value_unchanged():
    """430.08 MHz: same int_steps and cycle counts as the constant; step moves by ~5e-7."""
    from qicklab.experiments.t2_echo import quantised_t2e_step

    soccfg = capture.FakeSocCfg("A")
    int_steps, step = quantised_t2e_step(soccfg, 20, 121, 1)
    assert type(int_steps) is int and int_steps == 35
    assert step == pytest.approx(2 * 35 / 430.08, rel=1e-12)
    assert step == pytest.approx(OLD_CYCLE_US * 2 * 35, rel=1e-6)
    assert _wait_increment(soccfg, step, 1) == _wait_increment(soccfg, OLD_CYCLE_US * 70, 1)


@pytest.mark.parametrize("f_time", [430.08, 409.6, 384.0, 350.0])
@pytest.mark.parametrize("n, t2_max_us", [(1, 20), (3, 60)])
def test_x_axis_matches_programmed_wait(f_time, n, t2_max_us):
    """Every wait advances exactly int_steps cycles, so i * step is the realised free
    evolution; the old constant missed it by 0.3-1.7 % off 430.08 MHz."""
    from qicklab.experiments.t2_echo import quantised_t2e_step

    soccfg = _soccfg(f_time)
    expts = 121
    int_steps, step = quantised_t2e_step(soccfg, t2_max_us, expts, n)
    assert int_steps > 0
    assert _wait_increment(soccfg, step, n) == int_steps
    realised_last = (expts - 1) * (n + 1) * int_steps / f_time
    assert (expts - 1) * step == pytest.approx(realised_last, rel=1e-12)

    k_old = int(t2_max_us // (OLD_CYCLE_US * (n + 1) * expts))
    step_old = OLD_CYCLE_US * (n + 1) * k_old
    realised_old = (n + 1) * _wait_increment(soccfg, step_old, n) / f_time
    if f_time == 430.08:
        assert realised_old == pytest.approx(step_old, rel=1e-6)
    else:
        assert abs(realised_old / step_old - 1) > 2e-3


def test_too_many_points_gives_zero_steps():
    from qicklab.experiments.t2_echo import quantised_t2e_step

    assert quantised_t2e_step(capture.FakeSocCfg("A"), 0.1, 121, 1) == (0, 0.0)


class _StubT2E:
    cfgs = []

    def __init__(self, path, cfg, soc, soccfg, outerFolder):
        _StubT2E.cfgs.append(cfg)

    @staticmethod
    def acquire(inst):
        return None


T2E_RUN_PARAMS = {
    "repetitions": 1,
    "num_pi_pulses": 1,
    "T2_max_us": 20,
    "T2_expts": 121,
    "T2_reps": 10,
    "T2_rounds": 1,
    "relax_delay": 100,
    "freq_shift": 0.0,
    "rotation_angle": False,
}


def _ctx(soccfg):
    return types.SimpleNamespace(
        soccfg=soccfg,
        soc=types.SimpleNamespace(reset_gens=lambda: None),
        outerFolder="unused",
        qubit_gain=4200,
        pi2_gain=2100,
        qubit_frequency_center=2651.0,
        qubit_sigma=0.08,
        qubit_flattop=None,
        Qubit_Readout=[1],
        working_config=lambda expt: dict(expt),
    )


def test_run_t2e_uses_board_clock(monkeypatch):
    from qicklab.runs import coherence

    _StubT2E.cfgs = []
    monkeypatch.setattr(coherence, "T2EMUX", _StubT2E)
    monkeypatch.setattr(coherence, "finish", lambda *a, **k: None)
    monkeypatch.setattr(coherence.time, "sleep", lambda s: None)
    soccfg = _soccfg(409.6)
    coherence.run_t2e(_ctx(soccfg), T2E_RUN_PARAMS)
    (cfg,) = _StubT2E.cfgs
    assert cfg["step"] == pytest.approx(
        2 * 33 / 409.6, rel=1e-12
    )  # floor(20 / (2 * 121 / 409.6)) = 33
    assert soccfg.us2cycles(cfg["step"] / 2) == 33


@pytest.mark.parametrize("t2_max_us, int_steps", [(20, 33), (0.1, 1)])
def test_auto_coherence_stage_uses_board_clock(monkeypatch, t2_max_us, int_steps):
    """Stage 6 uses the same quantum; int_steps 0 is still clamped to 1."""
    from qicklab.runs import auto_coherence

    _StubT2E.cfgs = []
    monkeypatch.setattr(auto_coherence, "T2EMUX", _StubT2E)
    monkeypatch.setattr(auto_coherence, "finish", lambda *a, **k: None)
    monkeypatch.setattr(auto_coherence.time, "sleep", lambda s: None)
    soccfg = _soccfg(409.6)
    params = {
        "T2E_repetitions": 1,
        "T2E_num_pi_pulses": 1,
        "T2E_max_us": t2_max_us,
        "T2E_expts": 121,
        "T2E_reps": 10,
        "T2E_rounds": 1,
        "T2E_relax_delay": 100,
    }
    soc = types.SimpleNamespace(reset_gens=lambda: None)
    log = []
    auto_coherence._stage_run_t2e(
        soc, soccfg, {}, "unused", 2651.0, 4200, 2100, 0.08, None, [1], params, log
    )
    (cfg,) = _StubT2E.cfgs
    assert cfg["step"] == pytest.approx(2 * int_steps / 409.6, rel=1e-12)
    assert soccfg.us2cycles(cfg["step"] / 2) == int_steps
