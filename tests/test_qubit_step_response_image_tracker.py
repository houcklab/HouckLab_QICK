import unittest

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.image_ridge_tracker import (
    select_step_response_trace,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.trace_extraction import track_image_ridge


class ImageRidgeTrackerTests(unittest.TestCase):
    @staticmethod
    def _grid(n_time=91):
        frequency = np.arange(3.980, 4.0605, 0.0005)
        time = np.arange(n_time, dtype=float)
        return frequency, time

    @staticmethod
    def _ridge_map(frequency, truth, *, seed=4, dark=False, shoulder=True):
        rng = np.random.default_rng(seed)
        freq_mhz = frequency[:, None] * 1e3
        truth_mhz = truth[None, :] * 1e3
        image = 0.020 * (freq_mhz - np.mean(freq_mhz))
        image = image + 0.18 * np.sin(freq_mhz / 11.0)
        image = image + rng.normal(scale=0.22, size=(frequency.size, truth.size))
        ridge = 3.5 * np.exp(-0.5 * ((freq_mhz - truth_mhz) / 2.2) ** 2)
        if shoulder:
            ridge += 1.9 * np.exp(-0.5 * ((freq_mhz - truth_mhz - 7.0) / 1.5) ** 2)
        image = image - ridge if dark else image + ridge
        return image

    def test_tracks_asymmetric_ridge_through_a_vertical_column_artifact(self):
        frequency, time = self._grid()
        truth = 4.015 + 0.010 * np.sin(time / 17.0) + 0.00006 * time
        image = self._ridge_map(frequency, truth)
        image[:, 37] += 5.0  # time-local acquisition stripe, not a spectral ridge

        result = track_image_ridge(frequency, image, polarity="bright")

        error_mhz = np.abs((result["selected_frequency_ghz"] - truth) * 1e3)
        self.assertLess(np.nanmedian(error_mhz), 0.35)
        self.assertLess(np.nanpercentile(error_mhz, 95), 0.50)
        self.assertGreater(np.mean(result["supported"]), 0.85)

    def test_preserves_a_fast_physical_excursion_without_post_smoothing(self):
        frequency, time = self._grid(n_time=61)
        truth = np.full(time.size, 4.018)
        truth[22:] += 0.0055
        truth[24:] -= 0.0030
        image = self._ridge_map(frequency, truth, shoulder=False, seed=8)

        result = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            max_jump_mhz=7.0,
        )

        measured = result["selected_frequency_ghz"]
        self.assertLess(abs((measured[21] - truth[21]) * 1e3), 0.75)
        self.assertLess(abs((measured[22] - truth[22]) * 1e3), 0.75)
        self.assertLess(abs((measured[24] - truth[24]) * 1e3), 0.75)
        np.testing.assert_allclose(result["smoothed_frequency_ghz"], measured, equal_nan=True)

    def test_marks_equal_well_separated_double_peaks_as_ambiguous(self):
        frequency, time = self._grid(n_time=51)
        truth = np.full(time.size, 4.018)
        image = self._ridge_map(frequency, truth, shoulder=False, seed=12)
        freq_mhz = frequency[:, None] * 1e3
        second = 3.5 * np.exp(-0.5 * ((freq_mhz - 4.033 * 1e3) / 2.2) ** 2)
        image[:, 20:31] += second

        result = track_image_ridge(frequency, image, polarity="bright")

        self.assertLess(np.mean(result["supported"][20:31]), 0.35)
        self.assertGreater(np.mean(result["supported"][:15]), 0.8)
        self.assertGreater(np.mean(result["supported"][36:]), 0.8)

    def test_keeps_one_shoulder_identity_when_parallel_shoulders_trade_brightness(self):
        frequency, time = self._grid(n_time=81)
        lower = 4.017 + 0.003 * np.sin(time / 20.0)
        upper = lower + 0.0045
        f_mhz = frequency[:, None] * 1e3
        lower_mhz = lower[None, :] * 1e3
        upper_mhz = upper[None, :] * 1e3
        rng = np.random.default_rng(33)
        alternating = 0.85 * np.sin(np.pi * time / 3.0)
        image = rng.normal(scale=0.15, size=(frequency.size, time.size))
        image += (3.0 + alternating)[None, :] * np.exp(
            -0.5 * ((f_mhz - lower_mhz) / 1.25) ** 2
        )
        image += (3.0 - alternating)[None, :] * np.exp(
            -0.5 * ((f_mhz - upper_mhz) / 1.25) ** 2
        )

        result = track_image_ridge(frequency, image, polarity="bright")

        path = np.asarray(result["local_frequency_ghz"])
        chooses_lower = np.abs(path - lower) < np.abs(path - upper)
        lower_fraction = float(np.mean(chooses_lower))
        self.assertTrue(lower_fraction < 0.05 or lower_fraction > 0.95)
        self.assertGreater(np.mean(result["supported"]), 0.8)

    def test_explicit_lower_shoulder_never_switches_to_the_upper_branch(self):
        frequency, time = self._grid(n_time=81)
        lower = 4.017 + 0.0025 * np.sin(time / 18.0)
        upper = lower + 0.0045
        f_mhz = frequency[:, None] * 1e3
        lower_mhz = lower[None, :] * 1e3
        upper_mhz = upper[None, :] * 1e3
        rng = np.random.default_rng(41)
        trade = 1.25 * np.tanh((time - 40.0) / 6.0)
        image = rng.normal(scale=0.12, size=(frequency.size, time.size))
        image += (3.2 - trade)[None, :] * np.exp(
            -0.5 * ((f_mhz - lower_mhz) / 1.15) ** 2
        )
        image += (3.2 + trade)[None, :] * np.exp(
            -0.5 * ((f_mhz - upper_mhz) / 1.15) ** 2
        )

        result = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            shoulder="lower",
        )

        error_mhz = np.abs((result["local_frequency_ghz"] - lower) * 1e3)
        self.assertEqual(result["shoulder_mode"], "paired_lower")
        self.assertLess(np.nanpercentile(error_mhz, 95), 0.65)
        self.assertGreater(result["paired_support_fraction"], 0.8)

    def test_midpoint_follows_the_center_between_resolved_shoulders(self):
        frequency, time = self._grid(n_time=81)
        lower = 4.017 + 0.0025 * np.sin(time / 18.0)
        upper = lower + 0.0045
        center = 0.5 * (lower + upper)
        f_mhz = frequency[:, None] * 1e3
        rng = np.random.default_rng(42)
        trade = 1.25 * np.tanh((time - 40.0) / 6.0)
        image = rng.normal(scale=0.12, size=(frequency.size, time.size))
        image += (3.2 - trade)[None, :] * np.exp(
            -0.5 * ((f_mhz - lower[None, :] * 1e3) / 1.15) ** 2
        )
        image += (3.2 + trade)[None, :] * np.exp(
            -0.5 * ((f_mhz - upper[None, :] * 1e3) / 1.15) ** 2
        )

        result = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            shoulder="midpoint",
        )

        error_mhz = np.abs((result["local_frequency_ghz"] - center) * 1e3)
        self.assertEqual(result["shoulder_mode"], "paired_midpoint")
        self.assertLess(np.nanpercentile(error_mhz[result["supported"]], 95), 0.5)
        self.assertGreater(np.mean(result["supported"]), 0.8)

    def test_requested_shoulder_falls_back_for_a_single_ridge(self):
        frequency, time = self._grid(n_time=61)
        truth = 4.021 + 0.002 * np.sin(time / 14.0)
        image = self._ridge_map(frequency, truth, shoulder=False, seed=51)

        result = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            shoulder="lower",
        )

        error_mhz = np.abs((result["local_frequency_ghz"] - truth) * 1e3)
        self.assertEqual(result["shoulder_mode"], "single_fallback")
        self.assertLess(np.nanpercentile(error_mhz, 95), 0.5)

    def test_auto_polarity_tracks_a_dark_ridge(self):
        frequency, time = self._grid(n_time=71)
        truth = 4.030 - 0.008 * np.exp(-time / 18.0)
        image = self._ridge_map(frequency, truth, dark=True, shoulder=False, seed=21)

        result = track_image_ridge(frequency, image, polarity="auto")

        error_mhz = np.abs((result["selected_frequency_ghz"] - truth) * 1e3)
        self.assertEqual(result["polarity"], "dark")
        self.assertLess(np.nanpercentile(error_mhz, 95), 0.50)

    def test_interpolated_spectral_gap_is_not_reported_as_measured_support(self):
        frequency, time = self._grid(n_time=61)
        truth = np.full(time.size, 4.021)
        image = self._ridge_map(frequency, truth, shoulder=False, seed=4)
        missing_frequency = np.abs(frequency - truth[0]) <= 0.004
        image[np.ix_(missing_frequency, np.arange(20, 31))] = np.nan

        result = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            shoulder="midpoint",
        )

        self.assertFalse(np.any(result["supported"][20:31]))
        self.assertGreater(np.mean(result["supported"][:15]), 0.8)
        self.assertGreater(np.mean(result["supported"][36:]), 0.8)

    def test_auto_polarity_returns_the_selected_center_evidence(self):
        frequency, time = self._grid(n_time=41)
        truth = 4.020 + 0.002 * np.sin(time / 10.0)
        image = self._ridge_map(frequency, truth, shoulder=False, seed=71)

        automatic = track_image_ridge(frequency, image, polarity="auto")
        explicit = track_image_ridge(frequency, image, polarity="bright")

        self.assertEqual(automatic["polarity"], "bright")
        np.testing.assert_allclose(
            automatic["raw_center_evidence"],
            explicit["raw_center_evidence"],
        )

    def test_temporal_median_background_recovers_a_short_lived_step_trajectory(self):
        """A persistent target line must not hide the causal moving branch."""
        frequency, time = self._grid(n_time=61)
        target = 4.018
        moving = np.full(time.size, target)
        moving[:9] = np.array(
            [4.032, 4.039, 4.044, 4.047, 4.045, 4.040, 4.033, 4.026, 4.020]
        )
        f_mhz = frequency[:, None] * 1e3
        rng = np.random.default_rng(91)
        image = rng.normal(scale=0.14, size=(frequency.size, time.size))
        image += 4.0 * np.exp(
            -0.5 * ((f_mhz - target * 1e3) / 1.3) ** 2
        )
        transient_amplitude = np.r_[np.full(9, 3.6), np.zeros(time.size - 9)]
        image += transient_amplitude[None, :] * np.exp(
            -0.5 * ((f_mhz - moving[None, :] * 1e3) / 1.3) ** 2
        )

        persistent = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            max_jump_mhz=9.0,
        )
        transient = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            max_jump_mhz=9.0,
            jump_penalty=4.0,
            temporal_background="median",
        )

        persistent_error = np.abs(
            (persistent["local_frequency_ghz"][:9] - moving[:9]) * 1e3
        )
        transient_error = np.abs(
            (transient["local_frequency_ghz"][:9] - moving[:9]) * 1e3
        )
        self.assertGreater(np.nanmedian(persistent_error), 8.0)
        self.assertLess(np.nanmedian(transient_error), 0.75)
        self.assertEqual(transient["temporal_background"], "median")

        persistent["signal_source"] = "magnitude"
        transient["signal_source"] = "magnitude"
        selected, diagnostics = select_step_response_trace(
            [persistent, transient],
            target_frequency_ghz=target,
            baseline_frequency_ghz=5.0,
        )
        self.assertEqual(diagnostics["selection_reason"], "physical_transient")
        self.assertEqual(
            selected["temporal_background"], "hybrid_median_to_persistent"
        )
        hybrid_error = np.abs(
            (selected["local_frequency_ghz"][:9] - moving[:9]) * 1e3
        )
        self.assertLess(np.nanmedian(hybrid_error), 0.75)
        self.assertLess(
            abs(selected["local_frequency_ghz"][-1] - target) * 1e3,
            0.75,
        )

    def test_step_response_selector_keeps_persistent_trace_without_supported_motion(self):
        frequency, time = self._grid(n_time=61)
        target = 4.018
        image = self._ridge_map(
            frequency,
            np.full(time.size, target),
            shoulder=False,
            seed=92,
        )
        persistent = track_image_ridge(frequency, image, polarity="bright")
        transient = track_image_ridge(
            frequency,
            image,
            polarity="bright",
            jump_penalty=4.0,
            temporal_background="median",
        )
        persistent["signal_source"] = "magnitude"
        transient["signal_source"] = "magnitude"

        selected, diagnostics = select_step_response_trace(
            [persistent, transient],
            target_frequency_ghz=target,
            baseline_frequency_ghz=5.0,
        )

        self.assertIs(selected, persistent)
        self.assertEqual(diagnostics["selection_reason"], "persistent_fallback")


if __name__ == "__main__":
    unittest.main()
