import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.image_ridge_tracker import (
    track_template_causal_ridge,
)


def _doublet_map(frequency_ghz, time_us, center_ghz):
    image = np.empty((frequency_ghz.size, time_us.size), dtype=float)
    for column, center in enumerate(center_ghz):
        # Alternate which shoulder is brighter.  A local-maximum tracker tends
        # to zigzag by the 6 MHz shoulder separation; a full-line template must
        # preserve one identity and follow their common smooth translation.
        imbalance = 0.18 * (-1.0 if column % 2 else 1.0)
        lower = np.exp(-0.5 * ((frequency_ghz - (center - 0.003)) / 0.0011) ** 2)
        upper = np.exp(-0.5 * ((frequency_ghz - (center + 0.003)) / 0.0011) ** 2)
        image[:, column] = (1.0 + imbalance) * lower + (1.0 - imbalance) * upper
    rng = np.random.default_rng(1701)
    return image + 0.025 * rng.normal(size=image.shape)


def test_template_causal_tracker_does_not_switch_doublet_shoulders():
    frequency_ghz = np.linspace(4.00, 4.10, 201)
    time_us = np.concatenate(
        [np.arange(0.5, 25.5, 0.5), np.arange(27.0, 61.0, 2.0), np.arange(65.0, 195.0, 10.0), [197.0, 200.0]]
    )
    center_ghz = (
        4.032
        + 0.006 * np.exp(-time_us / 10.0)
        + 0.016 * (1.0 - np.exp(-time_us / 1.8)) * np.exp(-time_us / 65.0)
    )
    image = _doublet_map(frequency_ghz, time_us, center_ghz)

    result = track_template_causal_ridge(
        frequency_ghz,
        time_us,
        image,
        polarity="bright",
    )

    fitted = np.asarray(result["smoothed_frequency_ghz"])
    # The selected identity may be either shoulder, so compare after removing
    # its constant offset from the doublet center.
    offset = np.median(fitted - center_ghz)
    assert np.max(np.abs(fitted - center_ghz - offset)) < 0.0015
    assert np.mean(result["supported"]) >= 0.8
    assert result["shoulder_mode"] == "full_line_template"
    assert set(result["method"]) <= {
        "image_template_causal_bright",
        "image_template_causal_ambiguous",
    }


def test_template_causal_tracker_accepts_descending_frequency_axis():
    frequency_ghz = np.linspace(4.10, 4.00, 201)
    time_us = np.linspace(0.5, 120.0, 48)
    center_ghz = 4.034 + 0.012 * np.exp(-time_us / 35.0)
    image = _doublet_map(frequency_ghz, time_us, center_ghz)

    result = track_template_causal_ridge(
        frequency_ghz,
        time_us,
        image,
        polarity="bright",
    )

    fitted = np.asarray(result["smoothed_frequency_ghz"])
    offset = np.median(fitted - center_ghz)
    assert np.sqrt(np.mean((fitted - center_ghz - offset) ** 2)) < 0.001
