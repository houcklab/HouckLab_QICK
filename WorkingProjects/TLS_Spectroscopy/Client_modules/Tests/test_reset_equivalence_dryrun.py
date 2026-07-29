import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_reset_equivalence.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def out():
    env = dict(os.environ, PYTHONPATH=REPO)
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, f"exit {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def test_all_stages_ran(out):
    for marker in ("STAGE 0", "STAGE 1", "STAGE 2", "STAGE 3", "VERDICT"):
        assert marker in out, f"{marker} missing"
    assert "no usable calibration" not in out


def test_all_calibration_rounds_ran(out):
    assert len(re.findall(r"calibration round \d+/6", out)) == 6
    assert "unusable -- skipping" not in out


def test_equivalence_passes_on_the_simulated_instrument(out):
    assert out.count("-> PASS") >= 2
    assert "[PASS] aligned equivalence" in out


def test_round_means_are_small(out):
    for m in re.finditer(r"combined ([+-][\d.]+) \+/- [\d.]+ over \d+", out):
        assert abs(float(m.group(1))) < 0.02, m.group(0)


def test_superiority_at_offset_passes(out):
    assert "[PASS] superiority" in out
    m = re.search(r"old - rot2 = \+[\d.]+ \+/- [\d.]+ \(([+-][\d.]+) sigma", out)
    assert m and float(m.group(1)) >= 3.0


def test_iteration_sweep_tracks_model(out):
    assert "[PASS] both schemes follow the modelled convergence" in out
    m = re.search(r"worst DIFFERENTIAL deviation \(rot vs old\): ([\d.]+)", out)
    assert m, "stage 3 must report the differential deviation"
    assert float(m.group(1)) < 0.05


def test_overall_verdict_is_replacement_ready(out):
    assert "Part A passes" in out


def test_phase_restored_after_offset_stage(out):
    assert "restored res_phase" in out


def test_glitched_rows_are_detected_and_excluded(out):
    assert "glitch, excluded" in out
    assert re.search(r"kept \d+/\d+ repeats \(\d+ glitch-excluded\)", out)


def test_poisoned_calibration_is_caught_and_reprobed(out):
    assert "disagrees with a fresh reference measurement" in out
    assert "re-probing" in out


def test_stage3_uses_a_live_efficiency(out):
    m = re.search(r"probe eta ([\d.]+) -> live eta ([\d.]+)", out)
    assert m, "stage 3 must report the live efficiency it solved for"
    assert 0.05 <= float(m.group(2)) <= 1.0
