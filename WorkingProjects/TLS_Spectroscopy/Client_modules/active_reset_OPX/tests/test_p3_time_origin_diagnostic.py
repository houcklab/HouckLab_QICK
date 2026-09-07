import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.p3_time_origin_diagnostic_q3 import (
    compare_time_order,
)


def test_compare_time_order_identifies_physical_delay_feature():
    forward_time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    reverse_time = forward_time[::-1]
    forward = np.array([0.0, 1.0, -1.0, 0.3, 2.0])
    reverse = forward[::-1]

    result = compare_time_order(forward_time, forward, reverse_time, reverse)

    assert result["diagnosis"] == "physical_delay_feature"
    assert result["physical_time_correlation"] > 0.99
    assert result["acquisition_order_correlation"] < 0.5


def test_compare_time_order_identifies_acquisition_history_feature():
    forward_time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    reverse_time = forward_time[::-1]
    forward = np.array([0.0, 1.0, -1.0, 0.3, 2.0])
    reverse = forward.copy()

    result = compare_time_order(forward_time, forward, reverse_time, reverse)

    assert result["diagnosis"] == "acquisition_history_feature"
    assert result["acquisition_order_correlation"] > 0.99
    assert result["physical_time_correlation"] < 0.5
