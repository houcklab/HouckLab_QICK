import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_step6_timing.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def out():
    env = dict(os.environ, PYTHONPATH=REPO)
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, f"exit {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def test_production_vector_is_computed_from_the_real_flux_fit(out):
    m = re.search(r"production dc vector: (\d+) points", out)
    assert m and int(m.group(1)) > 100


def test_all_building_blocks_were_measured(out):
    for marker in ("ss cal run 1", "probe + validation", "dc points:",
                   "transmission run 1", "per-dc T1 cost"):
        assert marker in out, f"{marker} missing"


def test_both_scenarios_extrapolated(out):
    assert "SCENARIO A" in out and "SCENARIO B" in out
    assert re.search(r"one pass \(T1 sweep itself\)\s+\S", out)
    m = re.search(r"scenario B is ([\d.]+)x scenario A", out)
    assert m and float(m.group(1)) >= 1.0
    assert "passes/hour" in out


def test_rotated_reset_was_engaged_for_the_timing(out):
    assert "ROTATED reset selected" in out
    assert "fell back to PASSIVE" not in out
