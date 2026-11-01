"""Station, calibration store, settings, ramps and timing."""
import numpy as np
import pytest

from Bob.compiler.timing import ceil_to_cycle, samples_to_us, us_to_samples
from Bob.config.calibration import CalibrationError, CalibrationStore
from Bob.config.settings import ExperimentSettings, SweepAxis
from Bob.config.station import Station
from Bob.hardware.ramps import SHAPES, ramp


# ---------------------------------------------------------------- station
def test_station_loads_basic_values(station):
    assert station.name == "8QV1"
    assert station.n_channels == 8
    assert station.samples_per_us == pytest.approx(16 * 215.04)
    assert station.cycle_us == pytest.approx(16 / station.samples_per_us)
    assert station.get("nameserver/port") == 8888


def test_station_missing_key_names_what_exists(station):
    with pytest.raises(KeyError, match="available"):
        station.get("no_such_key")


def test_station_get_returns_copies(station):
    a = station.get("fast_flux_chs")
    a.append(99)
    assert 99 not in station.get("fast_flux_chs")


def test_station_listing():
    assert "8QV1" in Station.available()


# ---------------------------------------------------------------- calibration
def test_calibration_get_and_copy(calib):
    q = calib.get("drive_groups/readout_3800/entries/3/Qubit")
    q["Gain"] = -1
    assert calib.get("drive_groups/readout_3800/entries/3/Qubit/Gain") != -1


def test_calibration_missing_key_message(calib):
    with pytest.raises(CalibrationError) as e:
        calib.get("drive_groups/readout_3800/entries/3/Qubit/Freq")
    msg = str(e.value)
    assert "'Freq' not found" in msg and "Frequency" in msg and "entries/3/Qubit" in msg


def test_calibration_children_for_browsing(calib):
    keys = {k for k, is_branch, _ in calib.children("drive_groups") if is_branch}
    assert "readout_3800" in keys
    leaves = dict((k, prev) for k, br, prev in calib.children("drive_groups/readout_3800/entries/3/Qubit"))
    assert "Frequency" in leaves


def test_readout_groups_have_ff_readouts(calib):
    groups = calib.readout_groups()
    assert groups and all("FF_Readouts" in calib.get(f"drive_groups/{g}") for g in groups)


def test_readout_config_matches_qubitparams_formula(calib):
    """Same arithmetic as build_config.QubitParams.res_config."""
    qubits, res_lo = [3, 4], 9000.0
    cfg = calib.readout_config("readout_3800", qubits, res_lo)
    ros = [calib.get(f"drive_groups/readout_3800/entries/{q}/Readout") for q in qubits]
    assert cfg["res_gains"] == [r["Gain"] / 32766.0 * 2 for r in ros]
    assert cfg["res_freqs"] == [r["Frequency"] - res_lo for r in ros]
    assert cfg["readout_lengths"] == [r["Readout_Time"] for r in ros]
    assert cfg["ro_chs"] == [0, 1]
    ss = calib.get("drive_groups/readout_3800/entries/3/SingleShot")
    assert cfg["confusion_matrix"][0] == [[1 - ss["ng_contrast"], ss["ne_contrast"]],
                                          [ss["ng_contrast"], 1 - ss["ne_contrast"]]]


def test_calibration_is_pinned_by_hash(calib, tmp_path):
    assert calib.sha256 and len(calib.sha256) == 64
    copy = tmp_path / "qp.json"
    copy.write_bytes(open(calib.path, "rb").read() + b"\n")
    assert CalibrationStore.load(copy).sha256 != calib.sha256


# ---------------------------------------------------------------- settings / sweeps
def test_sweep_grid_outermost_first():
    s = ExperimentSettings(sweeps=[SweepAxis("a", 0, 1, 2), SweepAxis("b", 10, 30, 3)])
    pts = [p for _, p in s.iter_points()]
    assert s.n_points() == 6
    assert pts[0] == {"a": 0.0, "b": 10.0} and pts[1] == {"a": 0.0, "b": 20.0} and pts[3] == {"a": 1.0, "b": 10.0}


def test_no_sweeps_is_one_point():
    s = ExperimentSettings()
    assert s.n_points() == 1 and s.point(0) == {}


def test_settings_round_trip():
    s = ExperimentSettings(reps=123, rounds=2, relax_delay_us=50.0, sweeps=[SweepAxis("t", 0, 2, 5, "us")])
    assert ExperimentSettings.from_dict(s.to_dict()) == s


# ---------------------------------------------------------------- ramps / timing
@pytest.mark.parametrize("shape", SHAPES)
def test_ramp_ends_exactly_and_is_monotonic(shape):
    r = ramp(-1000.0, 5000.0, 400, shape)
    assert len(r) == 400 and r[-1] == pytest.approx(5000.0)
    assert np.all(np.diff(r) >= -1e-9)
    assert r[0] > -1000.0                       # first sample is already on the way


def test_cubic_ramp_matches_rampHelpers_formula():
    """RampHelpers.generate_cubic_ramp(reverse=False): (f - i) * ((t - T) / T)^3 + f."""
    i, f, n = 800.0, 4000.0, 750
    t = np.arange(1, n + 1)
    expected = (f - i) * ((t - n) / n) ** 3 + f
    assert np.allclose(ramp(i, f, n, "cubic"), expected)


def test_ramp_rejects_unknown_shape():
    with pytest.raises(ValueError):
        ramp(0, 1, 10, "zigzag")


def test_timing_conversions(station):
    spu = station.samples_per_us
    assert us_to_samples(1.0, spu) == 3441
    assert samples_to_us(3440.64, spu) == pytest.approx(1.0)
    assert [ceil_to_cycle(n) for n in (0, 1, 16, 17, 32)] == [0, 16, 16, 32, 32]
