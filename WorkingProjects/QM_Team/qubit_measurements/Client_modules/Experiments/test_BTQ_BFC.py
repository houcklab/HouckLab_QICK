"""
test_BTQ_BFC.py — Per-device orchestrator for the test_BTQ_BFC device.

Patterned after CSTQ02_BFC.py. Built once the test_BTQ_BFC chip is mounted;
Qubit_Parameters values are placeholders until device characterization fills
them in.

Workflow (set the boolean flags below and run this file):
  1. Optional transmission / spec calibration         (RunTransmissionSweep, Run2ToneSpec)
  2. **Coherence-benchmark block** (T1, T2R, T2E)     (RunT1, RunT2R, RunT2E)
       Standard step on every new device; see memory feedback_coherence_benchmark.md
  3. Optional single-shot readout calibration         (RunSingleShot)
  4. Zero-span parity measurement                     (RunZeroSpanParity)

────────────────────────────────────────────────────────────────────────────────
ZERO-SPAN PARITY — PER-RUN PARAMETERS
────────────────────────────────────────────────────────────────────────────────
Always required:
  Qubit_Target              int 1-N       row of Qubit_Parameters
  RunMode                   "strobe"|"decimated"   Path A (v1) | Path B (v2)
  StartSrc                  "internal"|"external"  spontaneous | triggered
  RecalibrateParityFreqs    bool           run narrow QubitSpecSliceFF first
  RecalibrateSeparator      bool           run single-shot pi-pulse calib
  ParityFreqs_Cached["which_to_park"]      "lower"|"higher"

Required if RecalibrateParityFreqs=False:
  ParityFreqs_Cached["lower_peak_MHz" | "higher_peak_MHz"]

Required if RecalibrateSeparator=False:
  Separator_Cached["g_center","e_center","normal","midpoint"]  np.ndarray(2,)

Strobe-mode (Path A):  sample_period_us, reps_per_chunk, n_chunks,
                       read_length, adc_trig_offset
Decimated-mode (Path B): capture_length_us, soft_avgs, n_captures,
                       read_length, adc_trig_offset

Drive: qubit_gain, pulse_gain, res_phase
Analysis: classifier_method, window_us, k_sigma,
          min_burst_duration_us, save_plots

Hard constraints (validated at start — fail-fast):
  sample_period_us >= adc_trig_offset + read_length + 1.0
  us2cycles(sample_period_us or capture_length_us) <= 65535
  reps_per_chunk   <= soccfg['readouts'][ro_ch]['avg_maxlen']
  capture samples  <= soccfg['readouts'][ro_ch]['buf_maxlen']
  Cached fields must be non-None when their Recalibrate flag is False.

Canonical full reference:
  docs/superpowers/specs/2026-05-16-bfc-charge-parity-zero-span-design.md §5
"""

import os
import numpy as np
import pyvisa

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import makeProxy
# Calibration / yoko helpers
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
# (uncomment once initialize4Q.py is configured for the test_BTQ_BFC setup)

# Existing experiments — copy in additional imports as device characterization progresses.
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX

# New zero-span parity modules
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    pick_parity_drive_freq, chunked_acquire, ramp_to,
)


# ============================================================================
# Hardware setup
# ============================================================================
soc, soccfg = makeProxy()

# yoko (mirrors CSTQ02_BFC.py)
start_voltage = 0.000
rm = pyvisa.ResourceManager()
yoko = rm.open_resource('GPIB1::9::INSTR')
yoko.write(":SOUR:FUNC VOLT")
yoko.write(":OUTP ON")
ramp_to(yoko, start_voltage)


# ============================================================================
# Qubit_Parameters — TODO: fill in values once test_BTQ_BFC is characterized
# ============================================================================
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': None, 'Gain': None},
        'Qubit':   {'Frequency': None, 'Gain': None, 'pi2_Gain': None,
                    'sigma': None, 'flattop_length': None},
        'outerfoldername': "V:/t1Team/Data/TBD_test_BTQ_BFC_cooldown/test_BTQ_BFC/RFSOC/Q1//",
    },
    # add rows '2', '3', ... as the device has more qubits
}


# ============================================================================
# Run flags — toggle these between runs
# ============================================================================
Qubit_Target = '1'

RunTransmissionSweep   = False    # cavity spec
Run2ToneSpec           = False    # qubit spec
RunT1                  = False    # coherence benchmark
RunT2R                 = False    # coherence benchmark
RunT2E                 = False    # coherence benchmark
RunSingleShot          = False    # readout calibration
RunZeroSpanParity      = False    # this spec


# ============================================================================
# Zero-span parity block — see module docstring for parameter meanings
# ============================================================================

# --- Calibration cache (filled by recalibration or set manually) -------------
ParityFreqs_Cached = {
    "lower_peak_MHz":  None,
    "higher_peak_MHz": None,
    "which_to_park":   "lower",
}
Separator_Cached = {
    "g_center": None, "e_center": None, "normal": None, "midpoint": None,
}

# --- Recalibration toggles ---------------------------------------------------
RecalibrateParityFreqs = True
RecalibrateSeparator   = True

# --- Acquisition mode --------------------------------------------------------
RunMode  = "strobe"          # "strobe" | "decimated"
StartSrc = "internal"        # "internal" | "external"

# --- Strobe-mode params (Path A) ---------------------------------------------
# sample_period_us : temporal resolution; floor = adc_trig_offset + read_length + 1.0 us
# reps_per_chunk   : capped at runtime by soccfg['readouts'][ro_ch]['avg_maxlen']
# n_chunks         : total record (s) = reps_per_chunk*n_chunks*sample_period_us*1e-6
StrobeParams = {
    "sample_period_us": 20.0,
    "reps_per_chunk":   50000,
    "n_chunks":         12,
    "read_length":      5.0,
    "adc_trig_offset":  0.488,
}

# --- Decimated-mode params (Path B) ------------------------------------------
# capture_length_us : capped at runtime by buf_maxlen / decimated_fs
# soft_avgs         : 1 = burst-resolved single shot; >1 = software-averaged
# n_captures        : outer loop, useful for triggered campaigns
DecimatedParams = {
    "capture_length_us": 1000.0,
    "soft_avgs":         1,
    "n_captures":        1,
    "read_length":       1000.0,
    "adc_trig_offset":   0.488,
}

# --- Drive parameters --------------------------------------------------------
def _drive_params_for(qt):
    return {
        "qubit_gain": Qubit_Parameters[qt]["Qubit"]["Gain"],
        "pulse_gain": Qubit_Parameters[qt]["Readout"]["Gain"],
        "res_phase":  0,
    }

# --- Analysis params ---------------------------------------------------------
AnalysisParams = {
    "classifier_method":       "apriori",
    "window_us":               1000.0,
    "k_sigma":                 5.0,
    "min_burst_duration_us":   None,
    "save_plots":              True,
}


# ============================================================================
# Execution
# ============================================================================
if RunZeroSpanParity:
    outerFolder = Qubit_Parameters[Qubit_Target]['outerfoldername'] + "ZeroSpanParity/"
    os.makedirs(outerFolder, exist_ok=True)

    # ---- Step 1: optional parity-freq pre-calibration -----------------------
    if RecalibrateParityFreqs:
        # TODO: build spec_cfg from BaseConfig + Qubit_Parameters[Qubit_Target]
        # once initialize4Q.py is configured for test_BTQ_BFC. The block below
        # is the canonical pattern — fill in the cfg dict.
        spec_cfg = {}  # FILL IN — see QubitSpecSliceFF expected keys
        raise NotImplementedError(
            "Implement spec_cfg construction once test_BTQ_BFC is characterized "
            "(see CSTQ02_BFC.py Run2ToneSpec block for the pattern)."
        )
        spec_exp  = QubitSpecSliceFF(soc=soc, soccfg=soccfg,
                                      path="ParityRecal_Spec",
                                      outerFolder=outerFolder, cfg=spec_cfg)
        spec_data = spec_exp.acquire(progress=True)
        spec_exp.display(spec_data, plotDisp=False)
        spec_exp.save_data(spec_data); spec_exp.save_config()
        chosen = pick_parity_drive_freq(spec_data,
                                         which=ParityFreqs_Cached["which_to_park"])
        ParityFreqs_Cached["lower_peak_MHz"]  = chosen["lower"]
        ParityFreqs_Cached["higher_peak_MHz"] = chosen["higher"]
        parity_drive_freq_MHz = chosen["picked"]
    else:
        which = ParityFreqs_Cached["which_to_park"]
        parity_drive_freq_MHz = (ParityFreqs_Cached["lower_peak_MHz"]
                                 if which == "lower"
                                 else ParityFreqs_Cached["higher_peak_MHz"])
        if parity_drive_freq_MHz is None:
            raise RuntimeError(
                "No cached parity freq and RecalibrateParityFreqs=False. "
                "Either set ParityFreqs_Cached or set RecalibrateParityFreqs=True."
            )

    # ---- Step 2: optional g/e separator pre-calibration ---------------------
    if RecalibrateSeparator:
        # TODO: implement single-shot calibration call once SingleShotProgramFFMUX
        # cfg is set for test_BTQ_BFC. See CSTQ02_BFC.py
        # get_apriori_separator_from_singleshot for the canonical pattern.
        raise NotImplementedError(
            "Implement single-shot separator calibration once test_BTQ_BFC is "
            "characterized (see CSTQ02_BFC.py get_apriori_separator_from_singleshot)."
        )
    else:
        if AnalysisParams["classifier_method"] == "apriori":
            for k in ("g_center", "e_center", "normal", "midpoint"):
                if Separator_Cached[k] is None:
                    raise RuntimeError(
                        f"Separator_Cached['{k}'] is None and classifier_method "
                        f"is 'apriori'. Either populate Separator_Cached or set "
                        f"RecalibrateSeparator=True or classifier_method='kmeans'."
                    )

    # ---- Step 3: build the ZeroSpanParity cfg -------------------------------
    drive = _drive_params_for(Qubit_Target)
    mode_params = StrobeParams if RunMode == "strobe" else DecimatedParams
    zsp_cfg = {
        # Channel routing (TODO: source from BaseConfig once initialize4Q is set up)
        "res_ch":     0,
        "qubit_ch":   1,
        "ro_chs":     [0],
        "nqz":        2,
        "qubit_nqz":  2,
        "mixer_freq": 0.0,
        # Frequencies
        "read_pulse_freq":   Qubit_Parameters[Qubit_Target]["Readout"]["Frequency"],
        "parity_drive_freq": parity_drive_freq_MHz,
        # Drive
        **drive,
        # Mode + start
        "mode":      RunMode,
        "start_src": StartSrc,
        # Mode-specific
        **mode_params,
    }

    # ---- Step 4: run acquisition --------------------------------------------
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg,
                         path="ZeroSpanParity",
                         outerFolder=outerFolder, cfg=zsp_cfg)
    if RunMode == "strobe" and StrobeParams["n_chunks"] > 1:
        data = chunked_acquire(exp, n_chunks=StrobeParams["n_chunks"], progress=True)
        # When stitched, replace exp.data so save_data writes the stitched arrays.
        exp.data = {"data": data}
    else:
        data = exp.acquire(progress=True)

    exp.save_data(); exp.save_config()

    # ---- Step 5: offline analysis -------------------------------------------
    separator = (Separator_Cached
                 if AnalysisParams["classifier_method"] == "apriori" else None)
    analyze_parity_run(
        h5_path=exp.fname,
        separator=separator,
        window_us=AnalysisParams["window_us"],
        k_sigma=AnalysisParams["k_sigma"],
        classifier_method=AnalysisParams["classifier_method"],
        min_burst_duration_us=AnalysisParams["min_burst_duration_us"],
        save_plots=AnalysisParams["save_plots"],
        out_dir=os.path.dirname(exp.fname),
    )

    print(f"ZeroSpanParity complete. Data: {exp.fname}")
