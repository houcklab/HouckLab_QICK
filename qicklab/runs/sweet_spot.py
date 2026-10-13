"""Standalone sweet-spot voltage search (Stage 1 of the auto-coherence pipeline)."""

from qicklab.runs.auto_coherence import AUTO_COHERENCE_PARAMS, _stage_sweet_spot_search


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
