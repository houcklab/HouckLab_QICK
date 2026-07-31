import os
import re
import subprocess
import sys

import h5py
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_tls_memory_audit.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def output():
    env = dict(os.environ, PYTHONPATH=REPO)
    process = subprocess.run(
        [sys.executable, DRYRUN], capture_output=True, text=True,
        env=env, timeout=300)
    assert process.returncode == 0, (
        f"exit {process.returncode}\n{process.stdout[-5000:]}\n{process.stderr[-5000:]}")
    assert "TLS MEMORY AUDIT DRY RUN COMPLETED" in process.stdout
    return process.stdout


def test_dryrun_writes_all_outputs(output):
    for label in ("raw H5", "CSV", "plot"):
        match = re.search(rf"{label}:\s+(\S+)", output)
        assert match and os.path.exists(match.group(1))


def test_h5_contains_complete_detected_memory_run(output):
    path = re.search(r"raw H5:\s+(\S+)", output).group(1)
    with h5py.File(path, "r") as handle:
        assert handle.attrs["schema"] == "tls_population_memory_audit_v1"
        assert bool(handle.attrs["retrieval_detected"])
        assert bool(handle.attrs["storage_stage_run"])
        assert int(handle["interaction_scan"].attrs["completed_points"]) == 45
        assert int(handle["storage_sweep"].attrs["completed_points"]) == 27
        assert handle["interaction_scan/I"].shape == (45, 40)
        assert handle["storage_sweep/Q"].shape == (27, 40)
        assert handle["targets/dc_gain"].shape == (3,)


def test_csv_contains_three_control_arms_and_two_stages(output):
    path = re.search(r"CSV:\s+(\S+)", output).group(1)
    table = pd.read_csv(path)
    assert len(table) == 72
    assert set(table["stage"]) == {"interaction_scan", "storage_sweep"}
    assert set(table["sequence"]) == {"single", "double", "ground_double"}
    assert set(table["role"]) == {"minus", "tls", "plus"}


def test_runner_reports_finite_stages_and_detection(output):
    assert "stage 1: 3 targets x 5 interactions x 3 arms = 45 points" in output
    assert "stage 2 if retrieval is detected: 3 targets x 3 storage delays x 3 arms = 27 points" in output
    assert "retrieval DETECTED" in output
