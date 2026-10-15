"""Register-swept wait axis = the waits the compiled program realises (F78).

T1, T2R and T2E sweep their wait with a tProc register that advances by
us2cycles(step / segments) whole cycles per point; qick's get_expt_pts reports
start + i * step, which differs by the rounding (lab clock 430.08 MHz: +2.3 % at a
0.05 us step, -7.0 % at 0.01 us, -0.019 % at 5 us and 0.1 us). The acquire methods now
report the realised axis. No hardware: programs compile against capture.FakeSocCfg and
qick's acquire is replaced by a stub that returns its get_expt_pts axis.
"""

import numpy as np
import pytest

from tests.regression import capture
from tests.test_program_timing import _cfg

F_TIME = 430.08  # tProc clock of board A (the lab clock)
EXPTS = 41


def _base():
    from qicklab.hardware.board import BaseConfig

    return BaseConfig


def _wait_increment(prog):
    """The per-point r_wait (register 3) increment of a compiled program, in cycles."""
    (inc,) = [x["args"][4] for x in prog.prog_list if x["name"] == "mathi" and x["args"][1] == 3]
    return inc


def _stub_acquire(monkeypatch, program_cls, seen):
    def fake(prog, soc, **kwargs):
        seen.append(prog)
        n = prog.cfg["expts"]
        zeros = [np.zeros((1, n))]
        return prog.get_expt_pts(), zeros, zeros

    monkeypatch.setattr(program_cls, "acquire", fake)


def test_helper_quantisation_examples():
    """The numbers quoted in docs/concepts/timing_and_units.md#register-swept-wait-axis."""
    from qicklab.core.schedule import realised_wait_axis_us

    soccfg = capture.FakeSocCfg("A")
    for step, rel in [
        (5, -0.000186),
        (0.1, -0.000186),
        (0.05, 0.0231),
        (0.02, 0.0463),
        (0.01, -0.0699),
    ]:
        x = realised_wait_axis_us(soccfg, 0, step, 3)
        assert x[0] == 0
        assert x[1] / step - 1 == pytest.approx(rel, abs=5e-5)
        assert x[2] == pytest.approx(2 * round(step * F_TIME) / F_TIME, rel=1e-12)
    # segments: each of the n + 1 waits is rounded, the total is (n + 1) times that
    x = realised_wait_axis_us(soccfg, 0, 0.05, 3, segments=2)
    assert x[1] == pytest.approx(2 * round(0.025 * F_TIME) / F_TIME, rel=1e-12)


@pytest.mark.parametrize("step", [0.01, 0.02, 0.05, 0.1, 5.0])
@pytest.mark.parametrize("kind", ["T1", "T2R"])
def test_t1_t2r_x_pts_match_compiled_register(monkeypatch, tmp_path, kind, step):
    if kind == "T1":
        from qicklab.experiments.t1 import T1FF as Exp
        from qicklab.experiments.t1 import T1Program as Prog
    else:
        from qicklab.experiments.t2_ramsey import T2R as Exp
        from qicklab.experiments.t2_ramsey import T2RProgram as Prog

    seen = []
    _stub_acquire(monkeypatch, Prog, seen)
    cfg = _cfg(_base(), start=0, step=step, expts=EXPTS, phase_step=0)
    exp = Exp(
        soc=None, soccfg=capture.FakeSocCfg("A"), path=kind, outerFolder=str(tmp_path), cfg=cfg
    )
    data = exp.acquire()
    x = np.asarray(data["data"]["x_pts"])

    (prog,) = seen
    inc = _wait_increment(prog)
    assert inc == round(step * F_TIME)
    np.testing.assert_allclose(x, inc * np.arange(EXPTS) / F_TIME, rtol=1e-12, atol=0)
    # the old axis was the unquantised step; at small steps it misses by several percent
    old = prog.get_expt_pts()
    rel = inc / (step * F_TIME) - 1
    np.testing.assert_allclose(x[1:] / old[1:] - 1, rel, atol=1e-12)
    if step <= 0.05:
        assert abs(rel) > 0.02
    assert exp.cfg["step"] == step  # cfg untouched


@pytest.mark.parametrize("n", [1, 3])
@pytest.mark.parametrize("step", [0.05, None])
def test_t2e_x_pts_match_compiled_register(monkeypatch, tmp_path, n, step):
    """Unquantised step: x_pts is (n + 1) * the realised segment; a recipe step from
    quantised_t2e_step: unchanged from i * step."""
    from qicklab.experiments.t2_echo import T2EMUX, T2EProgram, quantised_t2e_step

    soccfg = capture.FakeSocCfg("A")
    if step is None:
        _, step = quantised_t2e_step(soccfg, 20, EXPTS, n)
    seen = []
    _stub_acquire(monkeypatch, T2EProgram, seen)
    cfg = _cfg(_base(), start=0, step=step, expts=EXPTS, num_pi_pulses=n)
    exp = T2EMUX(soc=None, soccfg=soccfg, path="T2E", outerFolder=str(tmp_path), cfg=cfg)
    x = np.asarray(exp.acquire()["data"]["x_pts"])

    (prog,) = seen
    inc = _wait_increment(prog)
    np.testing.assert_allclose(x, (n + 1) * inc * np.arange(EXPTS) / F_TIME, rtol=1e-12, atol=0)
    if step == 0.05:
        np.testing.assert_allclose(x, prog.get_expt_pts(), rtol=0.08)
    else:  # already on the cycle grid: start + i * step, bit for bit
        np.testing.assert_array_equal(x, prog.get_expt_pts())
