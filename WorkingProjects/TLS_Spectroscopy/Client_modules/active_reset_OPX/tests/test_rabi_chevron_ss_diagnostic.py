import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.rabi_chevron_ss_diagnostic_q3 import (
    _axis_subset,
    classify_diagnostic,
    matrix_comparison,
    matrix_metrics,
)


def test_axis_subset_preserves_uniform_steps_for_even_length_axes():
    subset = _axis_subset(np.arange(20), 11)
    assert subset.size <= 11
    assert np.all(np.diff(subset) == np.diff(subset)[0])


def test_matrix_metrics_reports_contrast_and_peak_coordinates():
    values = np.asarray([[0.1, 0.2], [0.8, 0.3]])
    metrics = matrix_metrics(values, np.asarray([-1.0, 1.0]), np.asarray([10, 20]))
    assert metrics["contrast"] == pytest.approx(0.7)
    assert metrics["peak_frequency_mhz"] == 1.0
    assert metrics["peak_gain_dac"] == 10


def test_matrix_comparison_detects_identical_and_transposed_data():
    reference = np.asarray([[0.0, 0.2], [0.7, 1.0]])
    same = matrix_comparison(reference, reference.copy())
    transposed = matrix_comparison(reference, reference.T)
    assert same["rmse"] == 0.0
    assert same["correlation"] == pytest.approx(1.0)
    assert transposed["rmse"] > 0.0


def test_classify_diagnostic_identifies_payload_classifier_failure():
    result = classify_diagnostic(
        ss_fidelity=0.9,
        contrasts={
            "legacy_passive_axis": 0.7,
            "resident_passive_axis": 0.7,
            "resident_active_grid_axis": 0.6,
            "resident_active_grid_threshold": 0.02,
            "resident_active_rowwise_axis": 0.6,
        },
    )
    assert result == "payload_classifier"


def test_classify_diagnostic_identifies_resident_grid_failure():
    result = classify_diagnostic(
        ss_fidelity=0.9,
        contrasts={
            "legacy_passive_axis": 0.7,
            "resident_passive_axis": 0.03,
            "resident_active_grid_axis": 0.02,
            "resident_active_grid_threshold": 0.01,
            "resident_active_rowwise_axis": 0.6,
        },
    )
    assert result == "resident_grid_or_dmem"


def test_classify_diagnostic_identifies_nested_active_grid_failure():
    result = classify_diagnostic(
        ss_fidelity=0.9,
        contrasts={
            "legacy_passive_axis": 0.7,
            "resident_passive_axis": 0.6,
            "resident_active_grid_axis": 0.03,
            "resident_active_grid_threshold": 0.02,
            "resident_active_rowwise_axis": 0.7,
        },
    )
    assert result == "nested_grid_programming"


def test_classify_diagnostic_identifies_active_reset_failure():
    result = classify_diagnostic(
        ss_fidelity=0.9,
        contrasts={
            "legacy_passive_axis": 0.7,
            "resident_passive_axis": 0.6,
            "resident_active_grid_axis": 0.03,
            "resident_active_grid_threshold": 0.02,
            "resident_active_rowwise_axis": 0.04,
        },
    )
    assert result == "active_reset_lifecycle"


def test_classify_diagnostic_identifies_bad_reference_calibration():
    result = classify_diagnostic(
        ss_fidelity=0.55,
        contrasts={
            "legacy_passive_axis": 0.0,
            "resident_passive_axis": 0.0,
            "resident_active_grid_axis": 0.0,
            "resident_active_grid_threshold": 0.0,
            "resident_active_rowwise_axis": 0.0,
        },
    )
    assert result == "single_shot_or_pi_calibration"
