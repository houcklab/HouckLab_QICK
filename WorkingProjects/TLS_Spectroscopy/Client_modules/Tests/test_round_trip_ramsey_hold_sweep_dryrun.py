import os
import re
import subprocess
import sys

import h5py
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_round_trip_ramsey_hold_sweep.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def output():
    env = dict(os.environ, PYTHONPATH=REPO)
    process = subprocess.run(
        [sys.executable, DRYRUN], capture_output=True, text=True,
        env=env, timeout=300)
    assert process.returncode == 0, (
        f"exit {process.returncode}\n{process.stdout[-5000:]}\n{process.stderr[-5000:]}")
    assert "ROUND TRIP RAMSEY HOLD SWEEP DRY RUN COMPLETED" in process.stdout
    return process.stdout


def test_dryrun_writes_outputs(output):
    for label in ("CSV", "T1 CSV", "raw H5", "overview"):
        match = re.search(rf"{label}: (\S+)", output)
        assert match and os.path.exists(match.group(1))


def test_h5_has_complete_randomized_sweep(output):
    path = re.search(r"raw H5: (\S+)", output).group(1)
    with h5py.File(path, "r") as handle:
        assert handle.attrs["schema"] == "round_trip_ramsey_hold_sweep_v1"
        assert int(handle.attrs["total_points"]) == 18
        assert int(handle.attrs["completed_points"]) == 18
        assert not bool(handle.attrs["interrupted"])
        assert np.all(handle["channel/completed"][:] == 1)
        assert handle["channel/I_g"].shape == (18, 40)
        assert handle["channel/Q_q"].shape == (18, 40)
        assert len(np.unique(handle["schedule/target_index"][:])) == 6
        assert np.allclose(handle["hold_times_us"][:], [0.0, 0.2, 1.0])
        assert "t1_checks/start/T1_3pt_us" in handle
        assert "t1_checks/end/T1_3pt_us" in handle
        assert np.all(np.isfinite(handle["channel/coherence_magnitude"][:]))


def test_csv_is_visit_ordered_and_complete(output):
    path = re.search(r"CSV: (\S+)", output).group(1)
    with open(path) as handle:
        rows = handle.read().strip().splitlines()
    assert len(rows) == 19
    for name in ("hold_us", "nominal_freq_ghz", "park_anchored_freq_ghz",
                 "coherence_magnitude", "coherence_phase_relative_rad"):
        assert name in rows[0]


def test_runner_reports_finite_work_and_live_eta(output):
    assert "= 18 finite channel points" in output
    assert "live ETA includes hardware overhead" in output
    assert re.search(r"18/18.*ETA 0\.0 s", output)
