import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    saved_step_response_refit,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.saved_step_response_refit import (
    refit_saved_step_response,
)


Q3_FLUX_FIT = {
    "EJmax": 4.02378901539,
    "Ec": 0.449998775338,
    "period_volts": 50575.939402,
    "phase_offset_volts": -17654.3599163,
    "d": 0.369350889718,
    "tilt_slope": -4.72847424324e-05,
}


def _synthetic_q3_step_map():
    frequency_ghz = np.arange(4.000, 4.0805, 0.0005)
    time_ns = np.arange(1_000.0, 198_000.0, 4_000.0)
    baseline = -25_146.0
    target = -14_750.0
    response = 0.970 + 0.018 * (1.0 - np.exp(-time_ns / 70_000.0))
    effective_dc = baseline + response * (target - baseline)
    lower = flux_fit.estimate_fit_frequency_ghz_array(Q3_FLUX_FIT, effective_dc)
    upper = lower + 0.00475

    freq_mhz = frequency_ghz[:, None] * 1e3
    lower_mhz = lower[None, :] * 1e3
    upper_mhz = upper[None, :] * 1e3
    rng = np.random.default_rng(913)
    magnitude = rng.normal(scale=0.08, size=(frequency_ghz.size, time_ns.size))
    magnitude -= 2.8 * np.exp(-0.5 * ((freq_mhz - lower_mhz) / 1.2) ** 2)
    magnitude -= 3.4 * np.exp(-0.5 * ((freq_mhz - upper_mhz) / 1.2) ** 2)

    return {
        "qubit": "q3",
        "fit_frequency_axis_ghz": frequency_ghz,
        "t_vec": time_ns,
        "IQ_mag": magnitude,
        "dc_offset": target,
        "baseline_dc_offset": baseline,
        "flux_fit_params": Q3_FLUX_FIT,
        "meta_dict": {"flux_channel": 3, "flux_name": "ff_ch3"},
    }


def _replace_slow_parametric_fit(monkeypatch):
    def fitted_measurements(time_ns, response, *, time_origin_ns, **_kwargs):
        time_ns = np.asarray(time_ns, dtype=float)
        response = np.asarray(response, dtype=float)
        valid = np.isfinite(time_ns) & np.isfinite(response)
        measured_time = time_ns[valid]
        measured_response = response[valid]
        model_time = np.concatenate([[float(time_origin_ns)], measured_time])
        model_response = np.concatenate([[measured_response[0]], measured_response])
        return {
            "success": True,
            "error": None,
            "method": "test_measurement_model",
            "time_ns": model_time,
            "time_zeroed_ns": model_time - float(time_origin_ns),
            "measured_time_ns": measured_time,
            "measured_time_zeroed_ns": measured_time - float(time_origin_ns),
            "time_origin_ns": float(time_origin_ns),
            "response": measured_response,
            "asymptote": float(measured_response[-1]),
            "late_amplitude": float(measured_response[0] - measured_response[-1]),
            "late_tau_ns": 70_000.0,
            "bump_amplitude": 0.0,
            "rise_tau_ns": 1_000.0,
            "bump_tau_ns": 10_000.0,
            "fit_response": model_response,
            "residual": np.zeros_like(measured_response),
            "rms": 0.0,
            "bic": 0.0,
        }

    monkeypatch.setattr(
        saved_step_response_refit.flux_predistortion,
        "fit_rise_decay_bump_response_model",
        fitted_measurements,
    )


def test_refit_tracks_one_upper_shoulder_and_preserves_physical_time_origin(
    monkeypatch,
):
    _replace_slow_parametric_fit(monkeypatch)
    result = refit_saved_step_response(
        _synthetic_q3_step_map(),
        signal_source="magnitude",
        polarity="dark",
        shoulder="upper",
        time_origin_ns=0.0,
        max_first_supported_ns=5_000.0,
    )

    assert result["trace"]["shoulder_mode"] == "paired_upper"
    assert result["trace"]["paired_support_fraction"] > 0.8
    assert result["first_supported_time_ns"] <= 5_000.0
    assert result["model"]["time_ns"][0] == 0.0
    assert result["correction"]["segment_edges_ns"][0] == 0.0
    assert result["correction"]["segment_edges_ns"][-1] >= 190_000.0


def test_refit_inverse_reduces_the_fitted_transient_without_clipping(monkeypatch):
    _replace_slow_parametric_fit(monkeypatch)
    result = refit_saved_step_response(
        _synthetic_q3_step_map(),
        signal_source="magnitude",
        polarity="dark",
        shoulder="upper",
        time_origin_ns=0.0,
        max_first_supported_ns=5_000.0,
    )

    correction = result["correction"]
    raw = np.asarray(result["model"]["fit_response"], dtype=float)
    corrected = np.asarray(correction["corrected_response"], dtype=float)
    desired = float(correction["desired_response_level"])
    raw_rms = float(np.sqrt(np.mean((raw - desired) ** 2)))
    corrected_rms = float(np.sqrt(np.mean((corrected - desired) ** 2)))

    assert correction["method"] == "rise_decay_bump_set_dc_offset_correction"
    assert correction["success"] is True
    assert correction["multiplier_clipped"] is False
    assert corrected_rms < 0.35 * raw_rms


def test_refit_rejects_a_trace_that_starts_too_late_for_causal_alignment(
    monkeypatch,
):
    _replace_slow_parametric_fit(monkeypatch)
    data = _synthetic_q3_step_map()
    selected = np.full(data["t_vec"].shape, 4.045, dtype=float)
    supported = np.ones(data["t_vec"].shape, dtype=bool)
    supported[:6] = False
    monkeypatch.setattr(
        saved_step_response_refit,
        "track_image_ridge",
        lambda *_args, **_kwargs: {
            "selected_frequency_ghz": selected,
            "supported": supported,
            "shoulder_mode": "paired_upper",
            "paired_support_fraction": float(np.mean(supported)),
        },
    )

    try:
        refit_saved_step_response(
            data,
            signal_source="magnitude",
            polarity="dark",
            shoulder="upper",
            time_origin_ns=0.0,
            max_first_supported_ns=5_000.0,
        )
    except ValueError as exc:
        assert "first supported" in str(exc).lower()
    else:
        raise AssertionError("late-starting trace was accepted")


def test_parametric_model_can_be_evaluated_from_the_physical_step_origin(
    monkeypatch,
):
    class FitResult:
        success = True
        message = ""

        def __init__(self, x):
            self.x = np.asarray(x, dtype=float)

    monkeypatch.setattr(
        flux_predistortion.optimize,
        "least_squares",
        lambda _function, p0, **_kwargs: FitResult(p0),
    )
    time_ns = np.arange(1_000.0, 49_001.0, 4_000.0)
    response = 0.97 + 0.02 * (1.0 - np.exp(-time_ns / 30_000.0))

    model = flux_predistortion.fit_rise_decay_bump_response_model(
        time_ns,
        response,
        time_origin_ns=0.0,
    )

    assert model["time_origin_ns"] == 0.0
    assert model["time_ns"][0] == 0.0
    assert model["time_zeroed_ns"][0] == 0.0
    assert model["measured_time_ns"][0] == 1_000.0
    assert len(model["fit_response"]) == len(time_ns) + 1
