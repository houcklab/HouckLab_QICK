"""Deterministic virtual-device tests for the measurement-first basic auto tuner.

This file intentionally stubs QICK before importing the experiment module.  The
production class exposes five narrow hardware acquisition methods; the virtual tuner
overrides exactly those methods and leaves the orchestration, candidate archive,
step-5 analysis, confirmation, and finalization code under test.
"""

from __future__ import annotations

import ast
import copy
import io
import importlib.util
import os
import pickle
import sys
import tempfile
import types
from contextlib import redirect_stdout

import numpy as np
from scipy.special import ndtri


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# mBasicAutoTuner defines QICK program classes at import time, but this test exercises
# only its explicit virtual-backend seams.  Empty bases are therefore sufficient and
# keep the test runnable on a client machine without pynq/qick installed.
qick = types.ModuleType("qick")
qick.AveragerProgram = type("AveragerProgram", (), {})
qick.RAveragerProgram = type("RAveragerProgram", (), {})
sys.modules["qick"] = qick

import matplotlib
matplotlib.use("Agg")

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (  # noqa: E402
    mBasicAutoTuner as T,
    mActiveResetProbe as ARP,
    mRabiChevronIQ as RI,
    mSingleShot1Q as SS,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (  # noqa: E402
    find_blob_median,
    find_threshold,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (  # noqa: E402
    active_reset,
    config_updater,
    ff_pulse,
)


def _base_config():
    """A deliberately poor but physically valid starting tuple."""
    return {
        "res_ch": 0,
        "qubit_ch": 1,
        "ro_chs": [0],
        "nqz": 2,
        "qubit_nqz": 1,
        "mixer_freq": 0.0,
        "read_pulse_style": "const",
        "read_pulse_freq": 7247.0,
        "read_pulse_gain": 1500,
        "read_length": 4.0,
        "read_pulse_length": 6.0,
        "res_phase": 37.0,
        "adc_trig_offset": 0.5,
        "readout_guard_us": 1.0,
        "qubit_pulse_style": "arb",
        "qubit_freq": 2524.5,
        "qubit_pi_freq": 2524.5,
        "qubit_pi_gain": 2000,
        "qubit_pi2_gain": 1111,
        "sigma": 0.10,
        "qubit_drag_beta": 0.07,
        "relax_delay": 1000.0,
        "use_switch": False,
        "ff_ch": 3,
        "ff_nqz": 1,
        "ff_park_gain": 0,
        "ff_hold_gain": 0,
        "FF_Qubits": {"4": {
            "channel": 3, "Gain_Readout": 0, "Gain_Expt": 0, "Gain_Pulse": 0,
        }},
    }


FAST_PARAMS = {
    "random_seed": 1234,
    "baseline": {"shots": 79, "blocks": 2},
    "resonator": {
        "span_mhz": 5.0, "points": 17, "shots": 31,
        "search_min_mhz": 7245.0, "search_max_mhz": 7252.0,
        "search_step_mhz": 0.10,
        "confirmation_span_mhz": 4.0, "confirmation_points": 81,
        "confirmation_shots": 31,
    },
    "spectroscopy": {
        "local_span_mhz": 24.0, "local_points": 25,
        "wide_span_mhz": 40.0, "wide_points": 41,
        "gain": 7000, "pulse_length_us": 2.0, "shots": 31,
        "max_candidates": 2, "min_feature_snr": 2.0,
        "search_min_mhz": 2520.0, "search_max_mhz": 2545.0,
        "search_step_mhz": 1.0, "coarse_candidates": 4,
        "confirmation_span_mhz": 4.0, "confirmation_points": 31,
        "confirmation_shots": 31, "max_repeat_error_mhz": 0.35,
    },
    "iq_rabi": {
        "local_span_mhz": 2.0, "freq_points_per_candidate": 5,
        "gain_min": 0, "gain_max": 24000, "gain_points": 17,
        "shots": 31, "min_r2": 0.50, "fine_gain_points": 17,
    },
    "rough_single_shot": {"shots": 83, "blocks": 2},
    "parity_chevron": {
        "enabled": True, "freq_span_mhz": 1.0, "freq_points": 3,
        "gain_fraction": 0.25, "gain_points": 5, "pulse_counts": [3, 4, 5],
        "shots": 61, "confirm_shots": 101, "confirm_blocks": 2,
    },
    "fine_frequency": {
        "enabled": True, "span_mhz": 1.0, "points": 7, "pairs": 3,
        "shots": 61, "calibration_shots": 79,
        "confirm_shots": 103, "confirm_blocks": 2,
    },
    "amplified_error": {
        "enabled": True, "freq_span_mhz": 0.5, "freq_points": 3,
        "gain_fraction": 0.08, "gain_points": 5,
        "pulse_counts": [5, 6, 7, 9, 10, 11], "shots": 61,
        "calibration_shots": 79, "confirm_shots": 103,
        "confirm_blocks": 2,
    },
    "readout": {
        "enabled": True, "freq_span_mhz": 4.4, "freq_points": 3,
        "gain_min": 1500, "gain_max": 8500, "gain_points": 3,
        # 53 is used by the virtual backend to inject one coarse-only false maximum.
        "shots": 53, "shortlist": 2, "confirm_shots": 109,
        "confirm_blocks": 2,
        "local_freq_span_mhz": 1.0, "local_freq_points": 3,
        "local_gain_fraction": 0.40, "local_gain_points": 3,
    },
    "readout_length": {
        "enabled": True, "values_us": [4.0, 30.0], "shots": 57,
        "shortlist": 2, "confirm_shots": 113, "confirm_blocks": 2,
    },
    "qubit": {
        "enabled": True, "freq_span_mhz": 2.0, "freq_points": 3,
        "gain_fraction": 0.25, "gain_points": 3, "shots": 59,
        "shortlist": 2, "confirm_shots": 127, "confirm_blocks": 2,
        "local_freq_span_mhz": 0.8, "local_freq_points": 3,
        "local_gain_fraction": 0.18, "local_gain_points": 3,
    },
    "pulse_duration": {
        "enabled": True, "sigma_values_us": [0.10, 0.25],
        "freq_span_mhz": 1.0, "freq_points": 3,
        "gain_fraction": 0.20, "gain_points": 3, "shots": 67,
        "shortlist": 3, "confirm_shots": 131, "confirm_blocks": 2,
    },
    "joint_search": {
        "enabled": True,
        "read_lengths_us": [4.0, 30.0],
        "sigma_values_us": [0.10, 0.25],
        "read_gain_min": 1500, "read_gain_max": 8500,
        "read_gain_points": 3,
        "qubit_gain_points_including_ground": 9,
        "qubit_gain_max_scale": 2.0,
        "qubit_gain_hard_max": 24000,
        "coarse_shots": 43,
        "medium_per_duration_pair": 1,
        "medium_global_count": 2,
        "medium_max_candidates": 8,
        "medium_shots": 83, "medium_blocks": 2,
        "trust_regions": 2, "trust_proposals": 4,
        "trust_pool_size": 300,
        "trust_read_frequency_radius_mhz": 0.40,
        "trust_qubit_frequency_radius_mhz": 0.70,
        "trust_read_gain_fraction": 0.25,
        "trust_qubit_gain_fraction": 0.25,
        "trust_shots": 89, "trust_blocks": 2,
        "closure_iterations": 1,
        "closure_frequency_radius_scale": 0.5,
        "closure_gain_radius_scale": 0.5,
        "runtime_budget_minutes": 30.0,
        "reserve_final_minutes": 0.0,
    },
    "duration_portfolio": {"enabled": False},
    # Legacy timing-unit fixtures below were authored around a one-point epsilon.
    # Production v10 retains the tightened 0.5-percentage-point timing default.
    "latency": {"max_fidelity_loss": 0.010},
    "coordinate_descent_repeat": False,
    # Most unit tests target one subsystem in isolation.  End-to-end operational
    # screening tests enable the production-default screen explicitly.
    "leakage": {"enabled": False, "operational_enabled": False},
    "final": {
        "top_candidates": 3, "shots": 173, "blocks": 3,
        "confidence_sigma": 1.96, "max_block_spread": 0.08,
    },
}


def _relative_100mhz_search_params():
    """Fast-test form of the production seed-relative discovery policy."""
    params = copy.deepcopy(FAST_PARAMS)
    params["resonator"].update({
        "search_min_mhz": None, "search_max_mhz": None,
        "search_radius_mhz": 100.0,
        "search_expansion_radii_mhz": [5.0, 25.0, 100.0],
        "search_edge_padding_mhz": 2.0,
        "search_step_mhz": 0.20,
    })
    params["spectroscopy"].update({
        "search_min_mhz": None, "search_max_mhz": None,
        "search_radius_mhz": 100.0,
        "search_edge_padding_mhz": 10.0,
        "search_step_mhz": 2.0,
        "coarse_candidates": 8, "max_candidates": 8,
        "confirmation_span_mhz": 20.0, "confirmation_points": 81,
    })
    return params


class VirtualBasicAutoTuner(T.BasicAutoTuner):
    """A deterministic qubit with one known high-fidelity six-parameter basin."""

    READ_FREQ = 7249.1
    READ_GAIN = 5000
    READ_LENGTH = 30.0
    QUBIT_FREQ = 2534.5
    PI_GAIN_AT_SIGMA = 5790.0
    SIGMA = 0.25

    def __init__(self, *args, fail_parity=False, **kwargs):
        self.fail_parity = bool(fail_parity)
        self.virtual_shots = 0
        self.ss_calls = []
        super().__init__(*args, **kwargs)

    # No artifacts are needed for a unit test; all persistence structures are still
    # populated in memory by BasicAutoTuner itself.
    def pickle_data(self):
        return None

    def save_plot(self, plotDisp=False):
        del plotDisp
        return None

    @classmethod
    def _pi_gain(cls, sigma):
        return cls.PI_GAIN_AT_SIGMA * cls.SIGMA / float(sigma)

    @staticmethod
    def _gaussian(value, center, width):
        return float(np.exp(-0.5 * ((float(value) - float(center)) / float(width)) ** 2))

    def _physical_fidelity(self, candidate):
        """Balanced assignment fidelity, including readout and state-prep quality."""
        read = (
            self._gaussian(candidate["read_pulse_freq"], self.READ_FREQ, 0.48)
            * self._gaussian(candidate["read_pulse_gain"], self.READ_GAIN, 2200.0)
            * self._gaussian(candidate["read_length"], self.READ_LENGTH, 18.0)
        )
        sigma = float(candidate["sigma"])
        control = (
            self._gaussian(candidate["qubit_pi_freq"], self.QUBIT_FREQ, 0.55)
            * self._gaussian(candidate["qubit_pi_gain"], self._pi_gain(sigma),
                             0.18 * self._pi_gain(sigma))
            * self._gaussian(sigma, self.SIGMA, 0.12)
        )
        return float(np.clip(0.50 + 0.47 * read * control, 0.50, 0.97))

    @staticmethod
    def _shots_for_fidelity(fidelity, shots):
        """Deterministic Gaussian quantiles with the requested Bayes fidelity."""
        n = max(int(shots), 20)
        # Equal-variance unit Gaussians separated by d have balanced assignment
        # fidelity Phi(d/2).  Mid-quantiles avoid infinities and remove Monte Carlo
        # flakes while still exercising the exact 100-threshold step-5 calculation.
        requested = float(np.clip(fidelity, 0.500001, 0.999999))
        separation = 2.0 * float(ndtri(requested))
        base = ndtri((np.arange(n, dtype=float) + 0.5) / n)
        ground = base - 0.5 * separation
        excited = base + 0.5 * separation
        # Nonzero orthogonal noise exercises IQ rotation without changing the optimal
        # projected classifier.
        q_pattern = 0.025 * np.sin(np.linspace(0.0, 4.0 * np.pi, n, endpoint=False))
        return ground, q_pattern, excited, q_pattern

    def _acquire_transmission(self, freqs_mhz, candidate, shots):
        del candidate
        freqs = np.asarray(freqs_mhz, dtype=float)
        self.virtual_shots += int(shots) * freqs.size
        detuning = (freqs - self.READ_FREQ) / 0.22
        # A complex notch with a unique magnitude minimum at READ_FREQ.
        return 1.0 - 0.82 / (1.0 + 1j * detuning)

    def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                              pulse_length_us):
        del candidate, gain, pulse_length_us
        freqs = np.asarray(freqs_mhz, dtype=float)
        self.virtual_shots += int(shots) * freqs.size
        detuning = (freqs - self.QUBIT_FREQ) / 0.32
        baseline = 0.2 + 0.001 * (freqs - np.mean(freqs))
        ripple = 0.0007 * np.sin(0.71 * np.arange(freqs.size))
        return baseline + ripple + 0.24 / (1.0 + 1j * detuning)

    def _acquire_iq_chevron(self, freqs_mhz, gains, candidate, shots):
        freqs = np.asarray(freqs_mhz, dtype=float)
        gains = np.asarray(gains, dtype=float)
        self.virtual_shots += int(shots) * freqs.size * gains.size
        pi_gain = self._pi_gain(candidate["sigma"])
        i_map = np.empty((freqs.size, gains.size), dtype=float)
        q_map = np.empty_like(i_map)
        for row, freq in enumerate(freqs):
            contrast = 0.04 + self._gaussian(freq, self.QUBIT_FREQ, 0.42)
            oscillation = contrast * np.exp(-gains / (12.0 * pi_gain)) * np.cos(
                np.pi * gains / pi_gain)
            # Large common offsets intentionally ensure that max(I**2+Q**2) would be a
            # bad objective; production's common-mode-subtracted fit must find the ridge.
            i_map[row] = 12.0 + oscillation
            q_map[row] = -7.0 + 0.37 * oscillation
        return i_map, q_map

    def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
        fidelity = self._physical_fidelity(candidate)
        # One deliberately absurd coarse-grid maximum.  It disappears at the larger,
        # fresh confirmation shot count and therefore must never become the final tuple.
        if (int(shots) == int(self.params["readout"]["shots"])
                and int(candidate["read_pulse_gain"]) == 8500
                and abs(float(candidate["read_pulse_freq"])
                        - float(self._resonator_seed)) < 0.1):
            fidelity = 0.995
        self.virtual_shots += 2 * int(shots)
        self.ss_calls.append({
            "candidate": dict(candidate), "shots": int(shots),
            "state_order": str(state_order), "requested_fidelity": fidelity,
        })
        return self._shots_for_fidelity(fidelity, shots)

    def _acquire_parity_chevron(self, freqs_mhz, gains, candidate, shots,
                                pulse_counts, calibration):
        del calibration
        if self.fail_parity and list(pulse_counts) == [3, 4, 5]:
            raise RuntimeError("synthetic parity backend fault")
        freqs = np.asarray(freqs_mhz, dtype=float)
        gains = np.asarray(gains, dtype=float)
        pi_gain = self._pi_gain(candidate["sigma"])
        quality = np.empty((freqs.size, gains.size), dtype=float)
        for fi, freq in enumerate(freqs):
            for gi, gain in enumerate(gains):
                quality[fi, gi] = (
                    self._gaussian(freq, self.QUBIT_FREQ, 0.45)
                    * self._gaussian(gain, pi_gain, 0.16 * pi_gain)
                )
        populations = np.empty((len(pulse_counts), freqs.size, gains.size), dtype=float)
        for index, count in enumerate(pulse_counts):
            populations[index] = (0.5 + 0.46 * quality if int(count) % 2
                                  else 0.5 - 0.46 * quality)
        targets = np.asarray([int(count) % 2 for count in pulse_counts], dtype=bool)
        correctness = np.where(targets[:, None, None], populations, 1.0 - populations)
        self.virtual_shots += int(shots) * len(pulse_counts) * freqs.size * gains.size
        return np.mean(correctness, axis=0), populations

    def _acquire_inverse_pair_scan(self, freqs_mhz, candidate, shots, pairs,
                                   calibration):
        del candidate, calibration
        freqs = np.asarray(freqs_mhz, dtype=float)
        self.virtual_shots += int(shots) * int(pairs) * 2 * freqs.size
        # Repeated inverse pairs return to ground only at the planted frequency.
        return 0.03 + 0.75 * np.sin(
            np.pi * (freqs - self.QUBIT_FREQ) / 1.4) ** 2

    def _acquire_repeated_populations(self, candidate, pulse_counts, shots,
                                      calibration):
        del calibration
        counts = np.asarray(pulse_counts, dtype=int)
        beta_error = min(
            0.20, 0.008 + 8.0 * (float(candidate.get(
                "qubit_drag_beta", 0.0)) - 0.04) ** 2)
        normalized = np.where(counts % 2 == 1,
                              1.0 - beta_error, beta_error)
        # Mirror the approximately symmetric assignment errors produced by the
        # deterministic virtual step-5 clouds near their calibrated basin.
        fidelity = self._physical_fidelity(candidate)
        ground_error = 1.0 - fidelity
        contrast = max(2.0 * fidelity - 1.0, 1e-6)
        self.virtual_shots += int(shots) * counts.size
        return ground_error + contrast * normalized


def test_step5_metric_matches_shared_helpers():
    rng = np.random.default_rng(44)
    ig = rng.normal(-0.75, 0.58, 1400)
    qg = rng.normal(0.20, 0.42, 1400)
    ie = rng.normal(0.92, 0.67, 1400)
    qe = rng.normal(-0.34, 0.46, 1400)

    measured = T.step5_metrics(ig, qg, ie, qe)
    c0, c1 = ig + 1j * qg, ie + 1j * qe
    theta = np.angle(find_blob_median(c1) - find_blob_median(c0))
    c0_rot = np.exp(-1j * theta) * c0
    c1_rot = np.exp(-1j * theta) * c1
    thresholds, fidelities = find_threshold(c0_rot, c1_rot)
    index = int(np.argmax(fidelities))

    assert measured["fidelity"] == float(fidelities[index])
    assert measured["read_theta"] == float(theta)
    expected_threshold = float(thresholds[index])
    if np.mean(np.real(c0_rot)) > expected_threshold:
        expected_threshold *= -1.0
    assert measured["threshold"] == expected_threshold
    assert measured["visibility"] == 2.0 * measured["fidelity"] - 1.0


def test_third_blob_guard_catches_binary_invisible_excited_cloud():
    """A remote f-like cloud can score as excited and leave binary F near one."""
    n = 2000
    base = ndtri((np.arange(n, dtype=float) + 0.5) / n)
    ig, qg = -2.0 + 0.18 * base, 0.18 * np.sin(np.linspace(0, 8, n))
    ie, qe = 2.0 + 0.18 * base, 0.18 * np.cos(np.linspace(0, 8, n))
    # Ten percent of excited preparations occupy a well-separated third cloud, but
    # remain on the excited side of the binary threshold.
    leaked = np.arange(n) < n // 10
    ie[leaked] = 2.0 + 0.12 * base[leaked]
    qe[leaked] = 4.0 + 0.12 * base[leaked]
    measured = T.step5_metrics(ig, qg, ie, qe)
    assert measured["fidelity"] > 0.98
    assert measured["excited_outlier_frac"] > 0.08
    assert measured["ground_outlier_frac"] < 0.02
    assert measured["third_blob_excess_ucb_95"] > 0.08


def test_common_mode_third_cloud_cannot_cancel_out_of_the_safety_metric():
    """Regression for the visibly three-cloud 8-us hardware SS-cal failure."""
    rng = np.random.default_rng(441)

    def cloud(center, count, scale=0.55):
        points = (rng.normal(size=(int(count), 2)) * float(scale)
                  + np.asarray(center, dtype=float))
        return points[:, 0] + 1j * points[:, 1]

    # The extra population has the same 15% weight in both preparations.  Therefore
    # the old excited-minus-ground tail statistic cancels even though a third physical
    # cloud is unmistakable in IQ.
    ground = np.r_[
        cloud((-4.0, 0.0), 750),
        cloud((4.0, 0.0), 100),
        cloud((0.0, 6.0), 150),
    ]
    excited = np.r_[
        cloud((-4.0, 0.0), 100),
        cloud((4.0, 0.0), 750),
        cloud((0.0, 6.0), 150),
    ]
    measured = T.step5_metrics(
        ground.real, ground.imag, excited.real, excited.imag,
        analyze_multimodality=True)
    assert measured["third_blob_excess_ucb_95"] < 0.05
    assert measured["third_cluster_guard_available"] is True
    assert measured["third_cluster_supported"] is True
    assert measured["third_cluster_detected"] is True
    assert abs(measured["third_cluster_fraction"] - 0.15) < 0.02
    assert measured["third_cluster_fraction_ucb_95"] > 0.15
    assert measured["third_cluster_bic_improvement"] > 20.0
    assert measured["third_cluster_min_separation_sigma"] > 2.5


def test_two_physical_clouds_are_not_penalized_when_gmm_splits_a_tail():
    rng = np.random.default_rng(442)

    def cloud(center, count, scale=0.60):
        points = (rng.normal(size=(int(count), 2)) * float(scale)
                  + np.asarray(center, dtype=float))
        return points[:, 0] + 1j * points[:, 1]

    ground = np.r_[cloud((-4.0, 0.0), 950), cloud((4.0, 0.0), 50)]
    excited = np.r_[cloud((-4.0, 0.0), 150), cloud((4.0, 0.0), 850)]
    diagnostic = T._third_cluster_diagnostics(ground, excited)
    assert diagnostic["third_cluster_guard_available"] is True
    assert diagnostic["third_cluster_supported"] is False
    assert diagnostic["third_cluster_detected"] is False


def test_operational_safety_path_rejects_a_common_mode_third_population():
    """The real safety wrapper, not just its helper, must reject the shown fault."""
    rng = np.random.default_rng(443)

    def cloud(center, count, scale=0.50):
        points = (rng.normal(size=(int(count), 2)) * float(scale)
                  + np.asarray(center, dtype=float))
        return points[:, 0] + 1j * points[:, 1]

    ground = np.r_[
        cloud((-4.0, 0.0), 750), cloud((4.0, 0.0), 100),
        cloud((0.0, 6.0), 150)]
    excited = np.r_[
        cloud((-4.0, 0.0), 100), cloud((4.0, 0.0), 750),
        cloud((0.0, 6.0), 150)]
    raw = (ground.real, ground.imag, excited.real, excited.imag)
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": False, "operational_enabled": True,
        "max_third_cluster_fraction": 0.08,
        "max_single_state_third_cluster_fraction": 0.12,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        tuner._acquire_ss_pair = lambda candidate, shots, state_order="ge": raw
        measured = tuner._measure_operational_leakage_candidate(
            tuner.working, 1000, 1000, "common third population regression")
    assert measured["third_blob_excess_ucb"] < 0.05
    assert measured["third_cluster_fraction_ucb_95"] > 0.14
    assert measured["operational_safe"] is False
    assert "resolved third IQ population" in measured["failure"]


def test_duration_portfolio_reports_safe_unsafe_and_inconclusive_lengths():
    """Each fixed length gets its own exact safety result and no write winner."""
    class PortfolioVirtualTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            rng = np.random.default_rng(444)

            def cloud(center, count, scale=0.48):
                points = (rng.normal(size=(int(count), 2)) * float(scale)
                          + np.asarray(center, dtype=float))
                return points[:, 0] + 1j * points[:, 1]

            ground = np.r_[
                cloud((-4.0, 0.0), 750), cloud((4.0, 0.0), 100),
                cloud((0.0, 6.0), 150)]
            excited = np.r_[
                cloud((-4.0, 0.0), 100), cloud((4.0, 0.0), 750),
                cloud((0.0, 6.0), 150)]
            self.unsafe_pair = (
                ground.real, ground.imag, excited.real, excited.imag)

        def _physical_fidelity(self, candidate):
            return float(0.88 + 0.01 * float(candidate["read_length"]))

        def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
            del state_order
            length = float(candidate["read_length"])
            if self._analyze_multimodality and np.isclose(length, 3.0):
                raise RuntimeError("synthetic IQ-safety backend outage")
            if np.isclose(length, 1.0):
                return self.unsafe_pair
            return self._shots_for_fidelity(
                self._physical_fidelity(candidate), shots)

    params = copy.deepcopy(FAST_PARAMS)
    params.update({
        "reset": {"enabled": False},
        "leakage": {"enabled": False, "operational_enabled": True},
        "duration_portfolio": {
            "enabled": True, "read_lengths_us": [1.0, 2.0, 3.0],
            "native_seeds_per_length": 1,
            "readout_seeds_per_length": 1,
            "control_seed_count": 1,
            "local_proposals_per_length": 0,
            "refine_shots": 101, "refine_blocks": 2,
            "screen_shots": 101, "screen_reference_shots": 500,
            "screen_drift_retries": 1,
            "confirm_shots": 503, "confirm_blocks": 2,
            "require_control_audit": True,
        },
        "control_verify": {
            "enabled": True, "pulse_counts": [1, 2, 3, 4],
            "shots": 101, "calibration_shots": 151, "blocks": 1,
            "minimum_binary_contrast": 0.30,
            "max_even_return_error_ucb": 0.30,
            "max_odd_inversion_error_ucb": 0.30,
        },
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = PortfolioVirtualTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        seeds = []
        for length in (1.0, 2.0, 3.0):
            candidate = T._with_candidate(
                tuner.working, read_pulse_freq=tuner.READ_FREQ,
                read_pulse_gain=tuner.READ_GAIN, read_length=length,
                qubit_pi_freq=tuner.QUBIT_FREQ,
                qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
                sigma=tuner.SIGMA)
            candidate.update({
                "fidelity": 0.88 + 0.01 * length,
                "fidelity_se": 0.005,
                "fidelity_lcb_95": 0.88 + 0.01 * length - 0.0098,
            })
            seeds.append(candidate)
        tuner._joint_rows = seeds
        best = tuner._stage_duration_portfolio()
        tuner._finalize(best)

    entries = tuner.data["duration_portfolio"]["entries"]
    assert [entry["read_length_us"] for entry in entries] == [1.0, 2.0, 3.0]
    statuses = [entry["status"] for entry in entries]
    assert statuses == ["UNSAFE", "SAFE", "INCONCLUSIVE"], [
        (entry["read_length_us"], entry["status"], entry["failures"],
         {key: entry.get("selected", {}).get(key) for key in (
             "third_blob_excess_ucb", "third_cluster_supported",
             "third_cluster_fraction_ucb_95", "portfolio_safe",
             "third_cluster_binary_axis_projection",
             "third_cluster_perpendicular_ratio", "third_cluster_size_ratio",
             "control_failure")})
        for entry in entries]
    assert entries[0]["selected"]["third_cluster_fraction_ucb_95"] > 0.14
    assert entries[1]["selected"]["control_verified"] is True
    assert np.isnan(entries[2]["selected"][
        "third_cluster_fraction_ucb_95"])
    assert tuner.data["duration_portfolio"]["equal_refinement_budget"] is True
    assert tuner.data["eligible_tuned"] == {}
    assert tuner.data["manual_selection_required"] is True
    assert tuner.data["automatic_config_write_allowed"] is False
    assert tuner.data["final_stable"] is False


def test_production_portfolio_covers_every_integer_us_and_caps_at_twenty():
    expected = [float(value) for value in range(1, 21)]
    assert T.BASIC_DEFAULTS["duration_portfolio"]["read_lengths_us"] == expected
    assert T.BASIC_DEFAULTS["joint_search"]["read_lengths_us"] == expected
    assert T.BASIC_DEFAULTS["readout_length"]["values_us"] == expected
    assert T.BASIC_DEFAULTS["readout_length"]["max_us"] == 20.0
    assert T.BASIC_DEFAULTS["latency"]["max_read_length_us"] == 20.0


def test_portfolio_rank_uses_fidelity_only_and_never_leakage():
    """A cleaner lower-fidelity tuple cannot replace the fidelity winner."""
    params = copy.deepcopy(FAST_PARAMS)
    params["duration_portfolio"] = {"enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        higher_fidelity = T._with_candidate(tuner.working, **{
            "fidelity": 0.91, "fidelity_se": 0.005,
            "fidelity_lcb_95": 0.9002,
            "third_blob_excess_ucb": 0.0,
            "third_cluster_supported": True,
            "third_cluster_fraction_ucb_95": 0.040,
            "third_cluster_single_state_fraction_ucb_95": 0.040,
        })
        cleaner = T._with_candidate(tuner.working, **{
            "fidelity": 0.89, "fidelity_se": 0.005,
            "fidelity_lcb_95": 0.8802,
            "third_blob_excess_ucb": 0.0,
            "third_cluster_supported": True,
            "third_cluster_fraction_ucb_95": 0.005,
            "third_cluster_single_state_fraction_ucb_95": 0.005,
        })
        higher_fidelity = tuner._annotate_portfolio_objective(higher_fidelity)
        cleaner = tuner._annotate_portfolio_objective(cleaner)
    assert np.isclose(
        higher_fidelity["portfolio_selection_fidelity_lcb"], 0.9002)
    assert np.isclose(cleaner["portfolio_selection_fidelity_lcb"], 0.8802)
    assert tuner._portfolio_rank(higher_fidelity) > tuner._portfolio_rank(cleaner)


def test_portfolio_preserves_known_winner_and_never_uses_screen_fidelity():
    """Regression for a 93.5% 19-us incumbent becoming a 50% table row."""
    class FidelityFirstPortfolioTuner(VirtualBasicAutoTuner):
        def _confirm_candidates(self, candidates, shots, blocks, label,
                                add_to_history=True):
            del shots, add_to_history
            exact = "exact fidelity replay" in str(label)
            rows = []
            for candidate in T._unique_candidates(candidates):
                is_incumbent = int(candidate["qubit_pi_gain"]) == 6000
                if exact:
                    fidelity = 0.935 if is_incumbent else 0.900
                else:
                    # Simulate an unlucky low-shot refinement which would drop the
                    # already observed incumbent without protected replay.
                    fidelity = 0.600 if is_incumbent else 0.910
                se = 0.004
                row = dict(candidate)
                row.update({
                    "fidelity": fidelity, "fidelity_se": se,
                    "fidelity_lcb_95": fidelity - 1.96 * se,
                    "confirmation_blocks": int(blocks),
                    "confirmation_complete": True,
                    "confirmation_batch_complete": True,
                    "third_blob_excess_ucb": 0.0,
                    "third_cluster_guard_available": True,
                    "third_cluster_supported": False,
                    "third_cluster_fraction": 0.0,
                    "third_cluster_fraction_ucb_95": 0.0,
                    "third_cluster_single_state_fraction": 0.0,
                    "third_cluster_single_state_fraction_ucb_95": 0.0,
                })
                rows.append(row)
            return rows

        def _portfolio_screen_candidate(self, candidate, length, rank):
            del length, rank
            # Leakage acquisition has a different preparation/sequence and may have
            # a very different binary-fidelity number.  It must contribute leakage
            # fields only, never overwrite the selected replay's 0.935 fidelity.
            row = dict(candidate)
            row.update({
                "fidelity": 0.510, "fidelity_se": 0.030,
                "fidelity_lcb_95": 0.4512,
                "valid": True, "portfolio_safe": False,
                "portfolio_safety_kind": "resolved_2d_iq_population",
                "third_blob_excess_ucb": 0.20,
                "third_cluster_guard_available": True,
                "third_cluster_supported": True,
                "third_cluster_fraction": 0.20,
                "third_cluster_fraction_ucb_95": 0.25,
                "third_cluster_single_state_fraction": 0.20,
                "third_cluster_single_state_fraction_ucb_95": 0.25,
            })
            return row

        def _portfolio_control_audit(self, candidate, length):
            del candidate, length
            return {"verified": True}, None

    params = copy.deepcopy(FAST_PARAMS)
    params.update({
        "reset": {"enabled": False},
        "leakage": {"enabled": False, "operational_enabled": True},
        "duration_portfolio": {
            "enabled": True, "read_lengths_us": [19.0],
            "native_seeds_per_length": 2,
            "readout_seeds_per_length": 1,
            "control_seed_count": 2,
            "local_proposals_per_length": 0,
            "historical_champions_per_length": 1,
            "confirm_candidates_per_length": 1,
            "refine_shots": 101, "refine_blocks": 2,
            "confirm_shots": 503, "confirm_blocks": 3,
            "screen_shots": 101, "screen_reference_shots": 101,
            "require_control_audit": True,
        },
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = FidelityFirstPortfolioTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        incumbent = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=5200, read_length=19.0,
            qubit_pi_freq=tuner.QUBIT_FREQ, qubit_pi_gain=6000,
            sigma=tuner.SIGMA)
        incumbent.update({
            "fidelity": 0.935, "fidelity_se": 0.004,
            "fidelity_lcb_95": 0.92716,
        })
        challenger = T._with_candidate(
            incumbent, read_pulse_gain=5000, qubit_pi_gain=5000)
        challenger.update({
            "fidelity": 0.900, "fidelity_se": 0.004,
            "fidelity_lcb_95": 0.89216,
        })
        tuner._joint_rows = [incumbent, challenger]
        best = tuner._stage_duration_portfolio()
        tuner._finalize(best)

    entry = tuner.data["duration_portfolio"]["entries"][0]
    selected = entry["selected"]
    assert entry["search"]["historical_best_replayed"] is True
    assert int(selected["qubit_pi_gain"]) == 6000
    assert np.isclose(selected["fidelity"], 0.935)
    assert np.isclose(entry["screened_candidates"][0]["fidelity"], 0.510)
    assert np.isclose(selected["portfolio_leakage_risk_ucb"], 0.25)
    assert entry["leakage_status"] == "UNSAFE"
    assert entry["control_status"] == "VERIFIED"
    assert np.isclose(best["fidelity"], 0.935)
    assert np.isclose(tuner.data["best_found"]["fidelity"], 0.935)
    portfolio = tuner.data["duration_portfolio"]
    assert portfolio["selection_objective"] == "held_out_fidelity_lcb_95_only"
    assert portfolio["leakage_affects_selection"] is False


def test_portfolio_protects_heldout_control_from_perfect_shared_ground_outlier():
    """A 56-shot F=1 proposal cannot evict a confirmed passive Rabi control."""
    params = copy.deepcopy(FAST_PARAMS)
    params["duration_portfolio"] = {
        "enabled": True, "control_seed_count": 1,
        "native_seeds_per_length": 1, "readout_seeds_per_length": 1,
        "local_proposals_per_length": 0,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        confirmed = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=5500, read_length=10.0,
            qubit_pi_freq=tuner.QUBIT_FREQ, qubit_pi_gain=5750,
            sigma=0.25, fidelity=0.94, fidelity_se=0.005,
            fidelity_lcb_95=0.9302, confirmation_blocks=2,
            confirmation_complete=True, confirmation_batch_complete=True,
            evidence_level="held_out_complete_multi_block", evidence_tier=3)
        coarse_outlier = T._with_candidate(
            confirmed, read_length=8.0, qubit_pi_freq=tuner.QUBIT_FREQ - 2.0,
            qubit_pi_gain=3600, fidelity=1.0, fidelity_se=0.0088,
            fidelity_lcb_95=0.9828,
            state_order="shared-ground-gain-sweep",
            evidence_level="shared_ground_proposal", evidence_tier=0)
        tuner._bootstrap_control_candidate = copy.deepcopy(confirmed)
        tuner._qualified_control_candidates = [coarse_outlier, confirmed]
        tuner._qualified_transition_frequency = tuner.QUBIT_FREQ
        tuner._qualified_transition_frequencies = [
            tuner.QUBIT_FREQ - 2.0, tuner.QUBIT_FREQ]
        candidates, search = tuner._portfolio_candidates_for_length(
            8.0, [coarse_outlier, confirmed])

    assert search["cross_seed_count"] == 1
    assert any(
        np.isclose(row["read_length"], 8.0)
        and np.isclose(row["qubit_pi_freq"], tuner.QUBIT_FREQ)
        and int(row["qubit_pi_gain"]) == 5750
        for row in candidates)
    assert tuner._authoritative_rank(confirmed) > tuner._authoritative_rank(
        coarse_outlier)


def test_shelving_inversion_recovers_direct_f_population():
    calibration = {
        "g": (0.98, 0.003, 0.04, 0.004),
        "e": (0.05, 0.004, 0.03, 0.004),
        "f": (0.03, 0.004, 0.96, 0.004),
    }
    matrix = np.array([
        [calibration[state][0] for state in ("g", "e", "f")],
        [calibration[state][2] for state in ("g", "e", "f")],
        [1.0, 1.0, 1.0],
    ])
    population = np.array([0.18, 0.72, 0.10])
    observed = matrix @ population
    solved = T.solve_shelved_qutrit_population(
        calibration, (observed[0], 0.003), (observed[1], 0.003))
    assert solved["ok"] is True
    assert abs(solved["p2"] - 0.10) < 1e-9
    assert solved["p2_se"] > 0.0


def test_independent_long_reference_exposes_candidate_one_pulse_leakage():
    """Candidate leakage must not be absorbed into its own prepared-e reference."""
    class QutritVirtualTuner(VirtualBasicAutoTuner):
        @staticmethod
        def _cloud(population, shots):
            population = np.asarray(population, dtype=float)
            population = np.clip(population, 0.0, None)
            population /= np.sum(population)
            counts = np.floor(population * int(shots)).astype(int)
            counts[np.argmax(population)] += int(shots) - int(np.sum(counts))
            centres = ((-2.0, 0.0), (2.0, 0.0), (2.0, 4.0))
            i_parts, q_parts = [], []
            for count, (ci, cq) in zip(counts, centres):
                if count <= 0:
                    continue
                quantile = ndtri((np.arange(count, dtype=float) + 0.5) / count)
                i_parts.append(ci + 0.16 * quantile)
                q_parts.append(cq + 0.13 * quantile[::-1])
            return np.concatenate(i_parts), np.concatenate(q_parts)

        @staticmethod
        def _candidate_leakage(candidate):
            beta = float(candidate.get("qubit_drag_beta", 0.0))
            return float(0.002 + 0.078 * min(abs(beta - 0.04) / 0.04, 1.0) ** 2)

        def _acquire_sequence(self, candidate, sequence_ops, shots, seq_gap_us=None):
            del seq_gap_us
            state = np.array([1.0, 0.0, 0.0])
            for operation in sequence_ops:
                if operation[0] == "pulse":
                    leak = self._candidate_leakage(candidate)
                    state = np.array([
                        state[1], (1.0 - leak) * state[0],
                        state[2] + leak * state[0],
                    ])
                elif operation[0] == "pulse_at":
                    frequency = float(operation[3])
                    if abs(frequency - float(candidate["qubit_pi_freq"])) < 50.0:
                        state = state[[1, 0, 2]]  # independent long g-e pi
                    else:
                        state = state[[0, 2, 1]]  # independent long e-f pi
                elif operation[0] != "delay":
                    raise AssertionError("unexpected virtual sequence operation")
            return self._cloud(state, int(shots))

        def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
            del state_order
            ig, qg = self._acquire_sequence(candidate, [], shots)
            ie, qe = self._acquire_sequence(
                candidate, [self._ge_pulse(candidate)], shots)
            return ig, qg, ie, qe

    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": True, "depths": [1, 2, 4], "gap_phases": [0.0],
        "shots": 700, "reference_shots": 900,
        "max_single_p2": 0.02, "max_amplified_p2": 0.03,
        "max_third_blob_excess": 0.05,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = QutritVirtualTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        ef = {
            "ef_frequency": tuner.working["qubit_pi_freq"] - 200.0,
            "ef_gain": 9000, "anharmonicity_mhz": -200.0,
            "ge_reference_gain": 5000, "reference_sigma_us": 0.5,
        }
        unsafe = T._with_candidate(tuner.working, qubit_drag_beta=0.0)
        unsafe_row = tuner._measure_leakage_candidate(
            unsafe, ef, 700, 900, "virtual unsafe")
        safe = T._with_candidate(tuner.working, qubit_drag_beta=0.04)
        safe_row = tuner._measure_leakage_candidate(
            safe, ef, 700, 900, "virtual safe")
    direct_unsafe = [row for row in unsafe_row["witnesses"] if row["depth"] == 1]
    assert direct_unsafe
    assert direct_unsafe[0]["p2"] > 0.06
    assert unsafe_row["single_p2_ucb"] > 0.06
    assert unsafe_row["leakage_safe"] is False
    assert safe_row["single_p2_ucb"] < 0.02
    assert safe_row["leakage_safe"] is True


def test_opposed_ef_scans_match_a_reproduced_feature_after_rank_swaps():
    """Different strongest peaks must not hide a shared physical e-f line."""
    frequencies = np.arange(11, dtype=float)
    combined_snr = np.zeros(11)
    combined_snr[2], combined_snr[8] = 9.5, 8.0
    combined = {"snr_trace": combined_snr}
    left_snr = np.zeros(11)
    left_snr[2], left_snr[8] = 9.0, 6.0
    right_snr = np.zeros(11)
    right_snr[8], right_snr[2] = 10.0, 8.0
    individual = [
        {"candidates_mhz": [2.0, 8.0], "candidate_indices": [2, 8],
         "snr_trace": left_snr},
        {"candidates_mhz": [8.0, 2.0], "candidate_indices": [8, 2],
         "snr_trace": right_snr},
    ]
    matched = T.BasicAutoTuner._reproduced_spectral_seed(
        frequencies, combined, individual, max_error_mhz=1.0,
        min_combined_snr=4.0)
    assert matched["frequency_mhz"] == 2.0
    assert matched["pass_centres_mhz"] == (2.0, 2.0)


def test_long_reference_gain_recovers_from_a_rabi_fit_alias():
    """A bad global fit may be rescued only by a direct 0/pi/2pi audit."""
    class ReferenceAuditTuner(VirtualBasicAutoTuner):
        TRUE_PI_GAIN = 5000.0

        def _sequence_mean(self, candidate, sequence, shots, seq_gap_us=None):
            del candidate, seq_gap_us
            area = sum(float(operation[1]) for operation in sequence
                       if operation[0] == "pulse_at")
            excited = np.sin(np.pi * area / (2.0 * self.TRUE_PI_GAIN)) ** 2
            return {
                "i": float(excited), "q": 0.0,
                "se_i": 0.001, "se_q": 0.001, "shots": int(shots),
            }

    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "reference_gain_max": 30000, "reference_gain_points": 13,
        "reference_rabi_shots": 101, "reference_min_rabi_r2": 0.55,
        "reference_min_contrast": 0.20,
        "reference_max_return_fraction": 0.35,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = ReferenceAuditTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        original_fit = T.fit_anchored_rabi
        T.fit_anchored_rabi = lambda gains, signal: {
            "ok": True, "pi_gain": 10000.0, "pi_gain_err": 50.0,
            "period": 20000.0, "r2": 0.99, "contrast": 1.0,
            "decay_gain": 50000.0,
            "yfit": np.zeros_like(np.asarray(signal, dtype=float)),
        }
        try:
            calibrated = tuner._calibrate_reference_ge(tuner.working)
        finally:
            T.fit_anchored_rabi = original_fit
    assert calibrated["ge_reference_gain"] == 5000
    assert calibrated["harmonic_rescue_used"] is True
    assert calibrated["harmonic_return_error"] < 0.01


def test_basic_default_uses_operational_screen_not_direct_ef_calibration():
    cfg = _base_config()
    # An anharmonicity prior used to activate the full qutrit calibration implicitly.
    # It must no longer make the basic workflow strict unless requested explicitly.
    cfg["qubit_anharmonicity_mhz"] = -200.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params={"leakage": {"operational_enabled": True}},
        )
        strict = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params={"leakage": {
                "enabled": "auto", "operational_enabled": True}},
        )
    assert tuner._leakage_active is False
    assert tuner._operational_leakage_active is True
    assert tuner.data["leakage"]["direct_p2_measured"] is False
    assert "fixed-Gaussian" in tuner.data["leakage"]["measurement"]
    assert strict._leakage_active is True
    assert "qutrit" in strict.data["leakage"]["measurement"]


def test_operational_screen_detects_bad_repeated_returns_without_calling_it_p2():
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": False, "operational_enabled": True,
        "operational_repeated_return_enabled": True,
        "operational_depths": [1, 2, 3, 4, 6, 8],
        "operational_min_binary_contrast": 0.45,
        "operational_max_even_return_error": 0.15,
        "operational_max_odd_inversion_error": 0.15,
        "max_third_blob_excess": 0.05,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        optimum = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA, sigma=tuner.SIGMA,
            qubit_drag_beta=0.04)
        safe = tuner._measure_operational_leakage_candidate(
            optimum, 2000, 2000, "safe operational regression")
        unsafe = tuner._measure_operational_leakage_candidate(
            T._with_candidate(optimum, qubit_drag_beta=0.20),
            2000, 2000, "unsafe operational regression")
    assert safe["operational_safe"] is True
    assert safe["max_even_return_error_ucb"] < 0.15
    assert unsafe["operational_safe"] is False
    assert unsafe["max_even_return_error_ucb"] > 0.15
    assert "single_p2_ucb" not in safe


def test_default_fixed_gaussian_screen_does_not_call_repeated_or_drag_backends():
    class FixedGaussianScreenTuner(VirtualBasicAutoTuner):
        def _acquire_repeated_populations(self, *args, **kwargs):
            raise AssertionError(
                "default duration/power screen must not run repeated-return backend")

    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = FixedGaussianScreenTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        candidate = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA, sigma=tuner.SIGMA)
        measured = tuner._measure_operational_leakage_candidate(
            candidate, 200, 1000, "fixed Gaussian regression")
    assert measured["repeated_return_enabled"] is False
    assert measured["depths"].size == 0
    assert measured["qubit_drag_beta"] == candidate["qubit_drag_beta"]
    assert measured["operational_safe"] is True


def test_statistical_fidelity_tie_prefers_longer_lower_power_gaussian():
    common = {
        "fidelity_se": 0.004, "max_even_return_error_ucb": 0.04,
        "max_odd_inversion_error_ucb": 0.04,
        "third_blob_excess_ucb": 0.01,
    }
    short = dict(common, fidelity=0.950, fidelity_lcb_95=0.942,
                 sigma=0.05, qubit_pi_gain=28000)
    longer = dict(common, fidelity=0.944, fidelity_lcb_95=0.936,
                  sigma=0.25, qubit_pi_gain=5800)
    too_slow = dict(common, fidelity=0.900, fidelity_lcb_95=0.892,
                    sigma=0.50, qubit_pi_gain=2900)
    selected = T.BasicAutoTuner._prefer_longer_noninferior(
        [short, longer, too_slow], margin=0.003)
    assert selected is longer


def test_operational_shortlist_cannot_be_filled_by_one_duration():
    base = T._candidate_from_cfg(_base_config())
    rows = []
    for index, beta in enumerate(np.linspace(-0.08, 0.08, 7)):
        row = T._with_candidate(
            base, sigma=0.05, qubit_pi_gain=28000,
            qubit_drag_beta=float(beta))
        row.update(fidelity=0.96 - 0.001 * index,
                   fidelity_lcb_95=0.95 - 0.001 * index)
        rows.append(row)
    for sigma, gain, fidelity in ((0.25, 5800, 0.94), (0.50, 2900, 0.93)):
        row = T._with_candidate(
            base, sigma=sigma, qubit_pi_gain=gain, qubit_drag_beta=0.02)
        row.update(fidelity=fidelity, fidelity_lcb_95=fidelity - 0.01)
        rows.append(row)
    shortlist = T.BasicAutoTuner._duration_covered_shortlist(rows, limit=3)
    assert {float(row["sigma"]) for row in shortlist} == {0.05, 0.25, 0.50}


def test_readout_tie_prefers_lower_power_duration_exposure():
    high = {
        "fidelity": 0.950, "fidelity_se": 0.004,
        "fidelity_lcb_95": 0.942,
        "read_pulse_gain": 7000, "read_length": 30.0,
    }
    lower = {
        "fidelity": 0.944, "fidelity_se": 0.004,
        "fidelity_lcb_95": 0.936,
        "read_pulse_gain": 5000, "read_length": 14.0,
    }
    too_weak = {
        "fidelity": 0.900, "fidelity_se": 0.004,
        "fidelity_lcb_95": 0.892,
        "read_pulse_gain": 2500, "read_length": 8.0,
    }
    selected = T.BasicAutoTuner._prefer_lower_readout_exposure(
        [high, lower, too_weak], margin=0.003)
    assert selected is lower


class _DurationCoverageTuner(VirtualBasicAutoTuner):
    """Make every global coarse winner share the deliberately bad seed duration."""

    def __init__(self, *args, coordinate, optimum, **kwargs):
        self.coverage_coordinate = str(coordinate)
        self.coverage_optimum = float(optimum)
        self.confirmed_durations = set()
        super().__init__(*args, **kwargs)

    def _measure_candidate(self, candidate, shots, label, state_order="ge",
                           archive=True, reference_discriminator=None):
        del shots, reference_discriminator
        coordinate = float(candidate[self.coverage_coordinate])
        label = str(label)
        if "coarse" in label:
            seed = float(self.initial[self.coverage_coordinate])
            # All three variants of the starting duration outrank every other
            # duration in the noisy discovery map.  A global top-3 shortlist therefore
            # has no timing coverage at all.
            if np.isclose(coordinate, seed):
                fidelity = 0.990 - 1e-6 * abs(float(candidate[
                    "read_pulse_gain" if self.coverage_coordinate == "read_length"
                    else "qubit_pi_gain"]))
            else:
                fidelity = 0.800 - 0.01 * abs(
                    coordinate - self.coverage_optimum)
        else:
            self.confirmed_durations.add(coordinate)
            fidelity = (0.940 if np.isclose(coordinate, self.coverage_optimum)
                        else 0.840)
        row = dict(candidate)
        row.update({
            "fidelity": float(fidelity),
            "fidelity_se": 0.0005,
            "fidelity_lcb_95": float(fidelity - 1.96 * 0.0005),
            "sep_sigma": 4.0,
            "third_blob_excess_ucb_95": 0.0,
            "label": label,
            "state_order": str(state_order),
            "measurement_index": len(self._archive),
        })
        if archive:
            self._archive.append(row)
        return row


def test_readout_length_confirmation_covers_every_length_not_only_seed():
    cfg = _base_config()
    cfg["read_length"] = 10.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = _DurationCoverageTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
            coordinate="read_length", optimum=20.0,
        )
        lengths = (10.0, 20.0, 30.0)
        gains = (3000, 5000, 7000)
        candidates = [
            T._with_candidate(
                tuner.working, read_length=length, read_pulse_gain=gain)
            for length in lengths for gain in gains
        ]
        best = tuner._direct_grid(
            "readout_length_seed_regression", candidates,
            (len(lengths), len(gains)),
            {"read_length_us": np.asarray(lengths),
             "read_gain_dac": np.asarray(gains)},
            shots=41, shortlist=3, confirm_shots=101, confirm_blocks=2,
            coverage_values=[row["read_length"] for row in candidates],
            coverage_per_value=2, primary_fidelity_only=True,
        )
    assert tuner.confirmed_durations == {10.0, 20.0, 30.0}
    assert best["read_length"] == 20.0
    assert tuner.working["read_length"] == 20.0
    assert tuner.data["maps"]["readout_length_seed_regression"][
        "coverage_confirmation"]["groups"] == [10.0, 20.0, 30.0]


def test_pi_duration_confirmation_covers_every_sigma_not_only_seed():
    cfg = _base_config()
    cfg["sigma"] = 0.10
    with tempfile.TemporaryDirectory() as folder:
        tuner = _DurationCoverageTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
            coordinate="sigma", optimum=0.25,
        )
        sigmas = (0.10, 0.25, 0.50)
        gains = (3000, 5000, 7000)
        candidates = [
            T._with_candidate(tuner.working, sigma=sigma, qubit_pi_gain=gain)
            for sigma in sigmas for gain in gains
        ]
        best = tuner._direct_grid(
            "pulse_duration_seed_regression", candidates,
            (len(sigmas), len(gains)),
            {"sigma_us": np.asarray(sigmas),
             "qubit_gain_dac": np.asarray(gains)},
            shots=41, shortlist=3, confirm_shots=101, confirm_blocks=2,
            coverage_values=[row["sigma"] for row in candidates],
            coverage_per_value=2, primary_fidelity_only=True,
        )
    assert tuner.confirmed_durations == {0.10, 0.25, 0.50}
    assert best["sigma"] == 0.25
    assert tuner.working["sigma"] == 0.25


def test_operational_screen_retries_discriminator_drift_before_rejecting_waveform():
    class TransientDriftTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.operational_calls = 0
            super().__init__(*args, **kwargs)

        def _operational_waveform_pool(self):
            return [T._with_candidate(
                self.working,
                read_pulse_freq=self.READ_FREQ,
                read_pulse_gain=self.READ_GAIN,
                read_length=self.READ_LENGTH,
                qubit_pi_freq=self.QUBIT_FREQ,
                qubit_pi_gain=self.PI_GAIN_AT_SIGMA,
                sigma=self.SIGMA)]

        def _measure_operational_leakage_candidate(
                self, candidate, shots, reference_shots, label):
            del shots, reference_shots
            self.operational_calls += 1
            safe = self.operational_calls >= 3
            row = dict(candidate)
            row.update({
                "fidelity": 0.92,
                "fidelity_se": 0.002,
                "fidelity_lcb_95": 0.91608,
                "third_blob_excess_ucb": 0.004,
                "max_even_return_error_ucb": np.nan,
                "max_odd_inversion_error_ucb": np.nan,
                "valid": bool(safe),
                "operational_safe": bool(safe),
                "leakage_safe": bool(safe),
                "label": str(label),
                "failure": (None if safe
                            else "the bracketing discriminator drifted"),
            })
            return row

    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": False,
        "operational_enabled": True,
        "operational_drift_retries": 2,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = TransientDriftTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        chosen = tuner._stage_operational_leakage()
    attempts = tuner.data["leakage"]["attempts"][0]["rows"]
    assert tuner.operational_calls == 3
    assert [row["bracket_attempt"] for row in attempts] == [1, 2, 3]
    assert chosen["third_blob_excess_ucb"] <= 0.05
    assert tuner.data["leakage"]["selection_safe"] is True


def _latency_candidate(read_length, sigma, fidelity, fidelity_se=0.001,
                       **changes):
    """Complete physical tuple plus deterministic held-out fidelity evidence."""
    candidate = T._with_candidate(
        T._candidate_from_cfg(_base_config()),
        read_length=float(read_length), sigma=float(sigma), **changes)
    candidate.update({
        "fidelity": float(fidelity),
        "fidelity_se": float(fidelity_se),
        "fidelity_lcb_95": float(fidelity - 1.96 * fidelity_se),
        "confirmation_blocks": 3,
        "block_fidelities": np.asarray([fidelity, fidelity, fidelity]),
        "block_spread": 0.0,
        "label": "final exact synthetic latency replay",
    })
    return candidate


def _latency_settings():
    return {
        "max_fidelity_loss": 0.010,
        "minimum_mean_fidelity": 0.55,
        "minimum_lcb_fidelity": 0.55,
        "confidence_sigma": 1.96,
    }


def test_candidate_latency_is_read_length_plus_four_gaussian_sigmas():
    candidate = _latency_candidate(5.0, 0.05, 0.93)
    competing = _latency_candidate(4.0, 0.40, 0.93)

    assert np.isclose(
        T.BasicAutoTuner._candidate_latency_us(candidate), 5.20)
    assert np.isclose(
        T.BasicAutoTuner._candidate_latency_us(competing), 5.60)
    # Looking only at readout length, sigma, or read_length + sigma would choose
    # the wrong physical tuple in this deliberately crossed example.
    assert (T.BasicAutoTuner._candidate_latency_us(candidate)
            < T.BasicAutoTuner._candidate_latency_us(competing))


def test_latency_noninferiority_rejects_low_fidelity_and_uncertainty():
    reference = _latency_candidate(30.0, 0.25, 0.930, 0.001)
    stable = _latency_candidate(8.0, 0.20, 0.927, 0.001)
    coinflip = _latency_candidate(1.0, 0.05, 0.600, 0.001)
    uncertain = _latency_candidate(1.0, 0.05, 0.925, 0.020)

    stable_result = T.BasicAutoTuner._latency_noninferiority(
        reference, stable, max_loss=0.010, confidence_z=1.96)
    coinflip_result = T.BasicAutoTuner._latency_noninferiority(
        reference, coinflip, max_loss=0.010, confidence_z=1.96)
    uncertain_result = T.BasicAutoTuner._latency_noninferiority(
        reference, uncertain, max_loss=0.010, confidence_z=1.96)

    expected_stable_ucb = 0.003 + 1.96 * np.hypot(0.001, 0.001)
    assert stable_result["eligible"] is True
    assert np.isclose(stable_result["loss_ucb"], expected_stable_ucb)
    assert coinflip_result["eligible"] is False
    assert coinflip_result["loss_ucb"] > 0.30
    assert coinflip_result["reason"]
    # A noisy fast point must demonstrate noninferiority; broad error bars cannot
    # become permission to sacrifice an unknown amount of fidelity.
    assert uncertain_result["eligible"] is False
    assert uncertain_result["loss_ucb"] > 0.010
    assert uncertain_result["reason"]


def test_latency_noninferiority_uses_crossfit_not_optimistic_step5_fidelity():
    reference = _latency_candidate(20.0, 0.25, 0.930, 0.001)
    candidate = _latency_candidate(8.0, 0.10, 0.929, 0.001)
    # The historical step-5 resubstitution scores look noninferior, but held-out
    # discriminator scoring exposes a candidate-dependent optimism gap.
    reference.update({
        "crossfit_fidelity": 0.928,
        "crossfit_fidelity_se": 0.001,
        "crossfit_fidelity_lcb_95": 0.928 - 1.96 * 0.001,
    })
    candidate.update({
        "crossfit_fidelity": 0.900,
        "crossfit_fidelity_se": 0.001,
        "crossfit_fidelity_lcb_95": 0.900 - 1.96 * 0.001,
    })

    ordinary = T.BasicAutoTuner._latency_noninferiority(
        {key: value for key, value in reference.items()
         if not key.startswith("crossfit_")},
        {key: value for key, value in candidate.items()
         if not key.startswith("crossfit_")},
        max_loss=0.010, confidence_z=1.96)
    held_out = T.BasicAutoTuner._latency_noninferiority(
        reference, candidate, max_loss=0.010, confidence_z=1.96)

    assert ordinary["eligible"] is True
    assert held_out["fidelity_estimator"] == "two_fold_crossfit"
    assert held_out["eligible"] is False
    assert held_out["loss_ucb"] > 0.010


def test_latency_selector_rejects_one_us_sixty_percent_candidate():
    reference = _latency_candidate(30.0, 0.25, 0.930, 0.001)
    qualified = _latency_candidate(8.0, 0.20, 0.927, 0.001)
    fast_bad = _latency_candidate(1.0, 0.05, 0.600, 0.001)

    selected, diagnostics = T.BasicAutoTuner._select_latency_constrained(
        [fast_bad, reference, qualified], reference, _latency_settings())

    assert T._candidate_key(selected) == T._candidate_key(qualified)
    assert T._candidate_key(selected) != T._candidate_key(fast_bad)
    assert diagnostics
    # The absolute floors are intentionally below 60%, proving that the relative
    # loss certificate -- rather than the unrelated write floor -- rejects it.
    assert _latency_settings()["minimum_mean_fidelity"] < fast_bad["fidelity"]
    assert _latency_settings()["minimum_lcb_fidelity"] < fast_bad[
        "fidelity_lcb_95"]


def test_latency_selector_rejects_an_uncertain_fast_contender():
    reference = _latency_candidate(30.0, 0.25, 0.930, 0.001)
    qualified = _latency_candidate(8.0, 0.20, 0.927, 0.001)
    uncertain = _latency_candidate(1.0, 0.05, 0.925, 0.020)
    settings = _latency_settings()
    settings.update({
        "minimum_mean_fidelity": 0.85,
        "minimum_lcb_fidelity": 0.85,
    })

    selected, diagnostics = T.BasicAutoTuner._select_latency_constrained(
        [uncertain, reference, qualified], reference, settings)

    assert uncertain["fidelity"] > settings["minimum_mean_fidelity"]
    assert uncertain["fidelity_lcb_95"] > settings["minimum_lcb_fidelity"]
    assert T._candidate_key(selected) == T._candidate_key(qualified)
    assert diagnostics


def test_latency_selector_is_deterministic_on_equal_latency():
    reference = _latency_candidate(30.0, 0.25, 0.930, 0.001)
    lower_lcb = _latency_candidate(
        5.0, 0.25, 0.925, 0.001, qubit_pi_freq=2524.4)
    higher_lcb = _latency_candidate(
        4.0, 0.50, 0.927, 0.001, qubit_pi_freq=2524.6)
    assert np.isclose(
        T.BasicAutoTuner._candidate_latency_us(lower_lcb),
        T.BasicAutoTuner._candidate_latency_us(higher_lcb))

    selected, _ = T.BasicAutoTuner._select_latency_constrained(
        [lower_lcb, higher_lcb, reference], reference, _latency_settings())
    assert T._candidate_key(selected) == T._candidate_key(higher_lcb)

    # When both timing and evidence are exactly tied, physical tuple identity must
    # break the tie rather than input/acquisition order.
    tied_a = _latency_candidate(
        4.0, 0.25, 0.927, 0.001, qubit_pi_freq=2524.4)
    tied_b = _latency_candidate(
        4.0, 0.25, 0.927, 0.001, qubit_pi_freq=2524.6)
    forward, _ = T.BasicAutoTuner._select_latency_constrained(
        [tied_a, tied_b, reference], reference, _latency_settings())
    reverse, _ = T.BasicAutoTuner._select_latency_constrained(
        [tied_b, tied_a, reference], reference, _latency_settings())
    assert T._candidate_key(forward) == T._candidate_key(reverse)


def test_latency_selector_fails_closed_on_invalid_coordinates():
    reference = _latency_candidate(30.0, 0.25, 0.930, 0.001)
    qualified = _latency_candidate(8.0, 0.20, 0.927, 0.001)
    invalid_rows = []
    for read_length, sigma in (
            (0.0, 0.05), (-1.0, 0.05), (np.nan, 0.05),
            (1.0, 0.0), (1.0, -0.05), (1.0, np.inf)):
        row = _latency_candidate(1.0, 0.05, 0.930, 0.001)
        row["read_length"] = read_length
        row["sigma"] = sigma
        invalid_rows.append(row)
        assert np.isinf(T.BasicAutoTuner._candidate_latency_us(row))
    missing = dict(invalid_rows[0])
    missing.pop("read_length")
    assert np.isinf(T.BasicAutoTuner._candidate_latency_us(missing))

    selected, diagnostics = T.BasicAutoTuner._select_latency_constrained(
        invalid_rows + [qualified, reference], reference, _latency_settings())
    assert T._candidate_key(selected) == T._candidate_key(qualified)
    assert diagnostics


def test_latency_frontier_preserves_fast_candidate_beyond_fidelity_top_k():
    rows = []
    for index in range(5):
        rows.append(_latency_candidate(
            30.0, 0.25, 0.950 - 0.001 * index, 0.001,
            qubit_pi_freq=2524.0 + 0.1 * index,
            qubit_pi_gain=2000 + 100 * index))
    medium = _latency_candidate(
        8.0, 0.20, 0.935, 0.001,
        qubit_pi_freq=2525.0, qubit_pi_gain=3000)
    fast = _latency_candidate(
        4.0, 0.10, 0.925, 0.001,
        qubit_pi_freq=2526.0, qubit_pi_gain=4000)
    rows.extend([medium, fast])

    # A fidelity-only top-three truncation contains only 30-us rows.  The frontier
    # must retain the fast physical basin so held-out final replay can decide whether
    # its small fidelity loss is inside the configured budget.
    frontier = T.BasicAutoTuner._latency_frontier_candidates(
        rows, max_per_read_length=1, max_per_sigma=1, limit=3)
    keys = {T._candidate_key(row) for row in frontier}
    assert len(frontier) <= 3
    assert T._candidate_key(rows[0]) in keys
    assert T._candidate_key(fast) in keys


def test_latency_frontier_densely_preserves_the_short_boundary():
    rows = [
        _latency_candidate(
            length, 0.10, 0.900 + 0.002 * index, 0.001,
            qubit_pi_gain=4000 + 100 * index)
        for index, length in enumerate(
            [1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0,
             14.0, 16.0, 20.0, 24.0, 30.0, 45.0])
    ]
    frontier = T.BasicAutoTuner._latency_frontier_candidates(
        rows, max_per_read_length=1, max_per_sigma=1, limit=7)
    lengths = {float(row["read_length"]) for row in frontier}

    # The first six surviving durations plus the best-fidelity anchor are retained.
    # An evenly spaced truncation would skip 10 us and could falsely report a slower
    # duration as the shortest point inside the final one-point fidelity plateau.
    assert {1.0, 2.0, 4.0, 6.0, 8.0, 10.0}.issubset(lengths)
    assert 45.0 in lengths


def test_uncertainty_tied_joint_corner_survives_marginal_coarse_winners():
    common = {
        "read_pulse_freq": 7249.1,
        "read_pulse_gain": 5000,
        "qubit_freq": 2534.5,
        "qubit_pi_freq": 2534.5,
        "qubit_drag_beta": 0.0,
    }
    joint_corner = _latency_candidate(
        8.0, 0.10, 0.930, 0.002,
        qubit_pi_gain=14475, **common)
    read_marginal = _latency_candidate(
        8.0, 0.25, 0.934, 0.001,
        qubit_pi_gain=5790, **common)
    control_marginal = _latency_candidate(
        20.0, 0.10, 0.935, 0.001,
        qubit_pi_gain=14475, **common)
    slow_best = _latency_candidate(
        20.0, 0.25, 0.940, 0.001,
        qubit_pi_gain=5790, **common)

    retained = T.BasicAutoTuner._latency_frontier_candidates(
        [joint_corner, read_marginal, control_marginal, slow_best],
        limit=4, nondominated=False, uncertainty_sigma=3.0)
    keys = {T._candidate_key(row) for row in retained}

    # Top-1 marginal pruning would choose 8us/.25 and 20us/.10, omitting the
    # shortest joint 8us/.10 corner.  Its uncertainty interval still overlaps both
    # noisy marginals, so it must reach the common held-out cohort.
    assert T._candidate_key(joint_corner) in keys
    assert T._candidate_key(read_marginal) in keys
    assert T._candidate_key(control_marginal) in keys


def test_latency_search_expands_to_later_frontier_after_early_arms_fail():
    class ProgressiveFrontierTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.frontier_pool = []
            self.heldout_batches = []
            super().__init__(*args, **kwargs)

        def _latency_joint_candidate_pool(self, reference, control_rows=None):
            del reference, control_rows
            return [{key: row[key] for key in self.initial}
                    for row in self.frontier_pool]

        def _stage_final_control_verify(self, candidate):
            self._final_control_verified_key = T._control_key(candidate)
            return {
                "verified": True,
                "candidate_key": T._candidate_key(candidate),
                "control_key": T._control_key(candidate),
            }

        def _measure_candidate(self, candidate, shots, label, state_order="ge",
                               archive=True, reference_discriminator=None):
            del shots, reference_discriminator
            length = float(candidate["read_length"])
            if "coarse" in str(label):
                ordered = [1.0, 2.0, 4.0, 6.0, 8.0,
                           10.0, 12.0, 14.0, 16.0, 20.0]
                fidelity = 0.915 + 0.002 * ordered.index(length)
                if np.isclose(length, 10.0):
                    fidelity = 0.932
                elif np.isclose(length, 12.0):
                    # A noisy coarse reversal makes 12 us look dominated by 10 us.
                    # It must still reach the common held-out timing cohort.
                    fidelity = 0.931
                if np.isclose(length, 20.0):
                    fidelity = 0.940
            elif length <= 10.0:
                # Every early frontier arm survives the cheap plausibility bound but
                # fails the fresh held-out one-point noninferiority requirement.
                fidelity = 0.900
            else:
                fidelity = {
                    12.0: 0.936,
                    14.0: 0.937,
                    16.0: 0.938,
                    20.0: 0.940,
                }[length]
            row = dict(candidate)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": 0.00005,
                "fidelity_lcb_95": fidelity - 1.96 * 0.00005,
                "crossfit_fidelity": fidelity,
                "crossfit_fidelity_se": 0.00005,
                "crossfit_fidelity_lcb_95": fidelity - 1.96 * 0.00005,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "label": str(label),
                "state_order": str(state_order),
                "measurement_index": len(self._archive),
            })
            if archive:
                self._archive.append(row)
            return row

        def _confirm_candidates(self, candidates, shots, blocks, label,
                                add_to_history=True):
            self.heldout_batches.append({
                "label": str(label),
                "read_lengths": tuple(sorted({
                    float(row["read_length"]) for row in candidates})),
            })
            return super()._confirm_candidates(
                candidates, shots, blocks, label,
                add_to_history=add_to_history)

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "coarse_shots": 41,
        # A small historical shortlist must not truncate the measured frontier.
        "shortlist": 5,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_point_attempts": 1,
        "max_confirmation_attempts": 1,
        "adaptive_confirmation_rounds": 0,
        "max_readout_candidates": 10,
        "max_control_candidates": 1,
        "minimum_mean_fidelity": 0.88,
        "minimum_lcb_fidelity": 0.87,
        "max_fidelity_loss": 0.010,
    })
    folder = tempfile.TemporaryDirectory()
    try:
        tuner = ProgressiveFrontierTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder.name,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_pi_gain": 5790,
            "qubit_drag_beta": 0.0,
        }
        tuner.frontier_pool = [
            _latency_candidate(length, 0.25, 0.940, 0.00005, **common)
            for length in (
                1.0, 2.0, 4.0, 6.0, 8.0,
                10.0, 12.0, 14.0, 16.0, 20.0)
        ]
        reference = next(row for row in tuner.frontier_pool
                         if np.isclose(row["read_length"], 20.0))
        tuner.working = {key: reference[key] for key in tuner.initial}

        selected = tuner._stage_latency_selection(reference)
    finally:
        folder.cleanup()

    assert tuner.heldout_batches
    # All plausible frontier arms share one interleaved held-out cohort.  This both
    # reaches the later plateau and prevents cross-batch common drift from being
    # mistaken for an arm-to-arm fidelity difference.
    assert {4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0}.issubset(
        set(tuner.heldout_batches[0]["read_lengths"]))
    coarse = tuner.data["maps"]["latency"]["coarse_rows"]
    coarse_by_length = {float(row["read_length"]): row for row in coarse}
    assert coarse_by_length[10.0]["fidelity"] > coarse_by_length[12.0]["fidelity"]
    assert np.isclose(selected["read_length"], 12.0)
    assert np.isclose(selected["fidelity"], 0.936)
    assert tuner.data["latency_optimization"]["qualified_speedup"] is True
    assert tuner.data["latency_optimization"]["selected_latency_us"] < (
        tuner.data["latency_optimization"]["reference_latency_us"])
    batches = tuner.data["maps"]["latency"].get(
        "frontier_confirmation_batches", [])
    assert len(batches) == 1
    assert batches[0]["mode"] == "single_interleaved_frontier_cohort"
    confirmations = tuner.data["maps"]["latency"]["confirmations"]
    pairing_sets = {tuple(row.get("block_pairing_ids", []))
                    for row in confirmations}
    assert len(pairing_sets) == 1


def test_integrated_latency_stage_selects_joint_fast_plateau_tuple():
    class LatencyPlateauTuner(VirtualBasicAutoTuner):
        def _stage_final_control_verify(self, candidate):
            self._final_control_verified_key = T._control_key(candidate)
            return {"verified": True, "control_key": T._control_key(candidate)}

        def _measure_candidate(self, candidate, shots, label, state_order="ge",
                               archive=True, reference_discriminator=None):
            del shots, reference_discriminator
            read_length = float(candidate["read_length"])
            sigma = float(candidate["sigma"])
            if np.isclose(read_length, 1.0) or np.isclose(sigma, 0.05):
                fidelity = 0.600
            elif np.isclose(read_length, 20.0) and np.isclose(sigma, 0.25):
                fidelity = 0.930
            elif np.isclose(read_length, 8.0) and np.isclose(sigma, 0.10):
                fidelity = 0.925
            else:
                fidelity = 0.924
            row = dict(candidate)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": 0.0002,
                "fidelity_lcb_95": fidelity - 1.96 * 0.0002,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "label": str(label),
                "state_order": str(state_order),
                "measurement_index": len(self._archive),
            })
            if archive:
                self._archive.append(row)
            return row

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = {
        "enabled": True,
        "max_fidelity_loss": 0.010,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.89,
        "familywise_alpha": 0.05,
        "confidence_sigma": 1.96,
        "coarse_shots": 41,
        "screening_sigma": 3.0,
        "screening_slack": 0.020,
        "shortlist": 8,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_block_spread": 0.08,
        "max_reference_drift": 0.04,
        "max_readout_candidates": 4,
        "max_control_candidates": 4,
        "min_read_length_us": 1.0,
        "max_read_length_us": 45.0,
        "min_sigma_us": 0.05,
        "max_sigma_us": 0.50,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = LatencyPlateauTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.930, 0.0002,
            qubit_pi_gain=5790, **common)
        readout_representative = _latency_candidate(
            8.0, 0.25, 0.924, 0.0002,
            qubit_pi_gain=5790, **common)
        control_representative = _latency_candidate(
            20.0, 0.10, 0.924, 0.0002,
            qubit_pi_gain=14475, **common)
        # This tempting short readout must be measured and rejected by the fidelity
        # constraint, rather than being prohibited by a hard timing cutoff.
        one_us_row = _latency_candidate(
            1.0, 0.05, 0.990, 0.0002,
            qubit_pi_gain=28950, **common)
        tuner._confirmed.extend([
            reference, readout_representative,
            control_representative, one_us_row,
        ])
        tuner.working = {key: reference[key] for key in tuner.initial}

        selected = tuner._stage_latency_selection(reference)

    assert np.isclose(selected["read_length"], 8.0)
    assert np.isclose(selected["sigma"], 0.10)
    assert np.isclose(selected["fidelity"], 0.925)
    mapping = tuner.data["maps"]["latency"]
    assert mapping["selection_confirmation_complete"] is True
    assert mapping["search_complete"] is True
    assert mapping["selection_confirmed"] is True
    assert all(row["confirmation_batch_complete"] is True
               for row in mapping["confirmations"])
    assert all(row["confirmation_blocks"] == params["latency"]["confirm_blocks"]
               for row in mapping["confirmations"])
    assert any(np.isclose(row["read_length"], 1.0)
               for row in mapping["coarse_rows"])
    one_us_coarse = [row for row in mapping["coarse_rows"]
                     if np.isclose(row["read_length"], 1.0)]
    assert one_us_coarse
    assert all(np.isclose(row["fidelity"], 0.600)
               for row in one_us_coarse)
    # The obviously bad fast arm is rejected by the cheap plausibility screen and
    # therefore never consumes held-out confirmation shots.
    assert all(not np.isclose(row["read_length"], 1.0)
               for row in mapping["shortlist"])
    timing = tuner.data["latency_optimization"]
    assert timing["status"] == "selected"
    assert timing["selected_latency_us"] > 0.0
    assert timing["latency_saved_us"] > 0.0
    assert timing["reference_latency_us"] > timing["selected_latency_us"]
    assert tuner._final_replay_completed is True
    assert tuner._final_replay_kind == "latency_unconstrained"
    assert tuner.data["final_confirmation_complete"] is True


def test_incomplete_latency_confirmation_preserves_reference_replay():
    class IncompleteLatencyTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.failed_latency_confirmation = False
            super().__init__(*args, **kwargs)

        def _measure_candidate(self, candidate, shots, label, state_order="ge",
                               archive=True, reference_discriminator=None):
            if ("latency Pareto replay frontier batch" in str(label)
                    and not self.failed_latency_confirmation
                    and np.isclose(float(candidate["read_length"]), 8.0)
                    and np.isclose(float(candidate["sigma"]), 0.10)):
                self.failed_latency_confirmation = True
                raise RuntimeError("synthetic missing latency block")
            del shots, reference_discriminator
            read_length = float(candidate["read_length"])
            sigma = float(candidate["sigma"])
            fidelity = (0.930 if np.isclose(read_length, 20.0)
                        and np.isclose(sigma, 0.25) else 0.925)
            row = dict(candidate)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": 0.0002,
                "fidelity_lcb_95": fidelity - 1.96 * 0.0002,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "label": str(label),
                "state_order": str(state_order),
                "measurement_index": len(self._archive),
            })
            if archive:
                self._archive.append(row)
            return row

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = {
        "enabled": True,
        "max_fidelity_loss": 0.010,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.89,
        "familywise_alpha": 0.05,
        "confidence_sigma": 1.96,
        "coarse_shots": 41,
        "screening_sigma": 3.0,
        "screening_slack": 0.020,
        "shortlist": 8,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_block_spread": 0.08,
        "max_reference_drift": 0.04,
        "max_readout_candidates": 4,
        "max_control_candidates": 4,
        "min_read_length_us": 4.0,
        "max_read_length_us": 45.0,
        "min_sigma_us": 0.05,
        "max_sigma_us": 0.50,
    }
    # Production retries a transient incomplete batch once.  This test isolates the
    # terminal fail-closed path after that retry budget is exhausted.
    params["latency"]["max_confirmation_attempts"] = 1
    with tempfile.TemporaryDirectory() as folder:
        tuner = IncompleteLatencyTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.930, 0.0002,
            qubit_pi_gain=5790, **common)
        tuner._confirmed.extend([
            reference,
            _latency_candidate(
                8.0, 0.25, 0.925, 0.0002,
                qubit_pi_gain=5790, **common),
            _latency_candidate(
                20.0, 0.10, 0.925, 0.0002,
                qubit_pi_gain=14475, **common),
        ])
        tuner.working = {key: reference[key] for key in tuner.initial}
        reference_key = T._candidate_key(tuner.working)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner.data["final_confirmation_complete"] = True

        try:
            tuner._stage_latency_selection(reference)
        except RuntimeError as exc:
            assert "frontier replay did not complete every randomized block" in str(exc)
        else:
            raise AssertionError("an incomplete latency replay selected a tuple")

    assert tuner.failed_latency_confirmation is True
    assert T._candidate_key(tuner.working) == reference_key
    assert tuner._final_replay_completed is True
    assert tuner._final_replay_kind == "unconstrained"
    assert tuner.data["final_confirmation_complete"] is True
    mapping = tuner.data["maps"]["latency"]
    assert mapping["selection_confirmation_complete"] is False
    assert mapping["search_complete"] is False
    assert mapping["selection_confirmed"] is False
    assert tuner.data["latency_optimization"]["status"] == "not_run"


def test_paired_latency_noninferiority_uses_round_robin_block_evidence():
    reference = _latency_candidate(20.0, 0.25, 0.930, 0.010)
    candidate = _latency_candidate(8.0, 0.10, 0.925, 0.010)
    reference.update({
        "block_fidelities": np.asarray([0.940, 0.920, 0.930]),
        "block_fidelity_ses": np.asarray([0.0002, 0.0002, 0.0002]),
    })
    candidate.update({
        "block_fidelities": np.asarray([0.935, 0.915, 0.925]),
        "block_fidelity_ses": np.asarray([0.0002, 0.0002, 0.0002]),
    })

    paired = T.BasicAutoTuner._latency_noninferiority(
        reference, candidate, max_loss=0.010, confidence_z=1.96)
    assert paired["method"] == "paired_round_robin_blocks"
    assert paired["eligible"] is True
    assert np.isclose(paired["mean_loss"], 0.005)
    assert paired["loss_ucb"] < 0.010

    # Without the block pairing, the same common-mode drift is unresolved and the
    # aggregate uncertainties must fail closed.  This proves that fresh interleaved
    # evidence, rather than the point estimates alone, earns latency qualification.
    independent_reference = dict(reference)
    independent_candidate = dict(candidate)
    for row in (independent_reference, independent_candidate):
        row.pop("block_fidelities")
        row.pop("block_fidelity_ses")
    independent = T.BasicAutoTuner._latency_noninferiority(
        independent_reference, independent_candidate,
        max_loss=0.010, confidence_z=1.96)
    assert independent["method"] == "independent_aggregate"
    assert independent["eligible"] is False
    assert independent["loss_ucb"] > 0.010


def test_latency_drift_bound_accounts_for_estimating_variance_from_eight_blocks():
    reference = _latency_candidate(20.0, 0.25, 0.930, 0.002)
    candidate = _latency_candidate(8.0, 0.10, 0.930, 0.0001)
    # Eight paired blocks estimate, rather than know, the drift variance.  Choose the
    # spread so the normal familywise z would pass a 1% budget while the corresponding
    # finite-block tail does not.
    paired_se = 0.002
    excursion = paired_se * np.sqrt(7.0)
    reference_blocks = 0.930 + np.asarray([-excursion, excursion] * 4)
    candidate_blocks = np.full(8, 0.930)
    for row, blocks in ((reference, reference_blocks),
                        (candidate, candidate_blocks)):
        aggregate_se = float(np.std(blocks, ddof=1) / np.sqrt(8.0))
        row.update({
            "fidelity": float(np.mean(blocks)),
            "fidelity_se": aggregate_se,
            "fidelity_lcb_95": float(np.mean(blocks) - 1.96 * aggregate_se),
            "confirmation_blocks": 8,
            "block_fidelities": blocks,
            "block_fidelity_ses": np.full(8, 0.0001),
            "block_spread": float(np.ptp(blocks)),
            "confirmation_batch_complete": True,
        })
    comparisons = 6 * 5 * 3
    normal_familywise_z = float(ndtri(1.0 - 0.05 / comparisons))
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        family = tuner._latency_family_settings(
            comparisons, required_blocks=8)
    result = T.BasicAutoTuner._latency_noninferiority(
        reference, candidate, max_loss=0.010,
        confidence_z=family["confidence_sigma"])

    assert np.isclose(result["loss_se"], paired_se, rtol=0.02)
    assert normal_familywise_z * result["loss_se"] < 0.010
    assert family["familywise_distribution"] == "student_t"
    assert family["familywise_degrees_of_freedom"] == 7
    assert family["confidence_sigma"] > normal_familywise_z
    # Treating an eight-block sample SD as a known variance would be
    # anti-conservative; the finite-block familywise bound must reject this arm.
    assert result["eligible"] is False
    assert result["loss_ucb"] > 0.010


def test_exact_epsilon_loss_is_accepted_against_max_safe_fidelity():
    unsafe_global_best = _latency_candidate(30.0, 0.25, 0.970, 0.0)
    unsafe_global_best["operational_safe"] = False
    max_safe = _latency_candidate(20.0, 0.25, 0.940, 0.0)
    max_safe["operational_safe"] = True
    at_epsilon = _latency_candidate(8.0, 0.10, 0.930, 0.0)
    at_epsilon["operational_safe"] = True
    outside_epsilon = _latency_candidate(4.0, 0.10, 0.929999, 0.0)
    outside_epsilon["operational_safe"] = True
    settings = {
        "max_fidelity_loss": 0.010,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.90,
        "confidence_sigma": 1.96,
    }

    selected, diagnostics = T.BasicAutoTuner._select_latency_constrained(
        [outside_epsilon, at_epsilon, max_safe], max_safe, settings)
    by_key = {tuple(row["candidate_key"]): row for row in diagnostics}
    boundary = by_key[T._candidate_key(at_epsilon)]
    outside = by_key[T._candidate_key(outside_epsilon)]

    assert np.isclose(boundary["loss_ucb"], settings["max_fidelity_loss"])
    assert boundary["accepted"] is True
    assert outside["loss_ucb"] > settings["max_fidelity_loss"]
    assert outside["accepted"] is False
    assert T._candidate_key(selected) == T._candidate_key(at_epsilon)
    # The unconstrained 97% row is deliberately unsafe.  Anchoring to it would
    # reject the valid 93% safe tuple, so safety-constrained latency must use the
    # maximum *safe* fidelity reference established by the preceding screen.
    wrong_anchor = T.BasicAutoTuner._latency_noninferiority(
        unsafe_global_best, at_epsilon,
        max_loss=settings["max_fidelity_loss"], confidence_z=1.96)
    assert wrong_anchor["eligible"] is False


def test_latency_stage_retries_transient_measurement_and_evidence_failures():
    class RetryingLatencyTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.coarse_retry_seen = False
            self.confirmation_retry_seen = False
            super().__init__(*args, **kwargs)

        def _stage_final_control_verify(self, candidate):
            self._final_control_verified_key = T._control_key(candidate)
            return {"verified": True, "control_key": T._control_key(candidate)}

        def _measure_candidate(self, candidate, shots, label, state_order="ge",
                               archive=True, reference_discriminator=None):
            is_joint_fast = bool(
                np.isclose(float(candidate["read_length"]), 8.0)
                and np.isclose(float(candidate["sigma"]), 0.10))
            if (is_joint_fast
                    and str(label) == "latency joint coarse attempt 1"
                    and not self.coarse_retry_seen):
                self.coarse_retry_seen = True
                raise RuntimeError("synthetic transient coarse fault")
            if (is_joint_fast
                    and "latency Pareto replay frontier batch" in str(label)
                    and "attempt 1" in str(label)
                    and not self.confirmation_retry_seen):
                self.confirmation_retry_seen = True
                raise RuntimeError("synthetic transient confirmation fault")
            del shots, reference_discriminator
            read_length = float(candidate["read_length"])
            sigma = float(candidate["sigma"])
            fidelity = (0.930 if np.isclose(read_length, 20.0)
                        and np.isclose(sigma, 0.25) else 0.925)
            row = dict(candidate)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": 0.0002,
                "fidelity_lcb_95": fidelity - 1.96 * 0.0002,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "label": str(label),
                "state_order": str(state_order),
                "measurement_index": len(self._archive),
            })
            if archive:
                self._archive.append(row)
            return row

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "coarse_shots": 41,
        "shortlist": 6,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_point_attempts": 2,
        "max_confirmation_attempts": 2,
        "max_readout_candidates": 4,
        "max_control_candidates": 4,
        "min_read_length_us": 4.0,
        "max_sigma_us": 0.50,
        "max_fidelity_loss": 0.010,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = RetryingLatencyTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.930, 0.0002,
            qubit_pi_gain=5790, **common)
        tuner._confirmed.extend([
            reference,
            _latency_candidate(
                8.0, 0.25, 0.925, 0.0002,
                qubit_pi_gain=5790, **common),
            _latency_candidate(
                20.0, 0.10, 0.925, 0.0002,
                qubit_pi_gain=14475, **common),
        ])
        tuner.working = {key: reference[key] for key in tuner.initial}

        selected = tuner._stage_latency_selection(reference)

    assert tuner.coarse_retry_seen is True
    assert tuner.confirmation_retry_seen is True
    assert np.isclose(selected["read_length"], 8.0)
    assert np.isclose(selected["sigma"], 0.10)
    mapping = tuner.data["maps"]["latency"]
    assert mapping["coverage"] == 1.0
    assert mapping["failures"] == []
    assert mapping["selection_confirmation_complete"] is True
    assert all(row["confirmation_batch_complete"] is True
               for row in mapping["confirmations"])
    assert any("frontier batch" in row["label"]
               and "attempt 2" in row["label"]
               for batch in mapping["confirmation_rounds"] for row in batch)
    selected_diagnostic = next(
        row for row in tuner.data["latency_optimization"]["diagnostics"]
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(selected))
    assert selected_diagnostic["accepted"] is True
    assert selected_diagnostic["method"] == "paired_round_robin_blocks"
    assert selected_diagnostic["loss_ucb"] <= params["latency"][
        "max_fidelity_loss"]


def test_latency_control_screen_falls_through_to_next_coherent_tuple():
    class ControlFallbackTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.control_attempts = []
            super().__init__(*args, **kwargs)

        def _stage_final_control_verify(self, candidate):
            self.control_attempts.append(T._candidate_key(candidate))
            if np.isclose(float(candidate["read_length"]), 4.0):
                raise RuntimeError("synthetic incoherent fastest pulse")
            self._final_control_verified_key = T._control_key(candidate)
            return {
                "verified": True,
                "control_key": T._control_key(candidate),
                "candidate_key": T._candidate_key(candidate),
            }

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = ControlFallbackTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = tuner._annotate_candidate_latency(_latency_candidate(
            20.0, 0.25, 0.940, 0.0002,
            qubit_pi_gain=5790, **common))
        fastest = tuner._annotate_candidate_latency(_latency_candidate(
            4.0, 0.10, 0.935, 0.0002,
            qubit_pi_gain=14475, **common))
        coherent_fallback = tuner._annotate_candidate_latency(_latency_candidate(
            8.0, 0.15, 0.934, 0.0002,
            qubit_pi_gain=9650, **common))
        confirmations = [reference, coherent_fallback, fastest]
        tuner._maps["latency"] = {"confirmations": confirmations}
        tuner.data["latency_optimization"].update({
            "status": "selected",
            "reference": copy.deepcopy(reference),
            "selected": copy.deepcopy(fastest),
            "diagnostics": [{
                "candidate_key": list(T._candidate_key(row)),
                "accepted": True,
            } for row in confirmations],
        })
        tuner.working = {key: fastest[key] for key in tuner.initial}

        chosen = tuner._stage_latency_control_screen()

    assert tuner.control_attempts == [
        T._candidate_key(fastest), T._candidate_key(coherent_fallback)]
    assert T._candidate_key(chosen) == T._candidate_key(coherent_fallback)
    assert T._candidate_key(tuner.working) == T._candidate_key(coherent_fallback)
    record = tuner.data["latency_optimization"]
    assert record["control_screen_passed"] is True
    assert len(record["control_screen_failures"]) == 1
    assert (tuple(record["control_screen_failures"][0]["candidate_key"])
            == T._candidate_key(fastest))
    assert (record["selected_latency_us"]
            < T.BasicAutoTuner._candidate_latency_us(reference))
    assert tuner.data["maps"]["latency_control_screen"][
        "selection_confirmed"] is True
    # The screen is a fallback decision aid, not the later exact write certificate.
    assert tuner._final_control_verified_key is None


def test_retained_reference_control_screen_cannot_choose_a_slower_tuple():
    class PassingControlTuner(VirtualBasicAutoTuner):
        def _stage_final_control_verify(self, candidate):
            self._final_control_verified_key = T._control_key(candidate)
            return {
                "verified": True,
                "control_key": T._control_key(candidate),
                "candidate_key": T._candidate_key(candidate),
            }

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = PassingControlTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = tuner._annotate_candidate_latency(_latency_candidate(
            8.0, 0.10, 0.940, 0.0002,
            qubit_pi_gain=14475, **common))
        slower = tuner._annotate_candidate_latency(_latency_candidate(
            14.0, 0.15, 0.939, 0.0002,
            qubit_pi_gain=9650, **common))
        confirmations = [reference, slower]
        tuner._maps["latency"] = {"confirmations": confirmations}
        tuner.data["latency_optimization"].update({
            "status": "retained_reference_no_qualified_speedup",
            "reference": copy.deepcopy(reference),
            "selected": copy.deepcopy(reference),
            "certified_selected": copy.deepcopy(reference),
            "certified_selected_key": list(T._candidate_key(reference)),
            "latency_certificate_valid": True,
            "qualified_speedup": False,
            "diagnostics": [{
                "candidate_key": list(T._candidate_key(row)),
                "accepted": True,
            } for row in confirmations],
        })
        tuner.working = {key: reference[key] for key in tuner.initial}

        chosen = tuner._stage_latency_control_screen()

    assert T._candidate_key(chosen) == T._candidate_key(reference)
    assert (tuner.data["latency_optimization"]["selected_latency_us"]
            == T.BasicAutoTuner._candidate_latency_us(reference))
    assert tuner.data["latency_optimization"]["qualified_speedup"] is False


def test_binding_unsafe_reference_is_lazily_removed_before_latency_decision():
    class UnsafeBindingReferenceTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.synthetic_pool = []
            self.safety_attempts = []
            self.control_attempts = []
            super().__init__(*args, **kwargs)

        def _latency_joint_candidate_pool(self, reference, control_rows=None):
            del reference, control_rows
            return [dict(row) for row in self.synthetic_pool]

        @staticmethod
        def _latency_frontier_candidates(rows, max_per_read_length=1,
                                         max_per_sigma=1, limit=8,
                                         nondominated=True,
                                         uncertainty_sigma=3.0):
            del (max_per_read_length, max_per_sigma, nondominated,
                 uncertainty_sigma)
            return [dict(row) for row in rows[:int(limit)]]

        def _measure_candidate(self, candidate, shots, label, state_order="ge",
                               archive=True, reference_discriminator=None):
            del shots, reference_discriminator
            read_length = float(candidate["read_length"])
            if np.isclose(read_length, 20.0):
                fidelity, fidelity_se = 0.935, 0.001
            elif np.isclose(read_length, 14.0):
                # Lower LCB than the 20-us arm, but enough upper uncertainty to be
                # the binding possible-best reference for the fast candidate.
                fidelity, fidelity_se = 0.940, 0.006
            else:
                fidelity, fidelity_se = 0.930, 0.001
            row = dict(candidate)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": fidelity_se,
                "fidelity_lcb_95": fidelity - 1.96 * fidelity_se,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "label": str(label),
                "state_order": str(state_order),
                "measurement_index": len(self._archive),
            })
            if archive:
                self._archive.append(row)
            return row

        def _stage_final_control_verify(self, candidate):
            self.control_attempts.append(T._candidate_key(candidate))
            self._final_control_verified_key = T._control_key(candidate)
            return {"verified": True, "control_key": T._control_key(candidate)}

        def _stage_operational_leakage_verify(self, allow_fallback=True):
            del allow_fallback
            key = T._candidate_key(self.working)
            self.safety_attempts.append(key)
            unsafe = np.isclose(float(self.working["read_length"]), 14.0)
            if unsafe:
                self._leakage_verified_candidate_key = None
                self.data["leakage"].update({
                    "verified": False,
                    "failure": "synthetic unsafe binding reference",
                })
                return False
            self._leakage_verified_candidate_key = key
            self.data["leakage"].update({"verified": True, "failure": None})
            return True

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "coarse_shots": 31,
        "shortlist": 4,
        "confirm_shots": 61,
        "confirm_blocks": 8,
        "max_point_attempts": 1,
        "max_confirmation_attempts": 1,
        "adaptive_confirmation_rounds": 0,
        "max_readout_candidates": 3,
        "max_control_candidates": 3,
        "max_fidelity_loss": 0.010,
    })
    params["leakage"] = copy.deepcopy(T.BASIC_DEFAULTS["leakage"])
    params["leakage"].update({
        "enabled": False,
        "operational_enabled": True,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = UnsafeBindingReferenceTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.935, 0.001,
            qubit_pi_gain=5790, **common)
        unsafe_blocker = _latency_candidate(
            14.0, 0.20, 0.940, 0.006,
            qubit_pi_gain=7238, **common)
        fast_safe = _latency_candidate(
            8.0, 0.10, 0.930, 0.001,
            qubit_pi_gain=14475, **common)
        tuner.synthetic_pool = [reference, unsafe_blocker, fast_safe]
        tuner.working = {key: reference[key] for key in tuner.initial}

        selected = tuner._stage_latency_selection(reference)

    unsafe_key = T._candidate_key(unsafe_blocker)
    assert unsafe_key in tuner.safety_attempts
    assert unsafe_key in {
        tuple(key) for key in tuner.data["latency_optimization"][
            "safety_rejected_anchor_keys"]
    }
    assert T._candidate_key(selected) == T._candidate_key(fast_safe)
    selected_diagnostic = next(
        row for row in tuner.data["latency_optimization"]["diagnostics"]
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(fast_safe))
    assert selected_diagnostic["accepted"] is True


def test_realistic_block_uncertainty_shrinks_across_adaptive_rounds():
    candidate = _latency_candidate(8.0, 0.10, 0.930, 0.0094)

    def block(index):
        row = dict(candidate)
        row.update({
            "fidelity": 0.930,
            "fidelity_se": 0.0094,
            "crossfit_fidelity": 0.928,
            "crossfit_fidelity_se": 0.0094,
            "measurement_index": int(index),
            "sep_sigma": 3.8,
            "third_blob_excess_ucb_95": 0.01,
        })
        return row

    first = T.BasicAutoTuner._aggregate(
        candidate, [block(index) for index in range(3)],
        "first realistic latency batch")
    second = T.BasicAutoTuner._aggregate(
        candidate, [block(index) for index in range(3, 6)],
        "second realistic latency batch")
    combined = T.BasicAutoTuner._combine_latency_confirmation_rounds(
        [[first], [second]], "combined realistic latency evidence")[0]

    assert np.isclose(first["fidelity_se"], 0.0094 / np.sqrt(3.0))
    assert np.isclose(second["fidelity_se"], 0.0094 / np.sqrt(3.0))
    assert np.isclose(combined["fidelity_se"], 0.0094 / np.sqrt(6.0))
    assert np.isclose(
        combined["fidelity_se"], first["fidelity_se"] / np.sqrt(2.0))
    assert combined["confirmation_blocks"] == 6
    assert combined["block_fidelity_ses"].tolist() == [0.0094] * 6
    assert combined["fidelity_lcb_95"] > first["fidelity_lcb_95"]
    assert combined["block_crossfit_fidelities"].tolist() == [0.928] * 6
    assert combined["block_crossfit_fidelity_ses"].tolist() == [0.0094] * 6
    assert np.isclose(
        combined["crossfit_fidelity_se"],
        first["crossfit_fidelity_se"] / np.sqrt(2.0))
    assert combined["crossfit_fidelity_lcb_95"] > first[
        "crossfit_fidelity_lcb_95"]


class _AdaptiveLatencyEvidenceTuner(VirtualBasicAutoTuner):
    def __init__(self, *args, fail_optional_round=False, **kwargs):
        self.fail_optional_round = bool(fail_optional_round)
        self.optional_failure_seen = False
        super().__init__(*args, **kwargs)

    def _stage_final_control_verify(self, candidate):
        self._final_control_verified_key = T._control_key(candidate)
        return {"verified": True, "control_key": T._control_key(candidate)}

    def _measure_candidate(self, candidate, shots, label, state_order="ge",
                           archive=True, reference_discriminator=None):
        if (self.fail_optional_round
                and str(label).startswith("adaptive exact latency replay round 1")
                and not self.optional_failure_seen
                and np.isclose(float(candidate["read_length"]), 8.0)
                and np.isclose(float(candidate["sigma"]), 0.10)):
            self.optional_failure_seen = True
            raise RuntimeError("synthetic optional adaptive-block fault")
        del shots, reference_discriminator
        reference = bool(
            np.isclose(float(candidate["read_length"]), 20.0)
            and np.isclose(float(candidate["sigma"]), 0.25))
        fidelity = 0.930 if reference else 0.925
        row = dict(candidate)
        row.update({
            "fidelity": fidelity,
            # Three initial blocks leave the 0.5% loss unresolved; six paired blocks
            # shrink this realistic shot term enough to certify it.
            "fidelity_se": 0.0012,
            "fidelity_lcb_95": fidelity - 1.96 * 0.0020,
            "sep_sigma": 3.8,
            "third_blob_excess_ucb_95": 0.0,
            "label": str(label),
            "state_order": str(state_order),
            "measurement_index": len(self._archive),
        })
        if archive:
            self._archive.append(row)
        return row


def _run_adaptive_latency_fixture(fail_optional_round):
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "coarse_shots": 41,
        "shortlist": 4,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_point_attempts": 1,
        "max_confirmation_attempts": 1,
        "adaptive_confirmation_rounds": 1,
        "adaptive_ucb_slack": 0.012,
        "max_readout_candidates": 2,
        "max_control_candidates": 2,
        "min_read_length_us": 4.0,
        "max_sigma_us": 0.50,
        "max_fidelity_loss": 0.010,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = _AdaptiveLatencyEvidenceTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
            fail_optional_round=fail_optional_round,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.930, 0.0012,
            qubit_pi_gain=5790, **common)
        fast = _latency_candidate(
            8.0, 0.10, 0.925, 0.0012,
            qubit_pi_gain=14475, **common)
        tuner._confirmed.extend([reference, fast])
        tuner.working = {key: reference[key] for key in tuner.initial}
        selected = tuner._stage_latency_selection(reference)
    return tuner, reference, fast, selected, params


def test_adaptive_latency_evidence_moves_unresolved_candidate_to_accepted():
    tuner, reference, fast, selected, params = _run_adaptive_latency_fixture(False)
    mapping = tuner.data["maps"]["latency"]
    first_round = mapping["confirmation_rounds"][0]
    initial_reference = tuner._best_aggregate(first_round)
    initial_settings = tuner._latency_family_settings(
        max(len(first_round) * (len(first_round) - 1), 1),
        params["latency"]["confirm_blocks"])
    initial_selected, initial_diagnostics = tuner._select_latency_constrained(
        first_round, initial_reference, initial_settings)
    initial_fast = next(
        row for row in initial_diagnostics
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(fast))

    assert initial_fast["accepted"] is False
    assert initial_fast["loss_ucb"] > params["latency"]["max_fidelity_loss"]
    assert tuner._latency_has_ambiguous_faster_candidate(
        initial_diagnostics, initial_reference, initial_selected,
        initial_settings) is True
    assert mapping["adaptive_rounds_completed"] == 1
    assert mapping["adaptive_confirmation"] == [{
        "round": 1, "complete": True,
        "candidate_count": len(mapping["confirmations"]),
    }]
    assert all(row["confirmation_blocks"] == 6
               for row in mapping["confirmations"])
    final_fast = next(
        row for row in tuner.data["latency_optimization"]["diagnostics"]
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(fast))
    assert final_fast["accepted"] is True
    assert final_fast["loss_ucb"] <= params["latency"]["max_fidelity_loss"]
    assert T._candidate_key(selected) == T._candidate_key(fast)
    assert tuner.data["latency_optimization"]["status"] == "selected"


def test_incomplete_optional_adaptive_round_preserves_initial_complete_result():
    tuner, reference, _fast, selected, params = _run_adaptive_latency_fixture(True)
    mapping = tuner.data["maps"]["latency"]

    assert tuner.optional_failure_seen is True
    assert mapping["selection_confirmation_complete"] is True
    assert mapping["search_complete"] is True
    assert mapping["selection_confirmed"] is True
    assert len(mapping["confirmation_rounds"]) == 1
    assert mapping["adaptive_rounds_completed"] == 0
    assert mapping["adaptive_confirmation"] == [{
        "round": 1, "complete": False,
        "candidate_count": len(mapping["shortlist"]),
    }]
    assert all(row["confirmation_batch_complete"] is True
               for row in mapping["confirmations"])
    assert all(row["confirmation_blocks"] == params["latency"]["confirm_blocks"]
               for row in mapping["confirmations"])
    assert T._candidate_key(selected) == T._candidate_key(reference)
    record = tuner.data["latency_optimization"]
    assert record["status"] == "retained_reference_timing_uncertain"
    assert record["latency_certificate_valid"] is False
    assert tuner._final_replay_completed is True
    assert tuner._final_replay_kind == "latency_unconstrained"


class _SimultaneousBlockerLatencyTuner(VirtualBasicAutoTuner):
    """Three-arm latency fixture with a non-anchor statistical blocker."""

    def __init__(self, *args, blocker_is_coherent, **kwargs):
        self.blocker_is_coherent = bool(blocker_is_coherent)
        self.control_attempts = []
        self.synthetic_confirmations = []
        self.blocker_key = None
        super().__init__(*args, **kwargs)

    def _latency_joint_candidate_pool(self, reference, control_rows=None):
        del reference, control_rows
        return [
            {key: row[key] for key in self.initial}
            for row in self.synthetic_confirmations
        ]

    def _measure_candidate(self, candidate, shots, label, state_order="ge",
                           archive=True, reference_discriminator=None):
        del shots, reference_discriminator
        key = T._candidate_key(candidate)
        source = next(row for row in self.synthetic_confirmations
                      if T._candidate_key(row) == key)
        row = dict(source)
        row.update({
            "fidelity_se": 0.0002,
            "fidelity_lcb_95": float(source["fidelity"] - 1.96 * 0.0002),
            "sep_sigma": 4.0,
            "third_blob_excess_ucb_95": 0.0,
            "label": str(label),
            "state_order": str(state_order),
            "measurement_index": len(self._archive),
        })
        if archive:
            self._archive.append(row)
        return row

    def _confirm_candidates(self, candidates, shots, blocks, label,
                            add_to_history=True):
        del shots
        keys = {T._candidate_key(row) for row in candidates}
        rows = []
        for source in self.synthetic_confirmations:
            if T._candidate_key(source) not in keys:
                continue
            row = copy.deepcopy(source)
            row.update({
                "label": str(label),
                "scheduled_confirmation_blocks": int(blocks),
                "completed_confirmation_blocks": int(blocks),
                "missing_confirmation_blocks": 0,
                "confirmation_complete": True,
                "confirmation_batch_complete": True,
                "confirmation_failure_count": 0,
            })
            rows.append(row)
        if add_to_history:
            self._confirmed.extend(rows)
        return rows

    def _stage_final_control_verify(self, candidate):
        key = T._candidate_key(candidate)
        self.control_attempts.append(key)
        if key == self.blocker_key and not self.blocker_is_coherent:
            raise RuntimeError("synthetic incoherent simultaneous blocker")
        self._final_control_verified_key = T._control_key(candidate)
        return {
            "verified": True,
            "candidate_key": key,
            "control_key": T._control_key(candidate),
        }


def _simultaneous_blocker_latency_fixture(blocker_is_coherent):
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "coarse_shots": 41,
        "shortlist": 4,
        "confirm_shots": 79,
        "confirm_blocks": 3,
        "max_point_attempts": 1,
        "max_confirmation_attempts": 1,
        "adaptive_confirmation_rounds": 0,
        "max_readout_candidates": 3,
        "max_control_candidates": 3,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.90,
        "max_fidelity_loss": 0.010,
    })
    folder = tempfile.TemporaryDirectory()
    tuner = _SimultaneousBlockerLatencyTuner(
        soc=None, soccfg=None, path="q4", outerFolder=folder.name,
        cfg=_base_config(), params=params,
        blocker_is_coherent=blocker_is_coherent,
    )
    common = {
        "read_pulse_freq": tuner.READ_FREQ,
        "read_pulse_gain": tuner.READ_GAIN,
        "qubit_freq": tuner.QUBIT_FREQ,
        "qubit_pi_freq": tuner.QUBIT_FREQ,
        "qubit_drag_beta": 0.0,
    }

    def confirmed(read_length, sigma, gain, block_fidelities):
        block_fidelities = np.asarray(block_fidelities, dtype=float)
        block_ses = np.full(block_fidelities.size, 0.0001, dtype=float)
        fidelity = float(np.mean(block_fidelities))
        between = float(np.std(block_fidelities, ddof=1)
                        / np.sqrt(block_fidelities.size))
        within = float(np.sqrt(np.sum(block_ses ** 2))
                       / block_fidelities.size)
        fidelity_se = max(between, within)
        row = _latency_candidate(
            read_length, sigma, fidelity, fidelity_se,
            qubit_pi_gain=gain, **common)
        row.update({
            "block_fidelities": block_fidelities,
            "block_fidelity_ses": block_ses,
            "block_spread": float(np.ptp(block_fidelities)),
            "confirmation_blocks": int(block_fidelities.size),
            "confirmation_batch_complete": True,
            "fidelity_lcb_95": fidelity - 1.96 * fidelity_se,
        })
        return row

    # The anchor and fast arm share stable blocks, so their 0.6-point loss is
    # certifiable.  The 93.9% middle arm has a lower LCB than the anchor but a large
    # paired fluctuation; it is therefore the worst simultaneous reference for the
    # fast arm despite not being the descriptive best-fidelity anchor.
    anchor = confirmed(20.0, 0.25, 5790, [0.940, 0.940, 0.940])
    blocker = confirmed(12.0, 0.20, 7238, [0.948, 0.930, 0.939])
    fast = confirmed(4.0, 0.10, 14475, [0.934, 0.934, 0.934])
    tuner.synthetic_confirmations = [anchor, blocker, fast]
    tuner.blocker_key = T._candidate_key(blocker)
    tuner.working = {key: anchor[key] for key in tuner.initial}
    return folder, tuner, anchor, blocker, fast


def test_incoherent_simultaneous_blocker_is_audited_removed_then_fast_qualifies():
    folder, tuner, anchor, blocker, fast = (
        _simultaneous_blocker_latency_fixture(False))
    try:
        selected = tuner._stage_latency_selection(anchor)
    finally:
        folder.cleanup()

    assert T._candidate_key(anchor) in tuner.control_attempts
    assert T._candidate_key(blocker) in tuner.control_attempts
    assert T._candidate_key(selected) == T._candidate_key(fast)
    selected_diagnostic = next(
        row for row in tuner.data["latency_optimization"]["diagnostics"]
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(fast))
    assert selected_diagnostic["accepted"] is True
    assert all(
        tuple(row.get("reference_key") or ()) != T._candidate_key(blocker)
        for row in selected_diagnostic["pairwise_loss_bounds"])
    assert tuner.data["latency_optimization"]["latency_certificate_valid"] is True


def test_coherent_simultaneous_blocker_remains_and_prevents_certification():
    folder, tuner, anchor, blocker, fast = (
        _simultaneous_blocker_latency_fixture(True))
    try:
        selected = tuner._stage_latency_selection(anchor)
    finally:
        folder.cleanup()

    assert T._candidate_key(blocker) in tuner.control_attempts
    assert T._candidate_key(selected) == T._candidate_key(anchor)
    fast_diagnostic = next(
        row for row in tuner.data["latency_optimization"]["diagnostics"]
        if tuple(row.get("candidate_key") or ()) == T._candidate_key(fast))
    assert fast_diagnostic["accepted"] is False
    assert tuple(fast_diagnostic["worst_case_reference_key"]) == (
        T._candidate_key(blocker))
    assert fast_diagnostic["loss_ucb"] > tuner.params["latency"][
        "max_fidelity_loss"]
    assert tuner.data["latency_optimization"]["latency_certificate_valid"] is False


def test_final_tuple_mismatch_invalidates_latency_certificate():
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        certified = _latency_candidate(
            8.0, 0.10, 0.930, 0.001,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_freq=tuner.QUBIT_FREQ,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=14475,
            qubit_drag_beta=0.0,
        )
        final = T._with_candidate(certified, read_length=10.0)
        final["label"] = "final exact changed-after-latency replay"
        tuner.data["latency_optimization"].update({
            "status": "selected",
            "reference_latency_us": 21.0,
            "selected": copy.deepcopy(certified),
            "certified_selected": copy.deepcopy(certified),
            "certified_selected_key": list(T._candidate_key(certified)),
            "latency_certificate_valid": True,
            "qualified_speedup": True,
            "latency_saved_us": 12.0,
            "latency_reduction_fraction": 12.0 / 21.0,
        })
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "latency_unconstrained"
        tuner._finalize(final)

    timing = tuner.data["latency_optimization"]
    assert timing["certificate_matches_final_tuple"] is False
    assert timing["latency_certificate_valid"] is False
    assert timing["status"] == "invalidated_final_tuple_changed"
    assert timing["status_before_invalidation"] == "selected"
    assert timing["qualified_speedup"] is False
    assert timing["latency_saved_us"] == 0.0
    assert timing["latency_reduction_fraction"] == 0.0
    assert T._candidate_key(timing["final_selected"]) == T._candidate_key(final)
    assert T._candidate_key(timing["certified_selected"]) == (
        T._candidate_key(certified))


def test_uncertain_timing_reference_cannot_be_promoted_by_control_or_finalize():
    class PassingControlTuner(VirtualBasicAutoTuner):
        def _stage_final_control_verify(self, candidate):
            self._final_control_verified_key = T._control_key(candidate)
            return {
                "verified": True,
                "control_key": T._control_key(candidate),
                "candidate_key": T._candidate_key(candidate),
            }

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = PassingControlTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        reference = tuner._annotate_candidate_latency(_latency_candidate(
            20.0, 0.25, 0.930, 0.001,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_freq=tuner.QUBIT_FREQ,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=5790,
            qubit_drag_beta=0.0,
        ))
        key = T._candidate_key(reference)
        tuner._maps["latency"] = {"confirmations": [reference]}
        tuner.data["latency_optimization"].update({
            "status": "retained_reference_timing_uncertain",
            "reference": copy.deepcopy(reference),
            "selected": copy.deepcopy(reference),
            "certified_selected": copy.deepcopy(reference),
            "certified_selected_key": list(key),
            "latency_certificate_valid": False,
            "qualified_speedup": False,
            "reference_latency_us": tuner._candidate_latency_us(reference),
            "selected_latency_us": tuner._candidate_latency_us(reference),
            "max_fidelity_loss": params["latency"]["max_fidelity_loss"],
            "diagnostics": [{
                "candidate_key": list(key),
                "accepted": False,
                "loss_ucb": 0.02,
            }],
        })
        tuner.working = {name: reference[name] for name in tuner.initial}

        chosen = tuner._stage_latency_control_screen()
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "latency_unconstrained"
        tuner._finalize(chosen)

    timing = tuner.data["latency_optimization"]
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert timing["certificate_matches_final_tuple"] is False
    assert ("timing_uncertain" in timing["status"]
            or timing["status"].startswith("invalidated_"))


def test_final_latency_certificate_cannot_hide_more_loss_than_its_budget():
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        certified = tuner._annotate_candidate_latency(_latency_candidate(
            8.0, 0.10, 0.930, 0.001,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_freq=tuner.QUBIT_FREQ,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=14475,
            qubit_drag_beta=0.0,
        ))
        final = copy.deepcopy(certified)
        final.update({
            "fidelity": 0.915,
            "fidelity_se": 0.001,
            "fidelity_lcb_95": 0.915 - 1.96 * 0.001,
            "block_fidelities": np.asarray([0.915, 0.915, 0.915]),
            "block_fidelity_ses": np.asarray([0.001, 0.001, 0.001]),
            "block_spread": 0.0,
            "confirmation_blocks": 3,
            "label": "final exact timing-drift replay",
        })
        tuner.data["latency_optimization"].update({
            "status": "selected",
            "reference": copy.deepcopy(certified),
            "reference_latency_us": 21.0,
            "selected": copy.deepcopy(certified),
            "certified_selected": copy.deepcopy(certified),
            "certified_selected_key": list(T._candidate_key(certified)),
            "latency_certificate_valid": True,
            "qualified_speedup": True,
            "max_fidelity_loss": params["latency"]["max_fidelity_loss"],
            "latency_saved_us": 12.0,
            "latency_reduction_fraction": 12.0 / 21.0,
        })
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "latency_unconstrained"

        tuner._finalize(final)

    timing = tuner.data["latency_optimization"]
    assert certified["fidelity"] - final["fidelity"] > params["latency"][
        "max_fidelity_loss"]
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert timing["certificate_matches_final_tuple"] is False


class _LateTimingRecoveryTuner(VirtualBasicAutoTuner):
    """Exact-replay seam for a late timing-certificate regression."""

    def __init__(self, *args, fail_reference_replay=False,
                 reference_replay_fidelity=0.940, **kwargs):
        self.fail_reference_replay = bool(fail_reference_replay)
        self.reference_replay_fidelity = float(reference_replay_fidelity)
        self.reference_replay_candidates = []
        self.control_audit_candidates = []
        super().__init__(*args, **kwargs)

    def _stage_final_current_tuple(self, label, replay_kind, log_stage):
        del log_stage
        self.reference_replay_candidates.append(copy.deepcopy(self.working))
        if self.fail_reference_replay:
            # Match the fail-closed state transition of the production exact-replay
            # helper: no earlier completion provenance may survive a failed attempt.
            self._final_replay_completed = False
            self._final_replay_kind = None
            raise RuntimeError("synthetic fidelity-reference replay fault")
        reference = dict(self.working)
        rows = []
        for index in range(int(self.params["final"]["blocks"])):
            fidelity = self.reference_replay_fidelity
            row = dict(reference)
            row.update({
                "fidelity": fidelity,
                "fidelity_se": 0.001,
                "crossfit_fidelity": fidelity,
                "crossfit_fidelity_se": 0.001,
                "sep_sigma": 4.0,
                "third_blob_excess_ucb_95": 0.0,
                "measurement_index": index,
            })
            rows.append(row)
        replay = self._aggregate(reference, rows, str(label))
        replay["label"] = str(label)
        self._adopt(replay, "timing_reference_recovery")
        self.data["final_candidates"] = [replay]
        self._final_replay_completed = True
        self._final_replay_kind = str(replay_kind)
        self.data["final_confirmation_complete"] = True
        return replay

    def _stage_final_control_verify(self, candidate):
        self.control_audit_candidates.append(copy.deepcopy(candidate))
        self._final_control_verified_key = T._control_key(candidate)
        return {
            "verified": True,
            "candidate_key": T._candidate_key(candidate),
            "control_key": T._control_key(candidate),
        }


def _late_timing_recovery_fixture(fail_reference_replay=False,
                                  reference_replay_fidelity=0.940):
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["latency"].update({
        "max_fidelity_loss": 0.010,
        "max_final_fidelity_drop": 0.010,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.88,
    })
    folder = tempfile.TemporaryDirectory()
    tuner = _LateTimingRecoveryTuner(
        soc=None, soccfg=None, path="q4", outerFolder=folder.name,
        cfg=_base_config(), params=params,
        fail_reference_replay=fail_reference_replay,
        reference_replay_fidelity=reference_replay_fidelity,
    )
    common = {
        "read_pulse_freq": tuner.READ_FREQ,
        "read_pulse_gain": tuner.READ_GAIN,
        "qubit_freq": tuner.QUBIT_FREQ,
        "qubit_pi_freq": tuner.QUBIT_FREQ,
        "qubit_drag_beta": 0.0,
    }
    reference = _latency_candidate(
        20.0, 0.25, 0.940, 0.001,
        qubit_pi_gain=5790, **common)
    fast = _latency_candidate(
        8.0, 0.10, 0.935, 0.001,
        qubit_pi_gain=14475, **common)
    for row in (reference, fast):
        row.update({
            "crossfit_fidelity": row["fidelity"],
            "crossfit_fidelity_se": row["fidelity_se"],
            "crossfit_fidelity_lcb_95": row["fidelity_lcb_95"],
        })
    degraded_fast = copy.deepcopy(fast)
    degraded_fast.update({
        # This remains above the absolute .90/.88 timing floors.  Recovery is
        # triggered specifically because the independent exact replay lost 1.5
        # points relative to the certified fast arm, beyond the one-point allowance.
        "fidelity": 0.920,
        "fidelity_se": 0.001,
        "fidelity_lcb_95": 0.920 - 1.96 * 0.001,
        "crossfit_fidelity": 0.920,
        "crossfit_fidelity_se": 0.001,
        "crossfit_fidelity_lcb_95": 0.920 - 1.96 * 0.001,
        "block_fidelities": np.asarray([0.920, 0.920, 0.920]),
        "block_fidelity_ses": np.asarray([0.001, 0.001, 0.001]),
        "block_crossfit_fidelities": np.asarray([0.920, 0.920, 0.920]),
        "block_crossfit_fidelity_ses": np.asarray([0.001, 0.001, 0.001]),
        "block_spread": 0.0,
        "crossfit_block_spread": 0.0,
        "confirmation_blocks": int(params["final"]["blocks"]),
        "confirmation_batch_complete": True,
        "label": "final exact feedback-reset step-5 replay",
    })
    tuner.data["latency_optimization"].update({
        "enabled": True,
        "status": "selected",
        "reference": copy.deepcopy(reference),
        "reference_latency_us": tuner._candidate_latency_us(reference),
        "selected": copy.deepcopy(fast),
        "certified_selected": copy.deepcopy(fast),
        "certified_selected_key": list(T._candidate_key(fast)),
        "latency_certificate_valid": True,
        "qualified_speedup": True,
        "max_fidelity_loss": 0.010,
        "selected_latency_us": tuner._candidate_latency_us(fast),
        "latency_saved_us": (
            tuner._candidate_latency_us(reference)
            - tuner._candidate_latency_us(fast)),
    })
    tuner.working = {key: degraded_fast[key] for key in tuner.initial}
    tuner._final_replay_completed = True
    tuner._final_replay_kind = "feedback_validated"
    # Exercise the ordinary write path under real discovery/control gates, not the
    # unit-test shortcut in which discovery is disabled.
    tuner._discovery_guard_active = True
    tuner._discovery_status.update({
        "resonator": True,
        "spectroscopy": True,
    })
    return folder, tuner, reference, fast, degraded_fast


def test_late_timing_drop_replays_reference_and_preserves_ordinary_write():
    folder, tuner, reference, fast, degraded_fast = (
        _late_timing_recovery_fixture(False))
    try:
        recovered = tuner._recover_timing_reference_after_failed_final(
            degraded_fast)
        # acquire() performs this exact fresh audit immediately after the recovery
        # hook and before finalization.
        tuner._stage_final_control_verify(recovered)
        tuner._finalize(recovered)
    finally:
        folder.cleanup()

    timing = tuner.data["latency_optimization"]
    assert fast["crossfit_fidelity"] - degraded_fast["crossfit_fidelity"] > 0.010
    assert tuner.reference_replay_candidates
    assert T._candidate_key(tuner.reference_replay_candidates[-1]) == (
        T._candidate_key(reference))
    assert T._candidate_key(recovered) == T._candidate_key(reference)
    assert T._candidate_key(tuner.data["best_found"]) == T._candidate_key(reference)
    assert T._candidate_key(tuner.data["best_found"]) != (
        T._candidate_key(degraded_fast))
    assert timing["status"] == (
        "failed_final_timing_guard_retained_fidelity_reference")
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert timing["timing_certificate_was_active"] is False
    assert timing["final_fidelity_guard_passed"] is True
    assert tuner.control_audit_candidates
    assert T._candidate_key(tuner.control_audit_candidates[-1]) == (
        T._candidate_key(reference))
    assert tuner.data["control_validation"]["verified_for_write"] is True
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligible_tuned"]


def test_failed_late_timing_reference_replay_cannot_write_degraded_fast_arm():
    folder, tuner, _reference, _fast, degraded_fast = (
        _late_timing_recovery_fixture(True))
    try:
        recovered = tuner._recover_timing_reference_after_failed_final(
            degraded_fast)
        tuner._stage_final_control_verify(recovered)
        tuner._finalize(recovered)
    finally:
        folder.cleanup()

    timing = tuner.data["latency_optimization"]
    assert tuner.reference_replay_candidates
    assert T._candidate_key(recovered) == T._candidate_key(degraded_fast)
    assert T._candidate_key(tuner.data["best_found"]) == (
        T._candidate_key(degraded_fast))
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert timing["final_fidelity_guard_passed"] is False
    assert tuner.data["final_stable"] is False
    assert tuner.data["eligible_tuned"] == {}


def test_drift_collapsed_reference_recovery_keeps_better_exact_fast_replay():
    folder, tuner, reference, _fast, degraded_fast = (
        _late_timing_recovery_fixture(
            False, reference_replay_fidelity=0.880))
    try:
        recovered = tuner._recover_timing_reference_after_failed_final(
            degraded_fast)
        tuner._stage_final_control_verify(recovered)
        tuner._finalize(recovered)
    finally:
        folder.cleanup()

    timing = tuner.data["latency_optimization"]
    recovery = timing["reference_recovery"]
    assert tuner.reference_replay_candidates
    assert T._candidate_key(tuner.reference_replay_candidates[-1]) == (
        T._candidate_key(reference))
    assert recovery["attempted"] is True
    assert recovery["passed"] is True
    assert recovery["adopted"] is False
    assert T._candidate_key(recovery["original_final"]) == (
        T._candidate_key(degraded_fast))
    assert T._candidate_key(recovery["recovered_reference"]) == (
        T._candidate_key(reference))
    assert recovery["original_rank"] > recovery["recovered_rank"]
    assert recovery["comparison_estimator"].startswith("two_fold_crossfit")
    assert recovery["reason"]
    assert T._candidate_key(recovered) == T._candidate_key(degraded_fast)
    assert T._candidate_key(tuner.data["best_found"]) == (
        T._candidate_key(degraded_fast))
    assert tuner.data["best_found"]["crossfit_fidelity"] > 0.880
    assert timing["status"] == (
        "failed_final_timing_guard_retained_exact_final")
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligible_tuned"]


def test_retained_reference_guard_failure_demotes_exact_tuple_without_abort():
    folder, tuner, _reference, fast, degraded_fast = (
        _late_timing_recovery_fixture(False))
    try:
        timing = tuner.data["latency_optimization"]
        timing.update({
            "status": "retained_reference_no_qualified_candidate",
            "reference": copy.deepcopy(fast),
            "selected": copy.deepcopy(fast),
            "certified_selected": copy.deepcopy(fast),
            "certified_selected_key": list(T._candidate_key(fast)),
            "latency_certificate_valid": True,
            "qualified_speedup": False,
        })
        recovered = tuner._recover_timing_reference_after_failed_final(
            degraded_fast)
        tuner._stage_final_control_verify(recovered)
        tuner._finalize(recovered)
    finally:
        folder.cleanup()

    timing = tuner.data["latency_optimization"]
    recovery = timing["reference_recovery"]
    assert tuner.reference_replay_candidates == []
    assert T._candidate_key(recovered) == T._candidate_key(degraded_fast)
    assert timing["status"] == (
        "failed_final_timing_guard_retained_exact_final")
    assert timing["latency_certificate_valid"] is False
    assert timing["qualified_speedup"] is False
    assert recovery["attempted"] is False
    assert recovery["passed"] is False
    assert recovery["adopted"] is False
    assert "reference" in recovery["reason"]
    assert tuner.data["latency_optimization"][
        "final_fidelity_guard_passed"] is True
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligible_tuned"]


def test_constrained_reference_recovery_marks_final_leakage_replay_complete():
    class ConstrainedRecoveryTuner(_LateTimingRecoveryTuner):
        def _stage_operational_leakage_verify(self, allow_fallback=True):
            del allow_fallback
            self._leakage_verified_candidate_key = T._candidate_key(self.working)
            self.data["leakage"].update({
                "verified": True,
                "selection_safe": True,
                "verified_candidate_key": list(
                    self._leakage_verified_candidate_key),
            })
            return True

        def _stage_final_constrained(self):
            return self._stage_final_current_tuple(
                "final exact leakage-screened step-5 replay",
                "leakage_constrained", "final_safe")

    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["leakage"] = {
        "enabled": False,
        "operational_enabled": True,
        "required_for_write": True,
    }
    folder = tempfile.TemporaryDirectory()
    try:
        tuner = ConstrainedRecoveryTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder.name,
            cfg=_base_config(), params=params,
        )
        common = {
            "read_pulse_freq": tuner.READ_FREQ,
            "read_pulse_gain": tuner.READ_GAIN,
            "qubit_freq": tuner.QUBIT_FREQ,
            "qubit_pi_freq": tuner.QUBIT_FREQ,
            "qubit_drag_beta": 0.0,
        }
        reference = _latency_candidate(
            20.0, 0.25, 0.940, 0.001,
            qubit_pi_gain=5790, **common)
        fast = _latency_candidate(
            8.0, 0.10, 0.935, 0.001,
            qubit_pi_gain=14475, **common)
        degraded_fast = copy.deepcopy(fast)
        degraded_fast.update({
            "fidelity": 0.920,
            "fidelity_se": 0.001,
            "fidelity_lcb_95": 0.920 - 1.96 * 0.001,
            "crossfit_fidelity": 0.920,
            "crossfit_fidelity_se": 0.001,
            "crossfit_fidelity_lcb_95": 0.920 - 1.96 * 0.001,
            "label": "final exact leakage-screened step-5 replay",
        })
        fast.update({
            "crossfit_fidelity": 0.935,
            "crossfit_fidelity_se": 0.001,
            "crossfit_fidelity_lcb_95": 0.935 - 1.96 * 0.001,
        })
        tuner.data["latency_optimization"].update({
            "enabled": True,
            "status": "selected",
            "reference": copy.deepcopy(reference),
            "selected": copy.deepcopy(fast),
            "certified_selected": copy.deepcopy(fast),
            "certified_selected_key": list(T._candidate_key(fast)),
            "latency_certificate_valid": True,
            "qualified_speedup": True,
            "max_fidelity_loss": 0.010,
        })
        tuner.working = {key: degraded_fast[key] for key in tuner.initial}
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "leakage_constrained"
        tuner.data["leakage"]["final_replay_complete"] = False

        recovered = tuner._recover_timing_reference_after_failed_final(
            degraded_fast)
    finally:
        folder.cleanup()

    assert T._candidate_key(recovered) == T._candidate_key(reference)
    assert tuner.data["leakage"]["verified"] is True
    assert tuner.data["leakage"]["final_replay_complete"] is True
    assert tuner._final_replay_kind == "leakage_constrained"


def test_not_run_latency_uses_the_ordinary_exact_final_write_policy():
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        candidate = dict(tuner.working)
        candidate["read_pulse_freq"] += 0.10
        blocks = []
        for index in range(params["final"]["blocks"]):
            row = dict(candidate)
            row.update({
                "fidelity": 0.895,
                "fidelity_se": 0.002,
                "sep_sigma": 3.0,
                "third_blob_excess_ucb_95": 0.01,
                "measurement_index": index,
            })
            blocks.append(row)
        final = T.BasicAutoTuner._aggregate(
            candidate, blocks, "final exact ordinary-fidelity fallback")
        assert final["fidelity"] < params["latency"][
            "minimum_mean_fidelity"]
        assert final["fidelity_lcb_95"] > params["final"].get(
            "minimum_write_fidelity_lcb", 0.60)
        tuner.data["latency_optimization"]["status"] = "not_run"
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"

        tuner._finalize(final)

    assert tuner.data["latency_optimization"].get(
        "latency_certificate_valid", False) is False
    assert tuner.data["eligibility"]["latency_final_fidelity_guard"] is True
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligible_tuned"] == {
        "read_pulse_freq": candidate["read_pulse_freq"],
    }


def test_direct_leakage_verify_recalibrates_ef_for_final_latency_control():
    class FreshEfCalibrationTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.ef_calibration_calls = []
            self.leakage_measurement_calibrations = []
            super().__init__(*args, **kwargs)

        def _calibrate_ef_transition(self, candidate):
            key = T._control_key(candidate)
            self.ef_calibration_calls.append(key)
            return {
                "control_key": key,
                "ef_frequency": float(candidate["qubit_pi_freq"]) - 200.0,
                "ef_gain": 9000,
                "ge_reference_gain": 4000,
                "anharmonicity_mhz": -200.0,
            }

        def _measure_leakage_candidate(self, candidate, ef_calibration, shots,
                                       reference_shots, label):
            del shots, reference_shots, label
            assert tuple(ef_calibration["control_key"]) == T._control_key(candidate)
            self.leakage_measurement_calibrations.append(
                tuple(ef_calibration["control_key"]))
            row = dict(candidate)
            row.update({
                "valid": True,
                "leakage_safe": True,
                "single_p2_ucb": 0.005,
                "amplified_p2_ucb": 0.010,
                "third_blob_excess_ucb": 0.010,
            })
            return row

    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": True,
        "operational_enabled": False,
        "verify_blocks": 2,
        "verify_shots": 31,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = FreshEfCalibrationTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        final_latency_control = T._with_candidate(
            tuner.working,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=14475,
            sigma=0.10,
            qubit_drag_beta=0.0,
        )
        stale_control = T._with_candidate(
            final_latency_control, qubit_pi_gain=5790, sigma=0.25)
        tuner._leakage_ef_calibration = {
            "control_key": T._control_key(stale_control),
            "ef_frequency": tuner.QUBIT_FREQ - 199.0,
            "ef_gain": 8000,
        }
        tuner.working = dict(final_latency_control)

        passed = tuner._stage_leakage_verify()

    final_key = T._control_key(final_latency_control)
    assert passed is True
    assert tuner.ef_calibration_calls == [final_key]
    assert tuner.leakage_measurement_calibrations == [final_key, final_key]
    assert tuple(tuner._leakage_ef_calibration["control_key"]) == final_key
    assert tuner._leakage_verified_candidate_key == T._candidate_key(
        final_latency_control)
    assert tuner.data["leakage"]["verified"] is True
    assert tuner.data["leakage"]["verification_errors"] == []


def test_single_shot_feedback_buffers_return_only_the_final_readout():
    """Three reset reads per shot must never leak into the step-5 histograms."""
    program = object.__new__(T.SingleShotProgram)
    program.cfg = {
        "read_length": 1.0, "ro_chs": [0], "expts": 2, "reps": 2,
        "reset_mode": "feedback", "reset_max_iters": 3,
        "single_shot_state_order": "ge",
    }
    program.us2cycles = lambda *_args, **_kwargs: 1
    # [reset0, reset1, reset2, FINAL] for each rep and experiment.
    program.di_buf = [np.arange(16, dtype=float)]
    program.dq_buf = [100.0 + np.arange(16, dtype=float)]
    shot_i, shot_q = program.collect_shots()
    assert shot_i.tolist() == [[3.0, 7.0], [11.0, 15.0]]
    assert shot_q.tolist() == [[103.0, 107.0], [111.0, 115.0]]


def test_sequence_feedback_buffers_return_only_the_final_readout():
    program = types.SimpleNamespace(
        di_buf=[np.arange(8, dtype=float)],
        dq_buf=[50.0 + np.arange(8, dtype=float)],
        us2cycles=lambda *_args, **_kwargs: 1,
    )
    cfg = {
        "read_length": 1.0, "ro_chs": [0], "reps": 2,
        "reset_mode": "feedback", "reset_max_iters": 3,
    }
    shot_i, shot_q = T._shots_from_program(program, cfg)
    assert shot_i.tolist() == [3.0, 7.0]
    assert shot_q.tolist() == [53.0, 57.0]


def test_sequence_feedback_declares_its_frozen_reset_waveform():
    """The real QICK upload must not reference an undeclared reset waveform."""
    program = object.__new__(T.BasicSequenceProgram)
    program.cfg = {
        "shots": 10, "reps": 10, "reset_mode": "feedback",
        "sigma": 0.10, "qubit_drag_beta": 0.02,
        "reset_pi_sigma": 0.25, "reset_pi_drag_beta": 0.04,
        "sequence_ops": [],
    }
    program.synci = lambda *_args, **_kwargs: None
    calls = []
    original_declare = T._declare_common
    original_add = T.add_qubit_gaussian
    T._declare_common = lambda *_args, **_kwargs: None
    T.add_qubit_gaussian = lambda _program, name="qubit", **kwargs: (
        calls.append((name, kwargs)) or 1)
    try:
        program.initialize()
    finally:
        T._declare_common = original_declare
        T.add_qubit_gaussian = original_add

    assert calls[0] == ("qubit", {})
    assert calls[1] == ("qubit_reset", {
        "sigma_us": 0.25, "drag_beta": 0.04,
    })


def test_feedback_profile_is_bound_to_frequency_and_length_not_scoring_gain():
    cfg = _base_config()
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        profile_key = tuner._reset_profile_signature(tuner.working)
        tuner._reset_runtime = {
            "reset_mode": "feedback", "reset_threshold_raw": 1234,
            "reset_oper": "lower", "reset_ground_below": True,
            "reset_max_iters": 3, "reset_pi_freq": 2534.5,
            "reset_pi_gain": 5790, "reset_pi_sigma": 0.25,
            "reset_pi_drag_beta": 0.04,
            "reset_read_pulse_gain": 5000,
            "reset_read_pulse_freq": tuner.working["read_pulse_freq"],
            "reset_profile_key": profile_key,
        }
        tuner._reset_profiles[profile_key] = copy.deepcopy(tuner._reset_runtime)
        tuner._reset_readout_key = tuner._reset_readout_signature(tuner.working)
        exact = tuner._cfg_for(tuner.working)
        gain_changed = tuner._cfg_for(T._with_candidate(
            tuner.working,
            read_pulse_gain=tuner.working["read_pulse_gain"] + 1000))
        frequency_changed = tuner._cfg_for(T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.working["read_pulse_freq"] + 0.1))
    assert exact["reset_mode"] == "feedback"
    assert exact["reset_pi_gain"] == 5790
    assert gain_changed["reset_mode"] == "feedback"
    assert gain_changed["reset_read_pulse_gain"] == 5000
    assert frequency_changed["reset_mode"] == "passive"
    assert tuner._last_compiled_reset_runtime["reset_mode"] == "passive"


def test_feedback_exact_ab_rejects_the_observed_step5_collapse():
    """A residual-reset pass cannot authorize a 94%-to-53% scoring collapse."""
    params = copy.deepcopy(FAST_PARAMS)
    params["reset"] = {
        "enabled": True, "exact_qualification_shots": 101,
        "exact_qualification_blocks": 2,
        "exact_min_feedback_fidelity": 0.70,
        "exact_max_fidelity_loss": 0.03,
        "exact_max_block_loss": 0.08,
        "exact_min_separation_ratio": 0.70,
        "exact_catastrophic_loss": 0.10,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        profile_key = tuner._reset_profile_signature(tuner.working)
        runtime = {
            "reset_mode": "feedback", "reset_profile_key": profile_key,
            "reset_threshold_raw": 1234, "reset_oper": "lower",
            "reset_ground_below": True, "reset_max_iters": 3,
            "reset_pi_freq": tuner.working["qubit_pi_freq"],
            "reset_pi_gain": tuner.working["qubit_pi_gain"],
            "reset_pi_sigma": tuner.working["sigma"],
            "reset_read_pulse_freq": tuner.working["read_pulse_freq"],
            "reset_read_pulse_gain": tuner.working["read_pulse_gain"],
        }

        def measured(candidate, shots, label, state_order="ge", archive=True):
            del shots, label, state_order, archive
            feedback = not tuner._feedback_profiles_suspended
            fidelity = 0.53 if feedback else 0.94
            row = dict(candidate)
            row.update({
                "fidelity": fidelity, "fidelity_se": 0.005,
                "fidelity_lcb_95": fidelity - 0.0098,
                "sep_sigma": 0.08 if feedback else 5.8,
                "measurement_index": 0,
            })
            return row

        tuner._measure_candidate = measured
        activated = tuner._qualify_feedback_runtime(
            tuner.working, runtime, "regression bundle")
        compiled = tuner._cfg_for(tuner.working)

    assert activated is False
    assert tuner._feedback_disqualified is True
    assert profile_key not in tuner._reset_profiles
    assert compiled["reset_mode"] == "passive"
    qualification = tuner.data["reset"]["exact_step5_qualifications"][-1]
    assert qualification["catastrophic_path_mismatch"] is True
    assert qualification["passive"]["fidelity"] > 0.93
    assert qualification["feedback"]["fidelity"] < 0.54


def test_single_shot_feedback_uses_fixed_reset_gain_then_restores_scoring_gain():
    program = object.__new__(SS.SingleShotProgram)
    program.cfg = {
        "reset_mode": "feedback", "reset_read_pulse_gain": 5000,
        "read_pulse_gain": 7300, "read_pulse_freq": 7249.1,
        "qubit_ch": 1, "qubit_freq": 2534.7,
        "qubit_pi_freq": 2534.7, "qubit_pi_gain": 5800,
        "qubit_gain": 0, "ro_chs": [0], "res_ch": 0,
        "reset_threshold_raw": 123, "reset_max_iters": 3,
        "reset_pi_gain": 5800, "relax_delay": 1000.0,
        "adc_trig_offset": 0.5,
    }
    program.r_gain = 2
    program.r_gain2 = 3
    program.ch_page = lambda _channel: 0
    program.mathi = lambda *_args, **_kwargs: None
    program.set_pulse_registers = lambda *_args, **_kwargs: None
    program.freq2reg = lambda value, **_kwargs: value
    program.deg2reg = lambda value, **_kwargs: value
    program.us2cycles = lambda value, **_kwargs: value
    program.pulse = lambda *_args, **_kwargs: None
    program.sync_all = lambda *_args, **_kwargs: None
    program.measure = lambda *_args, **_kwargs: None
    calls = []
    original_set = SS.set_readout_pulse
    original_reset = SS.active_reset.active_reset_block
    original_park = SS.ff_pulse.play_static_park
    try:
        SS.set_readout_pulse = lambda prog, *args, gain=None, **kwargs: calls.append(
            int(prog.cfg["read_pulse_gain"] if gain is None else gain))
        SS.active_reset.active_reset_block = lambda *_args, **_kwargs: None
        SS.ff_pulse.play_static_park = lambda *_args, **_kwargs: None
        program.body()
    finally:
        SS.set_readout_pulse = original_set
        SS.active_reset.active_reset_block = original_reset
        SS.ff_pulse.play_static_park = original_park
    assert calls == [5000, 7300]


def test_rabi_sweep_feedback_restores_the_swept_gain_and_scoring_readout():
    program = types.SimpleNamespace(cfg={
        "reset_read_pulse_freq": 7249.1,
        "read_pulse_freq": 7249.1,
        "reset_read_pulse_gain": 5000,
        "read_pulse_gain": 7300,
        "qubit_ch": 1, "ro_chs": [0],
        "reset_threshold_raw": 123, "reset_max_iters": 3,
        "reset_pi_freq": 2534.7, "reset_pi_gain": 5800,
        "qubit_pi_gain": 9200, "rabi_drive_freq": 2534.8,
    })
    program.ch_page = lambda _channel: 0
    program.sreg = lambda _channel, _name: 2
    math = []
    program.mathi = lambda *args: math.append(args)
    program.set_pulse_registers = lambda *_args, **_kwargs: None
    program.freq2reg = lambda value, **_kwargs: value
    program.deg2reg = lambda value, **_kwargs: value
    readout_gains = []
    original_set = RI.set_readout_pulse
    original_reset = RI.active_reset.active_reset_block
    try:
        RI.set_readout_pulse = lambda prog, *args, gain=None, **kwargs: (
            readout_gains.append(int(
                prog.cfg["read_pulse_gain"] if gain is None else gain)))
        RI.active_reset.active_reset_block = lambda *_args, **_kwargs: None
        RI._rabi_feedback_reset(program)
    finally:
        RI.set_readout_pulse = original_set
        RI.active_reset.active_reset_block = original_reset
    assert readout_gains == [5000, 7300]
    assert math == [(0, 27, 2, "+", 0), (0, 2, 27, "+", 0)]


def test_reset_probe_uses_the_full_raw_distribution_not_last_dmem_word():
    probe = object.__new__(ARP.ActiveResetProbe)
    probe._read_dmem = lambda _addr: 999999
    program = types.SimpleNamespace(
        di_buf=[np.asarray([-20, -19, -18, -17, -16] * 5, dtype=np.int64)],
        dq_buf=[np.asarray([4, 3, 2, 1, 0] * 5, dtype=np.int64)],
    )
    lower, upper = probe._raw_shots(program)
    assert lower.size == 25 and upper.size == 25
    assert int(np.median(lower)) == -18
    assert int(np.median(upper)) == 2
    assert 999999 not in lower and 999999 not in upper


def test_reset_raw_threshold_maximizes_held_shot_assignment():
    discrimination = ARP.ActiveResetProbe._fit_raw_discriminator(
        np.asarray([-5, -4, -3, -2, 8]),
        np.asarray([2, 3, 4, 5, -8]),
    )
    assert discrimination["ground_below"] is True
    assert np.isclose(discrimination["fidelity"], 0.8)
    threshold = discrimination["threshold_raw"]
    assert -2 < threshold <= 2


def test_active_reset_primitive_always_clears_measurement_photons():
    class FakeProgram:
        cfg = {
            "res_ch": 0, "qubit_ch": 1, "adc_trig_offset": 0.5,
            "reset_thermalization_us": 17.5,
        }
        soccfg = {"readouts": [{"tproc_ch": 2}]}

        def __init__(self):
            self.syncs = []
            self.measurements = 0

        def ch_page(self, _channel): return 0
        def us2cycles(self, value): return float(value)
        def regwi(self, *_args, **_kwargs): pass
        def measure(self, *_args, **_kwargs): self.measurements += 1
        def read(self, *_args, **_kwargs): pass
        def condj(self, *_args, **_kwargs): pass
        def pulse(self, *_args, **_kwargs): pass
        def label(self, *_args, **_kwargs): pass
        def sync_all(self, delay): self.syncs.append(float(delay))

    program = FakeProgram()
    active_reset.active_reset_block(
        program, threshold_raw=123, max_iters=3)
    assert program.measurements == 3
    assert np.isclose(program.syncs[-1], 17.5)
    default_program = FakeProgram()
    default_program.cfg = dict(FakeProgram.cfg)
    default_program.cfg.pop("reset_thermalization_us")
    active_reset.active_reset_block(
        default_program, threshold_raw=123, max_iters=1)
    assert np.isclose(default_program.syncs[-1], 25.0)


def test_concise_console_hides_diagnostics_but_keeps_the_saved_report():
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        output = io.StringIO()
        with redirect_stdout(output):
            tuner._log("internal_detail", "WARN", "full diagnostic text")
        assert output.getvalue() == ""
        assert tuner.data["report"][-1]["message"] == "full diagnostic text"
        tuner.params["console"]["verbosity"] = "detailed"
        with redirect_stdout(output):
            tuner._log("internal_detail", "WARN", "visible while debugging")
        assert "visible while debugging" in output.getvalue()


def test_self_contained_diagnostic_bundle_round_trips_raw_iq_and_run_data():
    """One returned HDF5 must contain both raw shots and the full run archive."""
    params = copy.deepcopy(FAST_PARAMS)
    params.update({
        "reset": {"enabled": False},
        "diagnostics": {
            "enabled": True, "force_without_hardware": True,
            "compression": "gzip", "compression_level": 1,
            "flush_every_records": 1,
        },
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        measured = tuner._measure_candidate(
            tuner.working, shots=53, label="diagnostic round trip",
            state_order="eg")
        tuner.data["diagnostic_test_sentinel"] = {"fidelity": measured["fidelity"]}
        tuner.save_data()
        loaded = T.load_basic_autotuner_diagnostic(
            tuner.diagnostic_fname, load_raw=True)

    assert loaded["complete"] is True
    assert loaded["autotuner_revision"] == T.BASIC_AUTOTUNER_REVISION
    assert loaded["run_data"]["diagnostic_test_sentinel"]["fidelity"] == (
        measured["fidelity"])
    assert len(loaded["raw_records"]) == 1
    record = loaded["raw_records"][0]
    assert record["kind"] == "single_shot_pair"
    assert record["metadata"]["label"] == "diagnostic round trip"
    assert record["metadata"]["state_order"] == "eg"
    assert record["candidate"]["read_length"] == tuner.working["read_length"]
    assert set(record["raw"]) == {
        "ground_i", "ground_q", "excited_i", "excited_q"}
    assert all(np.asarray(value).shape == (53,)
               for value in record["raw"].values())

def test_static_fast_flux_is_replayed_but_never_tuned():
    """A signed park value is fixed context and survives every candidate config."""
    cfg = _base_config()
    cfg["ff_park_gain"] = -7341
    untouched = copy.deepcopy(cfg)
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        tuner._preflight()
        run_cfg = tuner._cfg_for(T._with_candidate(
            tuner.working, qubit_pi_freq=tuner.working["qubit_pi_freq"] + 1.0,
            qubit_pi_gain=tuner.working["qubit_pi_gain"] + 1000))

    assert cfg == untouched
    assert run_cfg["ff_ch"] == 3
    assert run_cfg["ff_park_gain"] == -7341
    assert "ff_park_gain" not in T.TUNED_KEYS
    context = tuner.data["fast_flux_operating_point"]
    assert context == {
        "mode": "static_park", "configured": True, "ff_ch": 3,
        "ff_park_gain": -7341, "tuned": False,
    }


def test_static_fast_flux_helper_forces_zero_and_nonzero_park():
    """Zero must also be emitted so a stale nonzero latched output is cleared."""
    class FakeProgram:
        def __init__(self, gain):
            self.cfg = {"ff_ch": 3, "ff_nqz": 1, "ff_park_gain": gain}
            self.events = []

        def declare_gen(self, **kwargs):
            self.events.append(("declare", kwargs))

        def set_pulse_registers(self, **kwargs):
            self.events.append(("registers", kwargs))

        def us2cycles(self, value, **kwargs):
            del kwargs
            return int(round(100 * float(value)))

        def pulse(self, **kwargs):
            self.events.append(("pulse", kwargs))

        def sync_all(self, cycles):
            self.events.append(("sync", cycles))

    for gain in (0, -7341, 8123):
        program = FakeProgram(gain)
        ff_pulse.declare_static_park(program)
        ff_pulse.play_static_park(program, settle_us=0.05)
        registers = [event[1] for event in program.events
                     if event[0] == "registers"]
        assert len(registers) == 1
        assert registers[0]["gain"] == gain
        assert any(event[0] == "pulse" for event in program.events)


def test_dynamic_flux_excursion_is_not_mistaken_for_static_park():
    cfg = _base_config()
    cfg["ff_park_gain"] = 4200
    cfg["ff_hold_gain"] = 7600
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        try:
            tuner._preflight()
        except ValueError as exc:
            assert "dynamic flux excursion" in str(exc)
        else:
            raise AssertionError("dynamic ff_hold_gain was silently treated as park")


def test_global_discovery_recovers_exact_far_frequency_seeds():
    """Discovery must use its device envelope, not a window around BaseConfig."""
    cfg = _base_config()
    cfg.update({
        "read_pulse_freq": 7000.0,
        "qubit_freq": 2400.7,
        "qubit_pi_freq": 2400.7,
    })
    params = copy.deepcopy(FAST_PARAMS)
    params["resonator"].update({
        "search_min_mhz": 7244.0, "search_max_mhz": 7253.0,
        "search_step_mhz": 0.05,
    })
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        resonator = tuner._stage_resonator()
        spectroscopy = tuner._stage_spectroscopy()
        tuner._stage_iq_rabi()

    assert abs(resonator - tuner.READ_FREQ) <= 0.08
    assert all(2240.0 <= value <= 2580.0 for value in spectroscopy)
    assert any(abs(value - tuner.QUBIT_FREQ) <= 0.25
               for value in spectroscopy)
    assert all(abs(value - 2400.7) > 100.0 for value in spectroscopy)
    assert any(abs(candidate["qubit_pi_freq"] - tuner.QUBIT_FREQ) <= 0.8
               for candidate in tuner._rabi_candidates)
    assert tuner.data["maps"]["resonator"]["selection_confirmed"] is True
    assert tuner.data["maps"]["spectroscopy"]["selection_confirmed"] is True


def test_relative_100mhz_prior_recovers_without_device_frequency_constants():
    """Production discovery is centered on initialize.py, not hardcoded to q4."""
    cfg = _base_config()
    cfg.update({
        # Both physical features are far beyond the old local/wide scans but remain
        # inside the explicitly accepted +/-100-MHz initialization contract.
        "read_pulse_freq": 7160.0,
        "qubit_freq": 2450.0,
        "qubit_pi_freq": 2450.0,
    })
    params = _relative_100mhz_search_params()
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        resonator = tuner._stage_resonator()
        spectroscopy = tuner._stage_spectroscopy()
        tuner._stage_iq_rabi()

    assert abs(resonator - tuner.READ_FREQ) <= 0.08
    assert any(abs(value - tuner.QUBIT_FREQ) <= 0.25
               for value in spectroscopy)
    assert any(abs(candidate["qubit_pi_freq"] - tuner.QUBIT_FREQ) <= 0.8
               for candidate in tuner._rabi_candidates)
    resonator_map = tuner.data["maps"]["resonator"]
    spectroscopy_map = tuner.data["maps"]["spectroscopy"]
    assert resonator_map["search_mode"] == "relative_prior"
    assert spectroscopy_map["search_mode"] == "relative_prior"
    assert resonator_map["allowed_min_mhz"] == 7060.0
    assert resonator_map["allowed_max_mhz"] == 7260.0
    assert spectroscopy_map["allowed_min_mhz"] == 2350.0
    assert spectroscopy_map["allowed_max_mhz"] == 2550.0
    assert all(2350.0 <= value <= 2550.0 for value in spectroscopy)
    # The resonator needed the outer adaptive expansion rather than a hidden q4 band.
    attempted = resonator_map["search_attempt_acceptance_bounds_mhz"]
    assert np.any(np.all(np.isclose(attempted, [7060.0, 7260.0]), axis=1))


def test_stronger_wrong_resonator_backtracks_to_the_qubit_coupled_branch():
    """A deep 7108-MHz distractor must not hide the 7249-MHz q4 resonator."""
    class DistractorResonatorTuner(VirtualBasicAutoTuner):
        DISTRACTOR_FREQ = 7108.4

        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate
            frequencies = np.asarray(freqs_mhz, dtype=float)
            self.virtual_shots += int(shots) * frequencies.size
            distractor = 1.0 - 0.72 / (
                1.0 + 1j * (frequencies - self.DISTRACTOR_FREQ) / 0.30)
            target = 1.0 - 0.30 / (
                1.0 + 1j * (frequencies - self.READ_FREQ) / 0.35)
            return distractor * target

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            if abs(float(candidate["read_pulse_freq"]) - self.READ_FREQ) <= 2.0:
                return super()._acquire_spectroscopy(
                    freqs_mhz, candidate, shots, gain, pulse_length_us)
            del gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            self.virtual_shots += int(shots) * frequencies.size
            offset = frequencies - np.mean(frequencies)
            # The wrong resonator branch has no reproducible qubit response.
            return ((0.2 + 5e-5 * offset)
                    + 1j * (0.1 - 3e-5 * offset))

    cfg = _base_config()
    cfg["read_pulse_freq"] = 7200.0
    params = _relative_100mhz_search_params()
    with tempfile.TemporaryDirectory() as folder:
        tuner = DistractorResonatorTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        tuner._stage_resonator()
        candidates = [
            float(row["read_pulse_freq"])
            for row in tuner._resonator_candidates]
        # The intentionally deeper wrong notch ranks first, proving this is not a
        # nearest/strongest-notch shortcut disguised as branch search.
        assert abs(candidates[0] - tuner.DISTRACTOR_FREQ) <= 0.08
        assert any(abs(value - tuner.READ_FREQ) <= 0.08 for value in candidates)
        assert tuner.data["maps"]["resonator"]["selection_confirmed"] is False

        spectroscopy = tuner._stage_spectroscopy()
        tuner._stage_iq_rabi()
        tuner._stage_readout_grid(
            "readout_grid", local=False, record_evidence=False)

    assert abs(tuner._resonator_seed - tuner.READ_FREQ) <= 0.08
    assert abs(tuner._discovery_readout["read_pulse_freq"]
               - tuner.READ_FREQ) <= 0.08
    assert any(abs(value - tuner.QUBIT_FREQ) <= 0.25
               for value in spectroscopy)
    branch_map = tuner.data["maps"]["spectroscopy"]
    assert np.allclose(
        branch_map["resonator_branch_frequencies_mhz"],
        [tuner.DISTRACTOR_FREQ, tuner.READ_FREQ], atol=0.08)
    assert np.array_equal(
        branch_map["resonator_branch_valid"], [False, True])
    assert branch_map["branch_backtracking_complete"] is True
    assert tuner.data["maps"]["resonator"]["selection_confirmed"] is True
    assert abs(tuner.working["read_pulse_freq"] - tuner.READ_FREQ) <= 0.6
    assert abs(tuner.working["read_pulse_freq"] - 7154.0) > 50.0


def test_multiple_resonators_without_a_qubit_branch_fail_closed():
    class NoQubitBranchTuner(VirtualBasicAutoTuner):
        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            frequencies = np.asarray(freqs_mhz, dtype=float)
            first = 1.0 - 0.70 / (
                1.0 + 1j * (frequencies - 7108.4) / 0.30)
            second = 1.0 - 0.32 / (
                1.0 + 1j * (frequencies - self.READ_FREQ) / 0.35)
            return first * second

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            offset = frequencies - np.mean(frequencies)
            return ((0.2 + 5e-5 * offset)
                    + 1j * (0.1 - 3e-5 * offset))

    cfg = _base_config()
    cfg["read_pulse_freq"] = 7200.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = NoQubitBranchTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=_relative_100mhz_search_params(),
        )
        tuner._stage_resonator()
        assert len(tuner._resonator_candidates) == 2
        try:
            tuner._stage_spectroscopy()
        except RuntimeError as exc:
            assert "none of 2 confirmed resonator branches" in str(exc)
        else:
            raise AssertionError("featureless resonator branches were accepted")

    assert tuner._spec_candidates_mhz == []
    assert tuner._discovery_status["spectroscopy"] is False
    assert tuner.data["maps"]["spectroscopy"]["search_complete"] is False
    assert tuner.data["maps"]["spectroscopy"]["selection_confirmed"] is False
    assert tuner.data["maps"]["resonator"]["selection_confirmed"] is False


def test_two_spectral_branches_are_resolved_by_coherent_rabi():
    class RabiResolvingTuner(VirtualBasicAutoTuner):
        DISTRACTOR_FREQ = 7108.4

        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            frequencies = np.asarray(freqs_mhz, dtype=float)
            first = 1.0 - 0.72 / (
                1.0 + 1j * (frequencies - self.DISTRACTOR_FREQ) / 0.30)
            second = 1.0 - 0.30 / (
                1.0 + 1j * (frequencies - self.READ_FREQ) / 0.35)
            return first * second

        def _acquire_iq_chevron(self, freqs_mhz, gains, candidate, shots):
            if abs(float(candidate["read_pulse_freq"]) - self.READ_FREQ) <= 2.0:
                return super()._acquire_iq_chevron(
                    freqs_mhz, gains, candidate, shots)
            frequencies = np.asarray(freqs_mhz, dtype=float)
            amplitudes = np.asarray(gains, dtype=float)
            return (np.full((frequencies.size, amplitudes.size), 12.0),
                    np.full((frequencies.size, amplitudes.size), -7.0))

    cfg = _base_config()
    cfg["read_pulse_freq"] = 7200.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = RabiResolvingTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=_relative_100mhz_search_params(),
        )
        tuner._stage_resonator()
        tuner._stage_spectroscopy()
        assert len(tuner._spectroscopy_branch_attempts) == 2
        assert tuner.data["maps"]["resonator"]["selection_confirmed"] is False
        tuner._stage_iq_rabi()

    assert abs(tuner._resonator_seed - tuner.READ_FREQ) <= 0.08
    assert tuner.data["maps"]["resonator"]["selection_confirmed"] is True
    assert tuner.data["maps"]["resonator"]["selected_by"].startswith(
        "coherent Rabi")
    rabi_map = tuner.data["maps"]["iq_rabi"]
    assert np.allclose(
        rabi_map["resonator_branch_frequencies_mhz"],
        [tuner.DISTRACTOR_FREQ, tuner.READ_FREQ], atol=0.08)
    assert np.array_equal(
        rabi_map["resonator_branch_coherent"], [False, True])
    assert not np.isfinite(rabi_map["resonator_branch_step5_lcb"][0])
    assert rabi_map["resonator_branch_step5_lcb"][1] > 0.50
    assert rabi_map["branch_selection_confirmed"] is True


def test_relative_100mhz_prior_rejects_the_old_out_of_contract_seeds():
    """The formerly supplied 7000/2400.7 seeds are explicitly outside +/-100."""
    cfg = _base_config()
    cfg.update({
        "read_pulse_freq": 7000.0,
        "qubit_freq": 2400.7,
        "qubit_pi_freq": 2400.7,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=_relative_100mhz_search_params(),
        )
        for stage in (tuner._stage_resonator, tuner._stage_spectroscopy):
            try:
                stage()
            except RuntimeError:
                pass
            else:
                raise AssertionError(
                    "an out-of-contract physical feature was accepted")

    assert tuner.data["maps"]["resonator"]["allowed_min_mhz"] == 6900.0
    assert tuner.data["maps"]["resonator"]["allowed_max_mhz"] == 7100.0
    assert tuner.data["maps"]["spectroscopy"]["allowed_min_mhz"] == 2300.7
    assert tuner.data["maps"]["spectroscopy"]["allowed_max_mhz"] == 2500.7
    assert tuner._discovery_status["resonator"] is False
    assert tuner._discovery_status["spectroscopy"] is False


def test_relative_prior_padding_fits_exact_edges_but_cannot_expand_policy():
    """A line at +/-100 is fittable; a line at +101 remains unauthorized."""
    class ExactEdgeTuner(VirtualBasicAutoTuner):
        READ_FREQ = _base_config()["read_pulse_freq"] + 100.0
        QUBIT_FREQ = _base_config()["qubit_pi_freq"] + 100.0

    class PaddingOnlyTuner(VirtualBasicAutoTuner):
        READ_FREQ = _base_config()["read_pulse_freq"] + 101.0
        QUBIT_FREQ = _base_config()["qubit_pi_freq"] + 101.0

    params = _relative_100mhz_search_params()
    with tempfile.TemporaryDirectory() as folder:
        edge = ExactEdgeTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        assert abs(edge._stage_resonator() - edge.READ_FREQ) <= 0.08
        lines = edge._stage_spectroscopy()
        assert any(abs(value - edge.QUBIT_FREQ) <= 0.25 for value in lines)

        padding = PaddingOnlyTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        for stage in (padding._stage_resonator, padding._stage_spectroscopy):
            try:
                stage()
            except RuntimeError:
                pass
            else:
                raise AssertionError("fit padding silently enlarged the prior")


def test_monotonic_transmission_cannot_be_reported_as_a_resonator():
    class MonotonicTransmissionTuner(VirtualBasicAutoTuner):
        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            frequencies = np.asarray(freqs_mhz, dtype=float)
            offset = frequencies - np.mean(frequencies)
            return (1.0 + 1e-3 * offset) + 1j * (0.2 + 2e-4 * offset)

    cfg = _base_config()
    cfg["read_pulse_freq"] = 7000.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = MonotonicTransmissionTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        try:
            tuner._stage_resonator()
        except RuntimeError as exc:
            assert "no independently reproduced resonator feature" in str(exc)
        else:
            raise AssertionError("a monotonic transmission slope was called a resonator")

    assert tuner._resonator_seed == 7000.0
    assert tuner._discovery_readout["read_pulse_freq"] == 7000.0
    measured = tuner.data["maps"]["resonator"]
    assert measured["search_complete"] is False
    assert measured["selection_confirmed"] is False
    assert not np.any(measured["trial_valid"])


def test_hardware_width_modest_depth_resonator_survives_confirmation():
    class HardwareLikeResonatorTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.transmission_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            self.transmission_calls += 1
            frequencies = np.asarray(freqs_mhz, dtype=float)
            rng = np.random.default_rng(600 + self.transmission_calls)
            # HWHM 0.17 MHz corresponds to the ~0.34-MHz linewidth in the hardware
            # log.  Three-percent depth is intentionally far less forgiving than the
            # old virtual notch's 82-percent depth.
            detuning = (frequencies - self.READ_FREQ) / 0.17
            noise = 5e-4 * (
                rng.standard_normal(frequencies.size)
                + 1j * rng.standard_normal(frequencies.size))
            return 1.0 - 0.03 / (1.0 + 1j * detuning) + noise

    params = _relative_100mhz_search_params()
    cfg = _base_config()
    cfg["read_pulse_freq"] = 7160.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = HardwareLikeResonatorTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        resonator = tuner._stage_resonator()

    mapping = tuner.data["maps"]["resonator"]
    assert abs(resonator - tuner.READ_FREQ) <= 0.08
    assert mapping["selection_confirmed"] is True
    assert mapping["search_mode"] == "relative_prior"
    assert mapping["confirmation_contrast_snr"] >= 5.0
    assert 0.25 <= mapping["confirmation_width_mhz"] <= 0.55


def test_featureless_spectroscopy_does_not_promote_noise_or_the_input_prior():
    class FeaturelessSpectroscopyTuner(VirtualBasicAutoTuner):
        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            offset = frequencies - np.mean(frequencies)
            return (0.2 + 8e-4 * offset) + 1j * (0.1 - 3e-4 * offset)

    cfg = _base_config()
    cfg["qubit_freq"] = 2400.7
    cfg["qubit_pi_freq"] = 2400.7
    with tempfile.TemporaryDirectory() as folder:
        tuner = FeaturelessSpectroscopyTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        try:
            tuner._stage_spectroscopy()
        except RuntimeError as exc:
            assert "qubit feature" in str(exc)
        else:
            raise AssertionError("featureless spectroscopy produced a qubit candidate")

    assert tuner._spec_candidates_mhz == []
    measured = tuner.data["maps"]["spectroscopy"]
    assert measured["search_complete"] is False
    assert measured["candidate_frequencies_mhz"].size == 0
    assert 2400.7 not in measured["candidate_frequencies_mhz"]


def test_shoulder_proposals_do_not_turn_noise_into_a_transition():
    class NoiseOnlySpectroscopyTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, noise_seed, **kwargs):
            self.noise_seed = int(noise_seed)
            self.spectroscopy_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            rng = np.random.default_rng(
                8000 + 100 * self.noise_seed + self.spectroscopy_calls)
            self.spectroscopy_calls += 1
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))
            return baseline + 0.003 * (
                rng.standard_normal(frequencies.size)
                + 1j * rng.standard_normal(frequencies.size))

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 8,
        "max_candidates": 8, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81,
    })
    for seed in range(6):
        with tempfile.TemporaryDirectory() as folder:
            tuner = NoiseOnlySpectroscopyTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=_base_config(), params=params, noise_seed=seed,
            )
            try:
                tuner._stage_spectroscopy()
            except RuntimeError:
                pass
            else:
                raise AssertionError(
                    "noise-only shoulder proposals produced a transition")
        mapping = tuner.data["maps"]["spectroscopy"]
        assert mapping["candidate_frequencies_mhz"].size == 0
        assert len(mapping["confirmation_valid"]) <= 8


def test_production_grid_recovers_a_broad_noisy_line_with_opposed_sweeps():
    """Exercise the shipped 2-MHz band, not an easier unit-test-only grid."""
    class BroadNoisyLineTuner(VirtualBasicAutoTuner):
        QUBIT_FREQ = 2534.6

        def __init__(self, *args, **kwargs):
            self.spectroscopy_axes = []
            self.spectroscopy_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            self.spectroscopy_axes.append(frequencies.copy())
            self.spectroscopy_calls += 1
            rng = np.random.default_rng(90210 + self.spectroscopy_calls)
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))
            # The 3.7-MHz FWHM mirrors the power-broadened line reported by the
            # hardware run.  It is deliberately wider than the previous 6-MHz
            # confirmation window could analyze without fitting it into the baseline.
            normalized = 2.0 * (frequencies - self.QUBIT_FREQ) / 3.7
            line = (0.18 + 0.06j) / (1.0 + normalized * normalized)
            noise = 0.003 * (
                rng.standard_normal(frequencies.size)
                + 1j * rng.standard_normal(frequencies.size))
            return baseline + line + noise

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 3,
        "max_candidates": 3, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81, "confirmation_shots": 31,
        "min_feature_snr": 3.0,
        "confirmation_min_feature_snr": 4.0,
        "coarse_capture_mhz": 2.0,
    })
    cfg = _base_config()
    cfg.update({"qubit_freq": 2400.7, "qubit_pi_freq": 2400.7})
    with tempfile.TemporaryDirectory() as folder:
        tuner = BroadNoisyLineTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        candidates = tuner._stage_spectroscopy()

    mapping = tuner.data["maps"]["spectroscopy"]
    assert mapping["axes"]["qubit_frequency_mhz"].size == 171
    assert mapping["axes"]["staggered_qubit_frequency_mhz"].size == 170
    assert np.isclose(mapping["axes"]["qubit_frequency_mhz"][0], 2240.0)
    assert np.isclose(mapping["axes"]["qubit_frequency_mhz"][-1], 2580.0)
    assert any(abs(value - tuner.QUBIT_FREQ) <= 0.20 for value in candidates)
    assert np.any(mapping["confirmation_valid"])
    valid_models = {
        str(T.BasicAutoTuner._fit_complex_spectral_line(
            mapping["axes"]["confirmation_frequency_mhz"][index],
            mapping["confirmation_complex_response"][index, 0],
            mapping["coarse_candidate_frequencies_mhz"][index], 3.0,
        ).get("model"))
        for index in np.flatnonzero(mapping["confirmation_valid"])
    }
    assert "population_lorentzian" in valid_models
    assert any(axis.size == 81 and axis[0] > axis[-1]
               for axis in tuner.spectroscopy_axes)


def test_spectral_fit_accepts_population_and_complex_pole_lines_under_noise():
    frequencies = np.linspace(2524.6, 2544.6, 81)
    center = 2534.6
    normalized = 2.0 * (frequencies - center) / 3.7
    baseline = ((0.20 + 0.04j)
                + (2e-4 - 1e-4j) * (frequencies - np.mean(frequencies)))
    profiles = {
        "population_lorentzian": 1.0 / (1.0 + normalized * normalized),
        "complex_pole": 1.0 / (1.0 + 1j * normalized),
    }
    for expected_model, profile in profiles.items():
        for seed in range(8):
            rng = np.random.default_rng(seed)
            response = (baseline + (0.08 + 0.02j) * profile
                        + 0.006 * (
                            rng.standard_normal(frequencies.size)
                            + 1j * rng.standard_normal(frequencies.size)))
            fitted = T.BasicAutoTuner._fit_complex_spectral_line(
                frequencies, response, 2534.0, 3.0,
                min_snr=4.0, min_r2=0.25, max_linewidth_mhz=8.0,
            )
            assert fitted["valid"] is True
            assert fitted["model"] == expected_model
            assert abs(fitted["frequency_mhz"] - center) <= 0.20


def test_target_line_fit_survives_a_stronger_nearby_tls():
    frequencies = np.linspace(2520.0, 2540.0, 81)
    target = 2530.0

    def population_line(center, amplitude):
        normalized = 2.0 * (frequencies - center) / 3.7
        return amplitude / (1.0 + normalized * normalized)

    baseline = ((0.20 + 0.04j)
                + (2e-4 - 1e-4j) * (frequencies - np.mean(frequencies)))
    for neighbor in (2526.0, 2534.0):
        for seed in range(6):
            rng = np.random.default_rng(seed)
            response = (
                baseline
                + population_line(target, 0.08 + 0.02j)
                + population_line(neighbor, 0.16 - 0.03j)
                + 0.003 * (
                    rng.standard_normal(frequencies.size)
                    + 1j * rng.standard_normal(frequencies.size)))
            fitted = T.BasicAutoTuner._fit_complex_spectral_line(
                frequencies, response, target, 2.0,
                min_snr=4.0, min_r2=0.25,
                excluded_centers_mhz=[neighbor],
                exclusion_half_width_mhz=1.5,
            )
            assert fitted["valid"] is True
            # Spectroscopy need only seed the coherent Rabi experiment; it must stay
            # in the target basin rather than sliding to the 2x stronger neighbor.
            assert abs(fitted["frequency_mhz"] - target) <= 1.25


def test_full_spectroscopy_and_rabi_preserve_a_weaker_coherent_neighbor():
    """A weaker qubit shoulder must survive a stronger nearby spectral line."""
    class StrongerNeighborTuner(VirtualBasicAutoTuner):
        QUBIT_FREQ = 2530.0

        def __init__(self, *args, noise_scale=0.003,
                     weak_amplitude=0.08 + 0.02j, noise_seed=1000, **kwargs):
            self.spectroscopy_calls = 0
            self.noise_scale = float(noise_scale)
            self.weak_amplitude = complex(weak_amplitude)
            self.noise_seed = int(noise_seed)
            super().__init__(*args, **kwargs)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, gain, pulse_length_us
            frequencies = np.asarray(freqs_mhz, dtype=float)
            self.virtual_shots += int(shots) * frequencies.size
            rng = np.random.default_rng(
                self.noise_seed + self.spectroscopy_calls)
            self.spectroscopy_calls += 1
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))

            def line(center, amplitude):
                normalized = 2.0 * (frequencies - center) / 3.7
                return amplitude / (1.0 + normalized * normalized)

            return (
                baseline
                + line(2530.0, self.weak_amplitude)
                + line(2534.0, 0.16 - 0.03j)
                + self.noise_scale * (
                    rng.standard_normal(frequencies.size)
                    + 1j * rng.standard_normal(frequencies.size)))

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 8,
        "max_candidates": 8, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81, "coarse_capture_mhz": 2.0,
    })
    regimes = (
        {"noise_scale": 0.003, "weak_amplitude": 0.08 + 0.02j,
         "noise_seed": 1000},
        # This noisier overlapping-line case made every one-line fit hit its
        # linewidth bound before provisional opposed-response seeding was added.
        {"noise_scale": 0.010, "weak_amplitude": 0.10 + 0.015j,
         "noise_seed": 10000},
    )
    for regime in regimes:
        with tempfile.TemporaryDirectory() as folder:
            tuner = StrongerNeighborTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=_base_config(), params=params, **regime,
            )
            seeds = tuner._stage_spectroscopy()
            tuner._stage_iq_rabi()

        assert min(abs(value - 2530.0) for value in seeds) <= 1.25
        assert min(abs(value - 2534.0) for value in seeds) <= 0.90
        witnesses = tuner.data["maps"]["iq_rabi"][
            "coherent_witness_frequencies_mhz"]
        assert np.any(np.abs(witnesses - 2530.0) <= 0.60)
        # Shoulder recovery spends the pre-existing global confirmation budget; it
        # does not silently turn an eight-candidate scan into unbounded work.
        assert len(tuner.data["maps"]["spectroscopy"][
            "confirmation_valid"]) <= 8


def test_padded_discovery_recovers_both_characterized_band_edges():
    """The advertised physical bands must not silently lose their edge values."""
    class EdgeSpectroscopyTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, line_center, **kwargs):
            self.line_center = float(line_center)
            self.spectroscopy_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            self.spectroscopy_calls += 1
            frequencies = np.asarray(freqs_mhz, dtype=float)
            rng = np.random.default_rng(700 + self.spectroscopy_calls)
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))
            normalized = 2.0 * (frequencies - self.line_center) / 3.7
            noise = 0.001 * (
                rng.standard_normal(frequencies.size)
                + 1j * rng.standard_normal(frequencies.size))
            return baseline + (0.18 + 0.06j) / (
                1.0 + normalized * normalized) + noise

    class EdgeResonatorTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, line_center, **kwargs):
            self.line_center = float(line_center)
            super().__init__(*args, **kwargs)

        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            frequencies = np.asarray(freqs_mhz, dtype=float)
            detuning = (frequencies - self.line_center) / 0.22
            return 1.0 - 0.82 / (1.0 + 1j * detuning)

    params = copy.deepcopy(FAST_PARAMS)
    params["resonator"].update({
        "search_min_mhz": 7244.0, "search_max_mhz": 7253.0,
        "search_step_mhz": 0.05,
    })
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 2,
        "max_candidates": 2, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81,
        "confirmation_min_feature_snr": 4.0,
        "coarse_capture_mhz": 2.0,
    })
    for expected in (7245.0, 7252.0):
        with tempfile.TemporaryDirectory() as folder:
            tuner = EdgeResonatorTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=_base_config(), params=params, line_center=expected,
            )
            measured = tuner._stage_resonator()
        assert abs(measured - expected) <= 0.08
    for expected in (2250.0, 2570.0):
        with tempfile.TemporaryDirectory() as folder:
            tuner = EdgeSpectroscopyTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=_base_config(), params=params, line_center=expected,
            )
            measured = tuner._stage_spectroscopy()
        assert any(abs(value - expected) <= 0.20 for value in measured)


def test_transient_spectral_line_cannot_pass_opposed_confirmation():
    class TransientLineTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.spectroscopy_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            self.spectroscopy_calls += 1
            frequencies = np.asarray(freqs_mhz, dtype=float)
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))
            # Primary, staggered, and first confirmation see the line.  It vanishes
            # from the independently acquired reverse pass.
            if self.spectroscopy_calls <= 3:
                return (baseline + (0.18 + 0.06j) /
                        (1.0 + 2j * (frequencies - 2534.6) / 3.7))
            return baseline

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 1,
        "max_candidates": 1, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81,
        "confirmation_min_feature_snr": 4.0,
        "coarse_capture_mhz": 2.0,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = TransientLineTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        try:
            tuner._stage_spectroscopy()
        except RuntimeError as exc:
            assert "reproduced independently" in str(exc)
        else:
            raise AssertionError("a one-pass transient became a qubit candidate")

    assert tuner._spec_candidates_mhz == []
    mapping = tuner.data["maps"]["spectroscopy"]
    assert mapping["confirmation_valid"].tolist() == [False]
    assert mapping["search_complete"] is False


def test_combined_trace_cannot_replace_the_agreed_opposed_pass_line():
    class CancellationTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.spectroscopy_calls = 0
            super().__init__(*args, **kwargs)

        @staticmethod
        def _line(frequencies, center, amplitude, linewidth):
            normalized = 2.0 * (frequencies - center) / linewidth
            return amplitude / (1.0 + normalized * normalized)

        def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                                  pulse_length_us):
            del candidate, shots, gain, pulse_length_us
            self.spectroscopy_calls += 1
            frequencies = np.asarray(freqs_mhz, dtype=float)
            baseline = ((0.20 + 0.04j)
                        + (2e-4 - 1e-4j)
                        * (frequencies - np.mean(frequencies)))
            target = self._line(
                frequencies, 2534.6, 0.18 + 0.04j, 2.0)
            if self.spectroscopy_calls <= 2:
                return baseline + target
            # Both independent passes fit the 2534.6-MHz target; its IQ direction
            # flips between them, so raw complex averaging cancels it and leaves a
            # different 2535.6-MHz feature.  That combined-only center is diagnostic,
            # never a valid replacement for the agreed opposed-pass estimate.
            sign = 1.0 if self.spectroscopy_calls == 3 else -1.0
            other = self._line(
                frequencies, 2535.6, 0.06 - 0.01j, 1.0)
            return baseline + sign * target + other

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"].update({
        "search_min_mhz": 2240.0, "search_max_mhz": 2580.0,
        "search_step_mhz": 2.0, "coarse_candidates": 1,
        "max_candidates": 1, "confirmation_span_mhz": 20.0,
        "confirmation_points": 81, "coarse_capture_mhz": 2.0,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = CancellationTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        try:
            tuner._stage_spectroscopy()
        except RuntimeError as exc:
            assert "reproduced independently" in str(exc)
        else:
            raise AssertionError("a combined-only line replaced the opposed-pass line")

    mapping = tuner.data["maps"]["spectroscopy"]
    assert mapping["confirmation_valid"].tolist() == [False]
    assert "combined fitted centre differs" in mapping["validation_errors"][0]
    assert tuner._spec_candidates_mhz == []


def test_resonator_confirmation_failure_falls_back_to_the_input_gain():
    class GainFallbackTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.calls_by_gain = {}
            super().__init__(*args, **kwargs)

        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            gain = int(candidate["read_pulse_gain"])
            self.calls_by_gain[gain] = self.calls_by_gain.get(gain, 0) + 1
            # The safe 5000-DAC bootstrap has a convincing first trace but its fresh
            # confirmation is only cable slope.  The input 1500-DAC setting is real on
            # both acquisitions and must be tried instead of aborting discovery.
            if gain == 5000 and self.calls_by_gain[gain] >= 2:
                frequencies = np.asarray(freqs_mhz, dtype=float)
                offset = frequencies - np.mean(frequencies)
                return ((1.0 + 1e-3 * offset)
                        + 1j * (0.2 + 2e-4 * offset))
            return super()._acquire_transmission(
                freqs_mhz, candidate, shots)

    with tempfile.TemporaryDirectory() as folder:
        tuner = GainFallbackTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        resonator = tuner._stage_resonator()

    mapping = tuner.data["maps"]["resonator"]
    assert abs(resonator - tuner.READ_FREQ) <= 0.08
    assert mapping["trial_gain_dac"].tolist() == [5000, 1500]
    assert mapping["trial_confirmation_valid"].tolist() == [False, True]
    assert mapping["bootstrap_gain_dac"] == 1500


def test_failed_critical_discovery_and_coinflip_replay_can_never_write():
    """A stable-looking local/noise result is reportable, never configurable."""
    class NoResonatorTuner(VirtualBasicAutoTuner):
        def _acquire_transmission(self, freqs_mhz, candidate, shots):
            del candidate, shots
            frequencies = np.asarray(freqs_mhz, dtype=float)
            offset = frequencies - np.mean(frequencies)
            return ((1.0 + 1e-3 * offset)
                    + 1j * (0.2 + 2e-4 * offset))

        def _stage_rough_single_shot(self):
            return None

    params = copy.deepcopy(FAST_PARAMS)
    params["spectroscopy"]["enabled"] = False
    params["iq_rabi"]["enabled"] = False
    params["reset"] = {"enabled": False}
    for name in ("parity_chevron", "fine_frequency", "amplified_error",
                 "readout", "readout_length", "qubit", "pulse_duration"):
        params[name]["enabled"] = False
    params["coordinate_descent_repeat"] = False
    params["leakage"] = {"enabled": False, "operational_enabled": False}
    cfg = _base_config()
    cfg.update({
        "read_pulse_freq": 7000.0,
        "qubit_freq": 2400.7,
        "qubit_pi_freq": 2400.7,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = NoResonatorTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        with redirect_stdout(io.StringIO()):
            result = tuner.acquire()["data"]

    assert result["outcome"] == "transition_qualification_failed"
    assert result["success"] is False
    assert result["expensive_search_skipped"] is True
    assert result["fidelity_replay_stable"] is False
    assert result["best_found"]["fidelity"] < 0.55
    assert result["pre_expensive_gate"]["passed"] is False
    assert any("resonator" in reason
               for reason in result["pre_expensive_gate"]["failures"])
    assert "joint_search" not in [row["name"] for row in result["stages"]]
    assert result["final_stable"] is False
    assert result["eligible_tuned"] == {}


def test_missing_spectroscopy_alone_blocks_a_high_fidelity_write():
    """Keep the discovery gate orthogonal to the low-fidelity write floor."""
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
            sigma=tuner.SIGMA,
        )
        final = tuner._confirm_candidates(
            [candidate], shots=173, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact discovery-gate isolation",
            add_to_history=False,
        )[0]
        tuner.working = dict(candidate)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._discovery_guard_active = True
        tuner._discovery_status.update({
            "resonator": True,
            "spectroscopy": False,
        })
        tuner._record_control_witness(
            "synthetic_rabi", candidate["qubit_pi_freq"],
            "averaged_iq_rabi", candidate=candidate, r2=0.99, snr=20.0,
        )
        tuner._final_control_verified_key = T._control_key(candidate)
        tuner._finalize(final)

    assert final["fidelity_lcb_95"] > 0.90
    assert tuner.data["write_fidelity_gate"]["passed"] is True
    assert tuner.data["control_validation"]["verified_for_write"] is True
    assert tuner.data["discovery"]["missing_for_write"] == ["spectroscopy"]
    assert tuner.data["final_stable"] is False
    assert tuner.data["eligible_tuned"] == {}


def test_high_fidelity_without_coherent_control_witness_cannot_write():
    """A stable saturation response is not automatically an X180 calibration."""
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
            sigma=tuner.SIGMA,
        )
        final = tuner._confirm_candidates(
            [candidate], shots=173, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact coherent-control-gate isolation",
            add_to_history=False,
        )[0]
        tuner.working = dict(candidate)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._discovery_guard_active = True
        tuner._discovery_status.update({
            "resonator": True,
            "spectroscopy": True,
        })
        tuner._finalize(final)

    assert final["fidelity_lcb_95"] > 0.90
    assert tuner.data["discovery"]["verified_for_write"] is True
    assert tuner.data["write_fidelity_gate"]["passed"] is True
    assert tuner.data["control_validation"]["verified_for_write"] is False
    assert tuner.data["final_stable"] is False
    assert tuner.data["eligible_tuned"] == {}


def test_control_witness_must_match_the_complete_selected_waveform():
    """Nearby-line or wrong-gain evidence cannot authorize another pulse tuple."""
    mismatches = (
        {"qubit_pi_freq": 2532.0},       # another TLS inside the old +/-3 MHz gate
        {"qubit_pi_gain": 20000},
        {"sigma": 0.10},
        {"qubit_drag_beta": 0.20},
    )
    for changes in mismatches:
        with tempfile.TemporaryDirectory() as folder:
            tuner = VirtualBasicAutoTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=_base_config(), params=FAST_PARAMS,
            )
            candidate = T._with_candidate(
                tuner.working,
                read_pulse_freq=tuner.READ_FREQ,
                read_pulse_gain=tuner.READ_GAIN,
                read_length=tuner.READ_LENGTH,
                qubit_pi_freq=tuner.QUBIT_FREQ,
                qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
                sigma=tuner.SIGMA,
                qubit_drag_beta=0.04,
            )
            final = tuner._confirm_candidates(
                [candidate], shots=173, blocks=FAST_PARAMS["final"]["blocks"],
                label="final exact tuple-witness isolation",
                add_to_history=False,
            )[0]
            witness_candidate = T._with_candidate(candidate, **changes)
            tuner._record_control_witness(
                "wrong_tuple", witness_candidate["qubit_pi_freq"],
                "averaged_iq_rabi", candidate=witness_candidate,
                r2=0.99, snr=20.0,
            )
            tuner.working = dict(candidate)
            tuner._final_replay_completed = True
            tuner._final_replay_kind = "unconstrained"
            tuner._discovery_guard_active = True
            tuner._discovery_status.update({
                "resonator": True, "spectroscopy": True,
            })
            tuner._final_control_verified_key = T._control_key(witness_candidate)
            tuner._finalize(final)

        assert final["fidelity_lcb_95"] > 0.90
        assert tuner.data["control_validation"]["verified_for_write"] is False
        assert tuner.data["final_stable"] is False
        assert tuner.data["eligible_tuned"] == {}

    # The identical waveform, in contrast, is accepted by the isolated gate.
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
            sigma=tuner.SIGMA,
        )
        final = tuner._confirm_candidates(
            [candidate], shots=173, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact tuple-witness positive control",
            add_to_history=False,
        )[0]
        tuner._record_control_witness(
            "matching_tuple", candidate["qubit_pi_freq"],
            "averaged_iq_rabi", candidate=candidate, r2=0.99, snr=20.0,
        )
        tuner.working = dict(candidate)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._discovery_guard_active = True
        tuner._discovery_status.update({
            "resonator": True, "spectroscopy": True,
        })
        tuner._final_control_verified_key = T._control_key(candidate)
        tuner._finalize(final)

    assert tuner.data["control_validation"]["verified_for_write"] is True
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligible_tuned"]


def test_final_exact_repeated_pulse_audit_rejects_saturation():
    """Two separated blobs from saturation cannot masquerade as coherent X180."""
    class SaturatedControlTuner(VirtualBasicAutoTuner):
        def _acquire_repeated_populations(self, candidate, pulse_counts, shots,
                                          calibration):
            del candidate, shots, calibration
            return np.full(len(pulse_counts), 0.5, dtype=float)

    with tempfile.TemporaryDirectory() as folder:
        tuner = SaturatedControlTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA),
            sigma=tuner.SIGMA,
        )
        try:
            tuner._stage_final_control_verify(candidate)
        except RuntimeError as exc:
            assert "failed odd/even coherence" in str(exc)
        else:
            raise AssertionError("an incoherently saturated pulse passed coherence")

    assert tuner._final_control_verified_key is None
    assert tuner.data["maps"]["final_control_verify"]["verified"] is False
    assert not any(row.get("exact_tuple", False)
                   for row in tuner.data["control_witnesses"])


def test_joint_search_is_independent_of_starting_readout_gain_and_length():
    selected = []
    for read_length, read_gain in ((4.0, 1500), (30.0, 8500)):
        cfg = _base_config()
        cfg.update({"read_length": read_length, "read_pulse_gain": read_gain})
        with tempfile.TemporaryDirectory() as folder:
            tuner = VirtualBasicAutoTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=cfg, params=FAST_PARAMS,
            )
            # Discovery/Rabi, rather than initialize.py, supplies this physical basin.
            tuner.working = T._with_candidate(
                tuner.working,
                read_pulse_freq=tuner.READ_FREQ,
                qubit_pi_freq=tuner.QUBIT_FREQ,
                qubit_pi_gain=14475,
                sigma=0.10,
            )
            result = tuner._stage_joint_search()
            selected.append(result)
    first, second = selected
    assert first["read_length"] == second["read_length"] == 30.0
    assert first["sigma"] == second["sigma"] == 0.25
    assert first["read_pulse_gain"] == second["read_pulse_gain"] == 5000
    assert abs(first["qubit_pi_gain"] - 5790) <= 750
    assert abs(second["qubit_pi_gain"] - 5790) <= 750


def test_runtime_limited_joint_search_covers_every_duration_before_repeating_power():
    """Even a zero optional budget must measure long and short duration families."""
    class MandatoryCoverageTuner(VirtualBasicAutoTuner):
        def _joint_budget_allows(self, reserve_final=True,
                                 additional_reserve_minutes=0.0):
            del reserve_final, additional_reserve_minutes
            return False

    params = copy.deepcopy(FAST_PARAMS)
    params["joint_search"].update({
        "read_lengths_us": [4.0, 8.0, 20.0],
        "sigma_values_us": [0.10, 0.25],
        "read_gain_min": 1000, "read_gain_max": 9000,
        "read_gain_points": 5,
        "minimum_duration_coverage_passes": 1,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = MandatoryCoverageTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        tuner.working = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=14475,
            sigma=0.10,
        )
        tuner._stage_joint_search()

    joint = tuner.data["joint_search"]
    assert joint["coarse_gain_passes_completed"] == 1
    assert joint["coverage"]["complete"] is True
    assert joint["coarse_cells_attempted"] == 6
    rows = joint["coarse_rows"]
    assert {float(row["read_length"]) for row in rows} == {4.0, 8.0, 20.0}
    assert {float(row["sigma"]) for row in rows} == {0.10, 0.25}
    assert len({int(row["read_pulse_gain"]) for row in rows}) == 1


def test_duration_balanced_schedule_uses_central_power_for_every_duration_first():
    jobs = T.duration_balanced_joint_jobs(
        [4.0, 8.0, 20.0], [0.10, 0.25],
        [1000, 3000, 5000, 8000, 10000], np.random.default_rng(19))
    first = jobs[:6]
    second = jobs[6:12]
    expected = {(length, sigma)
                for length in (4.0, 8.0, 20.0)
                for sigma in (0.10, 0.25)}
    assert {(row[0], row[1]) for row in first} == expected
    assert {(row[0], row[1]) for row in second} == expected
    assert {row[2] for row in first} == {5000}
    assert {row[2] for row in second} == {3000}


def test_finalize_reports_best_overall_and_shortest_near_best_separately():
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"].update({
        "enabled": True, "max_fidelity_loss": 0.010,
        "minimum_mean_fidelity": 0.90, "minimum_lcb_fidelity": 0.90,
    })
    params["leakage"] = {"enabled": False, "operational_enabled": False}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_pi_freq=tuner.QUBIT_FREQ,
        )

        def replay(read_length, sigma, gain, fidelity):
            row = T._with_candidate(
                common, read_length=read_length, sigma=sigma,
                qubit_pi_gain=gain)
            row.update({
                "fidelity": fidelity, "fidelity_se": 0.001,
                "fidelity_lcb_95": fidelity - 0.00196,
                "confirmation_blocks": params["final"]["blocks"],
                "confirmation_complete": True,
                "block_spread": 0.002,
                "label": "final exact objective regression",
            })
            return row

        overall = replay(20.0, 0.25, 5790, 0.950)
        faster = replay(8.0, 0.10, 14475, 0.945)
        tuner._remember_final_replays(
            [overall, faster], "unconstrained", batch_complete=True)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._finalize(overall)

    assert (T._candidate_key(tuner.data["best_overall_candidate"])
            == T._candidate_key(overall))
    assert (T._candidate_key(tuner.data["shortest_high_fidelity_candidate"])
            == T._candidate_key(faster))
    assert tuner.data["shortest_high_fidelity_status"] == (
        "independent_noninferiority_advisory_not_familywise_certified")


def test_practical_short_report_keeps_eight_us_candidate_but_rejects_one_us_coinflip():
    params = copy.deepcopy(FAST_PARAMS)
    params["latency"] = copy.deepcopy(T.BASIC_DEFAULTS["latency"])
    params["leakage"] = {"enabled": False, "operational_enabled": False}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_pi_freq=tuner.QUBIT_FREQ,
        )

        def replay(read_length, sigma, gain, fidelity, fidelity_se):
            row = T._with_candidate(
                common, read_length=read_length, sigma=sigma,
                qubit_pi_gain=gain)
            row.update({
                "fidelity": fidelity, "fidelity_se": fidelity_se,
                "fidelity_lcb_95": fidelity - 1.96 * fidelity_se,
                "confirmation_blocks": params["final"]["blocks"],
                "confirmation_complete": True,
                "block_spread": 0.010,
                "label": "final exact practical-Pareto regression",
            })
            return row

        overall = replay(20.0, 0.25, 5790, 0.930, 0.003)
        practical = replay(8.0, 0.10, 16677, 0.884, 0.007)
        coinflip = replay(1.0, 0.05, 26000, 0.600, 0.010)
        tuner._remember_final_replays(
            [overall, practical, coinflip], "unconstrained", batch_complete=True)
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._finalize(overall)

    assert (T._candidate_key(tuner.data["best_overall_candidate"])
            == T._candidate_key(overall))
    assert (T._candidate_key(tuner.data["shortest_high_fidelity_candidate"])
            == T._candidate_key(practical))
    assert tuner.data["shortest_high_fidelity_status"] == (
        "practical_pareto_advisory_not_write_eligible")


def test_short_report_cannot_borrow_a_different_tuples_safety_certificate():
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        common = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            qubit_pi_freq=tuner.QUBIT_FREQ,
        )

        def replay(read_length, sigma, gain, fidelity):
            row = T._with_candidate(
                common, read_length=read_length, sigma=sigma,
                qubit_pi_gain=gain)
            row.update({
                "fidelity": fidelity, "fidelity_se": 0.003,
                "fidelity_lcb_95": fidelity - 0.00588,
                "confirmation_blocks": params["final"]["blocks"],
                "confirmation_complete": True, "block_spread": 0.005,
                "label": "final exact safety-identity regression",
            })
            return row

        safe_overall = replay(20.0, 0.25, 5790, 0.930)
        unsafe_fast = replay(8.0, 0.10, 16677, 0.925)
        tuner._remember_final_replays(
            [safe_overall, unsafe_fast], "unconstrained", batch_complete=True)
        tuner._leakage_verified_candidate_key = T._candidate_key(safe_overall)
        tuner.data["leakage"].update({"verified": True, "selection_safe": True})
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "leakage_constrained"
        tuner._finalize(safe_overall)

    assert (T._candidate_key(tuner.data["shortest_high_fidelity_candidate"])
            == T._candidate_key(safe_overall))
    assert (T._candidate_key(tuner.data["shortest_high_fidelity_candidate"])
            != T._candidate_key(unsafe_fast))
    assert tuner.data["shortest_high_fidelity_candidate"][
        "safety_screen_verified_for_exact_tuple"] is True


def test_joint_resume_reuses_only_matching_input_and_flux_context():
    cfg = _base_config()
    row = dict(cfg)
    row.update({
        "qubit_pi_freq": cfg["qubit_pi_freq"],
        "qubit_freq": cfg["qubit_pi_freq"],
        "qubit_drag_beta": cfg["qubit_drag_beta"],
        "fidelity": 0.8,
    })
    previous = {
        "revision": T.BASIC_AUTOTUNER_REVISION,
        "initial": T._candidate_from_cfg(cfg),
        "fast_flux_operating_point": {
            "ff_ch": cfg["ff_ch"], "ff_park_gain": cfg["ff_park_gain"]},
        "candidate_archive": [row],
        "confirmed_candidates": [],
        "joint_search": {"coarse_rows": [row]},
    }
    with tempfile.TemporaryDirectory() as folder:
        checkpoint = os.path.join(folder, "resume.pkl")
        with open(checkpoint, "wb") as stream:
            pickle.dump(previous, stream)
        params = copy.deepcopy(FAST_PARAMS)
        params["resume_checkpoint"] = checkpoint
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params)
        assert tuner.data["resume"]["archived_measurements"] == 1
        assert tuner.data["joint_search"]["resumed_coarse_rows"] == [row]

        changed_flux = copy.deepcopy(cfg)
        changed_flux["ff_park_gain"] = 1
        try:
            VirtualBasicAutoTuner(
                soc=None, soccfg=None, path="q4", outerFolder=folder,
                cfg=changed_flux, params=params)
        except ValueError as exc:
            assert "input tuple" in str(exc) or "fast-flux" in str(exc)
        else:
            raise AssertionError("mismatched resume context was accepted")


def test_bad_start_recovers_and_preserves_best_effort_contract():
    cfg = _base_config()
    # Neither physical feature is inside the old local/wide scans, but both satisfy
    # the production tuner's explicit +/-100-MHz initialization contract.
    cfg["read_pulse_freq"] = 7160.0
    cfg["qubit_freq"] = 2450.0
    cfg["qubit_pi_freq"] = 2450.0
    untouched = copy.deepcopy(cfg)
    params = _relative_100mhz_search_params()
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params, fail_parity=True,
        )
        result = tuner.acquire(plotDisp=False)

    data = result["data"]
    best = data["best_found"]
    assert data["outcome"] == "completed"
    assert data["success"] is True
    assert data["final_stable"] is True
    assert data["control_validation"]["verified_for_write"] is True
    assert (tuple(data["control_validation"]["fresh_exact_audit_key"])
            == tuple(data["control_validation"]["selected_control_key"]))
    assert any(row["name"] == "final_control_verify" and row["status"] == "ok"
               for row in data["stages"])
    stage_order = [row["name"] for row in data["stages"]]
    ordered_safety_closure = [
        "operational_leakage",
        "latency_reference",
        "latency",
        "latency_control_screen",
        "operational_leakage_verify",
        "final_safe",
        "final_control_verify",
    ]
    assert all(name in stage_order for name in ordered_safety_closure)
    assert [stage_order.index(name) for name in ordered_safety_closure] == sorted(
        stage_order.index(name) for name in ordered_safety_closure)

    # The exact input replay is intentionally near random, but every later stage still ran.
    baseline = [row for row in data["confirmed_candidates"]
                if row["label"] == "exact input tuple"]
    assert len(baseline) == 1
    assert baseline[0]["fidelity"] < 0.58
    assert any(row["name"] == "final" and row["status"] == "ok"
               for row in data["stages"])
    assert data["maps"]["joint_search"]["search_complete"] is True
    assert data["joint_search"]["coverage"]["complete"] is True
    assert any(name.startswith("joint_aae_frequency_") for name in data["maps"])
    assert "amplified_error" in data["maps"]
    assert (data["maps"]["amplified_error"]["calibration_kind"]
            == "amplified_amplitude_error_x180")
    assert data["maps"]["amplified_error"]["leakage_measurement"] is False

    # A failed parity-map backend cannot erase the already established coherent-Rabi
    # transition.  Its high-statistics odd/even audit is useful rough evidence, while
    # final candidates still receive their own strict control audits.
    parity = [row for row in data["stages"] if row["name"] == "parity_chevron"]
    assert len(parity) == 1
    assert parity[0]["status"] == "ok"
    qualification = data["control_branch_qualification"]
    assert qualification["qualified"] is True
    assert qualification["expensive_search_allowed"] is True
    assert any("synthetic parity backend fault" in str(row["parity_failure"])
               for row in qualification["branches"])
    assert data["pre_expensive_gate"]["passed"] is True
    assert stage_order.index("pre_expensive_gate") < stage_order.index(
        "joint_search")
    assert data["candidate_count"] > 0

    # The final tuple lies in the known high-fidelity basin reached from a very bad prior.
    assert abs(best["read_pulse_freq"] - tuner.READ_FREQ) <= 0.12
    assert abs(best["read_pulse_gain"] - tuner.READ_GAIN) <= 250
    assert abs(best["read_length"] - tuner.READ_LENGTH) <= 0.1
    assert abs(best["qubit_pi_freq"] - tuner.QUBIT_FREQ) <= 0.30
    assert abs(best["qubit_pi_gain"] - tuner.PI_GAIN_AT_SIGMA) <= 700
    assert abs(best["sigma"] - tuner.SIGMA) <= 1e-12
    assert best["fidelity"] > 0.90

    # A coarse-only false maximum was shortlisted, then rejected by fresh confirmation.
    outlier_coarse = [row for row in data["candidate_archive"]
                      if row["label"] == "readout_grid coarse"
                      and row["read_pulse_gain"] == 8500
                      and abs(row["read_pulse_freq"]
                              - tuner._resonator_seed) < 0.1]
    assert len(outlier_coarse) == 1
    assert outlier_coarse[0]["fidelity"] > 0.98
    outlier_confirm = [row for row in data["confirmed_candidates"]
                       if row["label"] == "readout_grid confirm"
                       and row["read_pulse_gain"] == 8500
                       and abs(row["read_pulse_freq"]
                               - tuner._resonator_seed) < 0.1]
    assert len(outlier_confirm) == 1
    assert outlier_confirm[0]["fidelity"] < 0.70
    assert best["read_pulse_gain"] != 8500

    # Joint search gives every duration pair broad readout/pi-gain coverage before
    # local frequency proposals; no duration inherits one incumbent gain.
    duration_rows = [row for row in data["candidate_archive"]
                     if row.get("search_stage") == "joint_coarse"]
    tested_sigmas = sorted(set(float(row["sigma"]) for row in duration_rows))
    assert tested_sigmas == [0.10, 0.25]
    for sigma in tested_sigmas:
        rows = [row for row in duration_rows if float(row["sigma"]) == sigma]
        assert len(set(float(row["read_length"]) for row in rows)) == 2
        assert len(set(int(row["read_pulse_gain"]) for row in rows)) >= 3
        assert len(set(int(row["qubit_pi_gain"]) for row in rows)) >= 3

    # The experiment is dry by construction: neither the caller's dict nor returned cfg
    # is rewritten.  Only explicitly supported calibration keys may be eligible.
    assert cfg == untouched
    assert result["config"] == untouched
    # The default basic screen compares fixed-Gaussian duration/power candidates.  It
    # must not silently introduce a custom DRAG waveform; strict direct-P(f) mode owns
    # that optional search.
    assert set(data["eligible_tuned"]) == (
        set(T.TUNED_KEYS) - {"qubit_drag_beta"})
    assert best["qubit_drag_beta"] == untouched["qubit_drag_beta"]
    assert data["leakage"]["drag_tuned"] is False
    assert data["leakage"]["operational_verified"] is True
    assert data["leakage"]["direct_p2_measured"] is False
    for forbidden in ("res_phase", "qubit_pi2_gain"):
        assert forbidden not in data["eligible_tuned"]
    assert untouched["res_phase"] == 37.0
    assert untouched["qubit_pi2_gain"] == 1111
    assert untouched["qubit_drag_beta"] == 0.07


def test_interrupt_retains_a_completed_unconfirmed_measurement():
    class InterruptingTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self._pair_calls = 0
            super().__init__(*args, **kwargs)

        def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
            self._pair_calls += 1
            if self._pair_calls == 2:
                raise KeyboardInterrupt
            return super()._acquire_ss_pair(candidate, shots, state_order)

    with tempfile.TemporaryDirectory() as folder:
        tuner = InterruptingTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        result = tuner.acquire(plotDisp=False)
    data = result["data"]
    assert data["outcome"] == "interrupted_with_candidate"
    assert data["best_found"] is not None
    assert data["best_found"]["label"].startswith("partial best direct")
    assert data["candidate_count"] == 1
    assert data["eligible_tuned"] == {}


def test_failed_search_cannot_make_replayed_input_write_eligible():
    class SearchFailureTuner(VirtualBasicAutoTuner):
        @staticmethod
        def _fail():
            raise RuntimeError("synthetic search failure")

        _stage_resonator = lambda self: self._fail()
        _stage_spectroscopy = lambda self: self._fail()
        _stage_iq_rabi = lambda self: self._fail()
        _stage_rough_single_shot = lambda self: self._fail()
        _stage_parity_chevron = lambda self: self._fail()
        _stage_readout_length = lambda self: self._fail()
        _stage_pulse_duration = lambda self: self._fail()
        _stage_amplified_error = lambda self: self._fail()

        def _stage_fine_frequency(self, stage="fine_frequency"):
            del stage
            return self._fail()

        def _stage_readout_grid(self, stage="readout_grid", local=False,
                                record_evidence=True):
            del stage, local, record_evidence
            return self._fail()

        def _stage_qubit_grid(self, stage="qubit_grid", local=False):
            del stage, local
            return self._fail()

    params = copy.deepcopy(FAST_PARAMS)
    params["coordinate_descent_repeat"] = False
    with tempfile.TemporaryDirectory() as folder:
        tuner = SearchFailureTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        result = tuner.acquire(plotDisp=False)
    data = result["data"]
    assert data["outcome"] == "transition_qualification_failed"
    assert data["success"] is False
    assert data["best_found"] is not None
    assert data["eligible_tuned"] == {}
    assert data["expensive_search_skipped"] is True
    stage_names = [row["name"] for row in data["stages"]]
    assert "pre_expensive_gate" in stage_names
    assert "joint_search" not in stage_names
    assert "duration_portfolio" not in stage_names


def test_partial_direct_grid_with_failed_confirmation_has_no_key_evidence():
    """An archived coarse map is diagnostic, not proof of a writable value."""
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        frequencies = np.asarray([7246.5, 7247.0, 7247.5, 7248.0, 7249.1])
        candidates = []
        for frequency in frequencies:
            candidate = dict(tuner.working)
            candidate["read_pulse_freq"] = float(frequency)
            candidates.append(candidate)

        original_measure = tuner._measure_candidate

        def fail_one_coarse_point(candidate, shots, label, state_order="ge",
                                  archive=True):
            if abs(float(candidate["read_pulse_freq"]) - 7247.5) < 1e-12:
                raise RuntimeError("synthetic coarse point fault")
            return original_measure(candidate, shots, label, state_order, archive)

        def fail_candidate_confirmation(candidates, shots, blocks, label,
                                        add_to_history=True):
            del candidates, shots, blocks, label, add_to_history
            raise RuntimeError("synthetic candidate confirmation fault")

        tuner._measure_candidate = fail_one_coarse_point
        tuner._confirm_candidates = fail_candidate_confirmation
        try:
            tuner._direct_grid(
                "confirmation_failure_grid", candidates, (frequencies.size,),
                {"read_pulse_freq_mhz": frequencies}, shots=41, shortlist=2,
                confirm_shots=73, confirm_blocks=2,
            )
        except RuntimeError as exc:
            assert "synthetic candidate confirmation fault" in str(exc)
        else:
            raise AssertionError("candidate confirmation unexpectedly succeeded")

        archived_map = tuner.data["maps"]["confirmation_failure_grid"]
        assert archived_map["coverage"] == 0.8
        assert archived_map["search_complete"] is False
        assert archived_map["selection_coverage_usable"] is True
        assert archived_map["selection_confirmed"] is False
        assert np.count_nonzero(np.isfinite(archived_map["fidelity"])) == 4
        assert all(not rows for rows in tuner.data["key_evidence"].values())

        # A subsequent stable exact replay does not fabricate coordinate-search
        # provenance, but it directly measures the whole physical tuple and therefore
        # provides sufficient atomic write evidence in its own right.
        tuner._measure_candidate = original_measure
        replay = T.BasicAutoTuner._confirm_candidates(
            tuner, [candidates[-1]], shots=101,
            blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact regression replay", add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner._finalize(replay)
        assert tuner.data["final_stable"] is True
        assert tuner.data["eligibility"]["changed_keys"] == ["read_pulse_freq"]
        assert tuner.data["eligibility"]["missing_evidence"] == [
            "read_pulse_freq"
        ]
        assert tuner.data["eligibility"]["search_provenance_complete"] is False
        assert tuner.data["eligibility"]["eligibility_basis"] == (
            "stable_exact_full_tuple_replay")
        assert tuner.data["eligibility"]["atomic_tuple_safe"] is True
        assert tuner.data["eligible_tuned"] == {
            "read_pulse_freq": replay["read_pulse_freq"]
        }


def test_stable_full_tuple_replay_authorizes_atomic_update():
    """The jointly replayed tuple outranks incomplete per-axis bookkeeping."""
    cfg = _base_config()
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        candidate = dict(tuner.working)
        candidate["read_pulse_freq"] += 0.5
        candidate["qubit_pi_gain"] += 500
        tuner.working = dict(candidate)

        # The readout-frequency value has complete exact-value evidence, while the
        # changed pi gain deliberately has none.
        tuner._record_key_evidence(
            ["read_pulse_freq"], "complete synthetic readout search", complete=True)
        replay = tuner._confirm_candidates(
            [candidate], shots=101, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact regression replay", add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner._finalize(replay)

    eligibility = tuner.data["eligibility"]
    assert tuner.data["final_stable"] is True
    assert eligibility["changed_keys"] == ["read_pulse_freq", "qubit_pi_gain"]
    assert eligibility["exact_value_evidence"]["read_pulse_freq"] is True
    assert eligibility["exact_value_evidence"]["qubit_pi_gain"] is False
    assert eligibility["missing_evidence"] == ["qubit_pi_gain"]
    assert eligibility["search_provenance_complete"] is False
    assert eligibility["eligibility_basis"] == "stable_exact_full_tuple_replay"
    assert eligibility["atomic_tuple_safe"] is True
    assert tuner.data["eligible_tuned"] == {
        "read_pulse_freq": replay["read_pulse_freq"],
        "qubit_pi_gain": replay["qubit_pi_gain"],
    }

    applied = copy.deepcopy(cfg)
    applied.update(tuner.data["eligible_tuned"])
    assert applied["read_pulse_freq"] == replay["read_pulse_freq"]
    assert applied["qubit_pi_gain"] == replay["qubit_pi_gain"]


def test_leakage_constraint_prefers_safe_waveform_over_higher_binary_fidelity():
    """Fidelity wins only after the direct leakage constraints are satisfied."""
    class LeakageConstraintTuner(VirtualBasicAutoTuner):
        def _leakage_waveform_pool(self):
            unsafe = T._with_candidate(
                self.working, sigma=0.10, qubit_pi_gain=14475)
            safe = T._with_candidate(
                self.working, sigma=0.25, qubit_pi_gain=5790)
            return [unsafe, safe]

        def _calibrate_ef_transition(self, candidate):
            return {
                "ef_frequency": candidate["qubit_pi_freq"] - 200.0,
                "ef_gain": 9000,
                "anharmonicity_mhz": -200.0,
            }

        def _measure_leakage_candidate(self, candidate, ef_calibration, shots,
                                       reference_shots, label):
            del ef_calibration, shots, reference_shots
            safe = float(candidate["sigma"]) >= 0.20
            fidelity = 0.93 if safe else 0.97
            row = dict(candidate)
            row.update({
                "fidelity": fidelity, "fidelity_se": 0.003,
                "fidelity_lcb_95": fidelity - 1.96 * 0.003,
                "single_p2_ucb": 0.009 if safe else 0.08,
                "amplified_p2_ucb": 0.014 if safe else 0.12,
                "third_blob_excess_ucb": 0.012 if safe else 0.09,
                "valid": True, "leakage_safe": safe, "label": label,
            })
            return row

    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {
        "enabled": True, "max_candidate_waveforms": 2,
        "beta_span": 0.04, "beta_points": 5,
        "max_beta_span": 0.08, "max_extensions": 1,
        "max_single_p2": 0.02, "max_amplified_p2": 0.03,
        "max_third_blob_excess": 0.05,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = LeakageConstraintTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        chosen = tuner._stage_leakage()
    assert chosen["leakage_safe"] is True
    assert chosen["screening_fidelity"] == 0.93
    assert chosen["confirmation_blocks"] == 3
    assert chosen["selection_confirmation_complete"] is True
    assert tuner.working["sigma"] == 0.25
    assert tuner.data["leakage"]["selection_safe"] is True


def test_failed_leakage_calibration_retains_the_validated_unconstrained_result():
    """A failed P(f) audit blocks writes without replacing the measured best pulse."""
    class FailedLeakageTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self.final_safe_called = False
            super().__init__(*args, **kwargs)

        def _stage_leakage(self):
            raise RuntimeError("synthetic e-f calibration failure")

        def _stage_final_constrained(self):
            self.final_safe_called = True
            raise AssertionError(
                "a leakage-constrained replay must not run without a leakage audit")

    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {"enabled": True, "operational_enabled": False}
    with tempfile.TemporaryDirectory() as folder:
        tuner = FailedLeakageTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=params,
        )
        with redirect_stdout(io.StringIO()):
            result = tuner.acquire()["data"]
    assert tuner.final_safe_called is False
    assert result["best_found"]["fidelity"] > 0.90
    assert result["best_found"]["label"].startswith("final exact")
    assert result["eligibility"]["final_replay_kind"] in (
        "unconstrained", "latency_unconstrained")
    assert result["leakage_verified"] is False
    assert result["final_stable"] is False
    assert result["eligible_tuned"] == {}


def test_failed_operational_screen_preserves_the_unconstrained_fidelity_replay():
    """A basic safety-stage failure cannot erase or relabel the fidelity result."""
    class FailedOperationalTuner(VirtualBasicAutoTuner):
        def _stage_operational_leakage(self):
            self.data["leakage"].update({
                "selection_safe": False,
                "verified": False,
                "failure": "synthetic fixed-Gaussian screen failure",
            })
            raise RuntimeError(self.data["leakage"]["failure"])

    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = FailedOperationalTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        with redirect_stdout(io.StringIO()):
            result = tuner.acquire()["data"]
    assert result["best_found"]["label"].startswith("final exact")
    assert result["best_found"]["fidelity"] > 0.90
    # Safety-constrained runs now postpone latency selection until a safe control
    # family exists.  A failed screen therefore retains the ordinary fidelity replay
    # without fabricating a timing tradeoff from unscreened controls.
    assert result["latency_optimization"]["status"] == "not_run"
    assert result["best_fidelity_replay"]["fidelity"] == (
        result["best_found"]["fidelity"])
    assert result["fidelity_replay_stable"] is True
    assert result["final_stable"] is False
    assert result["leakage_verified"] is False
    assert result["leakage"]["failure"] == (
        "RuntimeError: synthetic fixed-Gaussian screen failure")
    assert result["eligible_tuned"] == {}


def test_partial_screened_final_cannot_replace_the_stable_fidelity_replay():
    class PartialScreenedFinalTuner(VirtualBasicAutoTuner):
        def _stage_final_constrained(self):
            partial = dict(self.working)
            partial.update({
                "fidelity": 0.70, "fidelity_se": 0.04,
                "fidelity_lcb_95": 0.6216,
                "confirmation_blocks": 1,
                "block_fidelities": np.asarray([0.70]),
                "block_spread": 0.0,
                "label": "final exact synthetic partial screened replay",
            })
            self._final_replay_completed = False
            self._final_replay_kind = None
            self.data["final_candidates"] = [partial]
            return partial

    params = copy.deepcopy(FAST_PARAMS)
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = PartialScreenedFinalTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        with redirect_stdout(io.StringIO()):
            result = tuner.acquire()["data"]
    assert result["leakage"]["verified"] is True
    assert result["leakage"]["final_replay_complete"] is False
    assert result["best_found"]["fidelity"] > 0.90
    assert result["best_found"]["fidelity"] == (
        result["best_fidelity_replay"]["fidelity"])
    assert result["best_found"]["label"].startswith("final exact step-5")
    assert result["fidelity_replay_stable"] is True
    assert result["final_stable"] is False
    assert result["eligible_tuned"] == {}
    assert result["rejected_late_final_candidates"][0]["fidelity"] == 0.70


def test_direct_leakage_verification_is_a_hard_write_gate():
    cfg = _base_config()
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.working["read_pulse_freq"] + 0.5)
        replay = tuner._confirm_candidates(
            [candidate], shots=101, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact leakage-gate regression", add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner.data["leakage"].update({
            "active": True, "required_for_write": True, "verified": False,
        })
        tuner._finalize(replay)
    assert tuner.data["final_stable"] is False
    assert tuner.data["eligibility"]["leakage_required"] is True
    assert tuner.data["eligibility"]["leakage_verified"] is False
    assert tuner.data["eligible_tuned"] == {}


def test_verified_leakage_tuple_can_atomically_write_drag_beta():
    """A certified final tuple includes DRAG rather than silently dropping it."""
    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working, qubit_drag_beta=0.04,
            read_pulse_freq=tuner.working["read_pulse_freq"] + 0.5)
        replay = tuner._confirm_candidates(
            [candidate], shots=101, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact verified leakage tuple regression",
            add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner.data["leakage"].update({
            "active": True, "required_for_write": True, "verified": True,
        })
        tuner._leakage_verified_candidate_key = T._candidate_key(candidate)
        tuner._final_replay_kind = "leakage_constrained"
        tuner._finalize(replay)
    assert tuner.data["final_stable"] is True
    assert tuner.data["eligibility"]["leakage_verified"] is True
    assert tuner.data["eligible_tuned"]["qubit_drag_beta"] == 0.04
    assert tuner.data["eligible_tuned"]["read_pulse_freq"] == (
        candidate["read_pulse_freq"])


def test_leakage_certificate_cannot_authorize_a_different_final_tuple():
    """An older unconstrained replay cannot borrow another tuple's P(f) audit."""
    cfg = _base_config()
    cfg["qubit_anharmonicity_mhz"] = -200.0
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        certified = T._with_candidate(tuner.working, qubit_drag_beta=0.04)
        older = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.working["read_pulse_freq"] + 0.5)
        replay = tuner._confirm_candidates(
            [older], shots=101, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact unconstrained stale regression",
            add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner._final_replay_kind = "unconstrained"
        tuner._leakage_verified_candidate_key = T._candidate_key(certified)
        tuner.data["leakage"].update({
            "active": True, "required_for_write": True, "verified": True,
        })
        tuner._finalize(replay)
    assert tuner.data["eligibility"]["leakage_verified"] is True
    assert tuner.data["eligibility"]["leakage_tuple_match"] is False
    assert tuner.data["final_stable"] is False
    assert tuner.data["eligible_tuned"] == {}


def test_refined_rabi_candidate_cannot_evict_a_spectral_basin():
    """The refined best replaces its coarse basin slot instead of consuming a fifth."""
    params = copy.deepcopy(FAST_PARAMS)
    params["iq_rabi"].update({
        "shortlist": 4, "local_span_mhz": 4.0,
        "freq_points_per_candidate": 3, "gain_points": 9,
        "fine_gain_points": 9,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        centers = [2500.0, 2510.0, 2520.0, 2530.0]
        tuner._spec_candidates_mhz = list(centers)
        tuner._resonator_seed = tuner.READ_FREQ
        tuner._discovery_readout = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=10.0)

        tuner._acquire_iq_chevron = lambda freqs, gains, candidate, shots: (
            np.zeros((len(freqs), len(gains))),
            np.zeros((len(freqs), len(gains))),
        )
        original_analysis = T.analyze_iq_chevron

        def synthetic_analysis(freqs, gains, i_map, q_map, min_r2=0.55):
            del i_map, q_map, min_r2
            freqs = np.asarray(freqs, dtype=float)
            gains = np.asarray(gains, dtype=float)
            if freqs.size == 1:
                projection = np.cos(np.linspace(0.0, 2.0 * np.pi, gains.size))
                fit = {
                    "ok": True, "pi_gain": 1111.0, "r2": 0.99,
                    "yfit": projection,
                }
                row = {"frequency": float(freqs[0]), "projection": projection,
                       "fit": fit, "score": 10.0}
                return {"ok": True, "best": row, "rows": [row]}
            rows = []
            for frequency in freqs:
                nearest = int(np.argmin(np.abs(np.asarray(centers) - frequency)))
                at_center = abs(float(frequency) - centers[nearest]) < 1e-9
                score = (100.0 - 10.0 * nearest) if at_center else 1.0
                projection = np.cos(np.linspace(0.0, 2.0 * np.pi, gains.size))
                rows.append({
                    "frequency": float(frequency), "projection": projection,
                    "fit": {"ok": True, "pi_gain": 1000.0 + 100.0 * nearest,
                            "r2": 0.98, "yfit": projection},
                    "score": score, "snr": 20.0,
                    "relative_contrast": 0.8,
                })
            best = max(rows, key=lambda row: row["score"])
            return {"ok": True, "best": best, "rows": rows}

        T.analyze_iq_chevron = synthetic_analysis
        try:
            tuner._stage_iq_rabi()
        finally:
            T.analyze_iq_chevron = original_analysis

    assert len(tuner._rabi_candidates) == len(centers)
    for center in centers:
        assert any(abs(candidate["qubit_pi_freq"] - center) <= 2.0
                   for candidate in tuner._rabi_candidates)
    refined = min(tuner._rabi_candidates,
                  key=lambda candidate: abs(candidate["qubit_pi_freq"] - centers[0]))
    assert refined["qubit_pi_gain"] == 1111


def test_noncoherent_spectral_branch_cannot_enter_the_control_search():
    """A strong non-oscillatory line must not beat a weaker coherent Rabi line."""
    params = copy.deepcopy(FAST_PARAMS)
    params["iq_rabi"].update({
        "local_span_mhz": 2.0, "freq_points_per_candidate": 3,
        "gain_points": 9, "fine_gain_points": 9, "shortlist": 4,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        distractor, target = 2526.7, 2534.3
        tuner._spec_candidates_mhz = [distractor, target]
        tuner._resonator_seed = tuner.READ_FREQ
        tuner._discovery_readout = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=10.0)
        tuner._acquire_iq_chevron = lambda freqs, gains, candidate, shots: (
            np.zeros((len(freqs), len(gains))),
            np.zeros((len(freqs), len(gains))))
        original_analysis = T.analyze_iq_chevron

        def synthetic_analysis(freqs, gains, i_map, q_map, min_r2=0.55):
            del i_map, q_map, min_r2
            freqs = np.asarray(freqs, dtype=float)
            gains = np.asarray(gains, dtype=float)
            projection = np.cos(np.linspace(0.0, 2.0 * np.pi, gains.size))
            if freqs.size == 1:
                row = {
                    "frequency": float(freqs[0]), "projection": projection,
                    "fit": {"ok": True, "pi_gain": 5700.0, "r2": 0.98,
                            "yfit": projection},
                    "score": 10.0,
                }
                return {"ok": True, "best": row, "rows": [row]}
            rows = []
            for frequency in freqs:
                is_distractor = abs(float(frequency) - distractor) < 1e-9
                is_target = abs(float(frequency) - target) < 1e-9
                rows.append({
                    "frequency": float(frequency), "projection": projection,
                    "fit": {"ok": True, "pi_gain": 4000.0 if is_distractor
                            else 5700.0, "r2": 0.99, "yfit": projection},
                    # The distractor deliberately wins the generic map score but has
                    # neither statistically resolved nor relative Rabi contrast.
                    "score": 100.0 if is_distractor else (50.0 if is_target else 1.0),
                    "snr": 1.0 if is_distractor else (20.0 if is_target else 1.0),
                    "relative_contrast": (0.02 if is_distractor
                                          else (0.80 if is_target else 0.02)),
                })
            return {"ok": True, "best": max(rows, key=lambda row: row["score"]),
                    "rows": rows}

        T.analyze_iq_chevron = synthetic_analysis
        try:
            tuner._stage_iq_rabi()
        finally:
            T.analyze_iq_chevron = original_analysis

    assert tuner._rabi_candidates
    assert all(abs(row["qubit_pi_freq"] - target) <= 1e-6
               for row in tuner._rabi_candidates)
    assert abs(tuner.working["qubit_pi_freq"] - target) <= 1e-6
    rejected = tuner.data["maps"]["iq_rabi"][
        "rejected_spectral_basin_indices"]
    assert 0 in rejected


def test_transition_qualification_falls_through_failed_high_fidelity_branch():
    """One-shot fidelity cannot retain a branch that fails coherent odd/even action."""
    params = copy.deepcopy(FAST_PARAMS)
    params["parity_chevron"].update({
        "branch_compare_shots": 101, "branch_compare_blocks": 2,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        wrong = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=10.0,
            qubit_pi_freq=2527.7, qubit_pi_gain=3000, sigma=tuner.SIGMA)
        right = T._with_candidate(
            wrong, qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA))
        wrong.update({"fidelity": 0.97, "fidelity_se": 0.002,
                      "fidelity_lcb_95": 0.966,
                      "confirmation_complete": True})
        right.update({"fidelity": 0.90, "fidelity_se": 0.004,
                      "fidelity_lcb_95": 0.892,
                      "confirmation_complete": True})
        tuner._rough_control_candidates = [wrong, right]

        def unavailable_parity(seed, stage, label):
            del seed, stage, label
            raise RuntimeError("synthetic parity-map backend fault")

        def exact_audit(candidate, **kwargs):
            del kwargs
            if abs(candidate["qubit_pi_freq"] - tuner.QUBIT_FREQ) > 1.0:
                raise RuntimeError("synthetic incoherent saturation")
            audit = {
                "verified": True, "control_key": T._control_key(candidate),
                "search_complete": True, "selection_confirmed": True,
            }
            tuner._maps["final_control_verify"] = audit
            return audit

        tuner._parity_refine_branch = unavailable_parity
        tuner._stage_final_control_verify = exact_audit
        selected = tuner._stage_parity_chevron()

        tuner._discovery_status.update({"resonator": True, "spectroscopy": True})
        tuner._maps["resonator"] = {
            "search_complete": True, "selection_confirmed": True}
        tuner._maps["spectroscopy"] = {
            "search_complete": True, "selection_confirmed": True}
        tuner._maps["iq_rabi"] = {
            "coherent_witness": True, "selection_confirmed": True,
            "coherent_witness_frequencies_mhz": np.asarray([
                tuner.QUBIT_FREQ]),
        }
        gate = tuner._stage_pre_expensive_gate()

    assert abs(selected["qubit_pi_freq"] - tuner.QUBIT_FREQ) < 0.3
    records = tuner.data["control_branch_qualification"]["branches"]
    wrong_record = min(records, key=lambda row: row["rabi_frequency_mhz"])
    assert wrong_record["status"] == "frequency_qualified_control_provisional"
    assert "incoherent saturation" in wrong_record["control_failure"]
    assert gate["qubit_pi_freq"] == selected["qubit_pi_freq"]
    assert tuner.data["control_branch_qualification"][
        "expensive_search_allowed"] is True


def test_rough_control_audit_failure_does_not_block_frequency_optimization():
    """A rough gain may be imperfect after the transition frequency is established."""
    params = copy.deepcopy(FAST_PARAMS)
    params["parity_chevron"].update({
        "branch_compare_shots": 101, "branch_compare_blocks": 2,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        candidate = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=10.0,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA), sigma=tuner.SIGMA)
        candidate.update({
            "fidelity": 0.94, "fidelity_se": 0.006,
            "fidelity_lcb_95": 0.928, "confirmation_complete": True,
        })
        tuner._rough_control_candidates = [candidate]

        def unavailable_parity(seed, stage, label):
            del seed, stage, label
            raise RuntimeError("synthetic rough parity-map fault")

        def imperfect_rough_control(contender, **kwargs):
            del contender, kwargs
            raise RuntimeError("synthetic rough amplitude error")

        tuner._parity_refine_branch = unavailable_parity
        tuner._stage_final_control_verify = imperfect_rough_control
        selected = tuner._stage_parity_chevron()
        tuner._discovery_status.update({"resonator": True, "spectroscopy": True})
        tuner._maps["resonator"] = {
            "search_complete": True, "selection_confirmed": True}
        tuner._maps["spectroscopy"] = {
            "search_complete": True, "selection_confirmed": True}
        tuner._maps["iq_rabi"] = {
            "coherent_witness": True, "selection_confirmed": True,
            "coherent_witness_frequencies_mhz": np.asarray([tuner.QUBIT_FREQ]),
        }
        gate = tuner._stage_pre_expensive_gate()

    qualification = tuner.data["control_branch_qualification"]
    gate = tuner.data["pre_expensive_gate"]
    assert abs(selected["qubit_pi_freq"] - tuner.QUBIT_FREQ) < 0.3
    assert qualification["frequency_qualified"] is True
    assert qualification["selected_control_verified"] is False
    assert qualification["status"] == "frequency_qualified_control_provisional"
    assert qualification["expensive_search_allowed"] is True
    assert gate["passed"] is True
    assert gate["rough_control_verified"] is False


def test_uninformative_branch_comparison_preserves_passive_bootstrap_and_basins():
    """Coin-flip feedback rows cannot select a branch or discard coherent Rabi."""
    params = copy.deepcopy(FAST_PARAMS)
    params["parity_chevron"].update({
        "branch_compare_shots": 101, "branch_compare_blocks": 2,
        "minimum_informative_branch_fidelity_lcb": 0.60,
        "minimum_informative_branch_separation_sigma": 0.75,
    })
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        wrong = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=5500, read_length=10.0,
            qubit_pi_freq=tuner.QUBIT_FREQ - 2.0,
            qubit_pi_gain=3600, sigma=0.25,
            fidelity=0.52, fidelity_se=0.005,
            fidelity_lcb_95=0.5102, sep_sigma=0.08,
            confirmation_blocks=2, confirmation_complete=True,
            confirmation_batch_complete=True, evidence_tier=3)
        right = T._with_candidate(
            wrong, qubit_pi_freq=tuner.QUBIT_FREQ, qubit_pi_gain=5750,
            fidelity=0.94, fidelity_se=0.005,
            fidelity_lcb_95=0.9302, sep_sigma=5.8)
        tuner._rough_control_candidates = [wrong, right]
        tuner._bootstrap_control_candidate = copy.deepcopy(right)
        tuner._parity_refine_branch = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic unavailable parity"))
        tuner._stage_final_control_verify = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic unavailable exact audit"))

        def collapsed_comparison(candidates, shots, blocks, label,
                                 add_to_history=True):
            del shots, label, add_to_history
            rows = []
            for index, candidate in enumerate(candidates):
                row = dict(candidate)
                fidelity = 0.532 if index == 0 else 0.531
                row.update({
                    "fidelity": fidelity, "fidelity_se": 0.006,
                    "fidelity_lcb_95": fidelity - 0.01176,
                    "sep_sigma": 0.09, "confirmation_blocks": blocks,
                    "confirmation_complete": True,
                    "confirmation_batch_complete": True,
                    "evidence_tier": 3,
                })
                rows.append(row)
            return rows

        tuner._confirm_candidates = collapsed_comparison
        selected = tuner._stage_parity_chevron()

    assert np.isclose(selected["qubit_pi_freq"], tuner.QUBIT_FREQ)
    assert int(selected["qubit_pi_gain"]) == 5750
    assert sorted(tuner._qualified_transition_frequencies) == sorted([
        tuner.QUBIT_FREQ - 2.0, tuner.QUBIT_FREQ])
    qualification = tuner.data["control_branch_qualification"]
    assert qualification["comparison_informative"] is False
    assert "passive bootstrap retained" in qualification["selection_reason"]
    assert tuner._candidate_in_qualified_transition(wrong)
    assert tuner._candidate_in_qualified_transition(right)


def test_provisional_rough_control_still_produces_the_duration_portfolio():
    """Final rows own strict control certification; the rough seed does not."""
    class ProvisionalControlTuner(VirtualBasicAutoTuner):
        def _stage_final_control_verify(self, candidate, **kwargs):
            del kwargs
            self._maps["final_control_verify"] = {
                "verified": False, "control_key": T._control_key(candidate),
                "search_complete": False, "selection_confirmed": False,
            }
            raise RuntimeError("synthetic exact odd/even control failure")

    params = copy.deepcopy(FAST_PARAMS)
    params["duration_portfolio"] = {
        "enabled": True, "read_lengths_us": [1.0, 2.0, 3.0],
        "native_seeds_per_length": 1,
        "readout_seeds_per_length": 1,
        "control_seed_count": 1,
        "local_proposals_per_length": 0,
        "refine_shots": 101, "refine_blocks": 2,
        "screen_shots": 101, "screen_reference_shots": 151,
        "screen_drift_retries": 0,
        "confirm_shots": 151, "confirm_blocks": 2,
        "confirm_candidates_per_length": 1,
        "require_control_audit": True,
    }
    with tempfile.TemporaryDirectory() as folder:
        tuner = ProvisionalControlTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params, fail_parity=True)
        with redirect_stdout(io.StringIO()):
            data = tuner.acquire(plotDisp=False)["data"]

    stage_names = [row["name"] for row in data["stages"]]
    entries = data["duration_portfolio"]["entries"]
    assert data["pre_expensive_gate"]["passed"] is True
    assert data["pre_expensive_gate"]["rough_control_verified"] is False
    assert "joint_search" in stage_names
    assert "duration_portfolio" in stage_names
    assert len(entries) == 3
    assert all(entry["status"] != "SAFE" for entry in entries)
    assert all(entry["control_status"] != "VERIFIED" for entry in entries)


def test_rejected_transition_cannot_reenter_late_recovery_or_safety_pools():
    """Raw archives cannot bypass the qualified transition phase boundary."""
    params = copy.deepcopy(FAST_PARAMS)
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        right = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN, read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=int(tuner.PI_GAIN_AT_SIGMA), sigma=tuner.SIGMA)
        wrong = T._with_candidate(
            right, qubit_pi_freq=2527.7, qubit_pi_gain=3000)
        right.update({"fidelity": 0.91, "fidelity_lcb_95": 0.89,
                      "confirmation_complete": True})
        wrong.update({"fidelity": 0.99, "fidelity_lcb_95": 0.98,
                      "confirmation_complete": True})
        tuner._qualified_transition_frequency = tuner.QUBIT_FREQ
        tuner._qualified_control_key = T._control_key(right)
        tuner.working = dict(right)
        tuner._confirmed = [wrong, right]
        tuner._archive = [wrong, right]
        tuner.data["final_candidates"] = [wrong, right]
        tuner._unconfirmed_contenders = [{
            "candidate": wrong, "missing_blocks": 3, "completed_blocks": 0,
            "scheduled_blocks": 3, "batch_incomplete": True,
            "label": "rejected transition regression", "order": 0,
        }]

        operational = tuner._operational_waveform_pool()
        direct = tuner._leakage_waveform_pool()
        tuner._stage_final()

    for row in operational + direct + tuner.data["final_candidates"]:
        assert abs(row["qubit_pi_freq"] - tuner.QUBIT_FREQ) <= 2.0
    assert not any(abs(row["qubit_pi_freq"] - 2527.7) < 1e-6
                   for row in tuner.data["final_candidates"])


def test_portfolio_safety_failure_is_not_mislabeled_as_leakage():
    params = copy.deepcopy(FAST_PARAMS)
    params["duration_portfolio"] = {"enabled": True}
    params["leakage"] = {"enabled": False, "operational_enabled": True}
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params)
        screening = {
            "valid": True, "portfolio_safe": True,
            "third_blob_excess_ucb": 0.004,
            "third_cluster_guard_available": True,
            "third_cluster_supported": False,
        }
        unavailable = {
            "confirmation_complete": False,
            "third_cluster_guard_available": False,
            "third_blob_excess_ucb": 0.004,
        }
        leaking = {
            "confirmation_complete": True,
            "third_cluster_guard_available": True,
            "third_cluster_supported": True,
            "third_blob_excess_ucb": 0.004,
            "third_cluster_fraction_ucb_95": 0.20,
            "third_cluster_single_state_fraction_ucb_95": 0.25,
        }
    assert tuner._portfolio_confirmation_status(
        screening, unavailable) == "INCONCLUSIVE"
    assert tuner._portfolio_confirmation_status(screening, leaking) == "UNSAFE"


def test_partial_wrapper_grid_can_report_but_not_authorize():
    """A confirmed interior winner does not make an 8/9 map write-complete."""
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        tuner.working = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA,
            sigma=tuner.SIGMA,
        )
        tuner._resonator_seed = tuner.READ_FREQ
        original_pair = tuner._acquire_ss_pair

        def fail_one_corner(candidate, shots, state_order="ge"):
            if (int(shots) == int(tuner.params["readout"]["shots"])
                    and int(candidate["read_pulse_gain"]) == 1500
                    and candidate["read_pulse_freq"] < tuner.READ_FREQ - 1.0):
                raise RuntimeError("synthetic missing corner")
            return original_pair(candidate, shots, state_order)

        tuner._acquire_ss_pair = fail_one_corner
        tuner._stage_readout_grid("coverage_readout", local=False)

    mapping = tuner.data["maps"]["coverage_readout"]
    assert mapping["coverage"] == 8.0 / 9.0
    assert mapping["selection_confirmed"] is True
    assert mapping["edge_winner"] is False
    assert mapping["search_complete"] is False
    assert tuner._key_has_evidence(
        "read_pulse_freq", tuner.working["read_pulse_freq"]) is False
    assert tuner._key_has_evidence(
        "read_pulse_gain", tuner.working["read_pulse_gain"]) is False


def test_interrupt_after_final_replay_never_emits_eligibility():
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        candidate = T._with_candidate(
            tuner.working, read_pulse_freq=tuner.working["read_pulse_freq"] + 0.5)
        tuner.working = dict(candidate)
        tuner._record_key_evidence(
            ["read_pulse_freq"], "synthetic complete search", complete=True)
        replay = tuner._confirm_candidates(
            [candidate], shots=101, blocks=FAST_PARAMS["final"]["blocks"],
            label="final exact interrupt replay", add_to_history=False,
        )[0]
        tuner._final_replay_completed = True
        tuner._interrupted = True
        tuner._finalize(replay)
    assert tuner.data["final_stable"] is False
    assert tuner.data["interrupted"] is True
    assert tuner.data["eligible_tuned"] == {}


def test_runner_is_report_only_for_manual_duration_portfolio_selection():
    """The shipped portfolio runner never applies one row automatically."""
    runner_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "Runners", "BasicAutoTune.py"))
    with open(runner_path, encoding="utf-8") as stream:
        source = stream.read()
    tree = ast.parse(source, filename=runner_path)
    assignments = {
        target.id: node.value
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    assert ast.literal_eval(assignments["APPLY_CONFIG"]) is False
    assert 'not bool(result.get("final_stable", False))' in source
    assert 'bool(result.get("interrupted", False))' in source
    assert "expected_source_hash=startup_source_hash" in source
    assert 'eligible = result.get("eligible_tuned", {})' in source
    assert "FREQUENCY QUALIFICATION FAILED" in source
    assert 'result.get("outcome") == "transition_qualification_failed"' in source

    discovery_updates = {}
    for node in ast.walk(tree):
        if (not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr != "update"
                or not isinstance(node.func.value, ast.Subscript)
                or not isinstance(node.func.value.value, ast.Name)
                or node.func.value.value.id != "P_BASIC"
                or len(node.args) != 1):
            continue
        key = ast.literal_eval(node.func.value.slice)
        discovery_updates[key] = ast.literal_eval(node.args[0])
    assert discovery_updates == {}
    assert T.BASIC_DEFAULTS["resonator"]["search_radius_mhz"] == 100.0
    assert T.BASIC_DEFAULTS["spectroscopy"]["search_radius_mhz"] == 100.0
    assert T.BASIC_DEFAULTS["resonator"]["search_min_mhz"] is None
    assert T.BASIC_DEFAULTS["spectroscopy"]["search_min_mhz"] is None
    for hardcoded_frequency in ("7244.0", "7253.0", "2240.0", "2580.0"):
        assert hardcoded_frequency not in source


def test_runner_main_never_writes_a_guard_rejected_result():
    """Execute the destructive boundary; source-string checks are insufficient."""
    runner_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "Runners", "BasicAutoTune.py"))
    initialize_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize")
    proxy_name = (
        "WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy")
    saved_modules = {name: sys.modules.get(name)
                     for name in (initialize_name, proxy_name)}
    fake_initialize = types.ModuleType(initialize_name)
    fake_initialize.BaseConfig = _base_config()
    fake_initialize.outerFolder = tempfile.gettempdir()
    fake_proxy = types.ModuleType(proxy_name)
    fake_proxy.makeProxy = lambda: (object(), object())
    sys.modules[initialize_name] = fake_initialize
    sys.modules[proxy_name] = fake_proxy
    try:
        spec = importlib.util.spec_from_file_location(
            "_basic_auto_tune_runner_runtime_test", runner_path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
    finally:
        for name, previous in saved_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    class RecordingUpdater:
        def __init__(self):
            self.update_calls = []
            self.history = []
            self.allow_update = False

        @staticmethod
        def baseconfig_source_hash():
            return "unchanged-source"

        def update_baseconfig(self, *args, **kwargs):
            self.update_calls.append((args, kwargs))
            if not self.allow_update:
                raise AssertionError(
                    "guard-rejected result reached update_baseconfig")
            values = dict(args[0])
            startup = _base_config()
            return {key: (startup.get(key), value)
                    for key, value in values.items()}

        def append_history(self, row):
            self.history.append(row)

        @staticmethod
        def prune_backups(keep=10):
            del keep

        @staticmethod
        def config_path():
            return "unused"

    updater = RecordingUpdater()
    runner.config_updater = updater
    runner.makeProxy = lambda: (object(), object())
    runner.APPLY_CONFIG = True

    best = T._with_candidate(
        T._candidate_from_cfg(_base_config()),
        qubit_pi_gain=5790,
    )
    best.update({
        "fidelity": 0.95, "fidelity_se": 0.005,
        "fidelity_lcb_95": 0.9402,
        "confirmation_blocks": 3,
        "block_fidelities": [0.95, 0.95, 0.95],
        "block_spread": 0.0,
        "label": "final exact leakage-screened step-5 replay",
    })
    current = {"result": None}

    class FakeExperiment:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            self.data = copy.deepcopy(current["result"])
            self.iname = None

        def acquire(self, **kwargs):
            del kwargs
            return {"data": copy.deepcopy(self.data)}

        def save_data(self):
            return None

        def save_plot(self):
            return None

    runner.BasicAutoTuner = FakeExperiment
    control_key = T._control_key(best)
    candidate_key = T._candidate_key(best)
    base_result = {
        "best_found": best,
        "tuned": {key: best[key] for key in T.TUNED_KEYS},
        "eligible_tuned": {"qubit_pi_gain": 5790},
        "outcome": "completed_with_warnings",
        "interrupted": False,
        "final_stable": True,
        "fidelity_replay_stable": True,
        "latency_optimization": {
            "enabled": True,
            "status": "not_run",
            "latency_certificate_valid": False,
            "qualified_speedup": False,
            "timing_certificate_was_active": False,
            "final_fidelity_guard_passed": True,
            "certificate_matches_final_tuple": False,
        },
        "leakage": {
            "active": True, "strict_direct_active": False,
            "operational_active": True, "required_for_write": True,
            "selection_safe": True, "verified": True,
            "third_cluster_guard": True,
            "worst_third_cluster_fraction": 0.02,
            "worst_third_cluster_fraction_ucb_95": 0.025,
            "worst_third_cluster_single_state_fraction": 0.03,
            "worst_third_cluster_single_state_fraction_ucb_95": 0.035,
            "final_replay_complete": True,
            "verified_candidate_key": list(candidate_key),
        },
        "maps": {
            "resonator": {
                "search_complete": True, "selection_confirmed": True,
                "used_global_scan": True,
                "allowed_min_mhz": 7147.0,
                "allowed_max_mhz": 7347.0,
            },
            "spectroscopy": {
                "search_complete": True, "selection_confirmed": True,
                "used_global_scan": True,
                "allowed_min_mhz": 2424.5,
                "allowed_max_mhz": 2624.5,
            },
            "joint_search": {
                "search_complete": True, "selection_confirmed": True,
            },
        },
        "joint_search": {
            "status": "complete",
            "coverage": {
                "complete": True, "expected_strata": 1,
                "measured_strata": 1, "missing_strata": [],
            },
        },
        "discovery": {
            "missing_for_write": [], "verified_for_write": True},
        "write_fidelity_gate": {
            "passed": True, "measured_lcb": 0.9402,
            "minimum_lcb": 0.60,
        },
        "control_validation": {
            "required_for_write": True, "verified_for_write": True,
            "selected_control_key": control_key,
            "fresh_exact_audit_key": control_key,
            "matching_witnesses": [{
                "stage": "final_control_verify",
                "kind": "exact_odd_even_repeated_pulses",
                "exact_tuple": True,
                "control_key": control_key,
                "blocks": 2,
                "pulse_counts": [1, 2, 3, 4, 5, 6],
                "worst_even_return_error_ucb": 0.10,
                "worst_odd_inversion_error_ucb": 0.11,
            }],
        },
        "eligibility": {
            "atomic_tuple_safe": True, "discovery_verified": True,
            "write_fidelity_qualified": True, "control_verified": True,
            "changed_keys": ["qubit_pi_gain"], "write_needed": True,
            "leakage_required": True, "leakage_verified": True,
            "leakage_tuple_match": True,
            "latency_final_fidelity_guard": True,
            "final_replay_kind": "leakage_constrained",
        },
    }
    assert runner._write_contract_errors(
        base_result, base_result["eligible_tuned"], _base_config()) == []

    forged_joint = copy.deepcopy(base_result)
    forged_joint["joint_search"]["coverage"]["complete"] = False
    forged_joint_errors = runner._write_contract_errors(
        forged_joint, forged_joint["eligible_tuned"], _base_config())
    assert any("joint-search coverage" in error for error in forged_joint_errors)

    forged_branch = copy.deepcopy(base_result)
    forged_branch["maps"]["resonator"].update({
        "candidate_frequencies_mhz": [7108.4, 7249.1],
        "selected_frequency_mhz": 7249.1,
        "branch_backtracking_complete": True,
    })
    forged_branch["maps"]["spectroscopy"].update({
        "resonator_branch_valid": [True, True],
        "selected_resonator_branch_mhz": 7249.1,
        "branch_backtracking_complete": True,
    })
    forged_branch_errors = runner._write_contract_errors(
        forged_branch, forged_branch["eligible_tuned"], _base_config())
    assert any("coherent Rabi/direct-SS" in error
               for error in forged_branch_errors)

    # A real timing certificate is substantially stronger than the ordinary
    # ``not_run`` fallback above: it contains finite-block Student-t multiplicity,
    # complete two-fold cross-fit blocks for every feasible arm, and an exact tuple
    # match at the final destructive boundary.  Keep one fully valid fixture here so
    # future guard hardening cannot accidentally make every timing result unwritable.
    timing_result = copy.deepcopy(base_result)
    timing_result.update({
        "revision": T.BASIC_AUTOTUNER_REVISION,
        "autotuner_revision": T.BASIC_AUTOTUNER_REVISION,
    })
    assert T.BASIC_AUTOTUNER_REVISION == "reset-qualified-portfolio-v10"
    timing_best = timing_result["best_found"]
    timing_blocks = 8
    timing_crossfit_se = 0.001 / np.sqrt(timing_blocks)
    timing_pairing_ids = ["fixture-timing-block-%d" % index
                          for index in range(timing_blocks)]
    timing_best.update({
        "confirmation_blocks": timing_blocks,
        "block_fidelities": [0.950] * timing_blocks,
        "block_fidelity_ses": [0.001] * timing_blocks,
        "block_spread": 0.0,
        "crossfit_fidelity": 0.950,
        "crossfit_fidelity_se": timing_crossfit_se,
        "crossfit_fidelity_lcb_95": 0.950 - 1.96 * timing_crossfit_se,
        "block_crossfit_fidelities": [0.950] * timing_blocks,
        "block_crossfit_fidelity_ses": [0.001] * timing_blocks,
        "block_pairing_ids": list(timing_pairing_ids),
        "crossfit_block_spread": 0.0,
        "fidelity_estimator_for_latency": "two_fold_crossfit",
    })
    timing_reference = copy.deepcopy(timing_best)
    timing_reference.update({
        "read_length": 20.0,
        "sigma": 0.25,
        "qubit_pi_gain": 5790,
        "fidelity": 0.952,
        "fidelity_se": 0.001,
        "fidelity_lcb_95": 0.952 - 1.96 * 0.001,
        "block_fidelities": [0.952] * timing_blocks,
        "crossfit_fidelity": 0.952,
        "crossfit_fidelity_se": timing_crossfit_se,
        "crossfit_fidelity_lcb_95": 0.952 - 1.96 * timing_crossfit_se,
        "block_crossfit_fidelities": [0.952] * timing_blocks,
    })
    family_count = 2 * (2 - 1) * (
        1 + int(runner.P_BASIC["latency"]["adaptive_confirmation_rounds"]))
    family_alpha = float(runner.P_BASIC["latency"]["familywise_alpha"])
    family_df = timing_blocks - 1
    family_z = max(
        float(runner.P_BASIC["latency"]["confidence_sigma"]),
        float(ndtri(1.0 - family_alpha / family_count)),
        float(runner.student_t.ppf(
            1.0 - family_alpha / family_count, family_df)),
    )
    selected_loss = T.BasicAutoTuner._latency_noninferiority(
        timing_reference, timing_best,
        runner.P_BASIC["latency"]["max_fidelity_loss"], family_z)
    timing_best_key = T._candidate_key(timing_best)
    timing_reference_key = T._candidate_key(timing_reference)
    timing_result["maps"]["latency"] = {
        "confirmations": [
            copy.deepcopy(timing_reference), copy.deepcopy(timing_best)],
        "infeasible_reference_keys": [],
    }
    timing_result["latency_optimization"] = {
        "enabled": True,
        "status": "selected",
        "reference": copy.deepcopy(timing_reference),
        "selected": copy.deepcopy(timing_best),
        "certified_selected": copy.deepcopy(timing_best),
        "certified_selected_key": list(timing_best_key),
        "latency_certificate_valid": True,
        "qualified_speedup": True,
        "timing_certificate_was_active": True,
        "certificate_matches_final_tuple": True,
        "final_fidelity_guard_passed": True,
        "max_fidelity_loss": float(
            runner.P_BASIC["latency"]["max_fidelity_loss"]),
        "max_final_fidelity_drop": float(min(
            runner.P_BASIC["latency"]["max_final_fidelity_drop"],
            runner.P_BASIC["latency"]["max_fidelity_loss"])),
        "familywise_comparison_count": family_count,
        "familywise_confidence_sigma": family_z,
        "familywise_distribution": "student_t",
        "familywise_degrees_of_freedom": family_df,
        "reference_latency_us": T.BasicAutoTuner._candidate_latency_us(
            timing_reference),
        "selected_latency_us": T.BasicAutoTuner._candidate_latency_us(
            timing_best),
        "latency_saved_us": (
            T.BasicAutoTuner._candidate_latency_us(timing_reference)
            - T.BasicAutoTuner._candidate_latency_us(timing_best)),
        "diagnostics": [{
            "candidate_key": list(timing_reference_key),
            "accepted": True,
            "loss_ucb": 0.0,
        }, {
            "candidate_key": list(timing_best_key),
            "accepted": True,
            "loss_ucb": float(selected_loss["loss_ucb"]),
        }],
        "infeasible_reference_keys": [],
        "anchor_control_audits": [],
        "anchor_safety_audits": [],
    }
    assert selected_loss["eligible"] is True
    assert runner._write_contract_errors(
        timing_result, timing_result["eligible_tuned"], _base_config()) == []

    forged_normal_z = copy.deepcopy(timing_result)
    forged_normal_z["latency_optimization"][
        "familywise_confidence_sigma"] = max(
            float(runner.P_BASIC["latency"]["confidence_sigma"]),
            float(ndtri(1.0 - family_alpha / family_count)))
    normal_z_errors = runner._write_contract_errors(
        forged_normal_z, forged_normal_z["eligible_tuned"], _base_config())
    assert any("confidence multiplier is too small" in error
               for error in normal_z_errors)

    forged_missing_crossfit = copy.deepcopy(timing_result)
    del forged_missing_crossfit["maps"]["latency"]["confirmations"][0][
        "block_crossfit_fidelities"]
    crossfit_errors = runner._write_contract_errors(
        forged_missing_crossfit,
        forged_missing_crossfit["eligible_tuned"], _base_config())
    assert any("lacks complete cross-fit blocks" in error
               for error in crossfit_errors)

    forged_cross_cohort = copy.deepcopy(timing_result)
    forged_cross_cohort["maps"]["latency"]["confirmations"][0][
        "block_pairing_ids"] = ["different-drift-window-%d" % index
                                for index in range(timing_blocks)]
    cohort_errors = runner._write_contract_errors(
        forged_cross_cohort,
        forged_cross_cohort["eligible_tuned"], _base_config())
    assert any("common interleaved drift cohort" in error
               for error in cohort_errors)

    forged_weak_recovery = copy.deepcopy(base_result)
    recovered_reference = copy.deepcopy(forged_weak_recovery["best_found"])
    displaced_exact_final = copy.deepcopy(recovered_reference)
    displaced_exact_final.update({
        "read_length": 8.0,
        "fidelity": 0.960,
        "fidelity_se": 0.004,
        "fidelity_lcb_95": 0.960 - 1.96 * 0.004,
        "block_fidelities": [0.960, 0.960, 0.960],
        "block_spread": 0.0,
        "label": "final exact feedback-reset step-5 replay",
    })
    certified_fast = copy.deepcopy(displaced_exact_final)
    certified_fast.update({
        "fidelity": 0.975,
        "fidelity_se": 0.002,
        "fidelity_lcb_95": 0.975 - 1.96 * 0.002,
        "block_fidelities": [0.975, 0.975, 0.975],
    })
    forged_weak_recovery["latency_optimization"] = {
        "enabled": True,
        "status": "failed_final_timing_guard_retained_fidelity_reference",
        "reference": copy.deepcopy(recovered_reference),
        "selected": copy.deepcopy(recovered_reference),
        "certified_selected": copy.deepcopy(certified_fast),
        "certified_selected_key": list(T._candidate_key(certified_fast)),
        "latency_certificate_valid": False,
        "qualified_speedup": False,
        "timing_certificate_was_active": False,
        "certificate_matches_final_tuple": False,
        "final_fidelity_guard_passed": True,
        "late_final_guard_probe": {
            "passed": False,
            "candidate_key": list(T._candidate_key(displaced_exact_final)),
            "certified_candidate_key": list(T._candidate_key(certified_fast)),
            "final_timing_fidelity": displaced_exact_final["fidelity"],
            "certified_timing_fidelity": certified_fast["fidelity"],
            "maximum_drop": float(
                runner.P_BASIC["latency"]["max_final_fidelity_drop"]),
            "estimator": "legacy_resubstitution",
        },
        # Internally explicit but physically backwards: this claims that a weaker
        # recovered reference displaced a better complete exact replay.
        "reference_recovery": {
            "attempted": True,
            "passed": True,
            "adopted": True,
            "original_final": copy.deepcopy(displaced_exact_final),
            "recovered_reference": copy.deepcopy(recovered_reference),
            "selected_candidate_key": list(
                T._candidate_key(recovered_reference)),
            "original_rank": [
                displaced_exact_final["fidelity_lcb_95"],
                displaced_exact_final["fidelity"],
            ],
            "recovered_rank": [
                recovered_reference["fidelity_lcb_95"],
                recovered_reference["fidelity"],
            ],
            "comparison_estimator": (
                "legacy_resubstitution_lcb_then_mean"),
            "reason": "forged weaker reference adoption",
        },
    }
    weak_recovery_errors = runner._write_contract_errors(
        forged_weak_recovery,
        forged_weak_recovery["eligible_tuned"], _base_config())
    assert any("recovery" in error or "weaker" in error
               for error in weak_recovery_errors)

    forged_crossfit_summary = copy.deepcopy(timing_result)
    forged_crossfit_summary["maps"]["latency"]["confirmations"][0].update({
        "crossfit_fidelity_se": 0.0,
        "crossfit_fidelity_lcb_95": 0.954,
    })
    summary_errors = runner._write_contract_errors(
        forged_crossfit_summary,
        forged_crossfit_summary["eligible_tuned"], _base_config())
    assert any("cross-fit timing-block summary is inconsistent" in error
               for error in summary_errors)

    current["result"] = copy.deepcopy(base_result)
    updater.allow_update = True
    with redirect_stdout(io.StringIO()):
        assert runner.main() == 0
    updater.allow_update = False
    assert len(updater.update_calls) == 1
    assert updater.update_calls[0][0][0] == {"qubit_pi_gain": 5790}
    assert updater.history[-1]["applied"] is True

    rejected = []
    discovery = copy.deepcopy(base_result)
    discovery["discovery"] = {
        "missing_for_write": ["spectroscopy"], "verified_for_write": False}
    discovery["eligibility"]["discovery_verified"] = False
    rejected.append(discovery)
    forged_discovery = copy.deepcopy(base_result)
    forged_discovery["maps"]["spectroscopy"]["selection_confirmed"] = False
    rejected.append(forged_discovery)
    fidelity = copy.deepcopy(base_result)
    fidelity["write_fidelity_gate"] = {
        "passed": False, "measured_lcb": 0.52, "minimum_lcb": 0.60}
    fidelity["eligibility"]["write_fidelity_qualified"] = False
    rejected.append(fidelity)
    forged_fidelity = copy.deepcopy(base_result)
    forged_fidelity["best_found"]["fidelity_lcb_95"] = 0.52
    forged_fidelity["write_fidelity_gate"].update({
        "passed": True, "measured_lcb": 0.52,
    })
    rejected.append(forged_fidelity)
    control = copy.deepcopy(base_result)
    control["control_validation"]["verified_for_write"] = False
    control["eligibility"]["control_verified"] = False
    rejected.append(control)
    forged_control = copy.deepcopy(base_result)
    forged_control["control_validation"]["matching_witnesses"] = []
    rejected.append(forged_control)
    unknown = copy.deepcopy(base_result)
    unknown["eligible_tuned"]["not_a_calibration_key"] = 123
    rejected.append(unknown)
    mismatched = copy.deepcopy(base_result)
    mismatched["eligible_tuned"]["qubit_pi_gain"] = 20000
    rejected.append(mismatched)
    split_frequency_alias = copy.deepcopy(base_result)
    split_frequency_alias["best_found"]["qubit_freq"] += 1.0
    split_frequency_alias["tuned"]["qubit_freq"] += 1.0
    rejected.append(split_frequency_alias)
    omitted = copy.deepcopy(base_result)
    omitted["best_found"]["read_pulse_freq"] += 0.25
    omitted["tuned"]["read_pulse_freq"] += 0.25
    rejected.append(omitted)
    leakage_bypass = copy.deepcopy(base_result)
    leakage_bypass["leakage"].update({
        "active": False, "operational_active": False,
        "required_for_write": False, "verified": False,
        "selection_safe": False, "final_replay_complete": False,
        "verified_candidate_key": None,
    })
    leakage_bypass["eligibility"].update({
        "leakage_required": False, "leakage_verified": False,
        "final_replay_kind": "unconstrained",
    })
    rejected.append(leakage_bypass)
    stale_leakage = copy.deepcopy(base_result)
    stale_leakage["leakage"]["verified_candidate_key"] = [0] * 7
    rejected.append(stale_leakage)
    resolved_third_population = copy.deepcopy(base_result)
    resolved_third_population["leakage"].update({
        "worst_third_cluster_fraction": 0.18,
        "worst_third_cluster_fraction_ucb_95": 0.19,
        "worst_third_cluster_single_state_fraction": 0.24,
        "worst_third_cluster_single_state_fraction_ucb_95": 0.25,
    })
    rejected.append(resolved_third_population)
    rejected.append(forged_weak_recovery)

    with redirect_stdout(io.StringIO()):
        for result in rejected:
            current["result"] = result
            assert runner.main() == 0

    assert len(updater.update_calls) == 1
    assert len(updater.history) == len(rejected) + 1
    assert all(row["applied"] is False for row in updater.history[1:])

    qualification_failure = copy.deepcopy(base_result)
    qualification_failure.update({
        "outcome": "transition_qualification_failed",
        "success": False, "final_stable": False,
        "fidelity_replay_stable": False,
        "eligible_tuned": {},
        "pre_expensive_gate": {
            "passed": False,
            "failures": ["no coherent-Rabi-qualified transition was selected"],
        },
        "control_branch_qualification": {
            "status": "failed", "frequency_qualified": False,
            "branches": [],
        },
    })
    current["result"] = qualification_failure
    runner.APPLY_CONFIG = False
    output = io.StringIO()
    with redirect_stdout(output):
        assert runner.main() == 1
    rendered = output.getvalue()
    assert "FREQUENCY QUALIFICATION FAILED" in rendered
    assert "BEST DIAGNOSTIC MEASUREMENT (NOT A TUNE)" in rendered
    assert "independent write contract:" not in rendered
    assert len(updater.update_calls) == 1


def test_config_update_compare_and_swap_refuses_stale_input():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "initialize.py")
        source = 'BaseConfig = {\n    "qubit_pi_gain": 1000,\n}\n'
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(source)
        try:
            config_updater.update_baseconfig(
                {"qubit_pi_gain": 1200}, path=path, backup=False,
                expected={"qubit_pi_gain": 999})
        except RuntimeError as exc:
            assert "compare-and-swap failed" in str(exc)
        else:
            raise AssertionError("stale compare-and-swap unexpectedly wrote")
        with open(path, encoding="utf-8") as stream:
            assert stream.read() == source
        config_updater.update_baseconfig(
            {"qubit_pi_gain": 1200}, path=path, backup=False,
            expected={"qubit_pi_gain": 1000})
        assert config_updater.read_baseconfig(path)["qubit_pi_gain"] == 1200


def test_config_source_hash_refuses_untuned_physical_change():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "initialize.py")
        original = (
            'BaseConfig = {\n'
            '    "qubit_pi_gain": 1000,\n'
            '    "qubit_drag_beta": 0.0,\n'
            '}\n'
        )
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(original)
        snapshot = config_updater.baseconfig_source_hash(path)
        changed_physical_path = original.replace(
            '"qubit_drag_beta": 0.0', '"qubit_drag_beta": 0.5')
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(changed_physical_path)
        try:
            config_updater.update_baseconfig(
                {"qubit_pi_gain": 1200}, path=path, backup=False,
                expected={"qubit_pi_gain": 1000},
                expected_source_hash=snapshot)
        except RuntimeError as exc:
            assert "complete BaseConfig source changed" in str(exc)
        else:
            raise AssertionError("untuned physical change unexpectedly passed CAS")
        live = config_updater.read_baseconfig(path)
        assert live["qubit_pi_gain"] == 1000
        assert live["qubit_drag_beta"] == 0.5


def test_config_source_hash_is_stable_for_windows_crlf():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "initialize.py")
        source = b'BaseConfig = {\r\n    "qubit_pi_gain": 1000,\r\n}\r\n'
        with open(path, "wb") as stream:
            stream.write(source)
        snapshot = config_updater.baseconfig_source_hash(path)
        config_updater.update_baseconfig(
            {"qubit_pi_gain": 1200}, path=path, backup=False,
            expected={"qubit_pi_gain": 1000},
            expected_source_hash=snapshot)
        with open(path, "rb") as stream:
            written = stream.read()
        assert b'"qubit_pi_gain": 1200' in written
        assert b"\r\r\n" not in written
        assert written.count(b"\r\n") == source.count(b"\r\n")


def test_amplified_scans_expand_boundary_once_and_retain_correction():
    """Fine/parity maps must look past a trending boundary before stopping."""
    params = copy.deepcopy(FAST_PARAMS)
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        optimum = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA,
            sigma=tuner.SIGMA,
        )

        # Put the physical minimum exactly on the high edge of the first inverse-pair
        # scan.  The second scan must be centered on that edge seed and find it inside.
        tuner.working = T._with_candidate(
            optimum,
            qubit_pi_freq=(tuner.QUBIT_FREQ
                           - 0.5 * params["fine_frequency"]["span_mhz"]),
        )
        tuner._stage_fine_frequency("edge_frequency_regression")
        first = tuner.data["maps"]["edge_frequency_regression"]
        expanded = tuner.data["maps"]["edge_frequency_regression_edge"]
        assert first["initial_edge_winner"] is True
        assert first["expanded"] is True
        assert first["edge_winner"] is False
        assert first["search_complete"] is True
        assert expanded["edge_winner"] is False
        assert abs(tuner.working["qubit_pi_freq"] - tuner.QUBIT_FREQ) < 1e-6

        # Repeat the same adversarial geometry for both repeated-pulse maps.  These
        # maps amplify coherent errors, so a statistically tied one-pulse replay must
        # not silently undo their preferred correction.
        for stage_name, method, key in (
                ("parity_chevron", tuner._stage_parity_chevron,
                 "parity_chevron"),
                ("amplified_error", tuner._stage_amplified_error,
                 "amplified_error")):
            span = params[key]["freq_span_mhz"]
            tuner.working = T._with_candidate(
                optimum, qubit_pi_freq=tuner.QUBIT_FREQ - 0.5 * span)
            method()
            mapping = tuner.data["maps"][stage_name]
            edge_mapping = tuner.data["maps"][stage_name + "_edge"]
            assert mapping["initial_edge_winner"] is True
            assert mapping["expanded"] is True
            assert mapping["edge_winner"] is False
            assert mapping["search_complete"] is True
            assert edge_mapping["edge_winner"] is False
            assert abs(tuner.working["qubit_pi_freq"] - tuner.QUBIT_FREQ) < 1e-6


def test_flat_amplified_map_cannot_move_or_authorize_control():
    class FlatParityTuner(VirtualBasicAutoTuner):
        def _acquire_parity_chevron(self, freqs_mhz, gains, candidate, shots,
                                    pulse_counts, calibration):
            del candidate, shots, calibration
            shape = (len(pulse_counts), len(freqs_mhz), len(gains))
            populations = np.full(shape, 0.5, dtype=float)
            return np.full(shape[1:], 0.5, dtype=float), populations

    with tempfile.TemporaryDirectory() as folder:
        tuner = FlatParityTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        before = dict(tuner.working)
        try:
            tuner._stage_amplified_error()
        except RuntimeError as exc:
            assert "insufficient repeated-pulse information" in str(exc)
        else:
            raise AssertionError("flat amplified map unexpectedly selected a pulse")

    mapping = tuner.data["maps"]["amplified_error"]
    assert mapping["information_complete"] is False
    assert mapping["search_complete"] is False
    assert tuner.working == before
    assert all(not rows for rows in tuner.data["key_evidence"].values())


def test_noisy_null_inverse_pair_scan_cannot_authorize_frequency():
    """A post-selected 3-sigma range across 17 null points is not a calibration."""
    null_populations = np.asarray([
        0.50, 0.53, 0.47, 0.51, 0.55, 0.49, 0.52, 0.43, 0.48,
        0.51, 0.46, 0.54, 0.50, 0.57, 0.49, 0.52, 0.47,
    ])

    class NoisyNullFrequencyTuner(VirtualBasicAutoTuner):
        def _acquire_inverse_pair_scan(self, freqs_mhz, candidate, shots, pairs,
                                       calibration):
            del candidate, shots, pairs, calibration
            assert len(freqs_mhz) == len(null_populations)
            return null_populations.copy()

    params = copy.deepcopy(FAST_PARAMS)
    params["fine_frequency"].update({"points": 17, "shots": 220})
    with tempfile.TemporaryDirectory() as folder:
        tuner = NoisyNullFrequencyTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=params,
        )
        before = dict(tuner.working)
        try:
            tuner._stage_fine_frequency("noisy_null_frequency")
        except RuntimeError as exc:
            assert "insufficient post-selection information" in str(exc)
        else:
            raise AssertionError("noisy null frequency scan unexpectedly moved the pulse")

    mapping = tuner.data["maps"]["noisy_null_frequency"]
    assert mapping["map_contrast_sigma"] < 5.0
    assert mapping["information_complete"] is False
    assert mapping["search_complete"] is False
    assert tuner.working == before
    assert all(not rows for rows in tuner.data["key_evidence"].values())


def test_common_mode_cloud_translation_fails_operational_drift_gate():
    """Equal pre/post fitted fidelity cannot hide a stale fixed threshold."""
    class TranslatingCalibrationTuner(VirtualBasicAutoTuner):
        def __init__(self, *args, **kwargs):
            self._ss_pair_count = 0
            super().__init__(*args, **kwargs)

        def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
            self._ss_pair_count += 1
            ig, qg, ie, qe = super()._acquire_ss_pair(
                candidate, shots, state_order)
            # The second SS pair is the post-map calibration.  Both clouds translate
            # together: their independently optimized theta/F are unchanged, but the
            # pre-map threshold is no longer operationally valid.
            if self._ss_pair_count == 2:
                ig = np.asarray(ig) + 2.0
                ie = np.asarray(ie) + 2.0
            return ig, qg, ie, qe

    with tempfile.TemporaryDirectory() as folder:
        tuner = TranslatingCalibrationTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        optimum = T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA,
            sigma=tuner.SIGMA,
        )
        tuner.working = dict(optimum)
        before = dict(tuner.working)
        try:
            tuner._stage_fine_frequency("translated_cloud_frequency")
        except RuntimeError as exc:
            assert "discriminator drifted" in str(exc)
        else:
            raise AssertionError("common-mode IQ translation passed drift gating")

    mapping = tuner.data["maps"]["translated_cloud_frequency"]
    drift = mapping["calibration_drift"]
    assert abs(drift["fidelity_change"]) < 0.01
    assert drift["angle_degrees"] < 1.0
    assert (drift["fixed_discriminator_fidelity_loss"] > 0.08
            or drift["midpoint_shift_fraction"] > 0.25)
    assert mapping["calibration_stable"] is False
    assert mapping["search_complete"] is False
    assert tuner.working == before
    assert all(not rows for rows in tuner.data["key_evidence"].values())


def test_confirmation_fault_retains_raw_basin_for_final_replay():
    """All failed confirms for one basin must not erase it from the final audit."""
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=_base_config(), params=FAST_PARAMS,
        )
        incumbent = dict(tuner.working)
        optimum = T._with_candidate(
            incumbent,
            read_pulse_freq=tuner.READ_FREQ,
            read_pulse_gain=tuner.READ_GAIN,
            read_length=tuner.READ_LENGTH,
            qubit_pi_freq=tuner.QUBIT_FREQ,
            qubit_pi_gain=tuner.PI_GAIN_AT_SIGMA,
            sigma=tuner.SIGMA,
        )
        original_measure = tuner._measure_candidate

        def fail_optimum_confirmation(candidate, shots, label, state_order="ge",
                                      archive=True):
            if (label.startswith("fault_tolerant_grid confirm")
                    and T._candidate_key(candidate) == T._candidate_key(optimum)):
                raise RuntimeError("synthetic transient on this basin")
            return original_measure(candidate, shots, label, state_order, archive)

        tuner._measure_candidate = fail_optimum_confirmation
        tuner._direct_grid(
            "fault_tolerant_grid", [incumbent, optimum], (2,),
            {"candidate_index": np.asarray([0, 1])},
            shots=53, shortlist=2, confirm_shots=101, confirm_blocks=2,
        )
        mapping = tuner.data["maps"]["fault_tolerant_grid"]
        assert mapping["selection_confirmed"] is True
        assert mapping["selection_confirmation_complete"] is False
        assert mapping["search_complete"] is False
        assert any(T._candidate_key(row) == T._candidate_key(optimum)
                   for row in tuner.data["candidate_archive"])
        assert not any(T._candidate_key(row) == T._candidate_key(optimum)
                       for row in tuner.data["confirmed_candidates"])
        assert any(T._candidate_key(entry["candidate"])
                   == T._candidate_key(optimum)
                   for entry in tuner.data["unconfirmed_contenders"])

        # Three later coarse outliers rank above the real basin in the raw archive.
        # A global top-3 raw shortlist would now drop the optimum; its explicit
        # incomplete-confirmation queue entry must preserve it independently.
        for index, false_fidelity in enumerate((0.999, 0.998, 0.997)):
            false_candidate = T._with_candidate(
                incumbent,
                read_pulse_freq=incumbent["read_pulse_freq"] + 0.2 * (index + 1),
                qubit_pi_gain=incumbent["qubit_pi_gain"] + 100 * (index + 1),
            )
            row = original_measure(
                false_candidate, 53, "synthetic later false maximum %d" % index)
            row["fidelity"] = false_fidelity
            row["fidelity_lcb_95"] = false_fidelity - 0.001

        # The transient disappears.  Final replay must reintroduce the top raw basin
        # from the explicit recovery queue and recover it even though no aggregate or
        # global top-raw shortlist from the failed batch contains it.
        tuner._measure_candidate = original_measure
        best = tuner._stage_final()
        assert T._candidate_key(best) == T._candidate_key(optimum)
        assert best["fidelity"] > 0.90
        assert tuner._final_replay_completed is True


def main():
    tests = [
        test_step5_metric_matches_shared_helpers,
        test_third_blob_guard_catches_binary_invisible_excited_cloud,
        test_common_mode_third_cloud_cannot_cancel_out_of_the_safety_metric,
        test_two_physical_clouds_are_not_penalized_when_gmm_splits_a_tail,
        test_operational_safety_path_rejects_a_common_mode_third_population,
        test_duration_portfolio_reports_safe_unsafe_and_inconclusive_lengths,
        test_production_portfolio_covers_every_integer_us_and_caps_at_twenty,
        test_portfolio_rank_uses_fidelity_only_and_never_leakage,
        test_portfolio_preserves_known_winner_and_never_uses_screen_fidelity,
        test_portfolio_protects_heldout_control_from_perfect_shared_ground_outlier,
        test_shelving_inversion_recovers_direct_f_population,
        test_independent_long_reference_exposes_candidate_one_pulse_leakage,
        test_opposed_ef_scans_match_a_reproduced_feature_after_rank_swaps,
        test_long_reference_gain_recovers_from_a_rabi_fit_alias,
        test_basic_default_uses_operational_screen_not_direct_ef_calibration,
        test_operational_screen_detects_bad_repeated_returns_without_calling_it_p2,
        test_default_fixed_gaussian_screen_does_not_call_repeated_or_drag_backends,
        test_statistical_fidelity_tie_prefers_longer_lower_power_gaussian,
        test_operational_shortlist_cannot_be_filled_by_one_duration,
        test_readout_tie_prefers_lower_power_duration_exposure,
        test_readout_length_confirmation_covers_every_length_not_only_seed,
        test_pi_duration_confirmation_covers_every_sigma_not_only_seed,
        test_operational_screen_retries_discriminator_drift_before_rejecting_waveform,
        test_candidate_latency_is_read_length_plus_four_gaussian_sigmas,
        test_latency_noninferiority_rejects_low_fidelity_and_uncertainty,
        test_latency_noninferiority_uses_crossfit_not_optimistic_step5_fidelity,
        test_latency_selector_rejects_one_us_sixty_percent_candidate,
        test_latency_selector_rejects_an_uncertain_fast_contender,
        test_latency_selector_is_deterministic_on_equal_latency,
        test_latency_selector_fails_closed_on_invalid_coordinates,
        test_latency_frontier_preserves_fast_candidate_beyond_fidelity_top_k,
        test_latency_frontier_densely_preserves_the_short_boundary,
        test_uncertainty_tied_joint_corner_survives_marginal_coarse_winners,
        test_latency_search_expands_to_later_frontier_after_early_arms_fail,
        test_integrated_latency_stage_selects_joint_fast_plateau_tuple,
        test_incomplete_latency_confirmation_preserves_reference_replay,
        test_paired_latency_noninferiority_uses_round_robin_block_evidence,
        test_latency_drift_bound_accounts_for_estimating_variance_from_eight_blocks,
        test_exact_epsilon_loss_is_accepted_against_max_safe_fidelity,
        test_latency_stage_retries_transient_measurement_and_evidence_failures,
        test_latency_control_screen_falls_through_to_next_coherent_tuple,
        test_retained_reference_control_screen_cannot_choose_a_slower_tuple,
        test_binding_unsafe_reference_is_lazily_removed_before_latency_decision,
        test_realistic_block_uncertainty_shrinks_across_adaptive_rounds,
        test_adaptive_latency_evidence_moves_unresolved_candidate_to_accepted,
        test_incomplete_optional_adaptive_round_preserves_initial_complete_result,
        test_incoherent_simultaneous_blocker_is_audited_removed_then_fast_qualifies,
        test_coherent_simultaneous_blocker_remains_and_prevents_certification,
        test_final_tuple_mismatch_invalidates_latency_certificate,
        test_uncertain_timing_reference_cannot_be_promoted_by_control_or_finalize,
        test_final_latency_certificate_cannot_hide_more_loss_than_its_budget,
        test_late_timing_drop_replays_reference_and_preserves_ordinary_write,
        test_failed_late_timing_reference_replay_cannot_write_degraded_fast_arm,
        test_drift_collapsed_reference_recovery_keeps_better_exact_fast_replay,
        test_retained_reference_guard_failure_demotes_exact_tuple_without_abort,
        test_constrained_reference_recovery_marks_final_leakage_replay_complete,
        test_not_run_latency_uses_the_ordinary_exact_final_write_policy,
        test_direct_leakage_verify_recalibrates_ef_for_final_latency_control,
        test_single_shot_feedback_buffers_return_only_the_final_readout,
        test_sequence_feedback_buffers_return_only_the_final_readout,
        test_sequence_feedback_declares_its_frozen_reset_waveform,
        test_feedback_profile_is_bound_to_frequency_and_length_not_scoring_gain,
        test_feedback_exact_ab_rejects_the_observed_step5_collapse,
        test_single_shot_feedback_uses_fixed_reset_gain_then_restores_scoring_gain,
        test_rabi_sweep_feedback_restores_the_swept_gain_and_scoring_readout,
        test_reset_probe_uses_the_full_raw_distribution_not_last_dmem_word,
        test_reset_raw_threshold_maximizes_held_shot_assignment,
        test_active_reset_primitive_always_clears_measurement_photons,
        test_concise_console_hides_diagnostics_but_keeps_the_saved_report,
        test_self_contained_diagnostic_bundle_round_trips_raw_iq_and_run_data,
        test_static_fast_flux_is_replayed_but_never_tuned,
        test_static_fast_flux_helper_forces_zero_and_nonzero_park,
        test_dynamic_flux_excursion_is_not_mistaken_for_static_park,
        test_global_discovery_recovers_exact_far_frequency_seeds,
        test_relative_100mhz_prior_recovers_without_device_frequency_constants,
        test_stronger_wrong_resonator_backtracks_to_the_qubit_coupled_branch,
        test_multiple_resonators_without_a_qubit_branch_fail_closed,
        test_two_spectral_branches_are_resolved_by_coherent_rabi,
        test_relative_100mhz_prior_rejects_the_old_out_of_contract_seeds,
        test_relative_prior_padding_fits_exact_edges_but_cannot_expand_policy,
        test_monotonic_transmission_cannot_be_reported_as_a_resonator,
        test_hardware_width_modest_depth_resonator_survives_confirmation,
        test_featureless_spectroscopy_does_not_promote_noise_or_the_input_prior,
        test_shoulder_proposals_do_not_turn_noise_into_a_transition,
        test_production_grid_recovers_a_broad_noisy_line_with_opposed_sweeps,
        test_spectral_fit_accepts_population_and_complex_pole_lines_under_noise,
        test_target_line_fit_survives_a_stronger_nearby_tls,
        test_full_spectroscopy_and_rabi_preserve_a_weaker_coherent_neighbor,
        test_padded_discovery_recovers_both_characterized_band_edges,
        test_transient_spectral_line_cannot_pass_opposed_confirmation,
        test_combined_trace_cannot_replace_the_agreed_opposed_pass_line,
        test_resonator_confirmation_failure_falls_back_to_the_input_gain,
        test_failed_critical_discovery_and_coinflip_replay_can_never_write,
        test_missing_spectroscopy_alone_blocks_a_high_fidelity_write,
        test_high_fidelity_without_coherent_control_witness_cannot_write,
        test_control_witness_must_match_the_complete_selected_waveform,
        test_final_exact_repeated_pulse_audit_rejects_saturation,
        test_joint_search_is_independent_of_starting_readout_gain_and_length,
        test_runtime_limited_joint_search_covers_every_duration_before_repeating_power,
        test_duration_balanced_schedule_uses_central_power_for_every_duration_first,
        test_finalize_reports_best_overall_and_shortest_near_best_separately,
        test_practical_short_report_keeps_eight_us_candidate_but_rejects_one_us_coinflip,
        test_short_report_cannot_borrow_a_different_tuples_safety_certificate,
        test_joint_resume_reuses_only_matching_input_and_flux_context,
        test_bad_start_recovers_and_preserves_best_effort_contract,
        test_interrupt_retains_a_completed_unconfirmed_measurement,
        test_failed_search_cannot_make_replayed_input_write_eligible,
        test_partial_direct_grid_with_failed_confirmation_has_no_key_evidence,
        test_stable_full_tuple_replay_authorizes_atomic_update,
        test_leakage_constraint_prefers_safe_waveform_over_higher_binary_fidelity,
        test_failed_leakage_calibration_retains_the_validated_unconstrained_result,
        test_failed_operational_screen_preserves_the_unconstrained_fidelity_replay,
        test_partial_screened_final_cannot_replace_the_stable_fidelity_replay,
        test_direct_leakage_verification_is_a_hard_write_gate,
        test_verified_leakage_tuple_can_atomically_write_drag_beta,
        test_leakage_certificate_cannot_authorize_a_different_final_tuple,
        test_refined_rabi_candidate_cannot_evict_a_spectral_basin,
        test_noncoherent_spectral_branch_cannot_enter_the_control_search,
        test_transition_qualification_falls_through_failed_high_fidelity_branch,
        test_rough_control_audit_failure_does_not_block_frequency_optimization,
        test_uninformative_branch_comparison_preserves_passive_bootstrap_and_basins,
        test_provisional_rough_control_still_produces_the_duration_portfolio,
        test_rejected_transition_cannot_reenter_late_recovery_or_safety_pools,
        test_portfolio_safety_failure_is_not_mislabeled_as_leakage,
        test_partial_wrapper_grid_can_report_but_not_authorize,
        test_interrupt_after_final_replay_never_emits_eligibility,
        test_runner_is_report_only_for_manual_duration_portfolio_selection,
        test_runner_main_never_writes_a_guard_rejected_result,
        test_config_update_compare_and_swap_refuses_stale_input,
        test_config_source_hash_refuses_untuned_physical_change,
        test_config_source_hash_is_stable_for_windows_crlf,
        test_amplified_scans_expand_boundary_once_and_retain_correction,
        test_flat_amplified_map_cannot_move_or_authorize_control,
        test_noisy_null_inverse_pair_scan_cannot_authorize_frequency,
        test_common_mode_cloud_translation_fails_operational_drift_gate,
        test_confirmation_fault_retains_raw_basin_for_final_replay,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("ALL BASIC AUTOTUNER TESTS PASSED")


if __name__ == "__main__":
    main()
