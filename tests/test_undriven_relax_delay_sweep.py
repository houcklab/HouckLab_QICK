"""run_undriven_single_shot's relax_delay sweep: order, per-point cfg, plot only on the last."""

import numpy as np
import pytest

from qicklab.runs import recipes as R
from qicklab.runs import single_shot


class _Ctx:
    outerFolder = soc = soccfg = yoko = None

    def __init__(self):
        self.overrides = []

    def working_config(self, overrides=None):
        self.overrides.append(dict(overrides or {}))
        return {"relax_delay": 300, **(overrides or {})}


class _FakeUSS:
    def __init__(self, cfg=None, **_):
        self.cfg = cfg

    @staticmethod
    def acquire(inst):
        d = {
            "read_indices": np.asarray([0]),
            "scheduled_rep_period_us": inst.cfg["relax_delay"] + 5.0,
            "n_blobs0": 2,
        }
        for name in single_shot._SUMMARY_RATES:
            d[f"ts_{name}0"] = 100.0
        return {"config": inst.cfg, "data": d}


@pytest.fixture
def fake(monkeypatch):
    shown = []
    monkeypatch.setattr(single_shot, "UndrivenSingleShot", _FakeUSS)
    monkeypatch.setattr(
        single_shot, "finish", lambda cls, inst, data, plotDisp: shown.append(plotDisp)
    )
    return shown


def test_sweep_runs_each_delay_inside_each_pass(fake, capsys):
    ctx = _Ctx()
    (us,) = R.undriven_single_shot(relax_delay_sweep=(20, 100), repeat=2).arguments({})
    runs = single_shot.run_undriven_single_shot(ctx, us)
    assert [r["config"]["relax_delay"] for r in runs] == [20.0, 100.0, 20.0, 100.0]
    assert fake == [False, False, False, True]  # only the very last on screen
    assert "relax_delay sweep summary" in capsys.readouterr().out


def test_no_sweep_is_the_single_relax_delay(fake):
    ctx = _Ctx()
    (us,) = R.undriven_single_shot(relax_delay=50, repeat=2).arguments({})
    assert us["relax_delay_sweep"] is None
    runs = single_shot.run_undriven_single_shot(ctx, us)
    assert [r["config"]["relax_delay"] for r in runs] == [50, 50]
    assert fake == [False, True]


@pytest.mark.parametrize("bad", [(), (10, -1), (float("nan"),)])
def test_bad_sweep_raises_before_acquiring(fake, bad):
    ctx = _Ctx()
    with pytest.raises(ValueError, match="relax_delay_sweep"):
        single_shot.run_undriven_single_shot(ctx, {"relax_delay_sweep": bad})
    assert ctx.overrides == [] and fake == []
