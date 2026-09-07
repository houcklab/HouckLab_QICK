from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.correction_waveform_ab_q3 import (
    infer_failure_source,
)


def test_infer_failure_source_identifies_correction_waveform():
    result = infer_failure_source(
        dynamic_corrected=[0.90, 0.08, 0.88, 0.05],
        isolated_dynamic_corrected=[0.89, 0.09, 0.89, 0.06],
        static_corrected=[0.88, 0.10, 0.90, 0.06],
        uncorrected_before=[0.90, 0.85, 0.80, 0.72],
        uncorrected_after=[0.89, 0.84, 0.81, 0.73],
    )

    assert result["diagnosis"] == "correction_waveform"
    assert result["corrected_dynamic_vs_static_rmse"] < 0.05
    assert result["corrected_vs_uncorrected_rmse"] > 0.20


def test_infer_failure_source_identifies_dynamic_assembly():
    result = infer_failure_source(
        dynamic_corrected=[0.90, 0.08, 0.88, 0.05],
        isolated_dynamic_corrected=[0.88, 0.11, 0.89, 0.07],
        static_corrected=[0.90, 0.84, 0.79, 0.71],
        uncorrected_before=[0.91, 0.85, 0.80, 0.72],
        uncorrected_after=[0.90, 0.84, 0.81, 0.71],
    )

    assert result["diagnosis"] == "dynamic_assembly"
    assert result["corrected_dynamic_vs_static_rmse"] > 0.20
    assert result["static_corrected_vs_uncorrected_rmse"] < 0.05


def test_infer_failure_source_reports_drift_before_blame():
    result = infer_failure_source(
        dynamic_corrected=[0.90, 0.08, 0.88, 0.05],
        isolated_dynamic_corrected=[0.88, 0.10, 0.90, 0.06],
        static_corrected=[0.88, 0.10, 0.90, 0.06],
        uncorrected_before=[0.90, 0.85, 0.80, 0.72],
        uncorrected_after=[0.40, 0.35, 0.30, 0.22],
    )

    assert result["diagnosis"] == "measurement_drift"


def test_infer_failure_source_identifies_cross_delay_history():
    result = infer_failure_source(
        dynamic_corrected=[0.90, 0.08, 0.88, 0.05],
        isolated_dynamic_corrected=[0.90, 0.84, 0.79, 0.71],
        static_corrected=[0.91, 0.85, 0.80, 0.72],
        uncorrected_before=[0.90, 0.85, 0.80, 0.72],
        uncorrected_after=[0.91, 0.84, 0.81, 0.71],
    )

    assert result["diagnosis"] == "cross_delay_flux_history"
    assert result["isolated_dynamic_vs_static_rmse"] < 0.05
    assert result["dynamic_vs_isolated_dynamic_rmse"] > 0.20
