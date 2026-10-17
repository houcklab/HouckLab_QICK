"""
Predicted parity -> state mapping of the Modified-Ramsey sequence (F31).

The Hahn-echo control is a parity null only for pulses short against 1/df: at the
bandwidth-limited operating point the detuned echo pi is itself parity-dependent.
predict_parity_mapping propagates the programmed pulses (finite truncated Gaussians, the
branch detuning acting during them) and build_control_variants / compare_parity_controls
exclude an echo_null that is predicted to keep parity contrast. Hardware-free.
"""

import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.special import erf

from qicklab.analysis.modified_ramsey import compare_parity_controls
from qicklab.experiments.modified_ramsey import (
    ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO,
    build_control_variants,
    plan_parity_mapping,
    predict_parity_mapping,
)


def _reference_p_e(detuning_mhz, sigma_us, tau_us, use_pi_pulse, final_phase_deg):
    """Independent solve_ivp integration of i dpsi/dt = H psi with the continuous
    truncated Gaussian, H = (Omega(t)(cos phi X + sin phi Y) + 2 pi Delta Z) / 2."""
    pulse = 4.0 * sigma_us
    n_gaps = 2 if use_pi_pulse else 1
    gap = tau_us / n_gaps - pulse
    area = sigma_us * math.sqrt(2.0 * math.pi) * erf(math.sqrt(2.0))
    pulses = [(math.pi / 2, 0.0)]
    if use_pi_pulse:
        pulses.append((math.pi, 0.0))
    pulses.append((math.pi / 2, final_phase_deg))
    starts = [i * (pulse + gap) for i in range(len(pulses))]
    delta = 2.0 * math.pi * detuning_mhz

    def rhs(t, y):
        psi = y[:2] + 1j * y[2:]
        hx = hy = 0.0
        for t0, (theta, phi) in zip(starts, pulses):
            if t0 <= t <= t0 + pulse:
                om = theta / area * math.exp(-((t - t0 - 2 * sigma_us) ** 2) / (2 * sigma_us**2))
                hx, hy = (
                    0.5 * om * math.cos(math.radians(phi)),
                    0.5 * om * math.sin(math.radians(phi)),
                )
        hz = 0.5 * delta
        d0 = -1j * (hz * psi[0] + (hx - 1j * hy) * psi[1])
        d1 = -1j * ((hx + 1j * hy) * psi[0] - hz * psi[1])
        return [d0.real, d1.real, d0.imag, d1.imag]

    sol = solve_ivp(
        rhs,
        (0.0, starts[-1] + pulse),
        [1.0, 0.0, 0.0, 0.0],
        method="DOP853",
        rtol=1e-10,
        atol=1e-12,
        max_step=sigma_us / 20,
    )
    y = sol.y[:, -1]
    return y[1] ** 2 + y[3] ** 2


def _scheme(df, sigma, k, symmetric, echo, flip=False):
    tau = k / (2.0 * df)
    offset = -df / 2.0 if symmetric else 0.0
    phase = ((90 if symmetric else 180) + (180 if flip else 0)) % 360
    return tau, offset, phase


def test_propagator_matches_solve_ivp_reference():
    for df, sigma, k, symmetric, echo in (
        (2.7, 0.1, 5, True, False),
        (2.7, 0.1, 5, True, True),
        (2.7, 0.1, 5, False, True),
        (2.7, 0.05, 5, True, True),
        (0.5, 0.1, 1, False, False),
    ):
        tau, offset, phase = _scheme(df, sigma, k, symmetric, echo)
        got = predict_parity_mapping(
            df, sigma, tau, offset, use_pi_pulse=echo, final_pi2_phase_deg=phase
        )
        for key, det in (("p_e_upper", -offset), ("p_e_lower", -df - offset)):
            ref = _reference_p_e(det, sigma, tau, echo, phase)
            assert abs(got[key] - ref) < 1e-3, (df, sigma, k, symmetric, echo, key, got[key], ref)


def test_short_pulse_limit_is_the_ideal_mapping():
    # sigma -> 0: standard maps upper -> g, lower -> e; symmetric (k = 1, 5) upper -> e;
    # the echo refocuses df completely (both branches end in the same state).
    for symmetric in (False, True):
        for k in (1, 5):
            tau, offset, phase = _scheme(2.7, 0.0005, k, symmetric, False)
            m = predict_parity_mapping(2.7, 0.0005, tau, offset, final_pi2_phase_deg=phase)
            assert m["contrast"] > 0.999, (symmetric, k, m)
            assert (m["p_e_upper"] > 0.999) is symmetric, (symmetric, k, m)
            e = predict_parity_mapping(
                2.7, 0.0005, tau, offset, use_pi_pulse=True, final_pi2_phase_deg=phase
            )
            assert e["contrast"] < 1e-3, (symmetric, k, e)


def test_finite_pulse_echo_keeps_parity_contrast():
    # CSTQ03 Q2 (df = 2.7 MHz, k = 5), sigma 0.1 us: the documented recommended setting.
    tau, offset, phase = _scheme(2.7, 0.1, 5, True, False)
    main = predict_parity_mapping(2.7, 0.1, tau, offset, final_pi2_phase_deg=phase)
    echo = predict_parity_mapping(
        2.7, 0.1, tau, offset, use_pi_pulse=True, final_pi2_phase_deg=phase
    )
    assert abs(main["contrast"] - 0.732) < 2e-3 and abs(echo["contrast"] - 0.641) < 2e-3
    # Standard scheme: the echo is more parity-sensitive than the measurement.
    tau, offset, phase = _scheme(2.7, 0.1, 5, False, False)
    main = predict_parity_mapping(2.7, 0.1, tau, offset, final_pi2_phase_deg=phase)
    echo = predict_parity_mapping(
        2.7, 0.1, tau, offset, use_pi_pulse=True, final_pi2_phase_deg=phase
    )
    assert abs(main["contrast"] - 0.127) < 2e-3 and abs(echo["contrast"] - 0.884) < 2e-3
    # (residual / main)^2, the lag-covariance scale, at the refuter's reference points.
    for sigma, k, expected in ((0.0739, 5, 0.27), (0.05, 5, 0.054), (0.04, 3, 0.004)):
        tau, offset, phase = _scheme(2.7, sigma, k, True, False)
        m = predict_parity_mapping(2.7, sigma, tau, offset, final_pi2_phase_deg=phase)
        e = predict_parity_mapping(
            2.7, sigma, tau, offset, use_pi_pulse=True, final_pi2_phase_deg=phase
        )
        assert abs((e["contrast"] / m["contrast"]) ** 2 - expected) < 0.01, (sigma, k)


def test_plan_reports_predicted_mapping():
    p = plan_parity_mapping(0.5, 0.1)
    assert 0.97 < p["predicted_mapping"]["contrast"] < 0.99, p["predicted_mapping"]  # ratio 0.5
    # No gap: no prediction (and infeasible).
    assert plan_parity_mapping(2.0, 0.1)["predicted_mapping"] is None


def _base(sigma, k):
    return {
        "f_ge": 4186.7,
        "df": 2.7,
        "sigma": sigma,
        "symmetric_ramsey": True,
        "ramsey_tau_us": k / (2 * 2.7),
        "max_drive_bandwidth_ratio": 1.4,
        "pi2_gain": 1200,
        "pi_gain": 2400,
    }


def test_control_variants_mark_echo_not_a_null():
    include = ("parity", "flip_final_pi2", "echo_null", "drive_off")
    by = {v["control_type"]: v for v in build_control_variants(_base(0.1, 5), include=include)}
    echo = by["echo_null"]
    assert echo["cfg"] is not None and echo["null_control_valid"] is False, echo
    assert "not a null at these settings" in echo["null_invalid_reason"]
    assert echo["cfg"]["mr_null_control_valid"] is False
    assert echo["cfg"]["mr_predicted_residual_ratio"] > ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO
    assert abs(echo["cfg"]["mr_predicted_contrast"] - 0.641) < 2e-3
    assert abs(by["parity"]["cfg"]["mr_predicted_contrast"] - 0.732) < 2e-3
    assert by["drive_off"]["cfg"]["mr_predicted_contrast"] == 0.0
    assert by["parity"]["null_control_valid"] is None
    assert "mr_null_control_valid" not in by["flip_final_pi2"]["cfg"]

    v = build_control_variants(_base(0.04, 3), include=("echo_null",))[0]
    assert v["null_control_valid"] is True and v["null_invalid_reason"] == "", v
    assert v["cfg"]["mr_predicted_residual_ratio"] < 0.1


def _rec(control_type=None, lag=1.0, seed=0, hmm=None, occ1=0.5):
    boot = np.random.default_rng(seed).normal(lag, 0.05, 1000)
    d = {
        "label": control_type or "parity",
        "hmm": hmm if hmm is not None else {"identifiable": True},
        "acf": {
            "amplitude": 0.5,
            "lag_covariance_sum": {
                "available": True,
                "value": lag,
                "boot": boot,
                "max_lag": 10,
                "reason": "",
            },
        },
        "occupancy_state1": occ1,
    }
    if control_type:
        d["control_type"] = control_type
    return d


def test_compare_excludes_echo_that_is_not_a_null():
    main = _rec(seed=1)
    # A genuine parity signal survives the finite-pulse echo (lag ratio ~0.8): it would
    # FAIL as a null, but at these settings it is no null at all.
    echo = _rec("echo_null", lag=0.8, seed=2)
    echo["null_control_valid"] = False
    echo["null_invalid_reason"] = "not a null at these settings: predicted residual ..."
    out = compare_parity_controls(main, [echo])
    entry = out["controls"][0]
    assert entry["checked"] is None and entry["verdict"] == "not a null at these settings"
    assert out["null_control_valid"] is False and out["decisive_controls"] == []
    assert not out["all_expected"], "no decisive check left"
    assert any("remaining decisive checks: none" in n for n in out["notes"]), out["notes"]

    # Next to an informative flip, the result says the flip alone decided.
    main_imb = _rec(seed=3, occ1=0.8)
    flip = _rec("flip_final_pi2", lag=1.0, seed=4, occ1=0.2)
    out = compare_parity_controls(main_imb, [flip, echo])
    assert out["decisive_controls"] == ["flip_final_pi2"], out
    assert any("remaining decisive checks: flip_final_pi2" in n for n in out["notes"])

    # Without the flag (offline dicts, older records) the echo is judged as before.
    echo_plain = _rec("echo_null", lag=0.8, seed=2)
    out = compare_parity_controls(main, [echo_plain])
    assert out["controls"][0]["checked"] is False and out["null_control_valid"] is True
    assert out["notes"] == []
