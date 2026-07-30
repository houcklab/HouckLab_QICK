import os
import re
import subprocess
import sys

import h5py
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_round_trip_ramsey.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))


@pytest.fixture(scope="module")
def output():
    env = dict(os.environ, PYTHONPATH=REPO)
    process = subprocess.run(
        [sys.executable, DRYRUN], capture_output=True, text=True,
        env=env, timeout=300)
    assert process.returncode == 0, (
        f"exit {process.returncode}\n{process.stdout[-4000:]}\n{process.stderr[-4000:]}")
    assert "ROUND TRIP RAMSEY DRY RUN COMPLETED" in process.stdout
    return process.stdout


def test_dryrun_finishes_and_writes_every_output(output):
    for label in ("CSV", "raw H5", "overview"):
        match = re.search(rf"{label}: (\S+)", output)
        assert match and os.path.exists(match.group(1))


def test_h5_contains_complete_channel_and_t1_data(output):
    path = re.search(r"raw H5: (\S+)", output).group(1)
    with h5py.File(path, "r") as handle:
        assert handle.attrs["schema"] == "round_trip_ramsey_audit_v1"
        assert "qubit_pi2_gain" in handle.attrs["base_config"]
        n_dc = int(handle["timing"].attrs["n_dc"])
        assert 15 <= n_dc <= 25
        assert handle["channel/freq_ghz"].shape == (n_dc,)
        for arm in ("g", "e", "i", "q"):
            for prefix in ("herald_I", "herald_Q", "I", "Q"):
                assert handle[f"channel/{prefix}_{arm}"].shape == (n_dc, 40)
        for key in ("ramsey_i", "ramsey_q", "coherence_magnitude",
                    "coherence_relative_to_park", "coherence_phase_rad",
                    "coherence_phase_relative_rad",
                    "coherence_phase_relative_unwrapped_rad",
                    "coherence_phase_unwrapped_rad",
                    "reference_contrast", "valid"):
            values = handle[f"channel/{key}"][:]
            assert values.shape == (n_dc,)
            assert np.all(np.isfinite(values))
        assert handle["t1/T1_3pt_us"].shape == (n_dc,)
        assert handle["park_channel_reference/I_g"].shape == (40,)
        assert bool(handle["reset"].attrs["rotated_in_use"]) is True


def test_csv_exposes_complex_response_and_matched_t1(output):
    path = re.search(r"CSV: (\S+)", output).group(1)
    with open(path) as handle:
        rows = handle.read().strip().splitlines()
    header = rows[0]
    for key in ("ramsey_i", "ramsey_q", "coherence_magnitude",
                "coherence_relative_to_park", "coherence_phase_rad",
                "coherence_phase_relative_rad",
                "coherence_phase_relative_unwrapped_rad",
                "coherence_phase_unwrapped_rad",
                "T1_3pt_us", "inv_T1_3pt_per_us"):
        assert key in header
    assert len(rows) >= 16


def test_runner_reports_park_validation(output):
    assert "park four-arm Ramsey reference" in output
    assert re.search(r"P_g=[\d.]+, P_e=[\d.]+, I=[+-][\d.]+, Q=[+-][\d.]+", output)
