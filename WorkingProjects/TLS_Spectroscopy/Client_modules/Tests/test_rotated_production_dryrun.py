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
    assert "every feedback program carried the rotated reset profile" in out


def test_failed_rotation_goes_passive_instead_of_legacy(out):
    m = re.search(r"programs built after failed rotation: (\d+), passive: (\d+), "
                  r"with rot_reset: (\d+)", out)
    assert m and int(m.group(1)) > 0
    assert int(m.group(1)) == int(m.group(2)) and int(m.group(3)) == 0
    assert "no program silently reverted to the legacy reset" in out


def test_all_scenarios_complete_the_full_production_pipeline(out):
    assert out.count("Done. One-stop 3-point CSV") == 3
    assert "FAILED" not in out


def test_wall_clock_series_reprobes_and_stays_rotated(out):
    assert "SCENARIO 3" in out
    assert "re-probing between passes" in out
    assert "ROTATED reset revalidated" in out
    m = re.search(r"probe calls: (\d+) \(1 initial \+ re-probes\), programs "
                  r"with rot_reset: (\d+)/(\d+)", out)
    assert m and int(m.group(1)) >= 3
    assert int(m.group(2)) == int(m.group(3)) > 0
