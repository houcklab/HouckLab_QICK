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


def _n_dc(out):
    return int(re.search(r"dc 0\.\.\d+ DAC \((\d+) freq-uniform points\)", out).group(1))


def test_span_is_400_mhz(out):
    m = re.search(r"400 MHz span: f ([\d.]+) -> ([\d.]+) GHz", out)
    assert m and abs((float(m.group(1)) - float(m.group(2))) - 0.400) < 0.002
    assert 380 <= _n_dc(out) <= 420


def test_per_dc_structure_ran_to_completion(out):
    n = _n_dc(out)
    m = re.search(r"per-dc pass complete: .+ \([\d.]+ s/dc\); (\d+)/(\d+) valid", out)
    assert m and int(m.group(2)) == n
    assert int(m.group(1)) >= n * 0.8
    assert "ss cal per dc" in out and "3-point T1 per dc" in out
    assert "transmission" not in out.lower()


def test_outputs_written_with_per_dc_columns(out):
    m = re.search(r"per-dc CSV: (\S+)", out)
    assert m and os.path.exists(m.group(1))
    with open(m.group(1)) as f:
        rows = f.read().strip().splitlines()
    assert len(rows) == _n_dc(out) + 1
    for col in ("T1_3pt_us", "ss_F", "ss_threshold", "ss_theta",
                "t_ss_s", "t_t1_s", "freq_ghz"):
        assert col in rows[0]


def test_h5_holds_every_calibration(out):
    import h5py
    m = re.search(r"raw-data h5: (\S+)", out)
    assert m and os.path.exists(m.group(1))
    n = _n_dc(out)
    with h5py.File(m.group(1), "r") as f:
        for name in ("I_0", "Q_0", "I_1", "Q_1"):
            assert f[f"ss_cal/{name}"].shape[0] == n
            assert f[f"ss_cal/{name}"].shape[1] >= 100
        for name in ("ss_F", "ss_threshold", "ss_theta"):
            assert f[f"ss_cal/{name}"].shape[0] == n
        assert f["t1/T1_3pt_us"].shape[0] == n
        assert f["timing/t_ss_s"].shape[0] == n
        assert f["timing/t_t1_s"].shape[0] == n
        assert bool(f["reset"].attrs["rotated_in_use"]) is True


def test_timing_summary_reports_the_split(out):
    assert re.search(r"ss cal per dc\s+[\d.]+ s median", out)
    assert re.search(r"3-point T1 per dc\s+[\d.]+ s median", out)
    assert "passes/hour" in out
