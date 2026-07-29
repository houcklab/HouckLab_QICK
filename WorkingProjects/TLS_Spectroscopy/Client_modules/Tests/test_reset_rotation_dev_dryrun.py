"""Assertions over the ResetRotationDev dry run.

Running the script end to end only proves it does not crash.  Three of the four
bugs that cost hardware runs did not crash -- they produced confident, wrong
numbers.  So these tests check the VALUES, against a simulated instrument whose
true residuals are known by construction.
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_reset_rotation_dev.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def out():
    env = dict(os.environ, PYTHONPATH=REPO)
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, f"dry run exited {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def _stage2(out):
    rows = {}
    for m in re.finditer(
            r"^\s+(old|rot2|rot3)\s*:\s*residual from \|g>\s+([-\d.]+)\s+"
            r"from \|e>\s+([-\d.]+)", out, re.M):
        rows[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return rows


def test_every_stage_actually_ran(out):
    for stage in ("STAGE 0", "STAGE 1", "STAGE 2", "STAGE 3", "STAGE 4"):
        assert stage in out, f"{stage} missing"
    for skipped in ("no rotation fit -- skipping",
                    "missing a fit or a recommendation -- skipping",
                    "probe exposed no raw_shots"):
        assert skipped not in out, (
            f"a stage skipped instead of running: {skipped!r}.  A skip is not a pass -- "
            f"this is how the raw_shots bug hid for a whole hardware run.")


def test_stage0_arithmetic_all_exact(out):
    assert "MISMATCH" not in out
    assert re.search(r"all \d+ cases exact", out)


def test_stage1_uses_the_probes_measured_efficiency_not_the_fallback(out):
    m = re.search(r"eta=([\d.]+) \(measured by the probe, not assumed\)", out)
    assert m, "stage 1 did not report which efficiency it used"
    eta = float(m.group(1))
    assert eta == pytest.approx(0.74, abs=0.005), (
        f"stage 1 used eta={eta}, but the simulated probe reports 0.74.  Reading it "
        f"from the wrong nesting level silently substitutes PI_EFFICIENCY_GUESS.")


def test_stage2_produced_all_three_arms(out):
    rows = _stage2(out)
    assert set(rows) == {"old", "rot2", "rot3"}, rows


def test_stage2_residuals_are_physically_plausible(out):
    """The simulated reset genuinely resets, so residuals must be small.

    ~0.6 for every arm is the signature of host-scale thresholds applied to raw
    accumulator buffers; 0.0 for every arm is the signature of a comparison that
    can never be true.  Both were real bugs and both land outside this band.
    """
    rows = _stage2(out)
    for arm, (rg, re_) in rows.items():
        for label, v in (("|g>", rg), ("|e>", re_)):
            assert 0.005 < v < 0.35, (
                f"{arm} residual from {label} is {v:.4f}, outside the plausible band "
                f"for a working reset on the simulated instrument")


def test_stage2_matches_the_modelled_residual(out):
    """Closes the loop: the simulator applies the same chain the analysis models,
    so the measured residual must track the prediction, not merely be small."""
    rows = _stage2(out)
    m = re.search(r"rotated 2-zone\s+([\d.]+)", out)
    assert m
    predicted = float(m.group(1))
    measured_worst = max(rows["rot2"])
    assert measured_worst < predicted * 1.5, (
        f"rot2 measured worst {measured_worst:.4f} vs predicted {predicted:.4f}")


def test_stage2_arms_are_not_all_identical(out):
    """If every arm returns the same number the measurement is not responding to
    the reset at all -- which is exactly what the units bug looked like."""
    rows = _stage2(out)
    worsts = [max(v) for v in rows.values()]
    assert max(worsts) - min(worsts) > 1e-6, worsts


def test_stage3_reports_paired_significance(out):
    assert "sigma paired" in out
    assert len(re.findall(r"sigma paired", out)) >= 3


def test_reference_separation_is_reported_and_sane(out):
    m = re.search(r"reference separation (\d+) raw units", out)
    assert m, "stage 2 must report the |g>/|e> reference separation"
    assert 5000 < int(m.group(1)) < 60000
