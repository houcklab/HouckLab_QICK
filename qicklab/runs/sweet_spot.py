"""Standalone sweet-spot voltage search (Stage 1 of the auto-coherence pipeline)."""

from qicklab.runs.auto_coherence import AUTO_COHERENCE_PARAMS, _stage_sweet_spot_search


def find_sweet_spot(
    soc, soccfg, config, save_folder, qubit_freq_center, qubit_readout, yoko, sweet_params=None
):
    """Stage 1 of run_auto_coherence on its own: move the yoko to the charge sweet spot.

    `save_folder` must end with "/"; strategies and sweet_params keys: docs/experiments/auto_coherence.md
    Returns (qubit_freq, sweet_spot_voltage, peak_info, log).
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
