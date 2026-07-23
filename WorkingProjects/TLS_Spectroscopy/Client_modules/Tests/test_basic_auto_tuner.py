"""Deterministic virtual-device tests for the measurement-first basic auto tuner.

This file intentionally stubs QICK before importing the experiment module.  The
production class exposes five narrow hardware acquisition methods; the virtual tuner
overrides exactly those methods and leaves the orchestration, candidate archive,
step-5 analysis, confirmation, and finalization code under test.
"""

from __future__ import annotations

import ast
import copy
import os
import sys
import tempfile
import types

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
    "resonator": {"span_mhz": 5.0, "points": 17, "shots": 31},
    "spectroscopy": {
        "local_span_mhz": 24.0, "local_points": 25,
        "wide_span_mhz": 40.0, "wide_points": 41,
        "gain": 7000, "pulse_length_us": 2.0, "shots": 31,
        "max_candidates": 2, "min_feature_snr": 2.0,
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
    "coordinate_descent_repeat": False,
    "final": {
        "top_candidates": 3, "shots": 173, "blocks": 3,
        "confidence_sigma": 1.96, "max_block_spread": 0.08,
    },
}


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


def test_feedback_threshold_is_bound_to_one_exact_readout_tuple():
    cfg = _base_config()
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS,
        )
        tuner._reset_runtime = {
            "reset_mode": "feedback", "reset_threshold_raw": 1234,
            "reset_oper": "lower", "reset_ground_below": True,
            "reset_max_iters": 3, "reset_pi_freq": 2534.5,
            "reset_pi_gain": 5790, "reset_pi_sigma": 0.25,
            "reset_pi_drag_beta": 0.04,
        }
        tuner._reset_readout_key = tuner._reset_readout_signature(tuner.working)
        exact = tuner._cfg_for(tuner.working)
        mismatched = tuner._cfg_for(T._with_candidate(
            tuner.working,
            read_pulse_freq=tuner.working["read_pulse_freq"] + 0.1))
    assert exact["reset_mode"] == "feedback"
    assert exact["reset_pi_gain"] == 5790
    assert mismatched["reset_mode"] == "passive"


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


def test_static_fast_flux_is_replayed_but_never_tuned():
    """Any signed park value is fixed context and survives every candidate config."""
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


def test_bad_start_recovers_and_preserves_best_effort_contract():
    cfg = _base_config()
    untouched = copy.deepcopy(cfg)
    with tempfile.TemporaryDirectory() as folder:
        tuner = VirtualBasicAutoTuner(
            soc=None, soccfg=None, path="q4", outerFolder=folder,
            cfg=cfg, params=FAST_PARAMS, fail_parity=True,
        )
        result = tuner.acquire(plotDisp=False)

    data = result["data"]
    best = data["best_found"]
    assert data["outcome"] == "completed_with_warnings"
    assert data["success"] is True
    assert data["final_stable"] is True

    # The exact input replay is intentionally near random, but every later stage still ran.
    baseline = [row for row in data["confirmed_candidates"]
                if row["label"] == "exact input tuple"]
    assert len(baseline) == 1
    assert baseline[0]["fidelity"] < 0.58
    assert any(row["name"] == "final" and row["status"] == "ok"
               for row in data["stages"])
    assert "fine_frequency" in data["maps"]
    assert "fine_frequency_post_duration" in data["maps"]
    assert "amplified_error" in data["maps"]
    assert (data["maps"]["amplified_error"]["calibration_kind"]
            == "amplified_amplitude_error_x180")
    assert data["maps"]["amplified_error"]["leakage_measurement"] is False

    # A recoverable optional-stage exception is recorded and cannot erase direct SS data.
    parity = [row for row in data["stages"] if row["name"] == "parity_chevron"]
    assert len(parity) == 1
    assert parity[0]["status"] == "warning"
    assert "synthetic parity backend fault" in parity[0]["error"]
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

    # Pulse duration is not a fixed-sigma comparison: each sigma has local f/g points.
    duration_rows = [row for row in data["candidate_archive"]
                     if row["label"] == "pulse_duration coarse"]
    tested_sigmas = sorted(set(float(row["sigma"]) for row in duration_rows))
    assert tested_sigmas == [0.10, 0.25]
    for sigma in tested_sigmas:
        rows = [row for row in duration_rows if float(row["sigma"]) == sigma]
        assert len(set(float(row["qubit_pi_freq"]) for row in rows)) >= 3
        assert len(set(int(row["qubit_pi_gain"]) for row in rows)) >= 3

    # The experiment is dry by construction: neither the caller's dict nor returned cfg
    # is rewritten.  Only explicitly supported calibration keys may be eligible.
    assert cfg == untouched
    assert result["config"] == untouched
    # DRAG remains exactly equal to the input because this virtual device does not
    # activate the optional e-f leakage stage; unchanged keys need no source rewrite.
    assert set(data["eligible_tuned"]) == set(T.TUNED_KEYS) - {"qubit_drag_beta"}
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
    assert data["outcome"] == "completed_with_warnings"
    assert data["success"] is True
    assert data["best_found"] is not None
    assert data["eligible_tuned"] == {}


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
                    "score": score,
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


def test_runner_enables_only_the_guarded_initialize_update_by_default():
    """The shipped runner applies stable replayed tuples, never partial results."""
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
    assert ast.literal_eval(assignments["APPLY_CONFIG"]) is True
    assert 'not bool(result.get("final_stable", False))' in source
    assert 'bool(result.get("interrupted", False))' in source
    assert "expected_source_hash=startup_source_hash" in source
    assert 'eligible = result.get("eligible_tuned", {})' in source


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
        test_shelving_inversion_recovers_direct_f_population,
        test_independent_long_reference_exposes_candidate_one_pulse_leakage,
        test_single_shot_feedback_buffers_return_only_the_final_readout,
        test_sequence_feedback_buffers_return_only_the_final_readout,
        test_feedback_threshold_is_bound_to_one_exact_readout_tuple,
        test_reset_probe_uses_the_full_raw_distribution_not_last_dmem_word,
        test_reset_raw_threshold_maximizes_held_shot_assignment,
        test_active_reset_primitive_always_clears_measurement_photons,
        test_static_fast_flux_is_replayed_but_never_tuned,
        test_static_fast_flux_helper_forces_zero_and_nonzero_park,
        test_dynamic_flux_excursion_is_not_mistaken_for_static_park,
        test_bad_start_recovers_and_preserves_best_effort_contract,
        test_interrupt_retains_a_completed_unconfirmed_measurement,
        test_failed_search_cannot_make_replayed_input_write_eligible,
        test_partial_direct_grid_with_failed_confirmation_has_no_key_evidence,
        test_stable_full_tuple_replay_authorizes_atomic_update,
        test_leakage_constraint_prefers_safe_waveform_over_higher_binary_fidelity,
        test_direct_leakage_verification_is_a_hard_write_gate,
        test_verified_leakage_tuple_can_atomically_write_drag_beta,
        test_leakage_certificate_cannot_authorize_a_different_final_tuple,
        test_refined_rabi_candidate_cannot_evict_a_spectral_basin,
        test_partial_wrapper_grid_can_report_but_not_authorize,
        test_interrupt_after_final_replay_never_emits_eligibility,
        test_runner_enables_only_the_guarded_initialize_update_by_default,
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
