"""Single shots to populations, checked against verbatim copies of the lab helpers."""
import numpy as np
import pytest

from Bob.runner.populations import correct_population, excited_fraction, populations
from Bob.tests.reference import legacy


@pytest.fixture
def shots():
    rng = np.random.default_rng(7)
    return rng.normal(0.2, 1.0, 2000), rng.normal(-0.1, 1.0, 2000)


@pytest.mark.parametrize("angle, threshold", [(0.0, 0.0), (0.7, 0.3), (-2.1, -0.4)])
def test_excited_fraction_matches_lab(shots, angle, threshold):
    i, q = shots
    expected = legacy.count_percentage(legacy.rotate_data((i, q), angle), threshold)
    assert excited_fraction(i, q, angle, threshold) == pytest.approx(expected)


def test_correction_matches_lab():
    conf = [[0.95, 0.08], [0.05, 0.92]]
    p = np.array([0.0, 0.1, 0.5, 0.9])
    assert np.allclose(correct_population(p, conf), legacy.correct_occ(p, np.array(conf)))
    assert correct_population(0.5, conf).shape == ()


def test_populations_per_readout(shots):
    i, q = shots
    cfg = {"angle": [0.0, 0.5], "threshold": [0.0, 0.2],
           "confusion_matrix": [[[0.9, 0.1], [0.1, 0.9]], [[0.95, 0.05], [0.05, 0.95]]]}
    out = populations([i, i], [q, q], cfg)
    assert out["population"].shape == (2,) and out["population_corrected"].shape == (2,)
    assert out["population_corrected"][0] == pytest.approx(
        legacy.correct_occ(np.array([out["population"][0]]), np.array(cfg["confusion_matrix"][0]))[0])


def test_no_confusion_matrix_means_no_corrected():
    out = populations([np.ones(10)], [np.zeros(10)], {"angle": [0.0], "threshold": [0.5]})
    assert out["population"][0] == 1.0 and "population_corrected" not in out
