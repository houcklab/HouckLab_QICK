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


def test_span_is_400_mhz_and_vector_matches(out):
    m = re.search(r"400 MHz span: f ([\d.]+) -> ([\d.]+) GHz maps to dc 0\.\.(\d+)", out)
    assert m
    assert abs((float(m.group(1)) - float(m.group(2))) - 0.400) < 0.002
    m2 = re.search(r"production dc vector: (\d+) freq-uniform points", out)
    assert m2 and 380 <= int(m2.group(1)) <= 420


def test_transmission_is_gone(out):
    assert "transmission" not in out.lower()


def test_full_pass_measured_directly(out):
    assert re.search(r"full pass: .+ \([\d.]+ s/dc\); \d+/\d+ valid", out)
    assert "passes/hour" in out


def test_standard_outputs_written(out):
    m = re.search(r"one-stop CSV:\s+(\S+)", out)
    assert m and os.path.exists(m.group(1))
    with open(m.group(1)) as f:
        rows = f.read().strip().splitlines()
    n_dc = int(re.search(r"production dc vector: (\d+)", out).group(1))
    assert len(rows) == n_dc + 1
    assert "inv_T1_3pt_per_us" in rows[0] and "P0" in rows[0]


def test_raw_h5_reconstructs_the_ss_cal(out):
    import h5py
    import json
    import numpy as np
    m = re.search(r"raw-data h5:\s+(\S+)", out)
    assert m and os.path.exists(m.group(1))
    with h5py.File(m.group(1), "r") as f:
        for name in ("I_0", "Q_0", "I_1", "Q_1"):
            assert f[f"ss_cal/{name}"].shape[0] >= 500
        calib = json.loads(f["ss_cal"].attrs["calib_params"])
        assert "threshold" in calib and "read_theta" in calib
        n_dc = int(re.search(r"production dc vector: (\d+)", out).group(1))
        assert f["t1/dc_vec"].shape[0] == n_dc
        assert f["t1/freq_ghz"].shape[0] == n_dc
        for key in ("T1_3pt_us", "P0", "P1", "Ps", "T1_3pt_valid_mask"):
            assert f[f"t1/{key}"].shape[0] == n_dc
        assert bool(f["reset"].attrs["rotated_in_use"]) is True
        assert float(f["timing"].attrs["t_pass_s"]) >= 0.0
        t1 = np.asarray(f["t1/T1_3pt_us"])
        valid = np.asarray(f["t1/T1_3pt_valid_mask"]) > 0.5
        assert valid.sum() > n_dc * 0.5
        assert np.nanmedian(t1[valid]) > 10.0
