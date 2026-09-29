"""Synthetic checks for the standalone sentinel analysis."""

import importlib

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSMillisecondSentinelAnalyze"


def subject():
    return importlib.import_module(MODULE)


def test_signed_two_flank_estimator_recovers_line_shift_and_strength():
    analysis = subject()
    displacement = np.array([.5, -1., 2.])
    baseline = {"A_minus": .55, "A_plus": .53, "B": .6}
    slope = {"A_minus": .10, "A_plus": -.10, "B": .08}
    values = {"A_minus": baseline["A_minus"] + .10*displacement,
              "A_plus": baseline["A_plus"] - .10*displacement,
              "B": baseline["B"] + .08*displacement}
    result = analysis.position_signals(values, baseline, slope)
    assert result["X_A_mhz"] == pytest.approx(displacement)
    assert result["X_B_mhz"] == pytest.approx(displacement)
    assert result["Y_A"] == pytest.approx(np.zeros(3))


def test_near_zero_dither_slope_is_not_divided_into_noise():
    analysis = subject()
    values = {site: np.array([.5]) for site in ("A_minus", "A_plus", "B")}
    with pytest.raises(ValueError, match="slope"):
        analysis.position_signals(values, values,
                                  {"A_minus": .001, "A_plus": -.1,
                                   "B": .1})


def test_irregular_timestamps_limit_bandwidth_and_flag_bank_gap():
    analysis = subject()
    ns = np.array([0, 5_000_000, 10_000_000, 30_000_000,
                   35_000_000, 40_000_000], dtype=np.int64)
    info = analysis.timing_quality(ns, valid=np.ones(6, dtype=bool))
    assert info["median_period_s"] == pytest.approx(.005)
    assert info["max_science_hz"] <= 80.0001
    assert info["gap_count"] == 1


def test_host_poll_jitter_reduces_defensible_frequency_band():
    analysis = subject()
    ns = np.array([0, 5, 11, 15, 22, 26], dtype=np.int64)*1_000_000
    info = analysis.timing_quality(ns)
    assert info["poll_jitter_mad_s"] >= .0009
    assert info["max_science_hz"] < 60


def test_motion_candidate_rejects_common_mode_or_nonnegative_flank_cross_spectrum():
    analysis = subject()
    good = analysis.motion_candidate(
        excess_sigma_first=6., excess_sigma_second=5.5,
        flank_cross_sigma_first=4., flank_cross_sigma_second=3.5,
        nuisance_coherence=.1, controls_valid=True)
    assert good["candidate"] is True
    assert analysis.motion_candidate(
        excess_sigma_first=6., excess_sigma_second=6.,
        flank_cross_sigma_first=4., flank_cross_sigma_second=4.,
        nuisance_coherence=.8, controls_valid=True)["candidate"] is False
    assert analysis.motion_candidate(
        excess_sigma_first=6., excess_sigma_second=6.,
        flank_cross_sigma_first=4., flank_cross_sigma_second=-.1,
        nuisance_coherence=.1, controls_valid=True)["candidate"] is False
    assert analysis.motion_candidate(
        excess_sigma_first=6., excess_sigma_second=6.,
        flank_cross_sigma_first=4., flank_cross_sigma_second=4.,
        nuisance_coherence=.1, controls_valid=False)["candidate"] is False


def test_binomial_white_floor_removes_stationary_science_null_mismatch():
    analysis = subject()
    # The uncorrected flank PSD exceeds the quiet null PSD solely because
    # p=.5 has greater Bernoulli variance than p=.8.
    period = .005
    science = analysis.binomial_position_white_floor(
        {"A_minus": .5, "A_plus": .5},
        {"A_minus": .1, "A_plus": -.1}, period)
    null = analysis.binomial_position_white_floor(
        {"A_minus": .8, "A_plus": .8},
        {"A_minus": .1, "A_plus": -.1}, period)
    assert science > null
    assert (science-science) == pytest.approx(null-null)


def test_binned_series_respects_actual_missing_time_and_not_just_shot_index():
    analysis = subject()
    time_s = np.array([.000, .005, .010, .050, .055])
    values = np.array([0., 1., 0., 1., 1.])
    centers, means, counts = analysis.bin_irregular(time_s, values, width_s=.010)
    assert counts.tolist() == [2, 1, 0, 0, 0, 2]
    assert np.isnan(means[2])
    assert means[-1] == pytest.approx(1.)


def test_pulse_tube_label_needs_independent_frequency():
    analysis = subject()
    report = analysis.pulse_tube_screen(np.array([1., 1.4, 2.8]),
                                         np.array([1., 100., 20.]),
                                         pt_frequency_hz=None)
    assert report["attribution"] == "unavailable_without_independent_frequency"


def test_irregular_spectrum_finds_known_line_without_filling_bank_gap():
    analysis = subject()
    times = np.arange(1000)*.005
    times[500:] += .025
    signal = np.sin(2*np.pi*2.0*times)
    frequency = np.arange(.2, 5.01, .2)
    spectrum = analysis.irregular_spectrum(times, {"x": signal}, frequency)
    peak = frequency[np.argmax(spectrum["power"]["x"])]
    assert peak == pytest.approx(2.0)
    assert spectrum["power"]["x"].max() > 20*spectrum["power"]["x"][0]


def test_allan_constant_stream_is_zero_and_long_tau_is_unresolved():
    analysis = subject()
    t = np.arange(1000)*.005
    result = analysis.allan_deviation(t, np.ones(1000), [0.01, 0.1, 3.0])
    assert result[0]["allan"] == pytest.approx(0)
    assert result[1]["allan"] == pytest.approx(0)
    assert result[2]["allan"] is None


def test_two_state_fit_beats_one_state_for_obvious_telegraph():
    analysis = subject()
    rng = np.random.default_rng(7)
    signal = np.repeat([-1., 1., -1., 1.], 60) + rng.normal(0, .08, 240)
    report = analysis.telegraph_fit(signal, max_states=2)
    assert report["models"]["2"]["bic"] + 10 < report["models"]["1"]["bic"]
    assert report["models"]["2"]["step_size"] > 1.5


def test_gaussian_block_crosscheck_finds_obvious_persistent_steps():
    analysis = subject()
    rng = np.random.default_rng(10)
    signal = np.repeat([-1., 1., -1., 1.], 40) + rng.normal(0, .08, 160)
    result = analysis.gaussian_block_change_points(signal, noise_sigma=.08)
    assert any(abs(index-40) <= 2 for index in result["change_indices"])
    assert any(abs(index-80) <= 2 for index in result["change_indices"])
    assert any(abs(index-120) <= 2 for index in result["change_indices"])


def test_derived_chunk_uses_saved_iq_and_calibrated_signed_slopes(tmp_path):
    analysis = subject()
    cal = np.zeros((100, 8, 2), dtype=np.int64)
    counts = (40, 30, 30, 40, 40, 30, 0, 100)
    for position, excited_count in enumerate(counts):
        cal[:, position, 0] = -1
        cal[:excited_count, position, 0] = 1
    cal_path = tmp_path / "cal.npz"
    np.savez_compressed(cal_path, iq=cal,
                        order=np.array(["A_minus_m", "A_minus_p",
                                        "A_plus_m", "A_plus_p", "B_m", "B_p",
                                        "ref_g", "ref_e"]))
    science = np.zeros((100, 8, 2), dtype=np.int64)
    science[:, :, 0] = -1
    science[:50, :, 0] = 1
    path = tmp_path / "science.npz"
    np.savez_compressed(path, iq=science,
                        order=np.array(["A_minus_0", "A_plus_1", "B_2", "C_3",
                                        "C_4", "B_5", "A_plus_6", "A_minus_7"]),
                        observed_utc_ns=np.arange(100, dtype=np.int64)*5_000_000,
                        timing_valid=np.ones(100, dtype=bool),
                        gap_after_previous=np.zeros(100, dtype=bool))
    result = analysis.derive_chunk(
        path, cal_path, {"theta_rad": 0., "threshold": 0.})
    assert result["slopes"]["A_minus"] == pytest.approx(.1)
    assert result["slopes"]["A_plus"] == pytest.approx(-.1)
    assert result["slopes"]["B"] == pytest.approx(.1)
    assert len(result["binary"]["X_A_mhz"]) == 100
    assert len(result["continuous"]["X_A_mhz"]) == 100
    assert result["timing"]["median_period_s"] == pytest.approx(.005)


def test_analysis_refuses_a_run_without_completed_controls(tmp_path):
    analysis = subject()
    path = tmp_path / "manifest.json"
    path.write_text('{"schema":"q3.tls-millisecond-sentinel.v1",'
                    '"status":"acquiring","controls_valid":false}')
    with pytest.raises(ValueError, match="complete"):
        analysis.analyze_session(path)


def test_complete_synthetic_session_produces_report_without_uniform_clock(tmp_path):
    analysis = subject()
    import json
    rng = np.random.default_rng(9)
    cal = np.zeros((100, 8, 2), dtype=np.int64)
    for position, count in enumerate((40, 30, 30, 40, 40, 30, 0, 100)):
        cal[:, position, 0] = -1
        cal[:count, position, 0] = 1
    cal_path = tmp_path / "cal.npz"
    np.savez_compressed(cal_path, iq=cal,
                        order=np.array(["A_minus_m", "A_minus_p",
                                        "A_plus_m", "A_plus_p", "B_m", "B_p",
                                        "ref_g", "ref_e"]))
    order = np.array(["A_minus_0", "A_plus_1", "B_2", "C_3",
                      "C_4", "B_5", "A_plus_6", "A_minus_7"])
    chunks = []
    for index in range(15):
        iq = np.zeros((200, 8, 2), dtype=np.int64)
        # Quiet null positions have a different Bernoulli floor from the
        # p=.5 science flanks despite having no time-dependent line motion.
        probability = .5 if index < 12 else .8
        iq[:, :, 0] = np.where(rng.random((200, 8)) < probability, 1, -1)
        times = (index*6_000_000_000 +
                 np.arange(200, dtype=np.int64)*5_000_000)
        times[100:] += 20_000_000
        path = tmp_path / f"chunk_{index}.npz"
        np.savez_compressed(path, iq=iq, order=order,
                            observed_utc_ns=times,
                            timing_valid=np.ones(200, dtype=bool),
                            gap_after_previous=np.r_[np.zeros(100, dtype=bool),
                                                      True, np.zeros(99, dtype=bool)])
        entry = {"kind": "science" if index < 12 else "null",
                 "status": "complete", "raw_npz": str(path)}
        if index < 12:
            entry["calibration"] = {"raw_npz": str(cal_path)}
            entry["calibration_report"] = {"valid": True}
        chunks.append(entry)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": "q3.tls-millisecond-sentinel.v1", "status": "complete",
        "controls_valid": True, "line_moved": False,
        "pre_readout_axis": {"theta_rad": 0., "threshold": 0.},
        "chunks": chunks}))
    report = analysis.analyze_session(manifest_path,
                                      pt_frequency_hz=1.4,
                                      compute_telegraph=False)
    assert report["science_chunks"] == 12
    assert report["null_chunks"] == 3
    assert report["max_science_hz"] <= 80.01
    assert (tmp_path / "sentinel_analysis.json").is_file()
    assert (tmp_path / "sentinel_derived_streams.npz").is_file()
    assert (tmp_path / "sentinel_analysis.png").is_file()
    with np.load(tmp_path / "sentinel_derived_streams.npz") as streams:
        assert "x_a_continuous_mhz" in streams
        assert "x_b_mhz" in streams
    assert "lag1" in report
    assert "binomial_white_floor" in report
    assert "change_point_crosscheck" in report
    assert report["pulse_tube"]["narrowband_grid_step_hz"] <= .011
    assert report["pulse_tube"]["physical_resolution_hz"] > .01
    assert not any(band["candidate"] for band in report["bands"])
    assert report["pulse_tube"]["attribution"] == "independent_frequency_test"


def test_within_shot_and_consecutive_shot_correlations_are_distinct():
    analysis = subject()
    stream = np.array([[0, 0], [1, 1], [0, 0], [1, 1]], dtype=float)
    result = analysis.lag_statistics(stream)
    assert result["early_late"] == pytest.approx(1.)
    assert result["consecutive_shots"] == pytest.approx(-1.)
