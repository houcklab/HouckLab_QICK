import json

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    ReferenceAxis,
    json_safe,
    load_park_history_method_frequencies,
)


def test_reference_axis_projects_iq_population():
    axis = ReferenceAxis.from_centers(1.0, 2.0, 5.0, 5.0)
    values = axis.population([1.0, 3.0, 5.0], [2.0, 3.5, 5.0])

    assert values == pytest.approx([0.0, 0.5, 1.0])
    assert axis.mean_population([1.0, 5.0], [2.0, 5.0]) == pytest.approx(0.5)
    assert ReferenceAxis.from_dict(axis.to_dict()) == axis


def test_reference_axis_rejects_coincident_centers():
    with pytest.raises(ValueError, match="coincide"):
        ReferenceAxis.from_centers(1.0, 2.0, 1.0, 2.0)


def test_json_safe_converts_numpy_and_nonfinite_values():
    value = {
        "array": np.asarray([1.0, np.nan]),
        "scalar": np.int64(3),
        "tuple": (np.float64(2.0), float("inf")),
    }

    assert json_safe(value) == {
        "array": [1.0, None],
        "scalar": 3,
        "tuple": [2.0, None],
    }


def test_park_history_frequency_loader_validates_and_averages(tmp_path):
    fits = {}
    centers = {
        "history_1_recovery_10": 4366.2,
        "history_750_recovery_10": 4366.4,
        "history_1_recovery_1000": 4365.8,
        "history_750_recovery_1000": 4366.0,
    }
    for name, center in centers.items():
        fits[name] = {
            "center_mhz": center,
            "center_err_mhz": 0.05,
            "contrast": 0.5,
            "boundary_peak": False,
        }
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"fits": fits}))

    observed = load_park_history_method_frequencies(path)

    assert observed == pytest.approx({
        "opx_unbounded": 4366.3,
        "passive": 4365.9,
    })
