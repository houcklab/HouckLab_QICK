"""T2R virtual detuning (F29): the Ramsey runs advance the second pi/2 pulse's phase.

Before the fix every caller passed phase_step = deg2reg(0, gen_ch=2) with freq_shift 0, so
the fringe frequency was the unknown residual detuning, often ~0, where T2* and f are
strongly correlated and the sign of the detuning is lost. Now phase_step =
deg2reg(360 * f_virt * dt, gen_ch=qubit_ch) with dt the realised step, f_virt defaulting
to 5 fringes over the window, and display reports delta = f_fit - f_virt.
docs/experiments/t2_ramsey.md#virtual-detuning. No hardware: FakeSocCfg + synthetic traces.
"""

import numpy as np
import pytest

from tests.regression import capture
from tests.test_program_timing import _cfg

F_TIME = 430.08  # tProc clock of board A (the lab clock)
DT = 43 / F_TIME  # realised 0.1 us step


def _helper(**cfg):
    from qicklab.experiments.t2_ramsey import ramsey_virtual_detuning

    f_virt = cfg.pop("f_virt_mhz", None)
    base = {"qubit_ch": 1, "step": 0.1, "expts": 201}
    return ramsey_virtual_detuning(capture.FakeSocCfg("A"), base | cfg, f_virt)


@pytest.mark.parametrize(
    ("expts", "f_virt", "phase_step"),
    [
        (100, 0.5000930, 214748365),  # 18 deg/step: 5 fringes over 100 x 0.1 us
        (201, 0.2488025, 106839982),  # AutoCoherence default
        (401, 0.1247115, 53553208),  # CSTQ03 AutoCoherence session
        (5, 1.2502326, 2**29),  # 5 fringes would be 1 turn/step: capped at 1/8 turn
    ],
)
def test_default_is_five_fringes_over_the_realised_window(expts, f_virt, phase_step):
    out = _helper(expts=expts)
    assert out["phase_step"] == phase_step
    assert out["f_virt_mhz"] == pytest.approx(f_virt, abs=1e-6)
    # realised value: exactly the integer register advance over the realised step
    assert out["f_virt_mhz"] == pytest.approx(phase_step / 2**32 / DT, rel=1e-12)
    if expts >= 40:
        assert out["f_virt_mhz"] * expts * DT == pytest.approx(5, rel=1e-8)


def test_explicit_values_and_limits():
    assert _helper(f_virt_mhz=0) == {"f_virt_mhz": 0.0, "phase_step": 0}  # legacy on-resonance
    out = _helper(f_virt_mhz=0.3)
    assert out["f_virt_mhz"] == pytest.approx(0.3, rel=1e-8)
    assert out["phase_step"] == round(0.3 * DT * 2**32)
    for bad in (-0.1, 0.25 / DT, 3.0, 1 / DT):  # 1 / DT: a whole turn, would wrap to 0
        with pytest.raises(ValueError, match="f_virt"):
            _helper(f_virt_mhz=bad)
    assert _helper(f_virt_mhz=0.2499 / DT)["phase_step"] < 2**30  # 31-bit mathi immediate
    with pytest.raises(ValueError, match="shorter than one tProc cycle"):
        _helper(step=0.001)


class _SpySocCfg(capture.FakeSocCfg):
    def __init__(self):
        super().__init__("A")
        self.gen_chs = []

    def deg2reg(self, deg, gen_ch=0, ro_ch=None):
        self.gen_chs.append(gen_ch)
        return super().deg2reg(deg, gen_ch=gen_ch, ro_ch=ro_ch)


def test_run_t2_uses_merged_qubit_ch_and_stores_f_virt(tmp_path, monkeypatch):
    import qicklab.runs.coherence as coherence

    made = []

    class FakeT2R:
        def __init__(self, path, cfg, soc, soccfg, outerFolder):
            made.append(cfg)

        def acquire(self):
            return {}

    class Ctx:
        outerFolder = str(tmp_path) + "/"
        soc = type("Soc", (), {"reset_gens": lambda self: None})()
        soccfg = _SpySocCfg()
        config = {"qubit_ch": 3, "reps": 3}  # not the literal 2 the old code used
        qubit_gain = pi2_gain = 1000
        qubit_frequency_center = 4000.0
        qubit_sigma = 0.05
        qubit_flattop = None

        def working_config(self, extra):
            return dict(self.config) | extra

    monkeypatch.setattr(coherence, "T2R", FakeT2R)
    monkeypatch.setattr(coherence, "finish", lambda *a, **k: None)
    monkeypatch.setattr(coherence.time, "sleep", lambda s: None)
    params = {"repetitions": 1, "T2_step": 0.1, "T2_expts": 100, "T2_reps": 1, "T2_rounds": 1}
    params |= {"relax_delay": 100, "freq_shift": 0.0}
    ctx = Ctx()
    coherence.run_t2(ctx, params)
    (cfg,) = made
    assert ctx.soccfg.gen_chs == [3]
    assert cfg["phase_step"] == 214748365
    assert cfg["f_virt_mhz"] == pytest.approx(0.5000930, abs=1e-6)
    assert cfg["f_ge"] == 4000.0  # pulses stay on f_ge + freq_shift

    made.clear()
    coherence.run_t2(ctx, params | {"f_virt_mhz": 0})
    assert made[0]["phase_step"] == 0 and made[0]["f_virt_mhz"] == 0.0


def test_auto_stage_uses_run_cfg_qubit_ch_and_override(tmp_path, monkeypatch):
    import qicklab.runs.auto_coherence as ac

    made = []

    class FakeT2R:
        def __init__(self, path, cfg, soc, soccfg, outerFolder):
            made.append(cfg)
            self.osc_fit = {"f_report": cfg["f_virt_mhz"] + 0.02}
            self.osc_fit["detuning_mhz"] = 0.02

        def acquire(self):
            return {}

    monkeypatch.setattr(ac, "T2R", FakeT2R)
    monkeypatch.setattr(ac, "finish", lambda *a, **k: None)
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)
    soccfg = _SpySocCfg()
    params = dict(ac.AUTO_COHERENCE_PARAMS, T2_repetitions=1)
    log = []
    kwargs = dict(
        soc=type("Soc", (), {"reset_gens": lambda self: None})(),
        soccfg=soccfg,
        cfg={"reps": 3, "qubit_ch": 5},
        auto_folder=str(tmp_path) + "/",
        qubit_freq=4000.0,
        pi_gain=1200,
        pi2_gain=600,
        sigma=0.05,
        flattop_length=None,
        qubit_readout=1,
        log=log,
    )
    ac._stage_run_t2(params=params, **kwargs)
    assert soccfg.gen_chs == [5]
    assert made[0]["phase_step"] == 106839982  # default 201 x 0.1 us
    assert any("delta = f - f_virt = +0.0200 MHz" in line for line in log)

    ac._stage_run_t2(params=params | {"T2_f_virt_mhz": 0.0}, **kwargs)
    assert made[1]["phase_step"] == 0


def _ramsey_trace(phase_step, delta, t2, x, noise, seed):
    """What T2RProgram produces: point k waits x[k] and the second pulse has phase
    k * phase_step (in 2**-32 turns), so P(e) oscillates as cos(2 pi delta t + phase)."""
    rng = np.random.default_rng(seed)
    k = np.arange(len(x))
    phase = 2 * np.pi * (delta * x + k * phase_step / 2**32)
    p = 0.5 + 0.4 * np.exp(-x / t2) * np.cos(phase)
    i = 1.0 * p + rng.normal(0, noise, len(x))
    q = 0.3 * p + rng.normal(0, noise, len(x))
    return i, q


@pytest.mark.parametrize("delta", [0.0, 0.01, 0.05, -0.05])
def test_display_reports_delta_and_recovers_t2(tmp_path, delta):
    """At residual detuning 0 or 0.01 MHz an on-resonance Ramsey cannot pin T2* (see the
    page); with the default virtual detuning the fit recovers T2* and f_fit - f_virt = delta."""
    from qicklab.core.schedule import realised_wait_axis_us
    from qicklab.experiments.t2_ramsey import T2R
    from qicklab.hardware.board import BaseConfig

    soccfg = capture.FakeSocCfg("A")
    cfg = _cfg(BaseConfig, start=0, step=0.1, expts=201)
    cfg |= _helper(expts=201)
    x = realised_wait_axis_us(soccfg, 0, 0.1, 201)
    i, q = _ramsey_trace(cfg["phase_step"], delta, 8.0, x, 0.01, seed=1)
    exp = T2R(soc=None, soccfg=soccfg, path="T2R", outerFolder=str(tmp_path) + "/", cfg=cfg)
    exp.display({"config": cfg, "data": {"x_pts": x, "avgi": [i[None]], "avgq": [q[None]]}})

    osc = exp.osc_fit
    assert osc["ok"] and osc["mode"] == "1f"
    assert osc["f_virt_mhz"] == cfg["f_virt_mhz"]
    assert osc["detuning_mhz"] == pytest.approx(delta, abs=0.005)
    assert osc["popt"][1] == pytest.approx(8.0, rel=0.1)


def test_display_without_f_virt_reports_no_delta(tmp_path):
    from qicklab.core.schedule import realised_wait_axis_us
    from qicklab.experiments.t2_ramsey import T2R
    from qicklab.hardware.board import BaseConfig

    soccfg = capture.FakeSocCfg("A")
    cfg = _cfg(BaseConfig, start=0, step=0.1, expts=201, phase_step=0)
    x = realised_wait_axis_us(soccfg, 0, 0.1, 201)
    i, q = _ramsey_trace(0, 0.3, 8.0, x, 0.01, seed=2)
    exp = T2R(soc=None, soccfg=soccfg, path="T2R", outerFolder=str(tmp_path) + "/", cfg=cfg)
    exp.display({"config": cfg, "data": {"x_pts": x, "avgi": [i[None]], "avgq": [q[None]]}})
    assert exp.osc_fit["f_virt_mhz"] is None and exp.osc_fit["detuning_mhz"] is None


def test_display_2f_reports_delta_from_the_doublet_centre(tmp_path):
    """A charge-parity doublet sits at f_virt + delta +/- split/2: the f_ge correction is the
    centre, so detuning_mhz = (f1 + f2) / 2 - f_virt, not f1 - f_virt (biased by split/2;
    curve_fit may also return the branches in either order)."""
    from qicklab.core.schedule import realised_wait_axis_us
    from qicklab.experiments.t2_ramsey import T2R
    from qicklab.hardware.board import BaseConfig

    soccfg = capture.FakeSocCfg("A")
    cfg = _cfg(BaseConfig, start=0, step=0.1, expts=201)
    cfg |= _helper(expts=201)
    x = realised_wait_axis_us(soccfg, 0, 0.1, 201)
    delta, split = 0.03, 0.2
    i1, q1 = _ramsey_trace(cfg["phase_step"], delta - split / 2, 8.0, x, 0.0, seed=3)
    i2, q2 = _ramsey_trace(cfg["phase_step"], delta + split / 2, 8.0, x, 0.0, seed=3)
    rng = np.random.default_rng(3)
    i = 0.5 * (i1 + i2) + rng.normal(0, 0.005, len(x))
    q = 0.5 * (q1 + q2) + rng.normal(0, 0.005, len(x))
    exp = T2R(soc=None, soccfg=soccfg, path="T2R", outerFolder=str(tmp_path) + "/", cfg=cfg)
    exp.display({"config": cfg, "data": {"x_pts": x, "avgi": [i[None]], "avgq": [q[None]]}})

    osc = exp.osc_fit
    assert osc["ok"] and osc["mode"] == "2f"
    f1, f2 = osc["popt"][3], osc["popt"][4]
    assert osc["detuning_mhz"] == pytest.approx(0.5 * (f1 + f2) - cfg["f_virt_mhz"], abs=1e-12)
    assert osc["detuning_mhz"] == pytest.approx(delta, abs=0.005)
    assert abs(osc["f_report"] - cfg["f_virt_mhz"] - delta) > 0.05  # f1 alone is off by split/2


def test_auto_stage_log_names_the_2f_centre(tmp_path, monkeypatch):
    import qicklab.runs.auto_coherence as ac

    class FakeT2R:
        def __init__(self, path, cfg, soc, soccfg, outerFolder):
            f_virt = cfg["f_virt_mhz"]
            self.osc_fit = {"mode": "2f", "f_report": f_virt - 0.07, "detuning_mhz": 0.03}

        def acquire(self):
            return {}

    monkeypatch.setattr(ac, "T2R", FakeT2R)
    monkeypatch.setattr(ac, "finish", lambda *a, **k: None)
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)
    log = []
    ac._stage_run_t2(
        params=dict(ac.AUTO_COHERENCE_PARAMS, T2_repetitions=1),
        soc=type("Soc", (), {"reset_gens": lambda self: None})(),
        soccfg=capture.FakeSocCfg("A"),
        cfg={"reps": 3, "qubit_ch": 1},
        auto_folder=str(tmp_path) + "/",
        qubit_freq=4000.0,
        pi_gain=1200,
        pi2_gain=600,
        sigma=0.05,
        flattop_length=None,
        qubit_readout=1,
        log=log,
    )
    (line,) = [ln for ln in log if "f_virt" in ln]
    assert "fringe (f1+f2)/2 = 0.2788 MHz" in line  # 0.2488 + 0.03, not f_report
    assert "delta = (f1+f2)/2 - f_virt = +0.0300 MHz" in line
