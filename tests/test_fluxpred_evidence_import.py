import importlib
import json
import unittest

import numpy as np


class EvidenceImportTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("tools.import_neutral_flux_evidence")
        except ModuleNotFoundError:
            self.module = None
        self.assertIsNotNone(self.module, "read-only evidence extractor is not implemented")

    def test_calibration_inversion_marks_out_of_branch_values_instead_of_clamping(self):
        params = dict(EJmax=1.0, Ec=0.1, period_volts=2.0, phase_offset_volts=0.0,
                      d=1.0, tilt_slope=-1.0)
        base_mhz = 794.4271909999159
        result = self.module.invert_calibration(
            [base_mhz + 100, base_mhz - 250, base_mhz - 1100], params, (0, 1))
        self.assertTrue(np.isnan(result[0]))
        self.assertAlmostEqual(result[1], 0.25, places=10)
        self.assertTrue(np.isnan(result[2]))

    def test_inversion_rejects_a_nonmonotonic_dispersion_branch(self):
        params = dict(EJmax=1.0, Ec=0.1, period_volts=2.0, phase_offset_volts=0.0,
                      d=0.3, tilt_slope=0.0)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            self.module.invert_calibration([700], params, (0, 2))

    def test_centroid_window_sensitivity_detects_an_asymmetric_nearby_feature(self):
        axis = np.arange(-12, 12.25, 0.25)
        symmetric = np.exp(-0.5 * (axis / 1.0) ** 2)
        asymmetric = symmetric + 0.8 * np.exp(-0.5 * ((axis - 8.5) / 0.75) ** 2)
        scores = np.column_stack((symmetric, asymmetric))
        centers = self.module.refine_centroid(axis, scores, [0, 0], half_window_mhz=10)
        self.assertAlmostEqual(centers[0], 0.0, places=10)
        self.assertGreater(centers[1], 2.0)
        sensitivity = self.module.centroid_window_sensitivity(axis, scores, [0, 0], [True, True])
        self.assertGreater(sensitivity["6"]["rms_shift_vs_8mhz"], 0.1)
        self.assertGreater(sensitivity["10"]["rms_shift_vs_8mhz"], 0.1)

    def test_centroid_unsupported_samples_do_not_contribute_to_sensitivity(self):
        axis = np.arange(-12, 12.5, 0.5)
        score = np.exp(-axis**2 / 2)
        summary = self.module.centroid_window_sensitivity(
            axis, np.column_stack((score, np.exp(-(axis - 8)**2 / 2))),
            [0, 0], [True, False])
        self.assertEqual(summary["6"]["supported_count"], 1)
        self.assertLess(summary["6"]["rms_shift_vs_8mhz"], 1e-12)

    def test_saved_ghz_coordinates_preserve_original_window_boundary_decisions(self):
        axis_ghz = np.array([4.0, 4.001, 4.002, 4.008])
        score = np.array([[1.0], [2.0], [1.0], [8.0]])
        center = self.module.refine_centroid(
            axis_ghz * 1000, score, [4000], half_window_mhz=8,
            source_axis_ghz=axis_ghz, source_seeds_ghz=np.array([4.0]))
        self.assertAlmostEqual(center[0], 4001.0, places=10)

    def test_serialization_preserves_boolean_support_and_maps_nonfinite_to_null(self):
        payload = {"support": np.array([True, False]),
                   "values": np.array([1.0, np.nan, np.inf, -np.inf]),
                   "nested": {"scalar": np.float64(np.nan)}}
        result = self.module.json_safe(payload)
        self.assertEqual(result["support"], [True, False])
        self.assertEqual(result["values"], [1.0, None, None, None])
        self.assertIsNone(result["nested"]["scalar"])
        text = self.module.compact_json(result)
        self.assertEqual(json.loads(text), result)
        self.assertNotIn("NaN", text)

    def test_incomplete_paired_csv_is_rejected_before_snapshot_acceptance(self):
        with self.assertRaisesRegex(ValueError, "rows|incomplete"):
            self.module.validate_csv_snapshot(b"delay,frequency\n1,4000\n", expected_rows=2)
        with self.assertRaisesRegex(ValueError, "columns|incomplete"):
            self.module.validate_csv_snapshot(b"delay,frequency\n1,4000\n2\n", expected_rows=2)
        self.module.validate_csv_snapshot(b"delay,frequency\n1,4000\n2,4001\n", expected_rows=2)


if __name__ == "__main__":
    unittest.main()
