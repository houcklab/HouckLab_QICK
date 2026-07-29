import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_reset_rotation_drift.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))

ROW = re.compile(
    r"^\s*(\d+)\s+(\d+\.\d)\s+([+-]\d+\.\d{2})\s+(\d+)\s+(\d+)"
    r"\s+(-?\d+\.\d{4})\s+(-?\d+\.\d{4})\s+(-?\d+\.\d{4})\s+(-?\d+\.\d{4})\s*$",
    re.M)
ARM = re.compile(r"arm (\w+)\s+mean\|e>\s+(-?[\d.]+)\s+worst\|e>\s+(-?[\d.]+)")


@pytest.fixture(scope="module", params=[7, 3], ids=["seed7", "seed3"])
def out(request):
    env = dict(os.environ, PYTHONPATH=REPO, RESET_SIM_SEED=str(request.param))
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, (
        f"exit {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def _rows(out):
    return list(ROW.finditer(out))


def _arms(out):
    d = {}
    for m in ARM.finditer(out):
        d[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return d


def test_enough_cycles_ran(out):
    assert len(_rows(out)) >= 24
    assert "too many refit failures" not in out


def test_drift_was_actually_exercised(out):
    angles = [float(m.group(3)) for m in _rows(out)]
    span = max(angles) - min(angles)
    assert span >= 18.0, f"angle span only {span:.2f} deg ({min(angles)}..{max(angles)})"


def test_all_three_criteria_pass(out):
    assert out.count("[PASS]") == 3
    assert "[FAIL]" not in out
    assert "Part C passes." in out


def test_tracked_rotated_matches_or_beats_stale_legacy_on_values(out):
    arms = _arms(out)
    assert set(arms) == {"legacy_fixed", "legacy_retuned", "rot_fixed",
                         "rot_tracked"}, arms
    assert arms["rot_tracked"][0] <= arms["legacy_fixed"][0] + 0.005, arms
    assert arms["rot_tracked"][1] < arms["legacy_fixed"][1], arms


def test_drift_genuinely_degraded_the_stale_legacy_arm(out):
    arms = _arms(out)
    mean_lf, worst_lf = arms["legacy_fixed"]
    assert worst_lf - mean_lf > 0.01, (
        f"legacy_fixed worst {worst_lf:.4f} barely exceeds its mean {mean_lf:.4f}; "
        f"the simulated drift never actually hurt the stale arm, so the run proves "
        f"nothing about drift protection")


def test_glitched_cycles_are_detected_and_excluded(out):
    assert "glitch, excluded" in out
    m = re.search(r"(\d+) cycles kept in [\d.]+ min \((\d+) glitch-excluded", out)
    assert m, "analysis must report kept and glitch-excluded counts"
    assert int(m.group(1)) >= 24
    assert int(m.group(2)) >= 1
