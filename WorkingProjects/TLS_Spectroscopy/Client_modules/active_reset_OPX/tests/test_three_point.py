import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.three_point import (
    canonicalize_bidirectional_records,
    distributed_p0_reference_indices,
    reduce_bidirectional_states,
)


def test_distributed_p0_references_match_qua_direction_balanced_schedule():
    assert distributed_p0_reference_indices(500) == (
        0, 1, 124, 125, 248, 249, 374, 375, 498, 499,
    )
    assert distributed_p0_reference_indices(6) == (0, 1, 2, 3, 4, 5)


@pytest.mark.parametrize("shots", [0, -1])
def test_distributed_p0_references_reject_nonpositive_shots(shots):
    with pytest.raises(ValueError, match="total_shots"):
        distributed_p0_reference_indices(shots)


def test_bidirectional_records_are_returned_on_an_ascending_dc_axis():
    values = np.empty((4, 3, 3), dtype=float)
    for shot in range(4):
        for visit in range(3):
            for reference in range(3):
                values[shot, visit, reference] = 100 * shot + 10 * visit + reference

    canonical = canonicalize_bidirectional_records(values)

    np.testing.assert_array_equal(canonical[0], values[0])
    np.testing.assert_array_equal(canonical[1], values[1, ::-1])
    np.testing.assert_array_equal(canonical[2], values[2])
    np.testing.assert_array_equal(canonical[3], values[3, ::-1])


def test_directional_reduction_uses_sparse_scalar_p0_and_all_p1_ps_shots():
    states = np.asarray([
        [[0, 1, 1, 0], [1, 1, 0, 0]],
        [[0, 1, 1, 1], [1, 0, 1, 0]],
        [[0, 0, 1, 1], [1, 1, 0, 1]],
    ], dtype=float)

    result = reduce_bidirectional_states(states, (0, 1))

    np.testing.assert_allclose(result["P0_scan_up"], [0.5, 0.5])
    np.testing.assert_allclose(result["P0_scan_down"], [1.0, 1.0])
    np.testing.assert_allclose(result["P0"], [0.75, 0.75])
    np.testing.assert_allclose(result["P1_scan_up"], [0.5, 1.0])
    np.testing.assert_allclose(result["P1_scan_down"], [1.0, 0.0])
    np.testing.assert_allclose(result["P1"], [0.75, 0.5])
    np.testing.assert_allclose(result["Ps_scan_up"], [0.5, 0.5])
    np.testing.assert_allclose(result["Ps_scan_down"], [0.5, 1.0])
    np.testing.assert_allclose(result["Ps"], [0.5, 0.75])
    assert result["dc_scan_up_shots"] == 2
    assert result["dc_scan_down_shots"] == 2
    assert result["p0_reference_up_sweeps"] == 1
    assert result["p0_reference_down_sweeps"] == 1


def test_directional_reduction_requires_a_p0_reference_in_each_direction():
    states = np.zeros((3, 2, 4), dtype=float)

    with pytest.raises(ValueError, match="both scan directions"):
        reduce_bidirectional_states(states, (0, 2))
