import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mActiveResetProbe


def _blobs(seed=0, n=4000):
    rng = np.random.default_rng(seed)
    lg = rng.normal(-3600, 1500, n).astype(np.int64)
    ug = rng.normal(-900, 1500, n).astype(np.int64)
    le = rng.normal(-3300, 1500, n).astype(np.int64)
    ue = rng.normal(17100, 1500, n).astype(np.int64)
    return lg, ug, le, ue


def _make_fake_probe(legacy_bad, rot_bad, e_bad=0.30):
    lg, ug, le, ue = _blobs()

    class FakeProbe:
        def __init__(self, **kw):
            self.raw_shots = {"ground": {"lower": lg, "upper": ug},
                              "excited": {"lower": le, "upper": ue}}

        def acquire(self, **kw):
            return {"data": {
                "supported": True,
                "recommended": {"oper": "upper", "threshold_raw": 8000,
                                "ground_below": True},
                "results": {"ground": {"raw_lower": -3600, "raw_upper": -900},
                            "excited": {"raw_lower": -3300, "raw_upper": 17100}},
                "raw_assignment_fidelity": 0.85,
                "raw_assignment_shots": 4000,
                "raw_assignment_errors": {"p_e_given_g": 0.06,
                                          "p_g_given_e": 0.20},
                "reset_threshold_tuning": {"pi_efficiency": 0.8}}}

        def _residual_at(self, res_phase, threshold_raw, ground_below, shots,
                         oper=None, rot_reset=None):
            bad = rot_bad if rot_reset else legacy_bad
            e = e_bad if bad else 0.05
            return {"baseline": 0.98, "reset_ground": 0.03, "reset_excited": e,
                    "reset": e, "works": not bad}

    return FakeProbe


def _run(legacy_bad, rot_bad, e_bad=0.30, **kw):
    saved = mActiveResetProbe.ActiveResetProbe
    mActiveResetProbe.ActiveResetProbe = _make_fake_probe(legacy_bad, rot_bad, e_bad)
    try:
        return ar.probe_reset_params(None, None, {"reset_max_iters": 3,
                                                  "res_phase": 0.0},
                                     path="q4", outer_folder="", shots=2000, **kw)
    finally:
        mActiveResetProbe.ActiveResetProbe = saved


def test_both_schemes_valid_selects_rotated():
    rec = _run(legacy_bad=False, rot_bad=False)
    assert rec is not None and rec["use"] == "rot"
    assert rec.get("rot_reset")
    assert rec.get("verdict")


def test_legacy_failure_falls_through_to_a_validated_rotated_reset():
    rec = _run(legacy_bad=True, rot_bad=False)
    assert rec is not None, ("a legacy validation failure must not abort the probe "
                             "before the rotated scheme gets its own chance")
    assert rec["use"] == "rot"
    assert rec.get("rot_reset")
    assert "verdict" not in rec


def test_both_above_bar_but_functional_runs_best_effort():
    rec = _run(legacy_bad=True, rot_bad=True)
    assert rec is not None, ("a functional-but-mediocre reset must run best-effort "
                             "by default, never silently become 2 ms passive")
    assert rec.get("degraded") is True
    assert rec["use"] in ("rot", "legacy")
    if rec["use"] == "rot":
        assert rec.get("rot_reset")


def test_strict_policy_still_goes_passive_when_both_fail_the_bar():
    rec = _run(legacy_bad=True, rot_bad=True, gate_policy="strict")
    assert rec is None


def test_a_truly_nonfunctional_reset_goes_passive_even_in_best_effort():
    rec = _run(legacy_bad=True, rot_bad=True, e_bad=0.60)
    assert rec is None


def test_rot_failure_with_valid_legacy_keeps_legacy():
    rec = _run(legacy_bad=False, rot_bad=True, allow_legacy_result=True)
    assert rec is not None and rec["use"] == "legacy"
    assert "rot_reset" not in rec


def test_rot_failure_with_valid_legacy_never_returns_legacy_by_default():
    rec = _run(legacy_bad=False, rot_bad=True)
    assert rec is None or (rec["use"] == "rot" and rec.get("rot_reset"))
