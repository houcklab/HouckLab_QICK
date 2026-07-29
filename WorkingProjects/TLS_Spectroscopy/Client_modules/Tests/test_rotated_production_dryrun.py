import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_rotated_production.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module", params=[7, 3], ids=["seed7", "seed3"])
def out(request):
    env = dict(os.environ, PYTHONPATH=REPO, RESET_SIM_SEED=str(request.param))
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, f"exit {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def test_rotated_reset_reaches_every_production_program(out):
    m = re.search(r"programs built: (\d+), with rot_reset: (\d+)", out)
    assert m and int(m.group(1)) > 0 and int(m.group(1)) == int(m.group(2))
    assert "ROTATED reset selected (probe-validated)" in out
    assert "legacy fallback present" in out


def test_the_flag_reverts_to_legacy_with_no_other_change(out):
    ms = re.findall(r"programs built: (\d+), with rot_reset: (\d+)", out)
    assert len(ms) == 2
    assert int(ms[1][0]) > 0 and int(ms[1][1]) == 0
    assert "USE_ROTATED_RESET=False -- running the LEGACY reset by request." in out


def test_both_scenarios_complete_the_full_production_pipeline(out):
    assert out.count("Done. One-stop 3-point CSV") == 2
    assert "FAILED" not in out
