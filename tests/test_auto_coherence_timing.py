"""AutoCoherence timing checks against the measured T1 (F65, warn only).

The relax delays (3500 us by default) and the sweep windows were never compared with the
T1 the pipeline measures: on CSTQ03 (T1 ~ 50 us) every shot waits 70 T1. After the first
usable T1 fit the run now logs relax/T1 and window/T1 and warns outside the ranges in
docs/experiments/auto_coherence.md#timing-checks. Nothing it measures changes. No hardware:
the stage runs on a fake T1FF that carries a synthetic fit.
"""

import copy
import math
import os

import numpy as np
import pytest

from tests.regression import capture

# the legacy CSTQ03 runner's AutoCoherence overrides that matter here (runners/CSTQ03_BFC.py,
# deleted in phase 5b; STEP["auto_coherence"] in runners/CSTQ03_session.py carries them)
CSTQ03 = {"T1_step": 5, "T2_step": 0.1, "T2_expts": 401, "T2E_max_us": 500}


def _params(**over):
    import qicklab.runs.auto_coherence as ac

    return dict(ac.AUTO_COHERENCE_PARAMS, **over)


def _warnings(lines):
    return [ln for ln in lines if "WARNING" in ln]


@pytest.mark.parametrize(
    "fit, usable",
    [
        ({"ok": True, "T": 50.0, "T_err": 2.0}, (50.0, 2.0)),
        ({"ok": True, "T": 50.0, "T_err": 25.0}, (50.0, 25.0)),  # exactly 0.5: kept
        ({"ok": True, "T": 50.0, "T_err": 26.0}, None),  # T1_err / T1 > 0.5
        ({"ok": False, "T": 50.0, "T_err": 2.0}, None),
        ({"ok": True, "T": np.nan, "T_err": 2.0}, None),
        ({"ok": True, "T": 50.0, "T_err": np.inf}, None),
        ({"ok": False, "error": "display raised"}, None),  # guarded-display stub
        (None, None),  # display never set self.fit
    ],
)
def test_usable_t1_fit(fit, usable):
    import qicklab.runs.auto_coherence as ac

    assert ac._usable_t1_fit(fit) == usable


def test_cstq03_settings_warn_relax_and_t2e_window():
    """T1 = 50 us: relax 3500 us = 70 T1 on all three stages, T2E window 499 us = 10 T1;
    the T1 window 5 x 60 = 300 us = 6 T1 is inside 3-10 T1."""
    import qicklab.runs.auto_coherence as ac

    params = _params(**CSTQ03)
    before = copy.deepcopy(params)
    lines = ac._timing_checks(capture.FakeSocCfg("A"), params, 50.0, "test")
    assert params == before  # warn only
    warns = _warnings(lines)
    assert len(warns) == 4
    for key in ("T1_relax_delay", "T2_relax_delay", "T2E_relax_delay"):
        (w,) = [w for w in warns if key in w]
        assert "70.0 T1 > 20 T1" in w
    (w,) = [w for w in warns if "T2E window" in w]
    assert "10.0 T1 > 6 T1" in w
    assert not [w for w in warns if "T1 window" in w]
    assert "    T1 window        = 300 us = 6.0 T1" in lines
    assert "    T2R window       = 40.1 us = 0.40 x 2 T1" in lines
    # T2E window = quantised step x expts: 534 cycles x 2 waits per point at 430.08 MHz
    (t2e,) = [ln for ln in lines if ln.startswith("    T2E window")]
    assert f"{2 * 534 / 430.08 * 201:.1f} us" in t2e


def test_defaults_on_long_t1_warn_short_relax_and_window():
    """T1 = 1000 us: relax 3500 us = 3.5 T1 (< 5 T1) and T1 window 2400 us = 2.4 T1 (< 3)."""
    import qicklab.runs.auto_coherence as ac

    lines = ac._timing_checks(capture.FakeSocCfg("A"), _params(), 1000.0, "test")
    warns = _warnings(lines)
    assert len(warns) == 4
    assert sum("3.5 T1 < 5 T1" in w for w in warns) == 3
    assert f"{math.exp(-3.5):.1%}" in warns[0]  # residual excited population after relax
    (w,) = [w for w in warns if "T1 window" in w]
    assert "2.4 T1 < 3 T1" in w


def test_defaults_on_short_t1_warn_long_t1_window():
    """Bare defaults at T1 = 50 us: T1 window 40 x 60 = 2400 us = 48 T1 (> 10 T1) on top of
    the three relax warnings; the default T2E window (199 us = 4 T1) does not warn."""
    import qicklab.runs.auto_coherence as ac

    lines = ac._timing_checks(capture.FakeSocCfg("A"), _params(), 50.0, "test")
    warns = _warnings(lines)
    assert len(warns) == 4
    assert sum("70.0 T1 > 20 T1" in w for w in warns) == 3
    (w,) = [w for w in warns if "T1 window" in w]
    assert "48.0 T1 > 10 T1" in w
    assert "    T1 window        = 2400 us = 48.0 T1" in lines
    assert not [w for w in warns if "T2E window" in w]


@pytest.mark.parametrize("n", [1, 3])
def test_t2e_window_uses_forced_step_when_quantised_step_is_zero(n):
    """T2E_expts so large that quantised_t2e_step gives int_steps = 0: Stage 6 forces one
    step of (n + 1) tProc cycles, and the check uses that same step x T2E_expts."""
    import qicklab.runs.auto_coherence as ac
    from qicklab.experiments.t2_echo import quantised_t2e_step

    soccfg = capture.FakeSocCfg("A")
    expts = 100_000
    assert quantised_t2e_step(soccfg, 200, expts, n)[0] == 0
    params = _params(
        T1_relax_delay=500,
        T2_relax_delay=500,
        T2E_relax_delay=500,
        T1_step=5,
        T2E_expts=expts,
        T2E_num_pi_pulses=n,
    )
    lines = ac._timing_checks(soccfg, params, 50.0, "test")
    window = (n + 1) / 430.08 * expts  # one step = n + 1 cycles at 430.08 MHz
    (t2e,) = [ln for ln in lines if ln.startswith("    T2E window")]
    assert t2e == f"    T2E window       = {window:.1f} us = {window / 50.0:.1f} T1"
    (w,) = _warnings(lines)  # 465.0 us = 9.3 T1 (n = 1), 930.1 us = 18.6 T1 (n = 3)
    assert f"T2E window = {window / 50.0:.1f} T1 > 6 T1" in w


def test_in_range_settings_do_not_warn():
    import qicklab.runs.auto_coherence as ac

    params = _params(
        T1_relax_delay=500, T2_relax_delay=500, T2E_relax_delay=500, T1_step=5, T2E_max_us=200
    )
    lines = ac._timing_checks(capture.FakeSocCfg("A"), params, 50.0, "test")
    assert _warnings(lines) == []
    assert "    T1_relax_delay   = 500 us = 10.0 T1" in lines


@pytest.mark.parametrize("n", [0, 2.0, -1])
def test_bad_num_pi_pulses_does_not_raise_early(n):
    """An invalid T2E_num_pi_pulses must still fail in Stage 6, not in the T1 check
    (n = -1 would otherwise divide by zero in the step quantisation)."""
    import qicklab.runs.auto_coherence as ac

    lines = ac._timing_checks(capture.FakeSocCfg("A"), _params(T2E_num_pi_pulses=n), 50.0, "test")
    assert any("T2E window       : not checked" in ln for ln in lines)


def _run_t1_stage(monkeypatch, tmp_path, fits, **over):
    import qicklab.runs.auto_coherence as ac

    queue = list(fits)
    made = []

    class FakeT1FF:
        def __init__(self, path, cfg, soc, soccfg, outerFolder):
            self.cfg = cfg
            made.append(self)

        def acquire(self):
            return {}

    def fake_finish(cls, inst, data, **kw):
        fit = queue.pop(0)
        if fit is not None:
            inst.fit = fit
        return None

    monkeypatch.setattr(ac, "T1FF", FakeT1FF)
    monkeypatch.setattr(ac, "finish", fake_finish)
    monkeypatch.setattr(ac.time, "sleep", lambda s: None)
    params = _params(**{**CSTQ03, "T1_repetitions": len(fits), **over})
    before = copy.deepcopy(params)
    log = []
    ac._stage_run_t1(
        soc=type("Soc", (), {"reset_gens": lambda self: None})(),
        soccfg=capture.FakeSocCfg("A"),
        cfg={"reps": 3, "qubit_ch": 1},
        auto_folder=str(tmp_path) + "/",
        qubit_freq=4000.0,
        pi_gain=1200,
        sigma=0.05,
        flattop_length=None,
        qubit_readout=1,
        params=params,
        log=log,
    )
    assert params == before
    # the T1 runs themselves are unchanged by the check
    assert [m.cfg["relax_delay"] for m in made] == [3500] * len(fits)
    assert [m.cfg["step"] for m in made] == [5] * len(fits)
    return log


def test_t1_stage_checks_once_on_first_usable_fit(monkeypatch, tmp_path):
    fits = [
        {"ok": False, "error": "bound"},
        {"ok": True, "T": 50.0, "T_err": 40.0},  # T1_err / T1 = 0.8: skipped
        {"ok": True, "T": 50.0, "T_err": 2.0},
        {"ok": True, "T": 500.0, "T_err": 2.0},  # later fits do not re-run the check
    ]
    log = _run_t1_stage(monkeypatch, tmp_path, fits)
    (head,) = [ln for ln in log if "Timing check" in ln]
    assert head == "  Timing check vs T1 = 50.0 us (T1 run 3 fit, +/- 2.0 us):"
    assert len(_warnings(log)) == 4
    # the check sits after run 3 and before run 4
    assert log.index("  T1 run 3/4 saved.") < log.index(head) < log.index("  T1 run 4/4 saved.")


@pytest.mark.parametrize(
    "over, error",
    [({"T2E_expts": 0}, "ZeroDivisionError"), ({"T2E_max_us": None}, "TypeError")],
)
def test_t1_stage_survives_a_failing_timing_check(monkeypatch, tmp_path, over, error):
    """The check is warn only: a T2E parameter it cannot evaluate is logged in Stage 4 and
    the T1 runs carry on (it still fails in Stage 6), instead of aborting before T2R."""
    import qicklab.runs.auto_coherence as ac

    with pytest.raises(Exception) as raised:  # the unguarded check does raise
        ac._timing_checks(capture.FakeSocCfg("A"), _params(**{**CSTQ03, **over}), 50.0, "t")
    assert type(raised.value).__name__ == error
    fits = [{"ok": True, "T": 50.0, "T_err": 2.0}, {"ok": True, "T": 50.0, "T_err": 2.0}]
    log = _run_t1_stage(monkeypatch, tmp_path, fits, **over)
    failed = [ln for ln in log if "Timing check failed" in ln]
    assert len(failed) == 1  # attempted once, not on every later run
    assert failed[0].startswith(f"  Timing check failed (warn only, run continues): {error}(")
    assert log.index("  T1 run 1/2 saved.") < log.index(failed[0])
    assert "  T1 run 2/2 saved." in log
    assert not any("Timing check skipped" in ln for ln in log)


def test_t1_stage_without_usable_fit_logs_skip(monkeypatch, tmp_path):
    log = _run_t1_stage(monkeypatch, tmp_path, [None, {"ok": True, "T": np.nan, "T_err": 1.0}])
    assert log[-1].startswith("  Timing check skipped: no T1 fit")
    assert _warnings(log) == []


def _preflight_log(monkeypatch, tmp_path, **auto):
    """Run log of an AutoCoherence run whose Stage 1 is stubbed to abort at once."""
    import qicklab.runs.auto_coherence as ac

    class Stop(Exception):
        pass

    def stop(**kw):
        raise Stop

    monkeypatch.setattr(ac, "_stage_sweet_spot_search", stop)
    qubit_params = {
        "1": {
            "Readout": {"Frequency": 7000.0, "Gain": 1000},
            "Qubit": {"Frequency": 4000.0, "Gain": 1200, "sigma": 0.05, "flattop_length": None},
        }
    }
    with pytest.raises(Stop):
        ac._run_auto_coherence(
            soc=None,
            soccfg=capture.FakeSocCfg("A"),
            config={"reps": 3},
            outerFolder=str(tmp_path),
            qubit_readout=1,
            qubit_params=qubit_params,
            auto_params={**CSTQ03, **auto},
        )
    run_dir = os.path.join(tmp_path, "AutoCoherence")
    (run,) = os.listdir(run_dir)
    (txt,) = [f for f in os.listdir(os.path.join(run_dir, run)) if f.endswith(".txt")]
    with open(os.path.join(run_dir, run, txt), encoding="utf-8") as fh:
        return fh.read().split("Run log")[1]


@pytest.mark.parametrize("t1_expected", [50.0, None, 0, "fifty"])
def test_preflight_runs_before_stage_1(monkeypatch, tmp_path, t1_expected):
    log = _preflight_log(monkeypatch, tmp_path, T1_expected_us=t1_expected)
    if t1_expected is None:
        assert "Pre-flight" not in log
        assert "Timing check" not in log
    elif t1_expected == 0:
        assert "Pre-flight skipped: T1_expected_us = 0 is not > 0." in log
    elif t1_expected == "fifty":  # not a number: skipped, not raised before the summary
        assert "Pre-flight skipped: T1_expected_us = 'fifty' is not > 0." in log
    else:
        assert "Timing check vs T1 = 50.0 us (T1_expected_us):" in log
        assert log.count("WARNING") == 4
        # before any stage ran
        assert log.index("Pre-flight") < log.index("Run aborted after stage 'start'")


def test_preflight_survives_a_failing_timing_check(monkeypatch, tmp_path):
    """A pre-flight check that cannot be evaluated is logged and Stage 1 still starts."""
    log = _preflight_log(monkeypatch, tmp_path, T1_expected_us=50.0, T2E_expts=0)
    line = "  Timing check failed (warn only, run continues): ZeroDivisionError("
    assert line in log
    assert log.index("Pre-flight") < log.index(line) < log.index("Run aborted after stage 'start'")
