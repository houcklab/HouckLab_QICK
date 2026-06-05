"""
mAutoCoherence.py
=================
Automated T1 / T2 / T2Echo calibration and measurement.

Workflow
--------
1. Two-tone spec (Gaussian drive, 10 reps / 10 rounds) sweeps the qubit
   frequency near a user-provided centre.  A voltage search (via yoko) locates
   the sweet spot where charge dispersion collapses to one peak.
2. AmplitudeRabi (max_gain=12000, using the selected qubit pulse shape) finds
   the pi-pulse gain.  If the trace shows too many oscillations the Gaussian
   sigma is automatically reduced and the sweep is re-run.
3. SingleShot (300 shots during scan, 500 shots for final check) optimises the
   pi-pulse gain to reach ≥70 % readout fidelity.  pi2_gain is set to pi_gain//2.
4. T1, T2 (Ramsey), and T2Echo are run with the calibrated parameters.
5. All calibration results are written to a timestamped .txt file inside an
   AutoCoherence_<timestamp> sub-folder.  Measurement data go into
   auto-T1 / auto-T2 / auto-T2E sub-folders inside the same root.

Usage
-----
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules\\
         .Experiments.mAutoCoherence import run_auto_coherence, AUTO_COHERENCE_PARAMS

    results = run_auto_coherence(
        soc=soc,
        soccfg=soccfg,
        config=config,               # full config dict (as in CSTQ02_BFC.py)
        outerFolder=outerFolder,     # root save folder
        qubit_readout=Qubit_Readout, # int key into Qubit_Parameters
        qubit_params=Qubit_Parameters,
        yoko=yoko,                   # pyvisa resource; pass None if no charge line
        auto_params={},              # optional overrides for AUTO_COHERENCE_PARAMS
    )

IMPORTANT
---------
* This module does NOT modify any caller-side global variables.
* The `config` argument is never mutated; all experiment configs are built
  from local copies via the `|` merge operator.
* Existing experiment classes (T1FF, T2R, T2EMUX, …) are not modified.
"""

import os
import time
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from scipy.signal import find_peaks, savgol_filter

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX

# ---------------------------------------------------------------------------
# Hardware clock quantisation constant (microseconds per QICK cycle × factor).
# Must match the constant in CSTQ02_BFC.py's T2E step calculation.
# ---------------------------------------------------------------------------
_T2E_CLOCK_STEP_US = 0.00232515

# ===========================================================================
# User-facing parameter dictionary  (override any key via the auto_params arg)
# ===========================================================================
AUTO_COHERENCE_PARAMS = {
    # ── two-tone spec (sweet-spot search) ───────────────────────────────────
    "spec_span":          1.0,   # MHz, ± span around qubit centre frequency
    "spec_num_pts":       101,   # number of frequency points per spec run
    "spec_reps":          10,
    "spec_rounds":        10,
    "spec_relax_delay":   1500,  # us
    "spec_sigma":         2.0,   # us  Gaussian drive sigma (sharp peaks → larger σ)
    "spec_gain":          700,   # qubit drive gain for spec (DAC units)
    "spec_qubit_length":  2.0,   # us  flat-top length (unused when Gauss=True)

    # ── sweet-spot voltage search ────────────────────────────────────────────
    # Set skip_sweet_spot_search=True to bypass Stage 1 entirely: the qubit
    # frequency is taken straight from qubit_params and the yoko is left at its
    # current voltage (no two-tone sweep / voltage walk).  Useful when the sweet
    # spot is already known and parked.
    "skip_sweet_spot_search": False,
    # Strategy (when not skipped):
    #   1. If we already see a single peak (sep < ss_accept_sep) → done.
    #   2. If we see two peaks separated by ≥ ss_search_df_trigger →
    #      step by cd_period_mv/2 (if known) or walk toward minimum sep.
    #   3. Repeat up to ss_max_tries times.
    "ss_search_df_trigger": 0.50,  # MHz – peak sep that flags "off sweet spot"
    "ss_accept_sep":        0.08,  # MHz – sep small enough to call "sweet spot"
    "ss_dV":                5e-4,  # V   – voltage step per attempt
    "ss_voltage_min":       0.000,
    "ss_voltage_max":       0.010,
    "ss_max_tries":         200,
    "cd_period_mv":         None,  # mV  – if known; enables half-period step

    # ── Qubit-frequency calibration (Stage 1.5) ─────────────────────────────
    # Runs one two-tone spec at the current voltage and re-centres f_ge on the
    # measured peak(s) before AmplitudeRabi.  Unlike the sweet-spot search it
    # does NOT move the yoko.  Reuses the spec_* parameters above.
    "calibrate_qubit_freq":    True,
    # If the two-tone peak is not clearly above the noise floor
    # (SNR < freqcal_min_snr), the spec is re-run at higher gain
    # (×freqcal_gain_growth each time) up to freqcal_max_gain or
    # freqcal_max_gain_retries attempts.  Set freqcal_auto_gain=False to keep
    # spec_gain fixed (just warn when the peak is weak).
    "freqcal_auto_gain":        True,
    "freqcal_min_snr":          4.0,    # peak SNR below this triggers a gain bump
    "freqcal_gain_growth":      1.8,    # spec_gain multiplier per retry
    "freqcal_max_gain":         30000,  # DAC units; stays under the 32767 ceiling
    "freqcal_max_gain_retries": 5,

    # ── AmplitudeRabi ────────────────────────────────────────────────────────
    "rabi_max_gain":           12000,
    "rabi_num_steps":          201,
    "rabi_reps":               15,
    "rabi_rounds":             15,
    "rabi_relax_delay":        3500,  # us
    "rabi_sigma":              None,  # us – None → use qubit_params sigma
    "rabi_sigma_min":          0.01,  # us – hard lower bound for auto-reduction
    "rabi_max_osc_peaks":      3,     # if # peaks > this, sigma is halved
    "rabi_max_sigma_retries":  10,     # max sigma reduction attempts

    # ── SingleShot pi-pulse optimisation ────────────────────────────────────
    "ss_shots":            1000,  # shots per gain point (fast scan)
    "ss_full_shots":       2000,  # shots for final fidelity measurement
    "ss_relax_delay":      3500,  # us
    "ss_readout_time":     15,    # us
    "ss_adc_offset":       1,     # us  adc_trig_offset
    "ss_target_fidelity":  0.70,  # minimum acceptable fidelity (70 %)
    "ss_gain_pts":         21,    # number of gain points in optimisation scan
    "ss_max_scan_expansions": 2,  # expand/recenter if best point is on scan edge
    "ss_gain_span_growth":  1.8,  # multiplier for each edge-hit expansion
    "ss_gain_span_frac":   0.20,  # ± fraction of estimated pi_gain to scan

    # ── Readout parameter optimisation (Stage 2.5) ──────────────────────────
    # Sweeps readout_length × adc_trig_offset at the Rabi pi_gain to find the
    # integration window that maximises single-shot fidelity.
    # Set auto_readout_opt=False to skip (faster runs, fixed readout params).
    "auto_readout_opt":      True,  # run Stage 2.5
    "readout_length_start":  5.0,   # us – shortest window to test
    "readout_length_stop":   30.0,  # us – longest window to test
    "readout_length_pts":    6,     # number of readout-length values
    "adc_offset_start":      0.2,   # us – shortest ADC trigger offset
    "adc_offset_stop":       3.0,   # us – longest ADC trigger offset
    "adc_offset_pts":        5,     # number of ADC-offset values

    # ── Extended pi / pi2 pulse optimisation (error amplification) ──────────
    # When extended_pi_pi2_opt=True, Stage 3 replaces the simple scan with a
    # sequential error-amplification scheme.  For each N in the nsteps list,
    # SingleShot is run with number_of_pulses=N at each candidate gain; the
    # best gain becomes the new centre, and the search span shrinks by
    # ext_gain_span_shrink each step.
    #
    #   pi  uses odd N  [1, 3, 5, 7, 11] – odd N rotations land on |e⟩
    #   pi2 uses N=2(2k+1) [2, 6, 10, 14, 22] – even multiples of 2(2k+1) pi/2
    #       rotations also land on |e⟩
    "extended_pi_pi2_opt":    False,
    "pi_nsteps_list":         [1, 3, 5, 7, 11],
    "pi2_nsteps_list":        [2, 6, 10, 14, 22],
    "ext_gain_pts":            51,    # gain points scanned at each N step
    "ext_pi_gain_span_init":   0.20,  # ± fraction of pi_gain_estimate (N=1 step)
    "ext_pi2_gain_span_init":  0.20,  # ± fraction of pi2_gain_estimate (N=2 step)
    "ext_gain_span_shrink":    0.40,  # span multiplier applied after each step

    # ── T1 ──────────────────────────────────────────────────────────────────
    "T1_step":         40,        # us – wait-time step
    "T1_expts":        60,        # number of time points
    "T1_reps":         20,
    "T1_rounds":       20,
    "T1_relax_delay":  3500,      # us
    "T1_repetitions":  1,         # number of consecutive T1 runs

    # ── T2 Ramsey ───────────────────────────────────────────────────────────
    "T2_step":         0.1,       # us – Ramsey delay step
    "T2_expts":        201,
    "T2_reps":         20,
    "T2_rounds":       20,
    "T2_relax_delay":  3500,      # us
    "T2_repetitions":  1,
    "T2_freq_shift":   0.0,       # MHz – artificial detuning from f_ge

    # ── T2Echo ──────────────────────────────────────────────────────────────
    "T2E_max_us":       200,      # us – maximum echo time
    "T2E_expts":        201,
    "T2E_reps":         25,
    "T2E_rounds":       25,
    "T2E_relax_delay":  3500,     # us
    "T2E_num_pi_pulses": 1,       # must be odd
    "T2E_repetitions":  1,
}


# ===========================================================================
# ─── Private helpers ────────────────────────────────────────────────────────
# ===========================================================================

def _ramp_to(yoko, target, step=0.001, delay=0.01):
    """Ramp yoko voltage to *target* in small steps (mirrors CSTQ02_BFC.py)."""
    if target > 10:
        raise ValueError(f"Voltage target {target} V exceeds 10 V safety limit")
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")


def _find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=0.10,
                         prominence_fraction=0.25, smooth_window=5):
    """
    Locate up to two prominent peaks in a two-tone spectrum.
    Returns dict with keys: peak_inds, peak_freqs, peak_vals, peak_sep.
    (Mirrors find_two_tone_peaks in CSTQ02_BFC.py.)
    """
    x_pts   = np.asarray(x_pts,   dtype=float)
    avgamp0 = np.asarray(avgamp0, dtype=float)
    n = len(avgamp0)

    if n <= 2:
        best = int(np.argmax(avgamp0))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    # Smooth
    sw = max(3, int(smooth_window) | 1)
    sw = min(sw, n if n % 2 == 1 else n - 1)
    sig = savgol_filter(avgamp0, window_length=sw, polyorder=2) if sw >= 3 \
          else avgamp0.copy()

    amp_range = sig.max() - sig.min()
    if amp_range < 1e-12:
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    prom_thresh = prominence_fraction * amp_range
    dx = abs(float(x_pts[1] - x_pts[0])) if n > 1 else 1.0
    min_dist = max(1, int(round(min_sep_mhz / dx)))

    peak_inds, _ = find_peaks(sig, prominence=prom_thresh, distance=min_dist)

    if len(peak_inds) == 0:
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    if len(peak_inds) > 2:
        order = np.argsort(sig[peak_inds])[::-1]
        peak_inds = np.sort(peak_inds[order[:2]])

    if len(peak_inds) == 2:
        i0, i1 = int(peak_inds[0]), int(peak_inds[1])
        return {
            "peak_inds": [i0, i1],
            "peak_freqs": np.array([x_pts[i0], x_pts[i1]]),
            "peak_vals":  np.array([avgamp0[i0], avgamp0[i1]]),
            "peak_sep":   abs(float(x_pts[i1]) - float(x_pts[i0])),
        }
    else:
        i0 = int(peak_inds[0])
        return {
            "peak_inds": [i0],
            "peak_freqs": np.array([x_pts[i0]]),
            "peak_vals":  np.array([avgamp0[i0]]),
            "peak_sep":   None,
        }


def _choose_next_voltage(current_v, dv, vmin, vmax, direction):
    """Step voltage in *direction*, reversing at bounds. Returns (new_v, direction)."""
    proposed = current_v + direction * dv
    if proposed > vmax:
        direction = -1
        proposed = current_v + direction * dv
    if proposed < vmin:
        direction = +1
        proposed = current_v + direction * dv
    proposed = float(np.clip(proposed, vmin, vmax))
    return proposed, direction


def _acquire_spec(soc, soccfg, cfg, outerFolder, qubit_freq_center, params):
    """
    Run one two-tone spec acquisition.

    Returns
    -------
    x_pts    : 1D array of drive frequencies [MHz]
    avgi     : 1D array of I quadrature signal
    avgq     : 1D array of Q quadrature signal
    avgamp0  : |I + iQ|^2
    peak_info: dict from _find_two_tone_peaks
    """
    spec_cfg = {
        "reps":          params["spec_reps"],
        "rounds":        params["spec_rounds"],
        "Gauss":         True,
        "sigma":         params["spec_sigma"],
        "qubit_gain":    params["spec_gain"],
        "qubit_length":  params["spec_qubit_length"],
        "SpecSpan":      params["spec_span"],
        "SpecNumPoints": params["spec_num_pts"],
        "step":  2.0 * params["spec_span"] / params["spec_num_pts"],
        "start": qubit_freq_center - params["spec_span"],
        "expts": params["spec_num_pts"],
        "relax_delay": params["spec_relax_delay"],
    }
    run_cfg = cfg | spec_cfg

    inst = QubitSpecSliceFF(
        path="auto-Spec",
        cfg=run_cfg,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder,
    )
    data = QubitSpecSliceFF.acquire(inst)
    QubitSpecSliceFF.save_data(inst, data)
    QubitSpecSliceFF.save_config(inst)

    x_pts  = np.array(data["data"]["x_pts"], dtype=float)
    avgi   = np.array(data["data"]["avgi"][0][0], dtype=float)
    avgq   = np.array(data["data"]["avgq"][0][0], dtype=float)
    avgamp0 = np.abs(avgi + 1j * avgq) ** 2

    peak_info = _find_two_tone_peaks(x_pts, avgamp0)
    return x_pts, avgi, avgq, avgamp0, peak_info


def _find_pi_gain_from_rabi(x_pts, avgi, avgq):
    """
    Identify the pi-pulse gain from an AmplitudeRabi trace.

    The IQ trace is projected onto its largest-variance axis so qubits with
    different IQ rotations are treated consistently.
    The first local maximum of the projected signal corresponds to the
    pi pulse.  Returns (pi_gain_int, n_oscillation_peaks).
    """
    x_pts = np.asarray(x_pts, dtype=float)
    avgi  = np.asarray(avgi,  dtype=float)
    avgq  = np.asarray(avgq,  dtype=float)

    if len(x_pts) == 0:
        raise ValueError("AmplitudeRabi returned no gain points.")

    if len(x_pts) == 1:
        return int(round(float(x_pts[0]))), 0

    # Project onto the axis where the Rabi trace actually moves in IQ space.
    iq = np.column_stack((avgi, avgq))
    iq_centered = iq - np.mean(iq, axis=0)
    try:
        _, _, vh = np.linalg.svd(iq_centered, full_matrices=False)
        y = iq_centered @ vh[0]
    except np.linalg.LinAlgError:
        y = avgi - np.mean(avgi)

    # Normalise to [0, 1]
    y_min, y_max = y.min(), y.max()
    dyn = y_max - y_min
    if dyn < 1e-12:
        return int(round(x_pts[np.argmax(y)])), 0
    y_norm = (y - y_min) / dyn

    # At gain=0 the qubit is in |g⟩ after the relax delay.  Depending on
    # the IQ geometry, y_norm[0] may be near 0 (|g⟩ → minimum) or near 1
    # (|g⟩ → maximum).  We always want to search for PEAKS that correspond
    # to |e⟩ (maximum excitation), so flip the trace if the ground state
    # sits near the top of the normalised scale.
    baseline_pts = max(1, min(5, len(y_norm) // 20 or 1))
    ground_level = float(np.median(y_norm[:baseline_pts]))
    if ground_level > 0.5:
        y_search = 1.0 - y_norm   # invert so |g⟩ → 0, |e⟩ → 1
    else:
        y_search = y_norm

    # Smooth only for peak finding; keep the original sweep points for the
    # returned gain.
    if len(y_search) >= 7:
        smooth_window = min(len(y_search) if len(y_search) % 2 else len(y_search) - 1, 11)
        y_for_peaks = savgol_filter(y_search, window_length=smooth_window, polyorder=2)
    else:
        y_for_peaks = y_search

    # Find all peaks with meaningful prominence and excitation height.
    peaks, _ = find_peaks(y_for_peaks, prominence=0.20, height=0.35)
    n_peaks = len(peaks)

    if n_peaks > 0:
        pi_gain = int(round(float(x_pts[peaks[0]])))
    else:
        # No clear peak – use the global extremum in the search direction
        pi_gain = int(round(float(x_pts[np.argmax(y_for_peaks)])))

    return pi_gain, n_peaks


def _sync_cfg_to_selected_qubit(cfg, qubit_readout, readout_freq, readout_gain,
                                qubit_freq, qubit_gain, sigma, flattop_length):
    """
    Return a local config copy whose scalar and single-qubit list fields all
    point at the selected qubit.

    This keeps the automation safe when a caller changes Qubit_Readout but has
    an older config dict in memory from a previous qubit.
    """
    synced = dict(cfg)
    synced.update({
        "pulse_freq":      readout_freq,
        "pulse_gain":      readout_gain,
        "qubit_gain":      qubit_gain,
        "f_ge":            qubit_freq,
        "qubit_gains":     [qubit_gain],
        "f_ges":           [qubit_freq],
        "sigma":           sigma,
        "flattop_length":  flattop_length,
        "Read_Indeces":    qubit_readout,
        "Qubit_number":    qubit_readout,
    })
    return synced


def _run_single_shot_at_gain(soc, soccfg, cfg, outerFolder,
                              qubit_gain, qubit_freq, sigma, flattop_length,
                              shots, relax_delay, readout_time, adc_offset,
                              qubit_readout, num_pulses=1,
                              path="auto-SingleShot"):
    """
    Run one SingleShot acquisition at the specified qubit gain.

    Parameters
    ----------
    num_pulses : int
        Number of qubit drive pulses applied before readout (used for error
        amplification).  1 = standard single-shot.  Odd values for pi-pulse
        calibration; even values N=2(2k+1) for pi/2-pulse calibration.
    path : str
        Sub-folder name passed to SingleShotProgramFFMUX (changes on-disk path).

    Returns (fidelity, threshold, angle, data, instance).
    """
    ss_cfg = {
        "read_pulse_style": "const",
        "readout_length":   readout_time,
        "adc_trig_offset":  adc_offset,
        "pi2_SS":           False,
        "qubit_pulse_style": "arb",
        "sigma":            sigma,
        "qubit_gain":       qubit_gain,
        "f_ge":             qubit_freq,
        "qubit_gains":      [qubit_gain],
        "f_ges":            [qubit_freq],
        "shots":            shots,
        "relax_delay":      relax_delay,
        "flattop_length":   flattop_length,
        "number_of_pulses": num_pulses,
        "Read_Indeces":     qubit_readout,
    }
    run_cfg = cfg | ss_cfg

    inst = SingleShotProgramFFMUX(
        path=path,
        cfg=run_cfg,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder,
    )
    data = SingleShotProgramFFMUX.acquire(inst)

    fid       = float(inst.fid[0])
    threshold = float(inst.threshold[0])
    angle     = float(inst.angle[0])

    SingleShotProgramFFMUX.display(inst, data, plotDisp=False)
    plt.close('all')   # hist_process always opens a figure; close it after saving
    SingleShotProgramFFMUX.save_data(inst, data)
    SingleShotProgramFFMUX.save_config(inst)

    return fid, threshold, angle, data, inst


# ===========================================================================
# ─── Main automation stages ─────────────────────────────────────────────────
# ===========================================================================

def _stage_sweet_spot_search(soc, soccfg, cfg, auto_folder,
                              qubit_freq_center, qubit_readout,
                              params, yoko, log):
    """
    Stage 1 – Two-tone spec sweep to find the sweet spot (single resonance peak).

    Returns
    -------
    qubit_frequency : float  (MHz)
    final_voltage   : float or None
    peak_info       : dict
    """
    log.append("=" * 60)
    log.append("STAGE 1 – Two-tone spec / sweet-spot search")
    log.append("=" * 60)

    # ── First spec at current state ─────────────────────────────────────────
    x_pts, avgi, avgq, avgamp0, peak_info = _acquire_spec(
        soc, soccfg, cfg, auto_folder, qubit_freq_center, params
    )

    current_voltage = None
    if yoko is not None:
        current_voltage = float(yoko.query(":SOUR:LEV?"))

    peak_sep = peak_info["peak_sep"]
    sep_str  = f"{peak_sep:.4f} MHz" if peak_sep is not None else "None (single peak)"
    log.append(f"  Initial voltage : {current_voltage}")
    log.append(f"  Initial peaks   : {peak_info['peak_freqs']}")
    log.append(f"  Initial sep     : {sep_str}")

    # ── Helper to extract qubit frequency from peak_info ────────────────────
    def _qubit_freq_from_peaks(pi):
        if len(pi["peak_freqs"]) == 2:
            return float(np.mean(pi["peak_freqs"]))  # midpoint of f+ and f-
        return float(pi["peak_freqs"][0])

    # ── If already at sweet spot (one peak or tiny sep) ─────────────────────
    accept_sep = params["ss_accept_sep"]
    if peak_sep is None or peak_sep < accept_sep:
        qfreq = _qubit_freq_from_peaks(peak_info)
        log.append(f"  Already near sweet spot.  f_ge = {qfreq:.6f} MHz")
        return qfreq, current_voltage, peak_info

    if yoko is None:
        # No voltage control available; use centre of the two peaks
        qfreq = _qubit_freq_from_peaks(peak_info)
        log.append(f"  No yoko provided.  Using peak midpoint: {qfreq:.6f} MHz")
        return qfreq, current_voltage, peak_info

    # ── Voltage search ──────────────────────────────────────────────────────
    dV         = params["ss_dV"]
    vmin       = params["ss_voltage_min"]
    vmax       = params["ss_voltage_max"]
    max_tries  = params["ss_max_tries"]
    df_trigger = params["ss_search_df_trigger"]
    cd_period  = params["cd_period_mv"]  # None or float in mV

    direction = +1  # initial search direction

    # ── Strategy A: half-period step if cd_period_mv is known ───────────────
    if cd_period is not None and peak_sep >= df_trigger:
        half_period_V = (cd_period * 1e-3) / 2.0
        candidate_v   = current_voltage + half_period_V
        # Keep within bounds
        candidate_v   = float(np.clip(candidate_v, vmin, vmax))
        log.append(
            f"  Known cd_period={cd_period} mV → stepping half period "
            f"({half_period_V*1e3:.2f} mV) to V={candidate_v:.6f} V"
        )
        _ramp_to(yoko, candidate_v)
        current_voltage = candidate_v

        x_pts, avgi, avgq, avgamp0, peak_info = _acquire_spec(
            soc, soccfg, cfg, auto_folder, qubit_freq_center, params
        )
        peak_sep = peak_info["peak_sep"]
        log.append(
            f"  After half-period step: sep = {peak_sep:.4f} MHz"
            if peak_sep is not None else
            "  After half-period step: single peak"
        )
        if peak_sep is None or peak_sep < accept_sep:
            qfreq = _qubit_freq_from_peaks(peak_info)
            log.append(f"  Sweet spot found at V={current_voltage:.6f} V, f_ge={qfreq:.6f} MHz")
            return qfreq, current_voltage, peak_info

    # ── Strategy B: incremental walk toward minimum separation ───────────────
    # Track the minimum separation and its corresponding voltage.
    best_sep_found = peak_sep if peak_sep is not None else np.inf
    best_voltage   = current_voltage
    best_peak_info = peak_info

    log.append(f"  Starting incremental walk (max {max_tries} steps, dV={dV*1e3:.2f} mV)")

    for attempt in range(max_tries):
        next_v, direction = _choose_next_voltage(current_voltage, dV, vmin, vmax, direction)
        if abs(next_v - current_voltage) < 1e-15:
            log.append("  Voltage stalled at bounds; stopping search.")
            break

        _ramp_to(yoko, next_v)
        current_voltage = next_v

        x_pts, avgi, avgq, avgamp0, peak_info = _acquire_spec(
            soc, soccfg, cfg, auto_folder, qubit_freq_center, params
        )
        peak_sep = peak_info["peak_sep"]

        if peak_sep is None or peak_sep < accept_sep:
            best_sep_found = 0.0
            best_voltage   = current_voltage
            best_peak_info = peak_info
            log.append(
                f"  Attempt {attempt+1}: V={current_voltage:.6f} V → "
                f"sweet spot found (sep={peak_sep})"
            )
            break

        if peak_sep < best_sep_found:
            best_sep_found = peak_sep
            best_voltage   = current_voltage
            best_peak_info = peak_info

        log.append(
            f"  Attempt {attempt+1}: V={current_voltage:.6f} V, sep={peak_sep:.4f} MHz "
            f"(best so far: {best_sep_found:.4f} MHz)"
        )

    # Move to the best voltage found
    if abs(current_voltage - best_voltage) > 1e-9:
        log.append(f"  Returning to best voltage {best_voltage:.6f} V")
        _ramp_to(yoko, best_voltage)
        current_voltage = best_voltage
        peak_info = best_peak_info

    qfreq = _qubit_freq_from_peaks(peak_info)
    final_sep = peak_info["peak_sep"]
    sep_txt = f"sep={final_sep:.4f} MHz" if final_sep is not None else "single peak"
    log.append(
        f"  Sweet-spot search complete. "
        f"V={current_voltage:.6f} V, f_ge={qfreq:.6f} MHz, {sep_txt}"
    )

    return qfreq, current_voltage, peak_info


def _spec_peak_snr(avgamp0, peak_info):
    """
    Robust signal-to-noise estimate for a two-tone spec peak.

    Uses the median as the baseline and the MAD (scaled to a Gaussian sigma) as
    the noise level, so a single sharp peak does not inflate the noise estimate.
    Returns (peak - baseline) / noise for the strongest detected peak.
    """
    avgamp0 = np.asarray(avgamp0, dtype=float)
    if avgamp0.size == 0:
        return 0.0

    baseline = float(np.median(avgamp0))
    mad      = float(np.median(np.abs(avgamp0 - baseline)))
    noise    = 1.4826 * mad
    if noise < 1e-12:
        noise = float(np.std(avgamp0)) or 1e-12

    peak_vals = peak_info.get("peak_vals") if peak_info else None
    if peak_vals is not None and len(peak_vals) > 0:
        peak = float(np.max(peak_vals))
    else:
        peak = float(np.max(avgamp0))

    return (peak - baseline) / noise


def _stage_calibrate_qubit_freq(soc, soccfg, cfg, auto_folder,
                                qubit_freq_center, qubit_readout,
                                params, log):
    """
    Stage 1.5 – Two-tone spec at the current voltage to refine the qubit
    frequency before AmplitudeRabi.

    Unlike the sweet-spot search (Stage 1) this does NOT move the yoko voltage;
    it only re-centres f_ge on the measured two-tone peak(s).  When two peaks
    are present (charge-split) the midpoint is used; otherwise the single peak.

    If freqcal_auto_gain is enabled and the peak is not clearly above the noise
    floor (SNR < freqcal_min_snr), the spec is re-run at progressively higher
    drive gain until a peak is visible, the gain cap is hit, or the retry budget
    is exhausted.

    Returns
    -------
    qubit_frequency : float (MHz)
    peak_info       : dict
    """
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 1.5 – Two-tone qubit-frequency calibration")
    log.append("=" * 60)

    auto_gain   = params.get("freqcal_auto_gain", True)
    gain        = int(params["spec_gain"])
    gain_growth = float(params.get("freqcal_gain_growth", 1.8))
    gain_cap    = int(params.get("freqcal_max_gain", 30000))
    max_retries = int(params.get("freqcal_max_gain_retries", 5))
    min_snr     = float(params.get("freqcal_min_snr", 4.0))

    peak_info = None
    snr = 0.0
    for attempt in range(max_retries + 1):
        spec_params = {**params, "spec_gain": gain}
        x_pts, avgi, avgq, avgamp0, peak_info = _acquire_spec(
            soc, soccfg, cfg, auto_folder, qubit_freq_center, spec_params
        )
        snr = _spec_peak_snr(avgamp0, peak_info)
        log.append(f"  Attempt {attempt + 1}: spec_gain={gain}, peak SNR={snr:.2f}")

        if not auto_gain or snr >= min_snr:
            break

        next_gain = min(gain_cap, int(round(gain * gain_growth)))
        if next_gain <= gain:
            log.append(f"    Peak weak (SNR {snr:.2f} < {min_snr}) but spec_gain "
                       f"capped at {gain}; stopping.")
            break

        log.append(f"    Peak not clearly visible (SNR {snr:.2f} < {min_snr}); "
                   f"raising spec_gain {gain} -> {next_gain}")
        gain = next_gain

    if auto_gain and snr < min_snr:
        log.append(f"  WARNING: no clear two-tone peak (best SNR {snr:.2f} < "
                   f"{min_snr}) up to spec_gain={gain}. f_ge may be unreliable -- "
                   f"check spec_span / drive power.")

    if len(peak_info["peak_freqs"]) == 2:
        qfreq = float(np.mean(peak_info["peak_freqs"]))
        log.append(f"  Two peaks at {peak_info['peak_freqs']} -> midpoint")
    else:
        qfreq = float(peak_info["peak_freqs"][0])
        log.append(f"  Single peak at {qfreq:.6f} MHz")

    log.append(
        f"  Calibrated f_ge = {qfreq:.6f} MHz "
        f"(was {qubit_freq_center:.6f} MHz, shift {qfreq - qubit_freq_center:+.6f} MHz) "
        f"at spec_gain={gain}"
    )
    return qfreq, peak_info


def _stage_amplitude_rabi(soc, soccfg, cfg, auto_folder,
                           qubit_freq, qubit_readout, sigma_initial,
                           flattop_length, params, log):
    """
    Stage 2 – AmplitudeRabi to find the pi-pulse gain.

    Automatically reduces sigma if too many oscillations are observed.

    Returns
    -------
    pi_gain    : int (DAC units)
    rabi_sigma : float (us) – final sigma used
    """
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 2 – AmplitudeRabi pi-pulse calibration")
    log.append("=" * 60)

    rabi_sigma  = params["rabi_sigma"] if params["rabi_sigma"] is not None else sigma_initial
    max_gain    = params["rabi_max_gain"]
    num_steps   = params["rabi_num_steps"]
    rabi_reps   = params["rabi_reps"]
    rabi_rounds = params["rabi_rounds"]
    relax_delay = params["rabi_relax_delay"]
    sigma_min   = params["rabi_sigma_min"]
    max_osc     = params["rabi_max_osc_peaks"]
    max_retries = params["rabi_max_sigma_retries"]

    step_size = max(1, int(round(max_gain / max(1, num_steps - 1))))

    pi_gain     = None
    rabi_data   = None
    rabi_inst   = None

    for retry in range(max_retries + 1):
        log.append(f"  Rabi attempt {retry+1}: sigma={rabi_sigma:.4f} us")

        rabi_cfg = {
            "start":         0,
            "step":          step_size,
            "expts":         num_steps,
            "reps":          rabi_reps,
            "rounds":        rabi_rounds,
            "sigma":         rabi_sigma,
            "f_ge":          qubit_freq,
            "relax_delay":   relax_delay,
            "flattop_length": flattop_length,
            "Qubit_number":  qubit_readout,
        }
        run_cfg = cfg | rabi_cfg

        inst = AmplitudeRabiFF(
            path="auto-AmplitudeRabi",
            cfg=run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=auto_folder,
        )
        data = AmplitudeRabiFF.acquire(inst)
        AmplitudeRabiFF.display(inst, data, plotDisp=False, figNum=10)
        AmplitudeRabiFF.save_data(inst, data)
        AmplitudeRabiFF.save_config(inst)

        x_pts = np.array(data["data"]["x_pts"], dtype=float)
        avgi  = np.array(data["data"]["avgi"][0][0], dtype=float)
        avgq  = np.array(data["data"]["avgq"][0][0], dtype=float)

        pi_gain_candidate, n_peaks = _find_pi_gain_from_rabi(x_pts, avgi, avgq)

        log.append(
            f"    Found {n_peaks} oscillation peak(s), "
            f"estimated pi_gain = {pi_gain_candidate}"
        )

        if n_peaks <= max_osc or retry == max_retries:
            # Accept this result
            pi_gain   = pi_gain_candidate
            rabi_data = data
            rabi_inst = inst
            break
        else:
            log.append(
                f"    Too many oscillations ({n_peaks} > {max_osc}). "
                f"Reducing sigma by 30 %."
            )
            rabi_sigma = max(sigma_min, rabi_sigma * 0.70)

    if pi_gain is None:
        raise RuntimeError("AmplitudeRabi: could not determine pi-pulse gain.")

    log.append(f"  pi_gain = {pi_gain}  (sigma = {rabi_sigma:.4f} us)")
    return pi_gain, rabi_sigma


def _stage_optimize_readout(soc, soccfg, cfg, auto_folder,
                            qubit_freq, pi_gain, sigma, flattop_length,
                            qubit_readout, params, log):
    """
    Stage 2.5 – Sweep readout_length × adc_trig_offset at the Rabi pi_gain.

    Tries all combinations of readout integration window length and ADC trigger
    offset to find the pair that maximises single-shot fidelity.  The optimised
    values are returned and propagated to Stage 3 and the coherence stages.

    Returns
    -------
    best_readout_length : float  (us)
    best_adc_offset     : float  (us)
    """
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 2.5 – Readout parameter optimisation")
    log.append("=" * 60)

    readout_lengths = np.linspace(
        params["readout_length_start"],
        params["readout_length_stop"],
        int(params["readout_length_pts"]),
    )
    adc_offsets = np.linspace(
        params["adc_offset_start"],
        params["adc_offset_stop"],
        int(params["adc_offset_pts"]),
    )

    log.append(
        f"  Sweeping readout_length: {params['readout_length_start']:.1f} – "
        f"{params['readout_length_stop']:.1f} us  ({int(params['readout_length_pts'])} pts)"
    )
    log.append(
        f"  Sweeping adc_offset:     {params['adc_offset_start']:.2f} – "
        f"{params['adc_offset_stop']:.2f} us  ({int(params['adc_offset_pts'])} pts)"
    )

    best_fid            = -1.0
    best_readout_length = float(params["ss_readout_time"])
    best_adc_offset     = float(params["ss_adc_offset"])

    for rl in readout_lengths:
        for ao in adc_offsets:
            fid, _, _, _, _ = _run_single_shot_at_gain(
                soc, soccfg, cfg, auto_folder,
                qubit_gain=pi_gain,
                qubit_freq=qubit_freq,
                sigma=sigma,
                flattop_length=flattop_length,
                shots=params["ss_shots"],
                relax_delay=params["ss_relax_delay"],
                readout_time=float(rl),
                adc_offset=float(ao),
                qubit_readout=qubit_readout,
                path="auto-ReadoutOpt",
            )
            log.append(
                f"    readout_length={rl:.1f} us, adc_offset={ao:.2f} us "
                f"-> fidelity={fid:.4f}"
            )
            if fid > best_fid:
                best_fid            = fid
                best_readout_length = float(rl)
                best_adc_offset     = float(ao)

    log.append(
        f"  Best: readout_length={best_readout_length:.1f} us, "
        f"adc_offset={best_adc_offset:.2f} us, fidelity={best_fid:.4f}"
    )
    return best_readout_length, best_adc_offset


def _stage_singleshot_optimize(soc, soccfg, cfg, auto_folder,
                                qubit_freq, sigma, flattop_length,
                                pi_gain_estimate, qubit_readout,
                                params, log):
    """
    Stage 3 – SingleShot gain scan to find the gain that maximises fidelity.

    Returns
    -------
    pi_gain_opt  : int (DAC units)
    pi2_gain_opt : int (DAC units)
    fidelity     : float
    threshold    : float
    angle        : float
    """
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 3 – SingleShot pi-pulse optimisation")
    log.append("=" * 60)

    target_fid    = params["ss_target_fidelity"]
    scan_pts      = params["ss_gain_pts"]
    scan_frac     = params["ss_gain_span_frac"]
    shots         = params["ss_shots"]
    full_shots    = params["ss_full_shots"]
    relax_delay   = params["ss_relax_delay"]
    readout_time  = params["ss_readout_time"]
    adc_offset    = params["ss_adc_offset"]
    max_expansions = int(params.get("ss_max_scan_expansions", 0))
    span_growth    = float(params.get("ss_gain_span_growth", 1.0))

    gain_lo = max(0,     int(pi_gain_estimate * (1.0 - scan_frac)))
    gain_hi = min(32767, int(pi_gain_estimate * (1.0 + scan_frac)))
    gains   = np.unique(
        np.linspace(gain_lo, gain_hi, scan_pts).astype(int)
    )

    log.append(f"  Scanning gains: {gain_lo} → {gain_hi}  ({len(gains)} points)")

    best_fid   = -1.0
    best_gain  = pi_gain_estimate
    best_thr   = 0.0
    best_angle = 0.0

    for g in gains:
        fid, thr, ang, _, _ = _run_single_shot_at_gain(
            soc, soccfg, cfg, auto_folder,
            qubit_gain=int(g),
            qubit_freq=qubit_freq,
            sigma=sigma,
            flattop_length=flattop_length,
            shots=shots,
            relax_delay=relax_delay,
            readout_time=readout_time,
            adc_offset=adc_offset,
            qubit_readout=qubit_readout,
        )
        log.append(f"    gain={int(g):6d}  fidelity={fid:.4f}")
        if fid > best_fid:
            best_fid   = fid
            best_gain  = int(g)
            best_thr   = thr
            best_angle = ang

    log.append(f"  Best gain from scan: {best_gain}  fidelity = {best_fid:.4f}")

    expansion = 0
    while (
        expansion < max_expansions
        and len(gains) > 1
        and (best_gain == int(gains[0]) or best_gain == int(gains[-1]))
    ):
        expansion += 1
        scan_center = max(1, int(best_gain))
        scan_frac *= span_growth
        gain_lo = max(0,     int(scan_center * (1.0 - scan_frac)))
        gain_hi = min(32767, int(scan_center * (1.0 + scan_frac)))
        gains = np.unique(np.linspace(gain_lo, gain_hi, scan_pts).astype(int))

        log.append(
            f"  Best point was on the scan edge; rescanning "
            f"{gain_lo} -> {gain_hi} around gain={scan_center}."
        )

        for g in gains:
            fid, thr, ang, _, _ = _run_single_shot_at_gain(
                soc, soccfg, cfg, auto_folder,
                qubit_gain=int(g),
                qubit_freq=qubit_freq,
                sigma=sigma,
                flattop_length=flattop_length,
                shots=shots,
                relax_delay=relax_delay,
                readout_time=readout_time,
                adc_offset=adc_offset,
                qubit_readout=qubit_readout,
            )
            log.append(f"    gain={int(g):6d}  fidelity={fid:.4f}")
            if fid > best_fid:
                best_fid   = fid
                best_gain  = int(g)
                best_thr   = thr
                best_angle = ang

        log.append(f"  Best gain after rescan {expansion}: {best_gain}  fidelity = {best_fid:.4f}")

    if best_fid < target_fid:
        log.append(
            f"  WARNING: best fidelity {best_fid:.4f} is below target "
            f"{target_fid:.4f}.  Proceeding anyway."
        )

    # Final high-shot measurement at best gain
    log.append(f"  Final SingleShot run at gain={best_gain}, shots={full_shots} …")
    fid_final, thr_final, ang_final, _, _ = _run_single_shot_at_gain(
        soc, soccfg, cfg, auto_folder,
        qubit_gain=best_gain,
        qubit_freq=qubit_freq,
        sigma=sigma,
        flattop_length=flattop_length,
        shots=full_shots,
        relax_delay=relax_delay,
        readout_time=readout_time,
        adc_offset=adc_offset,
        qubit_readout=qubit_readout,
    )
    log.append(f"  Final fidelity = {fid_final:.4f}  threshold = {thr_final:.4f}")

    pi2_gain = best_gain // 2
    log.append(f"  pi_gain = {best_gain},  pi2_gain = {pi2_gain}")

    return best_gain, pi2_gain, fid_final, thr_final, ang_final


def _optimize_gain_sequence(soc, soccfg, cfg, auto_folder,
                             qubit_freq, sigma, flattop_length, qubit_readout,
                             gain_estimate, nsteps_list,
                             gain_span_init, gain_span_shrink,
                             gain_pts, shots, relax_delay, readout_time,
                             adc_offset, pulse_path, log, label):
    """
    Iterative gain refinement using error amplification.

    For each N in *nsteps_list*:
      1. Build a gain grid of *gain_pts* points centred on the current best gain
         with a span of ±current_span fraction.
      2. Run SingleShot with number_of_pulses=N at each grid point.
      3. Select the gain with the highest fidelity as the new centre.
      4. Multiply the span by *gain_span_shrink* for the next step.

    Returns (best_gain, best_fid, best_thr, best_angle).
    """
    current_center = int(gain_estimate)
    current_span   = float(gain_span_init)

    # Track the overall best across all N steps
    overall_best_gain  = current_center
    overall_best_fid   = -1.0
    overall_best_thr   = 0.0
    overall_best_angle = 0.0

    for n_pulses in nsteps_list:
        gain_lo = max(1,     int(current_center * (1.0 - current_span)))
        gain_hi = min(32767, int(current_center * (1.0 + current_span)))
        gains   = np.unique(np.linspace(gain_lo, gain_hi, gain_pts).astype(int))

        log.append(
            f"  [{label}] N={n_pulses}: scanning {len(gains)} gains "
            f"[{gain_lo}, {gain_hi}] (span={current_span*100:.1f}%)"
        )

        step_best_fid   = -1.0
        step_best_gain  = current_center
        step_best_thr   = 0.0
        step_best_angle = 0.0

        for g in gains:
            fid, thr, ang, _, _ = _run_single_shot_at_gain(
                soc, soccfg, cfg, auto_folder,
                qubit_gain=int(g),
                qubit_freq=qubit_freq,
                sigma=sigma,
                flattop_length=flattop_length,
                shots=shots,
                relax_delay=relax_delay,
                readout_time=readout_time,
                adc_offset=adc_offset,
                qubit_readout=qubit_readout,
                num_pulses=n_pulses,
                path=pulse_path,
            )
            log.append(f"    gain={int(g):6d}  fidelity={fid:.4f}  (N={n_pulses})")
            if fid > step_best_fid:
                step_best_fid   = fid
                step_best_gain  = int(g)
                step_best_thr   = thr
                step_best_angle = ang

        log.append(
            f"  [{label}] N={n_pulses}: best gain={step_best_gain}, "
            f"fidelity={step_best_fid:.4f}"
        )

        # Advance centre and shrink span
        current_center = step_best_gain
        current_span   = current_span * gain_span_shrink

        if step_best_fid > overall_best_fid:
            overall_best_fid   = step_best_fid
            overall_best_gain  = step_best_gain
            overall_best_thr   = step_best_thr
            overall_best_angle = step_best_angle

    return overall_best_gain, overall_best_fid, overall_best_thr, overall_best_angle


def _stage_extended_pulse_opt(soc, soccfg, cfg, auto_folder,
                               qubit_freq, sigma, flattop_length,
                               pi_gain_estimate, qubit_readout,
                               params, log):
    """
    Stage 3 (extended) – Sequential pi and pi/2 gain optimisation using
    error amplification.

    Pi pulse  : odd N in params["pi_nsteps_list"]  → |e⟩ at correct pi gain
    Pi/2 pulse: N=2(2k+1) in params["pi2_nsteps_list"] → |e⟩ at correct pi/2 gain

    Returns
    -------
    pi_gain_opt  : int
    pi2_gain_opt : int
    fidelity     : float  (final 1-pulse SingleShot fidelity at pi_gain_opt)
    threshold    : float
    angle        : float
    """
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 3 – Extended pi / pi2 pulse optimisation")
    log.append("=" * 60)

    shots        = params["ss_shots"]
    full_shots   = params["ss_full_shots"]
    relax_delay  = params["ss_relax_delay"]
    readout_time = params["ss_readout_time"]
    adc_offset   = params["ss_adc_offset"]
    target_fid   = params["ss_target_fidelity"]

    pi_nsteps_list  = params["pi_nsteps_list"]
    pi2_nsteps_list = params["pi2_nsteps_list"]
    gain_pts        = params["ext_gain_pts"]
    pi_span_init    = params["ext_pi_gain_span_init"]
    pi2_span_init   = params["ext_pi2_gain_span_init"]
    span_shrink     = params["ext_gain_span_shrink"]

    # ── Optimise pi pulse ────────────────────────────────────────────────────
    log.append(
        f"  Pi optimisation: N sequence={pi_nsteps_list}, "
        f"initial estimate={pi_gain_estimate}, span=±{pi_span_init*100:.0f}%"
    )
    pi_gain_opt, pi_fid, pi_thr, pi_angle = _optimize_gain_sequence(
        soc=soc, soccfg=soccfg, cfg=cfg, auto_folder=auto_folder,
        qubit_freq=qubit_freq, sigma=sigma, flattop_length=flattop_length,
        qubit_readout=qubit_readout,
        gain_estimate=pi_gain_estimate,
        nsteps_list=pi_nsteps_list,
        gain_span_init=pi_span_init,
        gain_span_shrink=span_shrink,
        gain_pts=gain_pts,
        shots=shots,
        relax_delay=relax_delay,
        readout_time=readout_time,
        adc_offset=adc_offset,
        pulse_path="auto-PiOpt",
        log=log,
        label="pi",
    )
    log.append(f"  Pi optimisation done: pi_gain={pi_gain_opt}, fidelity={pi_fid:.4f}")

    # ── Optimise pi/2 pulse ──────────────────────────────────────────────────
    pi2_gain_estimate = pi_gain_opt // 2
    log.append(
        f"  Pi/2 optimisation: N sequence={pi2_nsteps_list}, "
        f"initial estimate={pi2_gain_estimate}, span=±{pi2_span_init*100:.0f}%"
    )
    pi2_gain_opt, pi2_fid, pi2_thr, pi2_angle = _optimize_gain_sequence(
        soc=soc, soccfg=soccfg, cfg=cfg, auto_folder=auto_folder,
        qubit_freq=qubit_freq, sigma=sigma, flattop_length=flattop_length,
        qubit_readout=qubit_readout,
        gain_estimate=pi2_gain_estimate,
        nsteps_list=pi2_nsteps_list,
        gain_span_init=pi2_span_init,
        gain_span_shrink=span_shrink,
        gain_pts=gain_pts,
        shots=shots,
        relax_delay=relax_delay,
        readout_time=readout_time,
        adc_offset=adc_offset,
        pulse_path="auto-Pi2Opt",
        log=log,
        label="pi/2",
    )
    log.append(f"  Pi/2 optimisation done: pi2_gain={pi2_gain_opt}, fidelity={pi2_fid:.4f}")

    # ── Final 1-pulse fidelity verification ─────────────────────────────────
    log.append(
        f"  Final SingleShot verification (N=1): gain={pi_gain_opt}, shots={full_shots} …"
    )
    fid_final, thr_final, ang_final, _, _ = _run_single_shot_at_gain(
        soc, soccfg, cfg, auto_folder,
        qubit_gain=pi_gain_opt,
        qubit_freq=qubit_freq,
        sigma=sigma,
        flattop_length=flattop_length,
        shots=full_shots,
        relax_delay=relax_delay,
        readout_time=readout_time,
        adc_offset=adc_offset,
        qubit_readout=qubit_readout,
        num_pulses=1,
        path="auto-SingleShot",
    )
    log.append(f"  Final fidelity={fid_final:.4f},  threshold={thr_final:.4f}")

    if fid_final < target_fid:
        log.append(
            f"  WARNING: final fidelity {fid_final:.4f} is below target "
            f"{target_fid:.4f}.  Proceeding anyway."
        )

    log.append(f"  pi_gain={pi_gain_opt},  pi2_gain={pi2_gain_opt}")
    return pi_gain_opt, pi2_gain_opt, fid_final, thr_final, ang_final


def _stage_run_t1(soc, soccfg, cfg, auto_folder,
                  qubit_freq, pi_gain, sigma, flattop_length,
                  qubit_readout, params, log):
    """Stage 4 – Run T1 measurement(s)."""
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 4 – T1 measurements")
    log.append("=" * 60)

    repetitions = params["T1_repetitions"]

    for i in range(repetitions):
        t1_cfg = {
            "start":        0,
            "step":         params["T1_step"],
            "expts":        params["T1_expts"],
            "reps":         params["T1_reps"],
            "rounds":       params["T1_rounds"],
            "pi_gain":      pi_gain,
            "relax_delay":  params["T1_relax_delay"],
            "sigma":        sigma,
            "flattop_length": flattop_length,
            "f_ge":         qubit_freq,
            "Qubit_number": qubit_readout,
        }
        run_cfg = cfg | t1_cfg

        iT1 = T1FF(
            path="auto-T1",
            cfg=run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=auto_folder,
        )
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=False, figNum=20)
        plt.close('all')
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        log.append(f"  T1 run {i+1}/{repetitions} saved.")
        time.sleep(5)
        soc.reset_gens()


def _stage_run_t2(soc, soccfg, cfg, auto_folder,
                  qubit_freq, pi_gain, pi2_gain, sigma, flattop_length,
                  qubit_readout, params, log):
    """Stage 5 – Run T2 Ramsey measurement(s)."""
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 5 – T2 Ramsey measurements")
    log.append("=" * 60)

    repetitions = params["T2_repetitions"]
    freq_shift  = params["T2_freq_shift"]

    # phase_step = 0 (no artificial detuning via phase advance)
    # The soccfg.deg2reg call mirrors CSTQ02_BFC.py
    try:
        phase_step = int(soccfg.deg2reg(0.0, gen_ch=cfg.get("qubit_ch", 1)))
    except Exception:
        phase_step = 0

    for i in range(repetitions):
        t2_cfg = {
            "start":        0,
            "step":         params["T2_step"],
            "phase_step":   phase_step,
            "expts":        params["T2_expts"],
            "reps":         params["T2_reps"],
            "rounds":       params["T2_rounds"],
            "pi_gain":      pi_gain,
            "pi2_gain":     pi2_gain,
            "relax_delay":  params["T2_relax_delay"],
            "f_ge":         qubit_freq + freq_shift,
            "sigma":        sigma,
            "flattop_length": flattop_length,
        }
        run_cfg = cfg | t2_cfg

        iT2R = T2R(
            path="auto-T2",
            cfg=run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=auto_folder,
        )
        dT2R = T2R.acquire(iT2R)
        T2R.display(iT2R, dT2R, plotDisp=False, figNum=21)
        plt.close('all')
        T2R.save_data(iT2R, dT2R)
        T2R.save_config(iT2R)

        log.append(f"  T2 run {i+1}/{repetitions} saved.")
        time.sleep(5)
        soc.reset_gens()


def _stage_run_t2e(soc, soccfg, cfg, auto_folder,
                   qubit_freq, pi_gain, pi2_gain, sigma, flattop_length,
                   qubit_readout, params, log):
    """Stage 6 – Run T2Echo measurement(s)."""
    log.append("")
    log.append("=" * 60)
    log.append("STAGE 6 – T2Echo measurements")
    log.append("=" * 60)

    repetitions  = params["T2E_repetitions"]
    num_pulses   = params["T2E_num_pi_pulses"]
    T2E_max_us   = params["T2E_max_us"]
    T2E_expts    = params["T2E_expts"]

    # Mirror CSTQ02_BFC.py step calculation (hardware quantisation)
    int_steps = int(T2E_max_us // (_T2E_CLOCK_STEP_US * (num_pulses + 1) * T2E_expts))
    if int_steps == 0:
        log.append(
            "  WARNING: T2E step is 0. Increase T2E_max_us or reduce T2E_expts."
        )
        int_steps = 1
    t2e_step = _T2E_CLOCK_STEP_US * (num_pulses + 1) * int_steps
    log.append(
        f"  num_pi_pulses={num_pulses}, step={t2e_step:.6f} us, "
        f"max_time={t2e_step * T2E_expts:.1f} us"
    )

    for i in range(repetitions):
        t2e_cfg = {
            "start":         0,
            "step":          t2e_step,
            "expts":         T2E_expts,
            "reps":          params["T2E_reps"],
            "rounds":        params["T2E_rounds"],
            "pi_gain":       pi_gain,
            "pi2_gain":      pi2_gain,
            "relax_delay":   params["T2E_relax_delay"],
            "f_ge":          qubit_freq,
            "num_pi_pulses": num_pulses,
            "sigma":         sigma,
            "flattop_length": flattop_length,
            "Qubit_number":  qubit_readout,
        }
        run_cfg = cfg | t2e_cfg

        iT2E = T2EMUX(
            path="auto-T2E",
            cfg=run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=auto_folder,
        )
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=False, figNum=22)
        plt.close('all')
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)

        log.append(f"  T2E run {i+1}/{repetitions} saved.")
        time.sleep(5)
        soc.reset_gens()


def _save_summary(auto_folder, timestamp, calibration, params, log):
    """Write a timestamped plain-text summary of all calibrated parameters."""
    fname = os.path.join(auto_folder, f"auto_coherence_summary_{timestamp}.txt")

    lines = [
        f"AutoCoherence calibration summary",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "─── Calibrated parameters ───────────────────────────────────────",
        f"  qubit_frequency  : {calibration.get('qubit_frequency', 'N/A')} MHz",
        f"  pi_gain          : {calibration.get('pi_gain', 'N/A')}",
        f"  pi2_gain         : {calibration.get('pi2_gain', 'N/A')}",
        f"  rabi_sigma       : {calibration.get('rabi_sigma', 'N/A')} us",
        f"  flattop_length   : {calibration.get('flattop_length', 'N/A')}",
        f"  fidelity         : {calibration.get('fidelity', 'N/A')}",
        f"  ss_threshold     : {calibration.get('ss_threshold', 'N/A')}",
        f"  ss_angle         : {calibration.get('ss_angle', 'N/A')} rad",
        f"  sweet_spot_voltage: {calibration.get('sweet_spot_voltage', 'N/A')} V",
        "",
        "─── Automation parameters used ──────────────────────────────────",
    ]
    for k, v in params.items():
        lines.append(f"  {k:<30}: {v}")
    lines += ["", "─── Run log ─────────────────────────────────────────────────────"]
    lines += log

    with open(fname, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    # Also save as JSON for easy programmatic access
    summary_json = {
        "timestamp": timestamp,
        "calibration": {k: (v if not isinstance(v, np.floating) else float(v))
                        for k, v in calibration.items()},
        "params": {k: (v if v is None or isinstance(v, (int, float, str, bool))
                       else str(v))
                   for k, v in params.items()},
    }
    with open(os.path.join(auto_folder, f"auto_coherence_summary_{timestamp}.json"), "w") as fh:
        json.dump(summary_json, fh, indent=2)

    print(f"[AutoCoherence] Summary saved to: {fname}")
    return fname


# ===========================================================================
# ─── Public entry points ────────────────────────────────────────────────────
# ===========================================================================

def find_sweet_spot(soc, soccfg, config, save_folder,
                    qubit_freq_center, qubit_readout,
                    yoko, sweet_params=None):
    """
    Standalone sweet-spot voltage search.

    Exposes Stage 1 of run_auto_coherence as a reusable function so that
    other experiment scripts (e.g. ModifiedRamsey_Control) can use the
    two-strategy search without running the full calibration pipeline.

    Strategy A (fast, when cd_period_mv is known):
        Step half a charge-dispersion period from the current voltage and
        check whether the two peaks have merged.  Typically converges in
        1–2 spec acquisitions.

    Strategy B (fallback):
        Walk incrementally tracking the minimum peak separation and return
        to the best voltage found.

    Parameters
    ----------
    soc, soccfg
        QICK hardware proxies.
    config : dict
        Full hardware config dict as built in CSTQ02_BFC.py.  NOT modified.
    save_folder : str
        Directory in which spec data are saved.  **Must end with "/"** so
        that ExperimentClass can concatenate the stage sub-folder name
        correctly (e.g. save_folder + "auto-Spec").
    qubit_freq_center : float
        Centre frequency for the two-tone spec sweep [MHz].
    qubit_readout : int
        Readout channel index passed through to QubitSpecSliceFF.
    yoko : pyvisa resource or None
        Yokogawa source for the charge line.  Pass None if unused.
    sweet_params : dict or None
        Overrides for any AUTO_COHERENCE_PARAMS keys.  Relevant ones:

        spec_span, spec_num_pts, spec_reps, spec_rounds,
        spec_relax_delay, spec_sigma, spec_gain, spec_qubit_length,
        ss_search_df_trigger  – peak sep that triggers the half-period step,
        ss_accept_sep         – sep below which the spot is accepted,
        ss_dV, ss_voltage_min, ss_voltage_max, ss_max_tries,
        cd_period_mv          – enables Strategy A when set.

    Returns
    -------
    qubit_freq : float
        Estimated qubit frequency at the sweet spot [MHz].
    sweet_spot_voltage : float or None
        Yoko voltage at the sweet spot [V], or None if yoko is None.
    peak_info : dict
        Peak information from the final two-tone spec
        (keys: peak_inds, peak_freqs, peak_vals, peak_sep).
    log : list of str
        Human-readable log of all search steps.
    """
    params = {**AUTO_COHERENCE_PARAMS, **(sweet_params or {})}
    log = []
    qubit_freq, voltage, peak_info = _stage_sweet_spot_search(
        soc=soc,
        soccfg=soccfg,
        cfg=dict(config),
        auto_folder=save_folder,
        qubit_freq_center=qubit_freq_center,
        qubit_readout=qubit_readout,
        params=params,
        yoko=yoko,
        log=log,
    )
    return qubit_freq, voltage, peak_info, log


def run_auto_coherence(soc, soccfg, config, outerFolder,
                       qubit_readout, qubit_params,
                       yoko=None, auto_params=None):
    """
    Fully-automated T1 / T2 / T2Echo calibration and measurement.

    Parameters
    ----------
    soc, soccfg
        QICK hardware proxies (from makeProxy()).
    config : dict
        Full config dict as constructed in CSTQ02_BFC.py (hardware channels,
        readout frequency, cavity gain, FF_Qubits, etc.).  NOT modified.
    outerFolder : str
        Root save directory.  All output goes into an AutoCoherence_<timestamp>
        sub-folder created here.
    qubit_readout : int
        Key into qubit_params (e.g. 4 for Qubit 4).
    qubit_params : dict
        Qubit_Parameters dictionary.  NOT modified.
    yoko : pyvisa resource or None
        Yokogawa charge-line controller.  Pass None if no charge line is used.
    auto_params : dict or None
        Optional overrides for AUTO_COHERENCE_PARAMS.  Only keys present in
        the override dict are changed; all others keep their defaults.

    Returns
    -------
    results : dict
        {
          'qubit_frequency'  : float,   # MHz
          'pi_gain'          : int,
          'pi2_gain'         : int,
          'rabi_sigma'       : float,   # us
          'flattop_length'   : value,
          'fidelity'         : float,
          'ss_threshold'     : float,
          'ss_angle'         : float,
          'sweet_spot_voltage': float or None,
          'auto_folder'      : str,
          'summary_file'     : str,
        }
    """
    # ── Merge default params with any user overrides ─────────────────────────
    params = {**AUTO_COHERENCE_PARAMS, **(auto_params or {})}

    # ── Timestamp for this run ───────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Create the folder hierarchy ──────────────────────────────────────────
    # Structure:
    #   outerFolder/
    #     AutoCoherence/          ← persistent root for all auto runs
    #       run_<timestamp>/      ← one folder per invocation
    #         auto-Spec/          ← per-stage sub-folders (created by ExperimentClass)
    #         auto-AmplitudeRabi/
    #         auto-SingleShot/
    #         auto-T1/  auto-T2/  auto-T2E/
    #
    # ExperimentClass concatenates outerFolder + path (no separator), so
    # auto_folder MUST end with "/" for stage sub-folders to land correctly.
    ac_root = os.path.join(outerFolder, "AutoCoherence")
    os.makedirs(ac_root, exist_ok=True)
    auto_folder = os.path.join(ac_root, f"run_{timestamp}") + "/"
    os.makedirs(auto_folder, exist_ok=True)
    print(f"[AutoCoherence] Starting run.  Output folder: {auto_folder}")

    # ── Read initial qubit parameters (read-only) ────────────────────────────
    q_key = str(qubit_readout)
    readout_freq    = qubit_params[q_key]["Readout"]["Frequency"]
    readout_gain    = qubit_params[q_key]["Readout"]["Gain"]
    qubit_freq_init = qubit_params[q_key]["Qubit"]["Frequency"]
    qubit_gain_init = qubit_params[q_key]["Qubit"]["Gain"]
    sigma_init      = qubit_params[q_key]["Qubit"]["sigma"]
    flattop_length  = qubit_params[q_key]["Qubit"]["flattop_length"]

    log = []
    log.append(f"Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.append(f"Qubit_readout key: {q_key}")
    log.append(f"Initial qubit_frequency: {qubit_freq_init} MHz")
    log.append(f"Initial qubit_gain: {qubit_gain_init}")
    log.append(f"Initial sigma: {sigma_init} us")
    log.append(f"flattop_length: {flattop_length}")
    log.append(f"Initial readout_freq: {readout_freq} MHz")
    log.append(f"Initial readout_gain: {readout_gain}")

    # ── Ensure readout parameters are in the working config ─────────────────
    # (config is already constructed by the caller, but we confirm the keys
    #  are present.  We never write back to the caller's config dict.)
    base_cfg = _sync_cfg_to_selected_qubit(
        cfg=config,
        qubit_readout=qubit_readout,
        readout_freq=readout_freq,
        readout_gain=readout_gain,
        qubit_freq=qubit_freq_init,
        qubit_gain=qubit_gain_init,
        sigma=sigma_init,
        flattop_length=flattop_length,
    )

    # ── Stage 1: Sweet-spot search ───────────────────────────────────────────
    if params.get("skip_sweet_spot_search", False):
        qubit_freq = qubit_freq_init
        sweet_spot_voltage = float(yoko.query(":SOUR:LEV?")) if yoko is not None else None
        peak_info = None
        log.append("")
        log.append("=" * 60)
        log.append("STAGE 1 – Sweet-spot search SKIPPED (skip_sweet_spot_search=True)")
        log.append("=" * 60)
        log.append(f"  Using qubit_frequency from qubit_params: {qubit_freq:.6f} MHz")
        log.append(f"  Holding yoko voltage at: {sweet_spot_voltage}")
    else:
        qubit_freq, sweet_spot_voltage, peak_info = _stage_sweet_spot_search(
            soc=soc,
            soccfg=soccfg,
            cfg=base_cfg,
            auto_folder=auto_folder,
            qubit_freq_center=qubit_freq_init,
            qubit_readout=qubit_readout,
            params=params,
            yoko=yoko,
            log=log,
        )

    # ── Stage 1.5: Two-tone qubit-frequency calibration ─────────────────────
    if params.get("calibrate_qubit_freq", True):
        qubit_freq, _ = _stage_calibrate_qubit_freq(
            soc=soc,
            soccfg=soccfg,
            cfg=base_cfg,
            auto_folder=auto_folder,
            qubit_freq_center=qubit_freq,
            qubit_readout=qubit_readout,
            params=params,
            log=log,
        )
    else:
        log.append("")
        log.append("STAGE 1.5 – Qubit-frequency calibration skipped (calibrate_qubit_freq=False)")

    # ── Stage 2: AmplitudeRabi ───────────────────────────────────────────────
    pi_gain, rabi_sigma = _stage_amplitude_rabi(
        soc=soc,
        soccfg=soccfg,
        cfg=base_cfg,
        auto_folder=auto_folder,
        qubit_freq=qubit_freq,
        qubit_readout=qubit_readout,
        sigma_initial=sigma_init,
        flattop_length=flattop_length,
        params=params,
        log=log,
    )

    # ── Stage 2.5: Readout parameter optimisation ───────────────────────────
    if params.get("auto_readout_opt", True):
        opt_rl, opt_ao = _stage_optimize_readout(
            soc=soc, soccfg=soccfg, cfg=base_cfg, auto_folder=auto_folder,
            qubit_freq=qubit_freq, pi_gain=pi_gain,
            sigma=rabi_sigma, flattop_length=flattop_length,
            qubit_readout=qubit_readout, params=params, log=log,
        )
        # Propagate to Stage 3 (reads from params) and T1/T2/T2E (read from cfg)
        params   = {**params,
                    "ss_readout_time": opt_rl,
                    "ss_adc_offset":   opt_ao}
        base_cfg = base_cfg | {"readout_length":  opt_rl,
                                "adc_trig_offset": opt_ao}
    else:
        log.append("")
        log.append("STAGE 2.5 – Readout optimisation skipped (auto_readout_opt=False)")

    # ── Stage 3: SingleShot / extended pi & pi2 pulse optimisation ─────────
    if params.get("extended_pi_pi2_opt", False):
        pi_gain_opt, pi2_gain_opt, fidelity, ss_threshold, ss_angle = \
            _stage_extended_pulse_opt(
                soc=soc,
                soccfg=soccfg,
                cfg=base_cfg,
                auto_folder=auto_folder,
                qubit_freq=qubit_freq,
                sigma=rabi_sigma,
                flattop_length=flattop_length,
                pi_gain_estimate=pi_gain,
                qubit_readout=qubit_readout,
                params=params,
                log=log,
            )
    else:
        pi_gain_opt, pi2_gain_opt, fidelity, ss_threshold, ss_angle = \
            _stage_singleshot_optimize(
                soc=soc,
                soccfg=soccfg,
                cfg=base_cfg,
                auto_folder=auto_folder,
                qubit_freq=qubit_freq,
                sigma=rabi_sigma,
                flattop_length=flattop_length,
                pi_gain_estimate=pi_gain,
                qubit_readout=qubit_readout,
                params=params,
                log=log,
            )

    # ── Collect calibrated parameters ────────────────────────────────────────
    calibration = {
        "qubit_frequency":   qubit_freq,
        "pi_gain":           pi_gain_opt,
        "pi2_gain":          pi2_gain_opt,
        "rabi_sigma":        rabi_sigma,
        "flattop_length":    flattop_length,
        "fidelity":          fidelity,
        "ss_threshold":      ss_threshold,
        "ss_angle":          ss_angle,
        "sweet_spot_voltage": sweet_spot_voltage,
    }

    log.append("")
    log.append("─── Calibration complete ─────────────────────────────────────────")
    for k, v in calibration.items():
        log.append(f"  {k:<25}: {v}")

    # ── Stage 4: T1 ─────────────────────────────────────────────────────────
    _stage_run_t1(
        soc=soc, soccfg=soccfg, cfg=base_cfg, auto_folder=auto_folder,
        qubit_freq=qubit_freq, pi_gain=pi_gain_opt,
        sigma=rabi_sigma, flattop_length=flattop_length,
        qubit_readout=qubit_readout, params=params, log=log,
    )

    # ── Stage 5: T2 Ramsey ──────────────────────────────────────────────────
    _stage_run_t2(
        soc=soc, soccfg=soccfg, cfg=base_cfg, auto_folder=auto_folder,
        qubit_freq=qubit_freq, pi_gain=pi_gain_opt, pi2_gain=pi2_gain_opt,
        sigma=rabi_sigma, flattop_length=flattop_length,
        qubit_readout=qubit_readout, params=params, log=log,
    )

    # ── Stage 6: T2Echo ─────────────────────────────────────────────────────
    _stage_run_t2e(
        soc=soc, soccfg=soccfg, cfg=base_cfg, auto_folder=auto_folder,
        qubit_freq=qubit_freq, pi_gain=pi_gain_opt, pi2_gain=pi2_gain_opt,
        sigma=rabi_sigma, flattop_length=flattop_length,
        qubit_readout=qubit_readout, params=params, log=log,
    )

    # ── Save summary file ────────────────────────────────────────────────────
    log.append("")
    log.append(f"Run completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_file = _save_summary(auto_folder, timestamp, calibration, params, log)

    print(f"[AutoCoherence] All done.")
    print(f"  qubit_frequency  = {qubit_freq:.6f} MHz")
    print(f"  pi_gain          = {pi_gain_opt}")
    print(f"  pi2_gain         = {pi2_gain_opt}")
    print(f"  rabi_sigma       = {rabi_sigma:.4f} us")
    print(f"  fidelity         = {fidelity:.4f}")
    print(f"  sweet_spot_voltage = {sweet_spot_voltage}")

    results = {**calibration,
               "auto_folder":   auto_folder,
               "summary_file":  summary_file}
    return results
