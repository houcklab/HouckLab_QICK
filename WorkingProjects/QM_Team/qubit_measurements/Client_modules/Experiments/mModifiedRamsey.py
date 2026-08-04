from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


# Numeric codes for the control state saved into the (numeric-only) h5 data.
# The string itself lives in cfg["mr_control_type"], persisted via save_config.
MR_CONTROL_TYPE_CODES = {
    "parity": 0,           # parity-sensing run (no control modification)
    "flip_final_pi2": 1,   # mapping inversion: parity signal must reverse
    "echo_null": 2,        # Hahn-echo null: parity contrast must vanish
    "tau_offset": 3,       # deliberately wrong tau: reduced contrast expected
    "drive_detuned": 4,    # qubit drive detuned off both branches
    "drive_off": 5,        # pi/2 pulses disabled (readout-only trace)
}


def plan_parity_mapping(df_mhz, sigma_us, use_pi_pulse=False,
                        symmetric_ramsey=False, flip_final_pi2=False,
                        max_bandwidth_ratio=1.0):
    """
    Hardware-free feasibility check of the parity -> state mapping.

    Mirrors the timing/bandwidth math of ModifiedRamseyProgram.initialize()
    with NOMINAL (un-quantized) 4*sigma envelopes, so it can run without a
    soccfg. The realized values after clock quantization are reported by the
    program itself (effective_tau_us); verify_ModifiedRamsey_timing.py checks
    the two agree on real clock domains.

    Conventions (tested in test_ModifiedRamseyParity_offline.py):
      tau = 1/(2*df)                       (pulse-CENTRE-to-CENTRE)
      gap = tau - 4*sigma                  (no pi)
      gap = (tau - 8*sigma)/2 per gap      (echo)
      final pi/2 base phase = 180 deg (standard) / 90 deg (symmetric),
      +180 deg when flip_final_pi2.

    Returns dict:
      feasible          : bool -- envelopes fit inside tau AND bandwidth ratio
                          is below max_bandwidth_ratio
      errors, warnings  : lists of str (errors => infeasible)
      tau_us, pulse_us, n_gaps, gap_us, df_max_mhz
      rabi_pi2_mhz, branch_detuning_mhz, bandwidth_ratio
      recommend_symmetric : True when the standard scheme is bandwidth-marginal
                          and symmetric drive would halve the branch detuning
      drive_freq_offset_mhz : add to f_ge to get the drive frequency
      final_pi2_phase_deg
    """
    errors, warnings = [], []
    if df_mhz <= 0:
        raise ValueError("df_mhz must be positive")
    if sigma_us <= 0:
        raise ValueError("sigma_us must be positive")

    tau_us = 1.0 / (2.0 * df_mhz)
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
    branch_detuning_mhz = df_mhz / 2.0 if symmetric_ramsey else df_mhz
    bandwidth_ratio = branch_detuning_mhz / rabi_pi2_mhz
    recommend_symmetric = (not symmetric_ramsey) and bandwidth_ratio > 0.2
    if bandwidth_ratio > max_bandwidth_ratio:
        errors.append(
            f"branch detuning {branch_detuning_mhz:.4f} MHz is "
            f"{bandwidth_ratio:.2f}x the pi/2 Rabi rate "
            f"({rabi_pi2_mhz:.4f} MHz): the off-resonant branch cannot be "
            "rotated; shorten sigma"
            + ("" if symmetric_ramsey else " or set symmetric_ramsey=True")
        )
    elif bandwidth_ratio > 0.2:
        warnings.append(
            f"branch detuning is {bandwidth_ratio:.2f}x the pi/2 Rabi rate; "
            "the off-resonant branch will be under-rotated"
            + (" -- symmetric_ramsey=True would halve the detuning"
               if recommend_symmetric else "")
        )
    if use_pi_pulse:
        warnings.append(
            "use_pi_pulse=True is a Hahn-echo NULL control: it refocuses the "
            "static parity detuning and should suppress the parity signal"
        )

    base = 90 if symmetric_ramsey else 180
    final_phase = (base + (180 if flip_final_pi2 else 0)) % 360
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
        "drive_freq_offset_mhz": (-df_mhz / 2.0 if symmetric_ramsey else 0.0),
        "final_pi2_phase_deg": final_phase,
    }


def build_control_variants(base_cfg,
                           include=("parity", "flip_final_pi2", "echo_null",
                                    "tau_offset", "drive_detuned",
                                    "drive_off"),
                           tau_offset_frac=0.25, detuning_mhz=None):
    """
    Build the cfg dicts for the parity run plus its validation controls.

    Pure function (no hardware): each entry copies base_cfg, applies the
    control modification, stamps cfg["mr_control_type"], and pre-validates
    feasibility with plan_parity_mapping. Infeasible variants are returned
    with cfg=None and a reason instead of raising, so a control suite can
    skip them explicitly rather than crash mid-run.

    Controls and their expected signatures:
      parity          : the measurement itself
      flip_final_pi2  : parity -> state mapping inverts; telegraph amplitude
                        and rates must be unchanged
      echo_null       : pi pulse refocuses the static parity detuning ->
                        parity contrast suppressed
      tau_offset      : tau scaled by (1 + tau_offset_frac) via df ->
                        df/(1+frac); mapping rotation is off the pi condition,
                        contrast reduced by ~cos(pi*(1+frac))... i.e. sign and
                        amplitude change predictably
      drive_detuned   : f_ge shifted by detuning_mhz (default +df, one full
                        branch spacing): both branches off-resonant, mapping
                        degraded
      drive_off       : pi2_gain = 0; readout-only record measuring the
                        readout/thermal baseline (no parity information)

    Returns list of dicts: {"label", "control_type", "cfg" (or None),
    "skip_reason" (or None), "expected", "plan"}.
    """
    out = []
    for name in include:
        if name not in MR_CONTROL_TYPE_CODES:
            raise ValueError(f"unknown control type {name!r}")
        cfg = dict(base_cfg)
        cfg["mr_control_type"] = name
        expected = ""
        if name == "parity":
            expected = "telegraph parity signal at tau = 1/(2 df)"
        elif name == "flip_final_pi2":
            cfg["flip_final_pi2"] = True
            expected = "parity->state mapping inverted; same rates/amplitude"
        elif name == "echo_null":
            cfg["use_pi_pulse"] = True
            expected = "parity contrast suppressed (echo refocuses df)"
        elif name == "tau_offset":
            cfg["df"] = float(base_cfg["df"]) / (1.0 + float(tau_offset_frac))
            cfg["mr_control_tau_offset_frac"] = float(tau_offset_frac)
            expected = (f"tau deliberately {tau_offset_frac:+.0%} off the pi "
                        "condition; contrast reduced/rotated")
        elif name == "drive_detuned":
            det = float(detuning_mhz) if detuning_mhz is not None \
                else float(base_cfg["df"])
            cfg["f_ge"] = float(base_cfg["f_ge"]) + det
            cfg["mr_control_detuning_mhz"] = det
            expected = f"drive detuned {det:+.4f} MHz; mapping degraded"
        elif name == "drive_off":
            cfg["pi2_gain"] = 0
            expected = "no Ramsey drive; readout baseline only"

        plan = plan_parity_mapping(
            cfg["df"], cfg["sigma"],
            use_pi_pulse=cfg.get("use_pi_pulse", False),
            symmetric_ramsey=cfg.get("symmetric_ramsey", False),
            flip_final_pi2=cfg.get("flip_final_pi2", False),
        )
        skip = None
        if not plan["feasible"]:
            skip = "; ".join(plan["errors"])
            cfg = None
        out.append({"label": name, "control_type": name, "cfg": cfg,
                    "skip_reason": skip, "expected": expected, "plan": plan})
    return out


class ModifiedRamseyProgram(AveragerProgram):
    """
    Fixed-tau Ramsey for charge-parity switching detection.

    Each shot optionally begins with hardware active reset to |g> (real
    measurement feedback: measure -> read accumulated I -> conditionally
    apply a pi pulse only if the qubit was found in |e>). After reset the
    qubit is deterministically in |g>, which is the correct starting state
    for the Ramsey sequence below.

    No-pi sequence:
        [active reset to |g>] -> pi/2 -> wait tau -> pi/2(final_phase) -> readout

    Echo/pi sequence:
        [active reset to |g>] -> pi/2 -> wait tau/2 -> pi -> wait tau/2 -> pi/2(final_phase) -> readout

    tau = 1 / (2 * cfg["df"]), df in MHz => tau in us. (Same tau in both the
    standard and symmetric-drive schemes; the |relative phase| between branches
    is pi either way.)

    TIMING CONVENTION: tau is the pulse-CENTRE-to-pulse-CENTRE precession
    interval. QICK schedules waits between pulse EDGES, so the gap written into
    r_wait is tau - 4*sigma (no pi) or (tau - 8*sigma)/2 per gap (echo). If the
    pulses no longer fit inside tau, initialize() raises rather than silently
    running at the wrong effective tau. The realized value is reported as
    data['effective_tau_us'] next to the requested data['tau_us'].

    cfg["use_pi_pulse"]: if True, inserts a pi pulse in the middle. NOTE this
                         makes the sequence a Hahn echo, which REFOCUSES the
                         static parity detuning df -- i.e. it deliberately
                         destroys the parity signal. Use it only as a
                         negative control; initialize() prints a warning.

    cfg["symmetric_ramsey"]: selects the drive frequency and the closing-pi/2 base
                          phase.
        False (default): STANDARD scheme. Drive on-resonant with the upper parity
            peak (cfg["f_ge"]). Closing pi/2 base phase 180 deg.
            on-resonant (upper) -> |g>,   off-resonant (lower) -> |e>.
        True:            SYMMETRIC-DRIVE scheme. Drive at the midpoint
            f_avg = (f_lower + f_upper)/2 = cfg["f_ge"] - cfg["df"]/2. The two
            branches are symmetrically detuned by +/- df/2 and rotate +/- 90 deg
            during tau. Closing pi/2 base phase 90 deg.
            f_upper -> |e>,   f_lower -> |g>.

    cfg["flip_final_pi2"]: adds 180 deg to the closing-pi/2 phase (sign-flips the
                           second pulse), which swaps the parity -> state mapping
                           in EITHER scheme (standard 180<->0, symmetric 90<->270).
    cfg["pi_gain"]     : DAC gain for the pi pulse, required if use_pi_pulse=True
                         or if use_active_reset=True (same pi pulse is reused
                         for the reset corrective flip).
    cfg["mr_relax_delay"]:
                         optional inter-shot delay in us after the final Ramsey
                         readout (default 0). This is deliberately separate from
                         cfg["relax_delay"], which the surrounding runner uses
                         for its two-tone spectroscopy search.

    Active-reset config:
    cfg["use_active_reset"]    : if True, prepend active reset to |g> to every
                                 shot. Default False (opt-in), which preserves the
                                 old behaviour (rely on thermal/measurement reset).
    cfg["readout_threshold"]   : single-shot I discrimination threshold, in the
                                 SAME normalized units as collect_shots()/the IQ
                                 plot (i.e. accumulated I divided by the readout
                                 window length in cycles). Internally rescaled to
                                 the raw accumulator units the tProc compares.
                                 NOTE: the feedback thresholds on the raw in-phase
                                 (I) value only, so this requires the readout phase
                                 (res_phase) to be rotated such that |g> and |e>
                                 separate ALONG I. If your single-shot calibration
                                 discriminates along an arbitrary 2D separator
                                 line, rotate the readout first (or ask for the
                                 rotated-projection variant of the feedback).
    cfg["reset_ground_below_threshold"]:
                                 True (default) if |g> has I below threshold (and
                                 |e> above). Set False if your IQ blobs are flipped.
    cfg["reset_cycles"]        : number of measure->feedback rounds per shot
                                 (default 1). More rounds = better ground-state
                                 fidelity at the cost of extra readouts.
    cfg["reset_readout_relax_delay"]:
                                 syncdelay (us) after each reset readout before the
                                 conditional flip (default 1.0).
    cfg["post_reset_wait"]     : extra settle time (us) after the reset block,
                                 before the first Ramsey pi/2 (default 0.0).
    """

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
        # The per-shot IQ record comes from di_buf, which holds only the LAST
        # round's shots: rounds > 1 would silently discard all earlier rounds
        # from the parity time series. Scale reps instead.
        if int(cfg.get("rounds", 1)) != 1:
            raise ValueError(
                f"cfg['rounds']={cfg.get('rounds')} is not supported: the "
                "shot buffer keeps only the final round, so earlier rounds "
                "would be silently dropped from the parity record. Use "
                "rounds=1 and increase cfg['reps']."
            )
        # Every qubit pulse here is a plain 4*sigma gaussian ("arb"). A
        # flat_top-calibrated pi/pi2 gain would be silently replayed on the
        # wrong envelope, so refuse rather than mis-rotate.
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

        # Free user registers on the qubit page. Pulse registers are allocated
        # from the TOP of each page downwards (asm_v1.py:610-625: regs 22-31 on
        # a 1-manager page, 12-31 on a 2-manager page), and AveragerProgram's
        # loop counters (rjj=14, rcount=15) plus trigger()'s output word (16)
        # all live on page 0. Registers 3/4/5 are therefore free on any page.
        self.r_read = 4    # holds the accumulated I read back from the ADC
        self.r_thresh = 5  # holds the single-shot discrimination threshold

        self.use_active_reset = cfg.get("use_active_reset", False)
        self.reset_cycles = int(cfg.get("reset_cycles", 1)) if self.use_active_reset else 0
        if self.reset_cycles < 0:
            raise ValueError("cfg['reset_cycles'] must be non-negative")
        if self.use_active_reset:
            for delay_key in ("reset_readout_relax_delay", "post_reset_wait"):
                if cfg.get(delay_key, 0.0) < 0:
                    raise ValueError(f"cfg['{delay_key}'] must be non-negative")
        # condj jumps (skips the corrective pi) when the qubit is already in |g>.
        # If |g> sits below threshold in I, the "already ground" test is I < thresh.
        self.reset_skip_op = "<" if cfg.get("reset_ground_below_threshold", True) else ">"
        # Sign-safe comparison offset. ActiveResetVerify data on TATQ01/BFE
        # (2026-06-05/06) showed the corrective pi firing on every shot whose
        # accumulated I is NEGATIVE (the deployed tProc compares as if
        # unsigned, so negative two's-complement I reads as a huge positive).
        # Adding the same large positive constant to BOTH operands keeps them
        # strictly positive, so signed and unsigned comparison agree. The offset
        # is sized from the readout window in initialize() below (it must exceed
        # the largest |raw I| the accumulator can produce, not merely the
        # threshold), and defaults to 0 when active reset is off.
        self.cmp_offset = 0

        # Total parity-mapping evolution time. tau = 1/(2*df) for both schemes:
        # the |relative phase| accumulated between the two parity branches is pi.
        # NOTE: tau is the PULSE-CENTRE-TO-PULSE-CENTRE precession interval, not
        # the inter-pulse gap. The gap actually programmed into r_wait is derived
        # from it below, after the envelope length is known.
        self.tau_us = 1.0 / (2.0 * cfg["df"])
        self.use_pi_pulse = cfg.get("use_pi_pulse", False)
        if self.use_pi_pulse:
            # A Hahn echo refocuses STATIC detuning -- and the parity branch
            # splitting df IS a static detuning within a shot. The pi pulse
            # therefore cancels exactly the phase this measurement exists to
            # read out, so the echo branch has zero parity contrast by
            # construction. Keep it only as a negative control.
            print(
                "[ModifiedRamsey] WARNING: use_pi_pulse=True inserts a Hahn "
                "echo, which refocuses the static parity detuning df. This is "
                "a NULL/CONTROL sequence -- expect zero parity contrast. Do "
                "not interpret its output as a parity trace."
            )

        # symmetric_ramsey: drive at the midpoint f_avg = (f_lower + f_upper)/2
        # rather than on-resonant with the upper branch. cfg["f_ge"] is passed as
        # the upper peak, so f_avg = f_ge - df/2. Both branches are then detuned by
        # +/- df/2 and rotate +/- 90 deg during tau.
        self.symmetric_ramsey = cfg.get("symmetric_ramsey", False)
        self.drive_freq_mhz = (
            cfg["f_ge"] - cfg["df"] / 2.0 if self.symmetric_ramsey else cfg["f_ge"]
        )

        # Closing-pi/2 phase sets the parity -> computational-state mapping. Base
        # phase is 180 deg (standard, undoes the first pi/2) or 90 deg (symmetric).
        # flip_final_pi2 adds 180 deg, swapping the mapping in either scheme.
        base_pi2_phase_deg = 90 if self.symmetric_ramsey else 180
        flip_offset_deg = 180 if cfg.get("flip_final_pi2", False) else 0
        self.final_pi2_phase_deg = (base_pi2_phase_deg + flip_offset_deg) % 360

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        # The ADC trigger starts adc_trig_offset after the resonator pulse starts,
        # so the tone must cover offset + integration window. Keep all config
        # durations in us, then convert each register using its actual clock domain.
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(
            cfg["length"], gen_ch=cfg["res_ch"]
        )
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch)
            for ch in cfg["ro_chs"]
        }

        # Re-check coverage after every duration has been quantized on its own
        # hardware clock. Equality in user-space microseconds does not guarantee
        # equality after generator/readout/tProc rounding.
        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch]
            * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(
            adc_end_tproc * res_f_fabric / f_time - 1e-12
        ))
        # Cross-clock rounding can make length == offset + window a fraction of
        # a cycle short. Extend only by the exact number of resonator-generator
        # cycles needed to cover the quantized ADC window.
        self.readout_tone_cycles = max(
            requested_tone_cycles, required_tone_cycles
        )
        self.readout_tone_extension_cycles = (
            self.readout_tone_cycles - requested_tone_cycles
        )

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        f_res = self.freq2reg(
            cfg["pulse_freq"],
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0]
        )
        # All qubit pulses (reset pi, pi/2s, echo pi) play at the drive frequency:
        # cfg["f_ge"] in the standard scheme, the midpoint f_avg in symmetric_ramsey.
        self.f_ge_reg = self.freq2reg(self.drive_freq_mhz, gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(
            cfg["sigma"] * 4,
            gen_ch=cfg["qubit_ch"]
        )
        # Actual envelope duration after generator-clock quantization.
        self.pulse_us = float(
            self.cycles2us(self.pulse_qubit_length, gen_ch=cfg["qubit_ch"])
        )

        # ---- free-evolution gap -------------------------------------------
        # QICK schedules the gap BETWEEN pulse edges: sync_all() advances the
        # tProc reference to the END of the preceding envelope and the next
        # pulse(t='auto') starts at that reference (asm_v1.py:895-904, 938-960).
        # The parity phase, however, accrues over the pulse-CENTRE-to-CENTRE
        # interval, because the two branches precess through the (mostly
        # low-amplitude) envelope as well. Programming the raw tau as the gap
        # therefore overshoots the pi condition by one full envelope length
        # (4*sigma; 8*sigma with the echo), which silently kills contrast --
        # and does so worst exactly when the doublet is best resolved, since
        # larger df means smaller tau against a fixed 4*sigma.
        #
        # So: solve for the gap that puts the OUTER pi/2 centres tau apart.
        #   no pi : centres are  gap + 4*sigma  apart      -> gap = tau - 4*sigma
        #   echo  : centres are 2*gap + 8*sigma apart      -> gap = (tau - 8*sigma)/2
        # In both cases centre-to-centre = n_gaps * (gap + 4*sigma).
        n_gaps = 2 if self.use_pi_pulse else 1
        total_pulse_span_us = n_gaps * self.pulse_us
        wait_us = (self.tau_us - total_pulse_span_us) / n_gaps
        if wait_us <= 0:
            df_max = 1.0 / (2.0 * n_gaps * self.pulse_us)
            raise ValueError(
                f"cfg['df']={cfg['df']} MHz needs tau={self.tau_us:.4f} us, but "
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
        # Realized centre-to-centre interval after tProc-cycle quantization of
        # the gap. Saved alongside the requested tau so a run can be reinterpreted.
        self.wait_cycles = self.us2cycles(wait_us)
        self.effective_tau_us = float(
            n_gaps * (self.cycles2us(self.wait_cycles) + self.pulse_us)
        )
        self.regwi(self.q_rp, self.r_wait, self.wait_cycles)

        # The pi/2 pulses must be broadband enough to rotate BOTH parity
        # branches. A 4*sigma gaussian pi/2 has peak Rabi Omega0/2pi ~=
        # 0.0997/sigma MHz; if the branch detuning approaches that, the
        # off-resonant branch is under-rotated and contrast degrades on top of
        # any timing error. Standard scheme detunes one branch by df; the
        # symmetric scheme detunes both by df/2 (hence its bandwidth advantage).
        rabi_pi2_mhz = 0.0997 / cfg["sigma"]
        branch_detuning_mhz = (
            cfg["df"] / 2.0 if self.symmetric_ramsey else cfg["df"]
        )
        self.drive_bandwidth_ratio = float(branch_detuning_mhz / rabi_pi2_mhz)
        # Above max_drive_bandwidth_ratio the off-resonant branch is not
        # rotated at all -- the parity mapping is unrealizable, so FAIL rather
        # than run and produce a contrast-free record. Between 0.2 and the
        # limit, warn. The limit is overridable for deliberate experiments.
        max_bw_ratio = float(cfg.get("max_drive_bandwidth_ratio", 1.0))
        if self.drive_bandwidth_ratio > max_bw_ratio:
            raise ValueError(
                f"branch detuning {branch_detuning_mhz:.4f} MHz is "
                f"{self.drive_bandwidth_ratio:.2f}x the pi/2 Rabi rate "
                f"({rabi_pi2_mhz:.4f} MHz at sigma={cfg['sigma']} us), above "
                f"the max_drive_bandwidth_ratio={max_bw_ratio:g} limit: the "
                "off-resonant parity branch cannot be rotated and the "
                "parity -> state mapping is unrealizable. Shorten sigma"
                + ("" if self.symmetric_ramsey
                   else ", set symmetric_ramsey=True (halves the detuning),")
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

        # The pi and pi/2 pulses share the SAME gaussian envelope shape; they
        # differ only in DAC gain, which is set per-pulse below. Define ONE
        # waveform rather than two identical ones: each gaussian envelope is
        # sigma*4 long, and two full-size copies on the same generator would be
        # loaded at sequential addresses (0 and ~length), so their combined
        # footprint can exceed the 65536-sample envelope memory even when a
        # single copy fits. (With sigma=2 us each copy is ~55056 samples, so two
        # copies = ~110112 > 65536 -> "AxisSignalGen: buffer length must be
        # 65536 samples or less.") Sharing one envelope halves the footprint.
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles
        )

        if self.use_active_reset:
            if "readout_threshold" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['readout_threshold'] "
                    "(single-shot I threshold, normalized units)."
                )
            if "pi_gain" not in cfg:
                raise KeyError(
                    "use_active_reset=True requires cfg['pi_gain'] for the "
                    "corrective reset flip."
                )
            # collect_shots() divides the accumulated I by the readout-window
            # length, so the threshold the user reads off the IQ plot is in those
            # normalized units. The tProc compares the RAW accumulator, so scale
            # the threshold back up by the same window length here.
            ro_norm = self.readout_window_cycles[cfg["ro_chs"][0]]
            raw_threshold = int(round(cfg["readout_threshold"] * ro_norm))

            # Size the sign-safe offset from the DATA range, not the threshold.
            # The accumulator sums ro_norm decimated samples of at most 15 bits
            # (12-bit ADC + 3 bits of decimation gain, per the overflow note in
            # qick_asm.declare_readout), so |raw I| <= ro_norm * 2^15. A fixed
            # 2^24 was smaller than that for any window beyond ~0.5 us: a shot
            # more negative than -2^24 would wrap back below the threshold and
            # the corrective pi would fire (or not) on the wrong branch, with
            # no error raised. The threshold guard alone could not catch it,
            # because the threshold sits BETWEEN the blobs while individual
            # shots sit on them.
            self.cmp_offset = int(ro_norm) << 15
            # Both operands must stay inside the 32-bit signed register, and the
            # immediate must stay inside safe_regwi's 2^30 plain-regwi window.
            if self.cmp_offset >= 1 << 30:
                raise ValueError(
                    f"cfg['readout_length']={cfg['readout_length']} us gives a "
                    f"readout window of {ro_norm} cycles, whose sign-safe "
                    f"comparison offset {self.cmp_offset} exceeds the 2^30 "
                    "immediate limit. Shorten the readout window for active reset."
                )
            if abs(raw_threshold) >= self.cmp_offset:
                raise ValueError(
                    f"raw_threshold {raw_threshold} exceeds the sign-safe "
                    f"comparison offset {self.cmp_offset}; the readout is "
                    "saturating the accumulator."
                )
            # r_thresh holds threshold + offset; r_read gets the same offset
            # added (mathi) right after each read, before the condj.
            self.regwi(self.q_rp, self.r_thresh, raw_threshold + self.cmp_offset)

        self.sync_all(self.us2cycles(0.2))

    def active_reset_to_g(self):
        """
        Real measurement-feedback reset to |g>.

        For each reset cycle: fire the readout, read back the accumulated I value
        into a tProc register, and conditionally apply a pi pulse ONLY if the
        qubit was found in |e>. After the block the qubit is in |g>.
        """
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]
        # The tProc `read` instruction addresses a tProc INPUT channel, which is
        # not the same namespace as the readout index. They happen to coincide on
        # the current firmware (readouts[0]['tproc_ch'] == 0), so passing ro_ch
        # worked -- but it would silently read the wrong buffer on any firmware
        # where the mapping is not the identity. Resolve it explicitly.
        tproc_in_ch = self.soccfg["readouts"][ro_ch].get("tproc_ch")
        if tproc_in_ch is None or tproc_in_ch < 0:
            raise RuntimeError(
                f"readout channel {ro_ch} has no tProc input channel "
                f"(tproc_ch={tproc_in_ch}); its accumulated value cannot be read "
                "back by the tProc, so active reset is impossible on it."
            )

        for i in range(self.reset_cycles):
            done_label = "RESET_DONE_%d" % i

            # 1) Measure the qubit (this readout also lands in the data buffer;
            #    collect_shots() ignores it and keeps only the final readout).
            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=self.ro_chs,
                adc_trig_offset=self.adc_trig_offset_cycles,
                wait=True,
                syncdelay=self.us2cycles(cfg.get("reset_readout_relax_delay", 1.0))
            )

            # 2) Read the accumulated in-phase value (lower = I) into r_read.
            self.read(tproc_in_ch, self.q_rp, "lower", self.r_read)

            # Offset I into strictly positive territory so the comparison is
            # sign-safe (see cmp_offset in initialize()); r_thresh already
            # carries the same offset.
            self.mathi(self.q_rp, self.r_read, self.r_read, "+", self.cmp_offset)

            # 3) If already in |g>, skip the corrective pi. Otherwise flip e -> g.
            self.condj(self.q_rp, self.r_read, self.reset_skip_op,
                       self.r_thresh, done_label)

            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit"
            )
            self.pulse(ch=cfg["qubit_ch"])

            # Label sits before the sync so timing reconverges on both branches
            # (whether or not the corrective pi played).
            self.label(done_label)
            self.sync_all()

        if self.reset_cycles:
            self.sync_all(self.us2cycles(cfg.get("post_reset_wait", 0.0)))

    def body(self):
        cfg = self.cfg

        # Per-shot active reset so every Ramsey sequence starts from |g>.
        if self.use_active_reset:
            self.active_reset_to_g()

        # First pi/2 at phase 0. (No explicit phase-register write is needed:
        # set_pulse_registers rewrites it, and the generator DDS is free-running
        # and phase-coherent across the wait, so phase=0 here and phase=180 on
        # the closing pulse are exact inverses independent of tau.)
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit"
        )
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.use_pi_pulse:
            # Echo pi pulse in the middle.
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit"
            )
            self.pulse(ch=cfg["qubit_ch"])

            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        # Final pi/2. Phase (180 deg default, 0 deg if flip_final_pi2) sets the
        # parity -> computational-state mapping; see class docstring.
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=self.deg2reg(self.final_pi2_phase_deg, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_gain"],
            waveform="qubit"
        )
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Final readout. The MR-specific delay is explicit so the spectroscopy
        # relax_delay carried in the shared cfg cannot silently slow this loop.
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(cfg.get("mr_relax_delay", 0.0))
        )

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False):
        # One readout per reset cycle plus the single final Ramsey readout.
        self.reads_per_rep = self.reset_cycles + 1
        if (
            readouts_per_experiment is not None
            and readouts_per_experiment != self.reads_per_rep
        ):
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
        # Readout ii of each rep lives at di_buf[ch][ii::reads_per_rep]; the final
        # Ramsey readout is the last one in each rep (the earlier ones are resets).
        final = reads_per_rep - 1
        shots_i = self.di_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        shots_q = self.dq_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        return shots_i, shots_q

    def collect_reset_shots(self):
        """
        The per-cycle active-reset readouts, shape (reset_cycles, reps) each
        for I and Q, in the same normalized units as collect_shots().

        Reset readout k of a shot measures the qubit state BEFORE corrective
        flip k, so row k's ground fraction reports the success of the k resets
        that preceded it (row 0 = the pre-reset thermal/leftover population).
        Saved so initialization fidelity can be validated offline instead of
        assumed.
        """
        n_cycles = self.reset_cycles
        reps = self.cfg["reps"]
        if not n_cycles:
            return (np.zeros((0, reps)), np.zeros((0, reps)))
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", n_cycles + 1)
        reset_i = np.stack([
            self.di_buf[0][k::reads_per_rep][:reps] / norm
            for k in range(n_cycles)
        ])
        reset_q = np.stack([
            self.dq_buf[0][k::reads_per_rep][:reps] / norm
            for k in range(n_cycles)
        ])
        return reset_i, reset_q

    def scheduled_rep_period_cycles(self):
        """
        Per-rep period of the EMITTED tProc schedule, in tProc cycles.

        Walks the compiled instruction list between the LOOP_J label and the
        loopnz, summing every synci immediate plus the register wait (r_wait,
        the only register this program ever syncs on). This is the same ledger
        verify_ModifiedRamsey_timing.py cross-checks against the
        modified_ramsey_timing() model, computed here from the program itself
        so the experiment layer needs no import from Runners. It includes the
        active-reset overhead, so shot_time = index * period is the ACTUAL
        scheduled sampling interval of the parity record.
        """
        plist = self.prog_list
        start = next(i for i, x in enumerate(plist)
                     if x.get("label") == "LOOP_J")
        end = next(i for i, x in enumerate(plist) if x["name"] == "loopnz")
        t = 0
        for inst in plist[start:end]:
            if inst["name"] == "synci":
                t += inst["args"][0]
            elif inst["name"] == "sync":
                t += self.wait_cycles
        return int(t)

    def scheduled_rep_period_us(self):
        f_time = float(self.soccfg["tprocs"][0]["f_time"])
        return self.scheduled_rep_period_cycles() / f_time


class ModifiedRamsey(ExperimentClass):
    """
    Repeated fixed-tau Ramsey for charge-parity switching time-series.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress
        )

    def acquire(self, progress=False, debug=False):
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(
            self.soc,
            load_pulses=True,
            progress=progress
        )

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()
        reset_i, reset_q = prog.collect_reset_shots()

        # QICK streamer stats measure start_tproc -> completed data-transfer
        # chunks. This is useful for comparing end-to-end acquisition throughput
        # against the scheduled cadence, but includes polling/transfer latency and
        # therefore is not used as the physical shot-time axis.
        streamer_elapsed_s = np.nan
        streamer_average_rep_period_us = np.nan
        if prog.stats:
            last_elapsed_s, last_shots, _, _ = prog.stats[-1]
            streamer_elapsed_s = float(last_elapsed_s)
            if last_shots:
                streamer_average_rep_period_us = (
                    streamer_elapsed_s * 1e6 / float(last_shots)
                )

        # ACTUAL per-shot sampling interval: the emitted tProc schedule,
        # including the full active-reset overhead. This -- not the streamer
        # wall clock -- is the physical time base of the parity record.
        rep_period_us = float(prog.scheduled_rep_period_us())
        n_shots = shots_i.size
        shot_index = np.arange(n_shots)
        shot_time_us = shot_index * rep_period_us

        ro_ch = self.cfg["ro_chs"][0]
        readout_window_us = float(
            prog.readout_window_cycles[ro_ch]
            / float(self.soccfg["readouts"][ro_ch]["f_output"])
        )
        symmetric = self.cfg.get("symmetric_ramsey", False)
        use_reset = self.cfg.get("use_active_reset", False)
        control_type = self.cfg.get("mr_control_type", "parity")

        data = {
            'config': self.cfg,
            'data': {
                # ---- unthresholded per-shot record + time base ------------
                'shots_i': shots_i,
                'shots_q': shots_q,
                'shot_index': shot_index,
                'shot_time_us': shot_time_us,
                'scheduled_rep_period_us': rep_period_us,
                # Continuous single acquisition (rounds == 1 enforced): no
                # record gaps. Kept as an (empty) dataset so offline analysis
                # can consume the same schema as stitched multi-chunk records.
                'gap_indices': np.zeros(0, dtype=int),
                # ---- Ramsey delay: requested vs realized ------------------
                # Requested centre-to-centre precession time.
                'tau_us': 1.0 / (2.0 * self.cfg["df"]),
                # Centre-to-centre time actually realized after the edge-gap
                # correction and tProc-cycle quantization; this is the number
                # the parity phase pi condition is set by.
                'effective_tau_us': float(prog.effective_tau_us),
                # Programmed inter-pulse gap (per gap), i.e. what r_wait holds.
                'wait_us': float(prog.wait_us),
                'qubit_pulse_us': float(prog.pulse_us),
                'sigma_us': float(self.cfg["sigma"]),
                'drive_bandwidth_ratio': float(prog.drive_bandwidth_ratio),
                # ---- parity branches + drive ------------------------------
                # f_ge is passed as the UPPER parity branch; the lower branch
                # sits df below it, and df is the branch separation.
                'f_ge': self.cfg["f_ge"],
                'f_branch_upper': self.cfg["f_ge"],
                'f_branch_lower': self.cfg["f_ge"] - self.cfg["df"],
                'df': self.cfg["df"],
                'drive_freq': float(prog.drive_freq_mhz),
                # ---- pulse gains and phases -------------------------------
                'pi2_gain': self.cfg["pi2_gain"],
                'pi_gain': self.cfg.get("pi_gain", np.nan),
                'first_pi2_phase_deg': 0.0,
                'final_pi2_phase_deg': float(prog.final_pi2_phase_deg),
                # ---- sequence / control state -----------------------------
                'use_pi_pulse': self.cfg.get("use_pi_pulse", False),
                'flip_final_pi2': self.cfg.get("flip_final_pi2", False),
                'symmetric_ramsey': symmetric,
                'mr_control_type_code': MR_CONTROL_TYPE_CODES.get(
                    control_type, -1),
                # ---- readout settings -------------------------------------
                'read_pulse_freq': self.cfg["pulse_freq"],
                'read_pulse_gain': self.cfg["pulse_gain"],
                'res_phase': self.cfg["res_phase"],
                'readout_length_us': self.cfg["readout_length"],
                'readout_window_us': readout_window_us,
                'adc_trig_offset_us': self.cfg["adc_trig_offset"],
                'mr_relax_delay_us': self.cfg.get("mr_relax_delay", 0.0),
                # ---- active reset -----------------------------------------
                'use_active_reset': use_reset,
                'reset_cycles': (
                    int(self.cfg.get("reset_cycles", 1)) if use_reset else 0
                ),
                # Per-cycle reset readouts, shape (reset_cycles, reps): row k
                # measures the state before corrective flip k, so the ground
                # fraction of row k validates the preceding k resets.
                'reset_shots_i': reset_i,
                'reset_shots_q': reset_q,
                'readout_threshold': self.cfg.get("readout_threshold", np.nan)
                if use_reset else np.nan,
                'reset_ground_below_threshold': self.cfg.get(
                    "reset_ground_below_threshold", True),
                'reset_readout_relax_delay_us': self.cfg.get(
                    "reset_readout_relax_delay", 1.0) if use_reset else 0.0,
                'post_reset_wait_us': self.cfg.get(
                    "post_reset_wait", 0.0) if use_reset else 0.0,
                # ---- wall-clock throughput diagnostics --------------------
                'streamer_elapsed_s': streamer_elapsed_s,
                'streamer_average_rep_period_us': streamer_average_rep_period_us,
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        shots_i = np.asarray(data['data']['shots_i'])
        shots_q = np.asarray(data['data']['shots_q'])
        tau_us = data['data']['tau_us']
        eff_tau_us = data['data'].get('effective_tau_us', tau_us)
        wait_us = data['data']['wait_us']
        df = data['data']['df']
        use_pi_pulse = data['data'].get('use_pi_pulse', False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        seq_label = "echo pi" if use_pi_pulse else "no pi"

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, '.', alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis('equal')
        plt.title(
            self.titlename
            + f"\n{seq_label}, tau={tau_us:.4f} us (realized {eff_tau_us:.4f} us),"
            + f" gap={wait_us:.4f} us, df={df:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
