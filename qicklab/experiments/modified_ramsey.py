import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram

from qicklab.core.active_reset import ActiveResetMixin
from qicklab.core.experiment import ExperimentClass
from qicklab.core.readout import cover_readout_window
from qicklab.core.schedule import RepPeriodMixin

# h5 code of cfg["mr_control_type"]; expected signatures in docs/experiments/modified_ramsey.md.
MR_CONTROL_TYPE_CODES = {
    "parity": 0,
    "flip_final_pi2": 1,
    "echo_null": 2,
    "tau_offset": 3,
    "drive_detuned": 4,
    "drive_off": 5,
}

# echo_null is "not a null at these settings" when its predicted residual contrast exceeds this
# fraction of the parity run's (docs/experiments/modified_ramsey.md#echo-is-a-null-only-for-short-pulses).
ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO = 0.2
# drive_detuned is a decisive inverted-mapping check (judged like flip_final_pi2) when its
# predicted contrast is at most -this times the parity run's (docs/experiments/modified_ramsey.md#analysis).
DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO = 0.8
# With use_active_reset, drive_detuned is decisive only when the reset pi, which plays at the
# detuned drive, is predicted to flip each branch |e> -> |g> with at least this probability;
# otherwise inter-shot carryover could fail the flip-like checks (docs/experiments/modified_ramsey.md#analysis).
DRIVE_DETUNED_MIN_RESET_PI_TRANSFER = 0.95
# The predicted mapping seeds the HMM mapping fit only when its contrast is at least this;
# below it the two seeds sit too close to separate the states (docs/experiments/modified_ramsey.md#analysis).
MAPPING_SEED_MIN_PREDICTED_CONTRAST = 0.1


def _step_unitaries(om_x, om_y, delta_rad_us, dt_us):
    """exp(-i dt (om_x X + om_y Y + delta Z) / 2) for each step; shape (n, 2, 2)."""
    hx, hy, hz = 0.5 * om_x, 0.5 * om_y, 0.5 * delta_rad_us * np.ones_like(om_x)
    norm = np.sqrt(hx * hx + hy * hy + hz * hz)
    c = np.cos(norm * dt_us)
    s = np.where(norm > 0, np.sin(norm * dt_us) / np.where(norm > 0, norm, 1.0), dt_us)
    u = np.empty((om_x.size, 2, 2), dtype=complex)
    u[:, 0, 0] = c - 1j * s * hz
    u[:, 0, 1] = -1j * s * (hx - 1j * hy)
    u[:, 1, 0] = -1j * s * (hx + 1j * hy)
    u[:, 1, 1] = c + 1j * s * hz
    return u


def predict_parity_mapping(
    df_mhz,
    sigma_us,
    tau_us,
    drive_freq_offset_mhz=0.0,
    use_pi_pulse=False,
    final_pi2_phase_deg=180.0,
    pi2_area_rad=np.pi / 2,
    pi_area_rad=np.pi,
    n_steps=200,
):
    """Predicted P(e|upper), P(e|lower) and contrast of the programmed sequence for an ideal
    two-level qubit (no T2, no readout error): nominal 4*sigma truncated Gaussians whose
    on-resonance area is calibrated to pi/2 (the echo pi: pi, phase 0), the branch detuning
    acting during the pulses and the gaps, pulses centre-to-centre at tau (the pi at tau/2).
    Piecewise-constant 2x2 propagator, n_steps per pulse
    (docs/experiments/modified_ramsey.md#echo-is-a-null-only-for-short-pulses)."""
    pulse_us = 4.0 * float(sigma_us)
    n_gaps = 2 if use_pi_pulse else 1
    gap_us = float(tau_us) / n_gaps - pulse_us
    if gap_us <= 0:
        raise ValueError(f"tau={tau_us} us leaves no gap between {n_gaps + 1} 4*sigma pulses")
    dt = pulse_us / n_steps
    t = (np.arange(n_steps) + 0.5) * dt
    env = np.exp(-((t - 2.0 * sigma_us) ** 2) / (2.0 * sigma_us**2))
    env_area = env.sum() * dt
    pulses = [(pi2_area_rad, 0.0)]
    if use_pi_pulse:
        pulses.append((pi_area_rad, 0.0))
    pulses.append((pi2_area_rad, float(final_pi2_phase_deg)))

    def p_excited(detuning_mhz):
        # detuning_mhz = f_branch - f_drive
        delta = 2.0 * np.pi * detuning_mhz
        free = np.diag([np.exp(-0.5j * delta * gap_us), np.exp(0.5j * delta * gap_us)])
        u_total = np.eye(2, dtype=complex)
        for idx, (area, phase_deg) in enumerate(pulses):
            om = area / env_area * env
            ph = np.deg2rad(phase_deg)
            for u_step in _step_unitaries(om * np.cos(ph), om * np.sin(ph), delta, dt):
                u_total = u_step @ u_total
            if idx < len(pulses) - 1:
                u_total = free @ u_total
        return float(abs(u_total[1, 0]) ** 2)

    offset = float(drive_freq_offset_mhz)
    p_upper = p_excited(-offset)
    p_lower = p_excited(-float(df_mhz) - offset)
    return {"p_e_upper": p_upper, "p_e_lower": p_lower, "contrast": abs(p_upper - p_lower)}


def predict_pi_transfer(sigma_us, detuning_mhz, area_rad=np.pi, n_steps=200):
    """Predicted |e> -> |g> probability of one nominal 4*sigma truncated Gaussian whose
    on-resonance area is area_rad (the active-reset pi), for an ideal two-level qubit at
    detuning_mhz = f_qubit - f_drive (same propagator as predict_parity_mapping)."""
    pulse_us = 4.0 * float(sigma_us)
    dt = pulse_us / n_steps
    t = (np.arange(n_steps) + 0.5) * dt
    env = np.exp(-((t - 2.0 * sigma_us) ** 2) / (2.0 * sigma_us**2))
    om = area_rad / (env.sum() * dt) * env
    u_total = np.eye(2, dtype=complex)
    for u_step in _step_unitaries(om, np.zeros_like(om), 2.0 * np.pi * float(detuning_mhz), dt):
        u_total = u_step @ u_total
    return float(abs(u_total[1, 0]) ** 2)


def _solve_tau_null(cfg, tau_lo_us, tau_hi_us, tau_guess_us, n_grid=25):
    """tau in [tau_lo_us, tau_hi_us] where the predicted P(e|upper) - P(e|lower) of cfg
    crosses zero, the crossing closest to tau_guess_us (brentq); None when there is none."""
    from scipy.optimize import brentq

    def signed(tau_us):
        trial = dict(cfg)
        trial["ramsey_tau_us"] = float(tau_us)
        pred = _plan_for_cfg(trial)["predicted_mapping"]
        return pred["p_e_upper"] - pred["p_e_lower"]

    grid = np.linspace(tau_lo_us, tau_hi_us, n_grid)
    vals = np.array([signed(t) for t in grid])
    brackets = [
        (grid[i], grid[i + 1])
        for i in range(n_grid - 1)
        if np.sign(vals[i]) != np.sign(vals[i + 1])
    ]
    if not brackets:
        return None
    lo, hi = min(brackets, key=lambda b: abs(0.5 * (b[0] + b[1]) - tau_guess_us))
    return float(brentq(signed, lo, hi, xtol=1e-7))


def plan_parity_mapping(
    df_mhz,
    sigma_us,
    use_pi_pulse=False,
    symmetric_ramsey=False,
    flip_final_pi2=False,
    max_bandwidth_ratio=1.0,
    tau_us=None,
    drive_freq_offset_mhz=None,
):
    """Hardware-free timing/bandwidth feasibility of the parity -> state mapping with
    nominal 4*sigma envelopes; returns feasible, errors, warnings and the derived
    numbers (docs/experiments/modified_ramsey.md)."""
    errors, warnings = [], []
    if df_mhz <= 0:
        raise ValueError("df_mhz must be positive")
    if sigma_us <= 0:
        raise ValueError("sigma_us must be positive")

    tau_us = 1.0 / (2.0 * df_mhz) if tau_us is None else float(tau_us)
    pulse_us = 4.0 * sigma_us
    n_gaps = 2 if use_pi_pulse else 1
    gap_us = (tau_us - n_gaps * pulse_us) / n_gaps
    df_max_mhz = 1.0 / (2.0 * n_gaps * pulse_us)
    if gap_us <= 0:
        errors.append(
            f"df={df_mhz} MHz needs tau={tau_us:.4f} us but the "
            f"{3 if use_pi_pulse else 2} pulses span "
            f"{n_gaps * pulse_us:.4f} us; need df < {df_max_mhz:.4f} MHz at "
            f"sigma={sigma_us} us (or shorter sigma)"
        )

    rabi_pi2_mhz = 0.0997 / sigma_us
    if drive_freq_offset_mhz is None:
        drive_freq_offset_mhz = -df_mhz / 2.0 if symmetric_ramsey else 0.0
    branch_detuning_mhz = max(
        abs(float(drive_freq_offset_mhz)), abs(float(drive_freq_offset_mhz) + df_mhz)
    )
    bandwidth_ratio = branch_detuning_mhz / rabi_pi2_mhz
    recommend_symmetric = (not symmetric_ramsey) and bandwidth_ratio > 0.2
    if bandwidth_ratio > max_bandwidth_ratio:
        errors.append(
            f"branch detuning {branch_detuning_mhz:.4f} MHz is "
            f"{bandwidth_ratio:.2f}x the pi/2 Rabi rate "
            f"({rabi_pi2_mhz:.4f} MHz): the off-resonant branch cannot be "
            "rotated; shorten sigma" + ("" if symmetric_ramsey else " or set symmetric_ramsey=True")
        )
    elif bandwidth_ratio > 0.2:
        warnings.append(
            f"branch detuning is {bandwidth_ratio:.2f}x the pi/2 Rabi rate; "
            "the off-resonant branch will be under-rotated"
            + (" -- symmetric_ramsey=True would halve the detuning" if recommend_symmetric else "")
        )
    if use_pi_pulse:
        warnings.append(
            "use_pi_pulse=True is a Hahn-echo NULL control: it refocuses the "
            "static parity detuning only for pulses short against 1/df; "
            "predicted_mapping gives the contrast it keeps"
        )

    base = 90 if symmetric_ramsey else 180
    final_phase = (base + (180 if flip_final_pi2 else 0)) % 360
    predicted = (
        predict_parity_mapping(
            df_mhz,
            sigma_us,
            tau_us,
            drive_freq_offset_mhz=float(drive_freq_offset_mhz),
            use_pi_pulse=use_pi_pulse,
            final_pi2_phase_deg=final_phase,
        )
        if gap_us > 0
        else None
    )
    return {
        "feasible": not errors,
        "errors": errors,
        "warnings": warnings,
        "tau_us": tau_us,
        "pulse_us": pulse_us,
        "n_gaps": n_gaps,
        "gap_us": gap_us,
        "df_max_mhz": df_max_mhz,
        "rabi_pi2_mhz": rabi_pi2_mhz,
        "branch_detuning_mhz": branch_detuning_mhz,
        "bandwidth_ratio": bandwidth_ratio,
        "recommend_symmetric": recommend_symmetric,
        "drive_freq_offset_mhz": float(drive_freq_offset_mhz),
        "final_pi2_phase_deg": final_phase,
        "predicted_mapping": predicted,
    }


def _plan_for_cfg(cfg):
    return plan_parity_mapping(
        cfg["df"],
        cfg["sigma"],
        use_pi_pulse=cfg.get("use_pi_pulse", False),
        symmetric_ramsey=cfg.get("symmetric_ramsey", False),
        flip_final_pi2=cfg.get("flip_final_pi2", False),
        tau_us=cfg.get("ramsey_tau_us"),
        drive_freq_offset_mhz=(
            cfg.get("ramsey_drive_freq_mhz") - cfg["f_ge"]
            if cfg.get("ramsey_drive_freq_mhz") is not None
            else None
        ),
        max_bandwidth_ratio=cfg.get("max_drive_bandwidth_ratio", 1.0),
    )


def build_control_variants(
    base_cfg,
    include=("parity", "flip_final_pi2", "echo_null", "tau_offset", "drive_detuned", "drive_off"),
    tau_offset_frac=None,
    detuning_mhz=None,
):
    """Copies of base_cfg for the parity run and each control in `include`, each
    pre-checked with plan_parity_mapping; infeasible ones get cfg=None and a
    skip_reason instead of raising. Each carries its predicted mapping (also in its cfg).
    echo_null and tau_offset are nulls: null_control_valid=False when they keep more than
    ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO of the parity run's predicted contrast. The
    default tau_offset tau is the even harmonic (k+1)/(2 df) of the programmed k/(2 df) when
    the drive sits on a branch (standard scheme); with any other drive offset (symmetric
    scheme) it is the predicted zero of the contrast closest to it, which the finite pulses
    move a few % below it. tau_offset_frac=f gives the programmed tau x (1 + f) instead.
    drive_detuned (default +df: a common phase k*pi) gets inverted_mapping_expected=True
    when its predicted contrast is <= -DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO times the
    parity run's and, with use_active_reset, the reset pi at the detuned drive is predicted
    to flip each branch with >= DRIVE_DETUNED_MIN_RESET_PI_TRANSFER
    (docs/experiments/modified_ramsey.md#analysis)."""
    base_plan = _plan_for_cfg(base_cfg)
    base_predicted = base_plan["predicted_mapping"]
    base_tau_us = base_plan["tau_us"]
    out = []
    for name in include:
        if name not in MR_CONTROL_TYPE_CODES:
            raise ValueError(f"unknown control type {name!r}")
        cfg = dict(base_cfg)
        cfg["mr_control_type"] = name
        expected = ""
        reset_transfer = None
        if name == "parity":
            expected = "telegraph parity signal at tau = 1/(2 df)"
        elif name == "flip_final_pi2":
            cfg["flip_final_pi2"] = not bool(base_cfg.get("flip_final_pi2", False))
            expected = "parity->state mapping inverted; same rates/amplitude"
        elif name == "echo_null":
            cfg["use_pi_pulse"] = True
            expected = "parity contrast suppressed (echo refocuses df)"
        elif name == "tau_offset":
            df_mhz = float(base_cfg["df"])
            if tau_offset_frac is None:
                # the even harmonic next to the programmed tau = k/(2 df): a phase (k+1)*pi
                k = max(1, int(round(2.0 * df_mhz * base_tau_us)))
                tau_even_us = (k + 1) / (2.0 * df_mhz)
                tau_us = tau_even_us
                expected = (
                    f"tau = (k+1)/(2 df) = {tau_us:.4f} us (k = {k}), the even harmonic: "
                    "both branches end in the same state; parity contrast suppressed"
                )
                if abs(base_plan["drive_freq_offset_mhz"]) > 1e-12 and base_plan["feasible"]:
                    # Drive off both branches (symmetric): the finite pulses lengthen the
                    # effective phase time, so the predicted null sits below the even
                    # harmonic; solve for it (a linear zero, like the even harmonic there).
                    half = 0.5 / (2.0 * df_mhz)
                    solved = _solve_tau_null(
                        cfg, tau_even_us - half, tau_even_us + half, tau_even_us
                    )
                    if solved is not None:
                        tau_us = solved
                        expected = (
                            f"tau = {tau_us:.4f} us, the predicted zero of the parity contrast "
                            f"near the even harmonic (k+1)/(2 df) = {tau_even_us:.4f} us "
                            f"(k = {k}; the finite pulses move it "
                            f"{tau_us / tau_even_us - 1.0:+.1%}): both branches end in the same "
                            "state; parity contrast suppressed"
                        )
            else:
                tau_us = base_tau_us * (1.0 + float(tau_offset_frac))
                expected = (
                    f"tau deliberately {float(tau_offset_frac):+.0%} off the programmed "
                    "tau; contrast reduced/rotated"
                )
            cfg["ramsey_tau_us"] = tau_us
            cfg["mr_control_tau_offset_frac"] = tau_us / base_tau_us - 1.0
        elif name == "drive_detuned":
            det = float(detuning_mhz) if detuning_mhz is not None else float(base_cfg["df"])
            base_drive = (
                float(base_cfg["f_ge"]) - float(base_cfg["df"]) / 2.0
                if base_cfg.get("symmetric_ramsey", False)
                else float(base_cfg["f_ge"])
            )
            cfg["ramsey_drive_freq_mhz"] = base_drive + det
            cfg["max_drive_bandwidth_ratio"] = 1e12
            cfg["mr_control_detuning_mhz"] = det
            if base_cfg.get("use_active_reset", False):
                # The reset pi plays at the (detuned) drive: branch detunings f_branch - f_drive.
                upper_det = float(base_cfg["f_ge"]) - cfg["ramsey_drive_freq_mhz"]
                reset_transfer = min(
                    predict_pi_transfer(base_cfg["sigma"], upper_det),
                    predict_pi_transfer(base_cfg["sigma"], upper_det - float(base_cfg["df"])),
                )
            expected = (
                f"drive detuned {det:+.4f} MHz: a common phase "
                f"{2.0 * det * base_tau_us:.2f} pi (odd: mapping inverted, even: unchanged)"
            )
        elif name == "drive_off":
            cfg["pi2_gain"] = 0
            expected = "no Ramsey drive; readout baseline only"

        plan = _plan_for_cfg(cfg)
        predicted = plan["predicted_mapping"]
        if name == "drive_off" and predicted is not None:
            # pi2_gain = 0: no rotation, both branches stay in |g>.
            predicted = {"p_e_upper": 0.0, "p_e_lower": 0.0, "contrast": 0.0}
        null_valid, null_reason, residual_ratio = None, "", float("nan")
        inverted_expected, inverted_reason, signed_ratio = None, "", float("nan")
        if (
            name in ("echo_null", "tau_offset")
            and predicted is not None
            and base_predicted is not None
        ):
            main_contrast = base_predicted["contrast"]
            if main_contrast > 0:
                residual_ratio = predicted["contrast"] / main_contrast
            else:
                residual_ratio = float("inf") if predicted["contrast"] > 0 else 0.0
            null_valid = bool(residual_ratio <= ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO)
            if not null_valid:
                null_reason = (
                    f"not a null at these settings: predicted residual contrast "
                    f"{predicted['contrast']:.3f} is {residual_ratio:.2f}x the parity run's "
                    f"{main_contrast:.3f} (limit {ECHO_NULL_MAX_PREDICTED_RESIDUAL_RATIO:g}x); "
                    + (
                        "the detuned echo pi is itself parity-dependent, shorten sigma"
                        if name == "echo_null"
                        else "the finite pulses leave the branches in different states at this tau"
                    )
                )
                expected = "NOT a null at these settings: " + (
                    "the echo keeps parity contrast"
                    if name == "echo_null"
                    else "this tau keeps parity contrast; informational"
                )
        if name == "drive_detuned" and predicted is not None and base_predicted is not None:
            main_signed = base_predicted["p_e_upper"] - base_predicted["p_e_lower"]
            if main_signed != 0:
                signed_ratio = (predicted["p_e_upper"] - predicted["p_e_lower"]) / main_signed
                inverted_expected = bool(signed_ratio <= -DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO)
                expected += f"; predicted contrast {signed_ratio:+.2f}x the parity run's: " + (
                    "inverted mapping at near-full contrast (a second flip control): "
                    "telegraph and rate unchanged, occupancy inverted"
                    if inverted_expected
                    else "not a clean inversion; informational"
                )
                if not inverted_expected:
                    inverted_reason = (
                        f"not predicted to invert the mapping at near-full contrast "
                        f"(predicted {signed_ratio:+.2f}x the parity run's, limit "
                        f"-{DRIVE_DETUNED_MIN_INVERTED_CONTRAST_RATIO:g}x)"
                    )
                elif (
                    reset_transfer is not None
                    and reset_transfer < DRIVE_DETUNED_MIN_RESET_PI_TRANSFER
                ):
                    inverted_expected = False
                    inverted_reason = (
                        f"the active-reset pi plays at the detuned drive and is predicted to "
                        f"flip the worse branch with only {reset_transfer:.3f} (limit "
                        f"{DRIVE_DETUNED_MIN_RESET_PI_TRANSFER:g}): inter-shot carryover could "
                        "change the rate/occupancy for reasons unrelated to parity"
                    )
                    expected += "; but the reset pi is off-resonant, so informational"
        skip = None
        if not plan["feasible"]:
            skip = "; ".join(plan["errors"])
            cfg = None
        if cfg is not None and predicted is not None:
            cfg["mr_predicted_p_e_upper"] = predicted["p_e_upper"]
            cfg["mr_predicted_p_e_lower"] = predicted["p_e_lower"]
            cfg["mr_predicted_contrast"] = predicted["contrast"]
            if null_valid is not None:
                cfg["mr_predicted_residual_ratio"] = residual_ratio
                cfg["mr_null_control_valid"] = null_valid
            if inverted_expected is not None:
                cfg["mr_predicted_contrast_ratio"] = signed_ratio
                cfg["mr_inverted_mapping_expected"] = inverted_expected
                if reset_transfer is not None:
                    cfg["mr_predicted_reset_pi_transfer"] = reset_transfer
        out.append(
            {
                "label": name,
                "control_type": name,
                "cfg": cfg,
                "skip_reason": skip,
                "expected": expected,
                "plan": plan,
                "predicted_mapping": predicted,
                "null_control_valid": null_valid,
                "null_invalid_reason": null_reason,
                "inverted_mapping_expected": inverted_expected,
                "inverted_mapping_reason": inverted_reason,
            }
        )
    return out


def predicted_mapping_seed(cfg, fallback=(0.1, 0.9)):
    """(p_e_state0, p_e_state1, source) seeding the HMM mapping fit of a record acquired
    with cfg: the predicted P(e) of its two branches (plan_parity_mapping) in ascending
    order, so state1 is the branch with the larger P(e), the label convention of the
    (0.1, 0.9) default; source "predicted". The fallback (source "fallback: <why>") when
    the plan is infeasible or raises, or the predicted contrast is below
    MAPPING_SEED_MIN_PREDICTED_CONTRAST."""
    try:
        predicted = _plan_for_cfg(cfg)["predicted_mapping"]
    except (KeyError, TypeError, ValueError) as exc:
        return float(fallback[0]), float(fallback[1]), f"fallback: no prediction ({exc})"
    if predicted is None:
        return float(fallback[0]), float(fallback[1]), "fallback: infeasible plan"
    if predicted["contrast"] < MAPPING_SEED_MIN_PREDICTED_CONTRAST:
        return (
            float(fallback[0]),
            float(fallback[1]),
            f"fallback: predicted contrast {predicted['contrast']:.3f} < "
            f"{MAPPING_SEED_MIN_PREDICTED_CONTRAST:g}",
        )
    lo, hi = sorted((float(predicted["p_e_upper"]), float(predicted["p_e_lower"])))
    return lo, hi, "predicted"


class ModifiedRamseyProgram(ActiveResetMixin, RepPeriodMixin, AveragerProgram):
    """Fixed-tau Ramsey for charge parity: [active reset] -> pi/2 -> tau -> pi/2(final
    phase) -> readout; echo: pi/2 -> tau/2 -> pi -> tau/2 -> pi/2. tau is the total
    centre-to-centre interval; cfg reference in docs/experiments/modified_ramsey.md."""

    def initialize(self):
        cfg = self.cfg

        if cfg["df"] <= 0:
            raise ValueError("cfg['df'] must be positive")
        if cfg["sigma"] <= 0:
            raise ValueError("cfg['sigma'] must be positive")
        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        for delay_key in ("adc_trig_offset", "mr_relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")
        if int(cfg.get("rounds", 1)) != 1:
            raise ValueError(
                f"cfg['rounds']={cfg.get('rounds')} is not supported: the "
                "shot buffer keeps only the final round, so earlier rounds "
                "would be silently dropped from the parity record. Use "
                "rounds=1 and increase cfg['reps']."
            )
        if cfg.get("flattop_length") is not None:
            raise ValueError(
                "ModifiedRamseyProgram plays gaussian 'arb' qubit pulses only, "
                "but cfg['flattop_length'] is set "
                f"({cfg['flattop_length']}). The pi/pi2 gains for a flat_top "
                "pulse do not transfer to a gaussian. Set flattop_length=None "
                "and supply arb-calibrated gains."
            )

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3

        self.configure_active_reset()

        self.tau_us = float(cfg.get("ramsey_tau_us", 1.0 / (2.0 * cfg["df"])))
        self.use_pi_pulse = cfg.get("use_pi_pulse", False)
        if self.use_pi_pulse:
            print(
                "[ModifiedRamsey] WARNING: use_pi_pulse=True inserts a Hahn "
                "echo, which refocuses the static parity detuning df. This is "
                "a NULL/CONTROL sequence -- it has zero parity contrast only "
                "for pulses short against 1/df (predict_parity_mapping gives "
                "the contrast it keeps). Do not interpret its output as a "
                "parity trace."
            )

        # f_ge is the UPPER branch; symmetric drives the midpoint f_ge - df/2.
        self.symmetric_ramsey = cfg.get("symmetric_ramsey", False)
        default_drive = cfg["f_ge"] - cfg["df"] / 2.0 if self.symmetric_ramsey else cfg["f_ge"]
        self.drive_freq_mhz = float(cfg.get("ramsey_drive_freq_mhz", default_drive))

        base_pi2_phase_deg = 90 if self.symmetric_ramsey else 180
        flip_offset_deg = 180 if cfg.get("flip_final_pi2", False) else 0
        self.final_pi2_phase_deg = (base_pi2_phase_deg + flip_offset_deg) % 360

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        cover_readout_window(self, cfg)

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        # Every qubit pulse, the reset pi included, plays at the drive frequency.
        self.f_ge_reg = self.freq2reg(self.drive_freq_mhz, gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.pulse_us = float(self.cycles2us(self.pulse_qubit_length, gen_ch=cfg["qubit_ch"]))

        # Waits run between pulse edges, tau is centre-to-centre (docs/experiments/modified_ramsey.md).
        n_gaps = 2 if self.use_pi_pulse else 1
        total_pulse_span_us = n_gaps * self.pulse_us
        wait_us = (self.tau_us - total_pulse_span_us) / n_gaps
        if wait_us <= 0:
            df_max = 1.0 / (2.0 * n_gaps * self.pulse_us)
            raise ValueError(
                f"programmed tau={self.tau_us:.4f} us (physical "
                f"df={cfg['df']} MHz), but "
                f"the {'three' if self.use_pi_pulse else 'two'} qubit pulses "
                f"already span {total_pulse_span_us:.4f} us "
                f"(4*sigma = {self.pulse_us:.4f} us each). The parity phase "
                f"condition is unreachable. At sigma={cfg['sigma']} us the "
                f"largest usable peak separation is df < {df_max:.4f} MHz; "
                f"either shorten cfg['sigma'] (df_max scales as 1/(8*sigma)) or "
                "cap the accepted doublet separation via "
                "ModifiedRamsey_params['max_sep_MHz']."
            )
        self.wait_us = wait_us
        self.wait_cycles = self.us2cycles(wait_us)
        self.effective_tau_us = float(n_gaps * (self.cycles2us(self.wait_cycles) + self.pulse_us))
        self.regwi(self.q_rp, self.r_wait, self.wait_cycles)

        # Drive-bandwidth gate: docs/experiments/modified_ramsey.md (Drive bandwidth).
        rabi_pi2_mhz = 0.0997 / cfg["sigma"]
        branch_upper = float(cfg["f_ge"])
        branch_lower = branch_upper - float(cfg["df"])
        branch_detuning_mhz = max(
            abs(self.drive_freq_mhz - branch_upper), abs(self.drive_freq_mhz - branch_lower)
        )
        self.drive_bandwidth_ratio = float(branch_detuning_mhz / rabi_pi2_mhz)
        max_bw_ratio = float(cfg.get("max_drive_bandwidth_ratio", 1.0))
        if self.drive_bandwidth_ratio > max_bw_ratio:
            raise ValueError(
                f"branch detuning {branch_detuning_mhz:.4f} MHz is "
                f"{self.drive_bandwidth_ratio:.2f}x the pi/2 Rabi rate "
                f"({rabi_pi2_mhz:.4f} MHz at sigma={cfg['sigma']} us), above "
                f"the max_drive_bandwidth_ratio={max_bw_ratio:g} limit: the "
                "off-resonant parity branch cannot be rotated and the "
                "parity -> state mapping is unrealizable. Shorten sigma"
                + (
                    ""
                    if self.symmetric_ramsey
                    else ", set symmetric_ramsey=True (halves the detuning),"
                )
                + " or raise cfg['max_drive_bandwidth_ratio'] deliberately."
            )
        if self.drive_bandwidth_ratio > 0.2:
            print(
                f"[ModifiedRamsey] WARNING: branch detuning "
                f"{branch_detuning_mhz:.4f} MHz is {self.drive_bandwidth_ratio:.2f}x "
                f"the pi/2 Rabi rate ({rabi_pi2_mhz:.4f} MHz at sigma="
                f"{cfg['sigma']} us). The off-resonant branch will be "
                "under-rotated. Shorten sigma or set symmetric_ramsey=True."
            )

        # One envelope shared by pi and pi/2: two copies can overflow the 65536-sample
        # envelope memory (docs/architecture.md#generators-and-registers).
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        self.load_reset_threshold()

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        cfg = self.cfg

        if self.use_active_reset:
            self.active_reset_to_g()

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit",
        )
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.use_pi_pulse:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit",
            )
            self.pulse(ch=cfg["qubit_ch"])

            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=self.deg2reg(self.final_pi2_phase_deg, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_gain"],
            waveform="qubit",
        )
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # mr_relax_delay, not the shared relax_delay (docs/experiments/modified_ramsey.md).
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(cfg.get("mr_relax_delay", 0.0)),
        )

    def acquire(
        self,
        soc,
        threshold=None,
        angle=None,
        load_pulses=True,
        readouts_per_experiment=None,
        save_experiments=None,
        start_src="internal",
        progress=False,
    ):
        self.reads_per_rep = self.reset_cycles + 1
        if readouts_per_experiment is not None and readouts_per_experiment != self.reads_per_rep:
            raise ValueError(
                "readouts_per_experiment must equal reset_cycles + 1 "
                f"({self.reads_per_rep}) for ModifiedRamseyProgram"
            )
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress,
            threshold=threshold,
            angle=angle,
            save_experiments=save_experiments,
        )
        return self.collect_shots()

    def collect_shots(self):
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", 1)
        # Read ii of each rep is di_buf[ch][ii::reads_per_rep]; the Ramsey read is last.
        final = reads_per_rep - 1
        shots_i = self.di_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        shots_q = self.dq_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        return shots_i, shots_q

    def collect_reset_shots(self):
        """Reset readouts as (reset_cycles, reps) I and Q in collect_shots() units; row k
        precedes flip k (docs/experiments/active_reset.md#reset-readout-k-is-taken-before-flip-k)."""
        n_cycles = self.reset_cycles
        reps = self.cfg["reps"]
        if not n_cycles:
            return (np.zeros((0, reps)), np.zeros((0, reps)))
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", n_cycles + 1)
        reset_i = np.stack(
            [self.di_buf[0][k::reads_per_rep][:reps] / norm for k in range(n_cycles)]
        )
        reset_q = np.stack(
            [self.dq_buf[0][k::reads_per_rep][:reps] / norm for k in range(n_cycles)]
        )
        return reset_i, reset_q


class ModifiedRamsey(ExperimentClass):
    """Repeated fixed-tau Ramsey record for charge-parity switching time series."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, debug=False):
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True, progress=progress)

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()
        reset_i, reset_q = prog.collect_reset_shots()

        # Streamer stats include polling/transfer latency: diagnostics only.
        streamer_elapsed_s = np.nan
        streamer_average_rep_period_us = np.nan
        if prog.stats:
            last_elapsed_s, last_shots, _, _ = prog.stats[-1]
            streamer_elapsed_s = float(last_elapsed_s)
            if last_shots:
                streamer_average_rep_period_us = streamer_elapsed_s * 1e6 / float(last_shots)

        # The time base is the emitted schedule, active-reset overhead included.
        rep_period_us = float(prog.scheduled_rep_period_us())
        n_shots = shots_i.size
        shot_index = np.arange(n_shots)
        shot_time_us = shot_index * rep_period_us

        ro_ch = self.cfg["ro_chs"][0]
        readout_window_us = float(
            prog.readout_window_cycles[ro_ch] / float(self.soccfg["readouts"][ro_ch]["f_output"])
        )
        symmetric = self.cfg.get("symmetric_ramsey", False)
        use_reset = self.cfg.get("use_active_reset", False)
        control_type = self.cfg.get("mr_control_type", "parity")

        data = {
            "config": self.cfg,
            "data": {
                "shots_i": shots_i,
                "shots_q": shots_q,
                "shot_index": shot_index,
                "shot_time_us": shot_time_us,
                "scheduled_rep_period_us": rep_period_us,
                "gap_indices": np.zeros(0, dtype=int),
                "tau_us": float(prog.tau_us),
                "effective_tau_us": float(prog.effective_tau_us),
                "wait_us": float(prog.wait_us),
                "qubit_pulse_us": float(prog.pulse_us),
                "sigma_us": float(self.cfg["sigma"]),
                "drive_bandwidth_ratio": float(prog.drive_bandwidth_ratio),
                "f_ge": self.cfg["f_ge"],
                "f_branch_upper": self.cfg["f_ge"],
                "f_branch_lower": self.cfg["f_ge"] - self.cfg["df"],
                "df": self.cfg["df"],
                "drive_freq": float(prog.drive_freq_mhz),
                "pi2_gain": self.cfg["pi2_gain"],
                "pi_gain": self.cfg.get("pi_gain", np.nan),
                "first_pi2_phase_deg": 0.0,
                "final_pi2_phase_deg": float(prog.final_pi2_phase_deg),
                "use_pi_pulse": self.cfg.get("use_pi_pulse", False),
                "flip_final_pi2": self.cfg.get("flip_final_pi2", False),
                "symmetric_ramsey": symmetric,
                "mr_control_type_code": MR_CONTROL_TYPE_CODES.get(control_type, -1),
                "read_pulse_freq": self.cfg["pulse_freq"],
                "read_pulse_gain": self.cfg["pulse_gain"],
                "res_phase": self.cfg["res_phase"],
                "readout_length_us": self.cfg["readout_length"],
                "readout_window_us": readout_window_us,
                "adc_trig_offset_us": self.cfg["adc_trig_offset"],
                "mr_relax_delay_us": self.cfg.get("mr_relax_delay", 0.0),
                "use_active_reset": use_reset,
                "reset_cycles": (int(self.cfg.get("reset_cycles", 1)) if use_reset else 0),
                "reset_shots_i": reset_i,
                "reset_shots_q": reset_q,
                "readout_threshold": self.cfg.get("readout_threshold", np.nan)
                if use_reset
                else np.nan,
                "reset_ground_below_threshold": self.cfg.get("reset_ground_below_threshold", True),
                "reset_readout_relax_delay_us": self.cfg.get("reset_readout_relax_delay", 1.0)
                if use_reset
                else 0.0,
                "post_reset_wait_us": self.cfg.get("post_reset_wait", 0.0) if use_reset else 0.0,
                "streamer_elapsed_s": streamer_elapsed_s,
                "streamer_average_rep_period_us": streamer_average_rep_period_us,
            },
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        shots_i = np.asarray(data["data"]["shots_i"])
        shots_q = np.asarray(data["data"]["shots_q"])
        tau_us = data["data"]["tau_us"]
        eff_tau_us = data["data"].get("effective_tau_us", tau_us)
        wait_us = data["data"]["wait_us"]
        df = data["data"]["df"]
        use_pi_pulse = data["data"].get("use_pi_pulse", False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        seq_label = "echo pi" if use_pi_pulse else "no pi"

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, ".", alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis("equal")
        plt.title(
            self.titlename
            + f"\n{seq_label}, tau={tau_us:.4f} us (realized {eff_tau_us:.4f} us),"
            + f" gap={wait_us:.4f} us, df={df:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "_IQ.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


def modified_ramsey_timing(soccfg, cfg):
    """Model of ModifiedRamseyProgram's per-rep schedule (excludes initialize(), tProc
    latency, transfer and Python overhead); docs/experiments/modified_ramsey.md#timing-ledger."""
    res_ch = cfg["res_ch"]
    qubit_ch = cfg["qubit_ch"]
    ro_chs = cfg["ro_chs"]

    if not ro_chs:
        raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
    if cfg["df"] <= 0:
        raise ValueError("cfg['df'] must be positive")
    if cfg["sigma"] <= 0:
        raise ValueError("cfg['sigma'] must be positive")
    if cfg["readout_length"] <= 0:
        raise ValueError("cfg['readout_length'] must be positive")
    delay_keys = ["adc_trig_offset", "mr_relax_delay"]
    if cfg.get("use_active_reset", False):
        delay_keys.extend(["reset_readout_relax_delay", "post_reset_wait"])
    for delay_key in delay_keys:
        if cfg.get(delay_key, 0.0) < 0:
            raise ValueError(f"cfg['{delay_key}'] must be non-negative")

    f_time = float(soccfg["tprocs"][0]["f_time"])
    res_f_fabric = float(soccfg["gens"][res_ch]["f_fabric"])
    qubit_f_fabric = float(soccfg["gens"][qubit_ch]["f_fabric"])

    # Native cycles -> tProc cycles, truncated by sync_all() (docs/architecture.md#timing).
    requested_tone_native_cycles = soccfg.us2cycles(cfg["length"], gen_ch=res_ch)
    adc_offset_tproc_cycles = soccfg.us2cycles(cfg["adc_trig_offset"])
    window_native_cycles_by_ch = {
        int(ch): soccfg.us2cycles(cfg["readout_length"], ro_ch=ch) for ch in ro_chs
    }
    adc_end_tproc_by_ch = {
        int(ch): (
            adc_offset_tproc_cycles
            + window_native_cycles_by_ch[int(ch)]
            * f_time
            / float(soccfg["readouts"][ch]["f_output"])
        )
        for ch in ro_chs
    }
    adc_window_end_tproc = max(adc_end_tproc_by_ch.values())
    required_tone_native_cycles = int(np.ceil(adc_window_end_tproc * res_f_fabric / f_time - 1e-12))
    tone_native_cycles = max(requested_tone_native_cycles, required_tone_native_cycles)
    tone_extension_native_cycles = tone_native_cycles - requested_tone_native_cycles
    tone_end_tproc = tone_native_cycles * f_time / res_f_fabric
    readout_slot_tproc_cycles = int(max(tone_end_tproc, adc_window_end_tproc))

    qubit_native_cycles = soccfg.us2cycles(cfg["sigma"] * 4, gen_ch=qubit_ch)
    qubit_end_tproc = qubit_native_cycles * f_time / qubit_f_fabric
    qubit_pulse_tproc_cycles = int(qubit_end_tproc)
    use_pi_pulse = bool(cfg.get("use_pi_pulse", False))
    ramsey_pulse_count = 3 if use_pi_pulse else 2
    # Centre-to-centre tau, edge-to-edge gap: gap = tau/n_gaps - 4*sigma.
    tau_us = float(cfg.get("ramsey_tau_us", 1.0 / (2.0 * cfg["df"])))
    qubit_pulse_us = float(qubit_native_cycles / qubit_f_fabric)
    wait_count = 2 if use_pi_pulse else 1
    wait_request_us = tau_us / wait_count - qubit_pulse_us
    if wait_request_us <= 0:
        raise ValueError(
            f"cfg['df']={cfg['df']} MHz needs tau={tau_us:.4f} us, but the "
            f"qubit pulses span {wait_count * qubit_pulse_us:.4f} us "
            f"(4*sigma = {qubit_pulse_us:.4f} us each). Shorten cfg['sigma'] "
            "or work at a smaller peak separation."
        )
    wait_cycles_each = soccfg.us2cycles(wait_request_us)
    wait_tproc_cycles = wait_count * wait_cycles_each
    effective_tau_us = float(wait_count * (wait_cycles_each / f_time + qubit_pulse_us))
    final_padding_tproc_cycles = soccfg.us2cycles(0.05)
    mr_relax_tproc_cycles = soccfg.us2cycles(cfg.get("mr_relax_delay", 0.0))

    reset_cycles = int(cfg.get("reset_cycles", 1)) if cfg.get("use_active_reset", False) else 0
    if reset_cycles < 0:
        raise ValueError("cfg['reset_cycles'] must be non-negative")
    reset_delay_tproc_cycles = (
        soccfg.us2cycles(cfg.get("reset_readout_relax_delay", 1.0)) if reset_cycles else 0
    )
    post_reset_wait_tproc_cycles = (
        soccfg.us2cycles(cfg.get("post_reset_wait", 0.0)) if reset_cycles else 0
    )

    ramsey_sequence_tproc_cycles = (
        ramsey_pulse_count * qubit_pulse_tproc_cycles
        + wait_tproc_cycles
        + final_padding_tproc_cycles
        + readout_slot_tproc_cycles
        + mr_relax_tproc_cycles
    )
    reset_block_tproc_cycles = (
        # The conditional pi is reserved on both branches (docs/experiments/active_reset.md).
        reset_cycles
        * (readout_slot_tproc_cycles + reset_delay_tproc_cycles + qubit_pulse_tproc_cycles)
        + post_reset_wait_tproc_cycles
    )
    scheduled_rep_period_tproc_cycles = ramsey_sequence_tproc_cycles + reset_block_tproc_cycles

    to_us = lambda cycles: float(cycles / f_time)
    tone_us = float(tone_end_tproc / f_time)
    adc_offset_us = to_us(adc_offset_tproc_cycles)
    window_us_by_ch = {
        int(ch): float(
            window_native_cycles_by_ch[int(ch)] / float(soccfg["readouts"][ch]["f_output"])
        )
        for ch in ro_chs
    }

    return {
        "scheduled_rep_period_us": to_us(scheduled_rep_period_tproc_cycles),
        "scheduled_rep_period_tproc_cycles": int(scheduled_rep_period_tproc_cycles),
        "ramsey_sequence_us": to_us(ramsey_sequence_tproc_cycles),
        "reset_block_us": to_us(reset_block_tproc_cycles),
        "readout_slot_us": to_us(readout_slot_tproc_cycles),
        "readout_slot_tproc_cycles": int(readout_slot_tproc_cycles),
        "resonator_tone_us": tone_us,
        "requested_resonator_tone_us": float(requested_tone_native_cycles / res_f_fabric),
        "tone_quantization_extension_cycles": int(tone_extension_native_cycles),
        "adc_offset_us": adc_offset_us,
        "max_readout_window_us": float(max(window_us_by_ch.values())),
        "tone_coverage_margin_us": float((tone_end_tproc - adc_window_end_tproc) / f_time),
        "qubit_pulse_us": to_us(qubit_pulse_tproc_cycles),
        "ramsey_qubit_pulse_count": int(ramsey_pulse_count),
        "ramsey_wait_us": to_us(wait_tproc_cycles),
        "requested_tau_us": float(tau_us),
        "effective_tau_us": effective_tau_us,
        "ramsey_gap_per_wait_us": float(wait_cycles_each / f_time),
        "final_padding_us": to_us(final_padding_tproc_cycles),
        "mr_relax_delay_us": to_us(mr_relax_tproc_cycles),
        "reset_cycles": int(reset_cycles),
        "reset_readout_relax_delay_us": to_us(reset_delay_tproc_cycles),
        "post_reset_wait_us": to_us(post_reset_wait_tproc_cycles),
        "f_time_mhz": f_time,
        "res_f_fabric_mhz": res_f_fabric,
        "qubit_f_fabric_mhz": qubit_f_fabric,
        "ro_f_output_mhz": {int(ch): float(soccfg["readouts"][ch]["f_output"]) for ch in ro_chs},
    }
