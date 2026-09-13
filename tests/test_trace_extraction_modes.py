from unittest import mock

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import trace_extraction


def _trace_result(label, n_time):
    frequency = np.full(n_time, 4.02)
    return {
        "selected_frequency_ghz": frequency,
        "ridge_frequency_ghz": frequency,
        "local_frequency_ghz": frequency,
        "smoothed_frequency_ghz": frequency,
        "extracted_if_frequency_hz": frequency * 1e9,
        "extracted_fwhm_hz": np.ones(n_time),
        "supported": np.ones(n_time, dtype=bool),
        "method": [label] * n_time,
        "polarity": "bright",
        "score": np.ones((21, n_time)),
    }


def test_legacy_ridge_ignores_image_only_shoulder_option():
    n_time = 7
    image = np.ones((21, n_time))
    frequency = np.linspace(4.0, 4.04, image.shape[0])
    time_ns = np.arange(n_time, dtype=float)

    with (
        mock.patch.object(
            trace_extraction,
            "extract_trace_ridge",
            autospec=True,
            return_value=_trace_result("ridge", n_time),
        ) as ridge,
        mock.patch.object(
            trace_extraction,
            "extract_trace_independent_slices",
            autospec=True,
            return_value=_trace_result("independent", n_time),
        ) as independent,
    ):
        result = trace_extraction.extract_trace_from_map(
            image,
            frequency,
            time_ns,
            baseline_frequency_ghz=4.01,
            target_frequency_ghz=4.03,
            frequency_margin_ghz=0.01,
            trace_tracking_mode="ridge",
            trace_polarity="bright",
            trace_shoulder="auto",
        )

    assert result["method"] == ["ridge"] * n_time
    ridge.assert_called_once()
    independent.assert_not_called()


def test_image_failure_falls_back_to_legacy_ridge_with_shoulder_option_present():
    n_time = 7
    image = np.ones((21, n_time))
    frequency = np.linspace(4.0, 4.04, image.shape[0])
    time_ns = np.arange(n_time, dtype=float)

    with (
        mock.patch.object(
            trace_extraction,
            "track_image_ridge",
            autospec=True,
            side_effect=ValueError("synthetic image failure"),
        ),
        mock.patch.object(
            trace_extraction,
            "extract_trace_ridge",
            autospec=True,
            return_value=_trace_result("ridge_fallback", n_time),
        ) as ridge,
    ):
        result = trace_extraction.extract_trace_from_map(
            image,
            frequency,
            time_ns,
            baseline_frequency_ghz=4.01,
            target_frequency_ghz=4.03,
            frequency_margin_ghz=0.01,
            trace_tracking_mode="image_v26",
            trace_polarity="bright",
            trace_shoulder="midpoint",
        )

    assert result["method"] == ["ridge_fallback"] * n_time
    ridge.assert_called_once()
