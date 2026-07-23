"""Canonical QICK pulse primitives shared by calibration and production experiments.

Keeping these conversions in one place is a calibration invariant: a pi gain measured
with a Gaussian built on the qubit generator clock is not the same physical pulse when
another program accidentally builds it on the tProc clock; likewise, ADC integration
must see the same readout generator duration and phase that the tuner certified.
"""

import numpy as np


def readout_drive_length_us(cfg):
    """Generator duration covering the delayed ADC window plus an optional guard."""
    integration = float(cfg["read_length"])
    offset = max(float(cfg.get("adc_trig_offset", 0.0)), 0.0)
    guard = max(float(cfg.get("readout_guard_us", 1.0)), 0.0)
    minimum = integration + offset + guard
    requested = float(cfg.get("read_pulse_length", minimum))
    return float(max(requested, minimum))


def explicit_flat_top_fields(cfg):
    """Return every explicitly populated flat-top alias used in this repository.

    The QM-Team programs use ``flattop_length`` while the TLS programs use
    ``flat_top_length``.  Some QM programs select a flat-top solely from the field being
    non-None, even when ``qubit_pulse_style`` still says ``arb``.  Keeping the aliases
    visible prevents that contradictory config from silently denoting two waveforms.
    """
    return {key: cfg[key] for key in ("flat_top_length", "flattop_length")
            if key in cfg and cfg[key] is not None}


def pulse_fingerprint(cfg):
    """Serializable identity of the physical qubit/readout path being calibrated.

    Frequency and gain are included as well as waveform/timing fields so saved manual
    and automatic runs can be compared directly.  It intentionally records switch and
    fast-flux state even though the current Gaussian tuner accepts only the inactive
    cases; absence of a feature is part of the pulse identity.
    """
    plateaus = explicit_flat_top_fields(cfg)
    q_style = str(cfg.get("qubit_pulse_style", "arb")).lower()
    if plateaus and q_style == "arb":
        envelope = "ambiguous_arb_with_flat_top_selector"
    elif plateaus or q_style == "flat_top":
        envelope = "gaussian_flat_top"
    elif q_style == "arb":
        envelope = "gaussian_4sigma"
    else:
        envelope = q_style
    integration_us = float(cfg.get("read_length", cfg.get("readout_length", 0.0)))
    offset_us = float(cfg.get("adc_trig_offset", 0.0))
    guard_us = float(cfg.get("readout_guard_us", 1.0))
    minimum_generator_us = integration_us + max(offset_us, 0.0) + max(guard_us, 0.0)
    if "read_pulse_length" in cfg:
        # TLS canonical semantics: an explicit request may extend but never truncate
        # the delayed ADC window.
        generator_us = max(float(cfg["read_pulse_length"]), minimum_generator_us)
    elif "length" in cfg:
        # QM programs emit this value literally; retaining it is essential because a
        # too-short or deliberately longer tone must remain visible in an A/B diff.
        generator_us = float(cfg["length"])
    else:
        generator_us = minimum_generator_us
    ff_rows = []
    for qid, row in sorted((cfg.get("FF_Qubits", {}) or {}).items(), key=lambda x: str(x[0])):
        if not hasattr(row, "get"):
            continue
        ff_rows.append({
            "qubit": str(qid),
            "channel": int(row.get("channel", cfg.get("ff_ch", -1)) or 0),
            "delay_time_us": float(row.get("delay_time", 0.0) or 0.0),
            "Gain_Readout": int(row.get("Gain_Readout", 0) or 0),
            "Gain_Expt": int(row.get("Gain_Expt", 0) or 0),
            "Gain_Pulse": int(row.get("Gain_Pulse", 0) or 0),
        })
    drag_beta = float(cfg.get("qubit_drag_beta", 0.0) or 0.0)
    if envelope == "gaussian_4sigma" and abs(drag_beta) > 0.0:
        envelope = "gaussian_4sigma_drag"
    return {
        "schema": 2,
        "qubit_channel": int(cfg.get("qubit_ch", -1)),
        "qubit_nyquist_zone": int(cfg.get("qubit_nqz", 1)),
        "implementation": str(cfg.get("pulse_implementation", "unspecified")),
        "qubit_style": q_style,
        "qubit_envelope": envelope,
        "sigma_us": float(cfg.get("sigma", 0.0)),
        # Dimensionless peak derivative-quadrature / peak in-phase ratio.  The sign is
        # the physical QICK I/Q convention and is therefore part of pulse identity.
        "qubit_drag_beta": drag_beta,
        "flat_top_fields_us": {key: float(value) for key, value in plateaus.items()},
        "qubit_freq_mhz": float(cfg.get(
            "qubit_pi_freq", cfg.get("f_ge",
                cfg.get("drive_freq", cfg.get("qubit_freq", 0.0))))),
        "qubit_gain_dac": int(cfg.get("qubit_pi_gain", cfg.get("qubit_gain", 0))),
        "qubit_phase_deg": float(cfg.get("qubit_phase", 0.0)),
        "sequence_gap_us": float(cfg.get("seq_gap_us", 0.01)),
        "switch_enabled": bool(cfg.get("switch_triggered", cfg.get("use_switch", False))),
        "switch_trigger_pin": int(cfg.get("trig_pin", 0)),
        "switch_trigger_delay_us": float(cfg.get("trig_delay", 0.0)),
        "switch_buffer_start_us": float(cfg.get("trig_buffer_start", 0.0)),
        "switch_buffer_end_us": float(cfg.get("trig_buffer_end", 0.0)),
        "readout_style": str(cfg.get("read_pulse_style", "const")).lower(),
        "readout_channel": int(cfg.get("res_ch", -1)),
        "readout_nyquist_zone": int(cfg.get("nqz", 1)),
        "readout_mixer_freq_mhz": float(cfg.get("mixer_freq", 0.0)),
        "readout_freq_mhz": float(cfg.get("read_pulse_freq", cfg.get("pulse_freq", 0.0))),
        "readout_gain_dac": int(cfg.get("read_pulse_gain", cfg.get("pulse_gain", 0))),
        "readout_integration_us": integration_us,
        "readout_generator_us": generator_us,
        "adc_trigger_offset_us": offset_us,
        "readout_phase_deg": float(cfg.get("res_phase", 0.0)),
        "ff_park_gain": int(cfg.get("ff_park_gain", 0) or 0),
        "ff_hold_gain": int(cfg.get("ff_hold_gain", 0) or 0),
        "ff_qubits": ff_rows,
    }


def _generator_envelope_limits(prog, ch):
    """Return (samples/fabric-clock, maximum envelope code) for a QICK generator.

    The laboratory board currently runs QICK 0.2.133, where arbitrary envelopes are
    loaded as sample arrays, while newer clients expose the same fields through a
    slightly different mapping object.  Conservative fallbacks match the full-speed
    axis_signal_gen_v4/v5/v6 used by this project.
    """
    gencfg = {}
    try:
        gencfg = prog.soccfg["gens"][int(ch)]
    except Exception:
        try:
            gencfg = prog.cfg.get("_qubit_gen_cfg", {})
        except Exception:
            pass
    get = gencfg.get if hasattr(gencfg, "get") else lambda key, default=None: default
    samples_per_clock = int(get("samps_per_clk", get("samples_per_clock", 16)) or 16)
    maxv = float(get("maxv", 32766) or 32766)
    maxv *= float(get("maxv_scale", 1.0) or 1.0)
    return max(samples_per_clock, 1), max(min(maxv, 32766.0), 1.0)


def drag_envelope_arrays(prog, sigma_us, beta):
    """Build a Gaussian plus normalized derivative quadrature for QICK waveform RAM.

    ``beta`` is the signed ratio between the *peak* Q envelope and the peak I envelope.
    This convention is hardware- and duration-independent, unlike a raw numerical
    derivative coefficient.  At beta=0 callers deliberately use QICK's built-in
    ``add_gauss`` so legacy Gaussian pulses remain bit-for-bit unchanged.
    """
    qch = int(prog.cfg["qubit_ch"])
    sigma_cycles = max(int(prog.us2cycles(float(sigma_us), gen_ch=qch)), 1)
    samples_per_clock, maxv = _generator_envelope_limits(prog, qch)
    sigma_samples = float(sigma_cycles * samples_per_clock)
    length = int(4 * sigma_cycles * samples_per_clock)
    # Half-sample centring makes both quadratures exactly symmetric/antisymmetric even
    # for the even waveform lengths required by QICK.
    u = (np.arange(length, dtype=float) + 0.5 - 0.5 * length) / sigma_samples
    gauss = np.exp(-0.5 * u ** 2)
    gauss /= max(float(np.max(gauss)), 1e-15)
    deriv = -u * gauss
    deriv /= max(float(np.max(np.abs(deriv))), 1e-15)
    idata = np.rint(maxv * gauss).astype(np.int16)
    qdata = np.rint(maxv * float(beta) * deriv).astype(np.int16)
    return sigma_cycles, idata, qdata


def add_qubit_gaussian(prog, name="qubit", sigma_us=None, drag_beta=None):
    """Add the canonical 4-sigma Gaussian/DRAG pulse on the qubit generator clock.

    The historical function name is retained because all production consumers import
    it.  Once ``qubit_drag_beta`` is calibrated, those same consumers automatically
    replay the identical two-quadrature waveform instead of silently reverting to a
    plain Gaussian.
    """
    cfg = prog.cfg
    qch = cfg["qubit_ch"]
    sigma = float(cfg["sigma"] if sigma_us is None else sigma_us)
    sigma_cycles = max(int(prog.us2cycles(sigma, gen_ch=qch)), 1)
    beta = float(cfg.get("qubit_drag_beta", 0.0) if drag_beta is None else drag_beta)
    if abs(beta) > 1e-15 and str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
        raise ValueError("qubit_drag_beta is defined only for the canonical arb "
                         "Gaussian/DRAG pulse, not %r" % cfg.get("qubit_pulse_style"))
    if abs(beta) <= 1e-15:
        prog.add_gauss(ch=qch, name=name, sigma=sigma_cycles, length=4 * sigma_cycles)
    else:
        sigma_cycles, idata, qdata = drag_envelope_arrays(prog, sigma, beta)
        # QICK 0.2.133's v1 API infers the arbitrary style from idata/qdata.  This call
        # shape is already used by the RFSoC waveform programs in this repository.
        prog.add_pulse(ch=qch, name=name, idata=idata, qdata=qdata)
    return sigma_cycles


def set_readout_pulse(prog, read_freq=None):
    """Configure the canonical constant readout tone and return its frequency register."""
    cfg = prog.cfg
    rch, ro = cfg["res_ch"], cfg["ro_chs"][0]
    style = str(cfg.get("read_pulse_style", "const")).lower()
    if style != "const":
        raise ValueError("canonical readout setup currently requires style='const'; got %r"
                         % cfg.get("read_pulse_style"))
    if read_freq is None:
        read_freq = prog.freq2reg(cfg["read_pulse_freq"], gen_ch=rch, ro_ch=ro)
    phase = prog.deg2reg(float(cfg.get("res_phase", 0.0)), gen_ch=rch)
    kwargs = dict(ch=rch, style="const", freq=read_freq, phase=phase,
                  gain=int(cfg["read_pulse_gain"]),
                  length=prog.us2cycles(readout_drive_length_us(cfg), gen_ch=rch))
    if bool(cfg.get("ro_mode_periodic", False)):
        kwargs["mode"] = "periodic"
    prog.set_pulse_registers(**kwargs)
    return read_freq
