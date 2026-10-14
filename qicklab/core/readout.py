"""Readout window and resonator-tone coverage, converted on each owning clock.

The ADC trigger offset is in tProc cycles, the integration window in readout cycles
and the tone in generator cycles; the tone is then extended by the fewest generator
cycles that cover the quantised ADC window. See docs/concepts/readout_window.md.
"""

import numpy as np


def cover_readout_window(prog, cfg):
    """Set prog.adc_trig_offset_cycles, .readout_window_cycles (per ro ch),
    .readout_tone_cycles and .readout_tone_extension_cycles (ModifiedRamsey version)."""
    required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
    cfg.setdefault("length", required_tone_us)
    if cfg["length"] < required_tone_us:
        raise ValueError(
            "cfg['length'] must cover cfg['adc_trig_offset'] + "
            f"cfg['readout_length'] ({cfg['length']} us < "
            f"{required_tone_us} us)"
        )

    prog.adc_trig_offset_cycles = prog.us2cycles(cfg["adc_trig_offset"])
    requested_tone_cycles = prog.us2cycles(cfg["length"], gen_ch=cfg["res_ch"])
    if not cfg["ro_chs"]:
        raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
    prog.readout_window_cycles = {
        ch: prog.us2cycles(cfg["readout_length"], ro_ch=ch) for ch in cfg["ro_chs"]
    }

    f_time = prog.soccfg["tprocs"][0]["f_time"]
    res_f_fabric = prog.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
    adc_end_tproc = max(
        prog.adc_trig_offset_cycles
        + prog.readout_window_cycles[ch] * f_time / prog.soccfg["readouts"][ch]["f_output"]
        for ch in cfg["ro_chs"]
    )
    required_tone_cycles = int(np.ceil(adc_end_tproc * res_f_fabric / f_time - 1e-12))
    prog.readout_tone_cycles = max(requested_tone_cycles, required_tone_cycles)
    prog.readout_tone_extension_cycles = prog.readout_tone_cycles - requested_tone_cycles
