"""Measurement routines: each `run_*(ctx, params...)` is one `if RunX:` block of the legacy runner.

`__all__` also re-exports the helpers runners/CSTQ03_BFC.py gets from its star import (until phase 5).
"""

from datetime import datetime

from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter
from sklearn.cluster import KMeans

from qicklab.analysis.fitting import (
    cos_func,
    estimate_noise_floor,
    fit_hanger_transmission,
    fit_lorentzian_feature,
    fit_rabi_cosine,
    hanger_model_db,
    lorentzian_dip,
    lorentzian_peak,
)
from qicklab.analysis.iq import (
    classify_and_average_iq,
    project_iq_onto_separator,
    project_iq_signal,
)
from qicklab.analysis.modified_ramsey import (
    analyze_modified_ramsey_record,
    compare_parity_controls,
)
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.analysis.spectroscopy import (
    analyze_charge_dispersion,
    choose_two_tone_freqs_from_lorentz_or_peaks,
    find_two_tone_peaks,
    pick_parity_drive_freq,
    save_two_tone_plot,
)
from qicklab.analysis.zero_span import analyze_parity_run
from qicklab.core.acquisition import (
    acquire_with_retry,
    chunked_acquire,
    modulated_strobe_acquire,
)
from qicklab.core.config import rebuild_singleshot_config, sanity_dump
from qicklab.core.context import Context, build_context
from qicklab.experiments.active_reset_verify import ActiveResetVerify
from qicklab.experiments.charge_dispersion import ChargeDispersion, ChargeDispersionQuasiCW
from qicklab.experiments.chi_shift import ChiShift
from qicklab.experiments.cw_tones import ConstantTwoTone, SingleTone
from qicklab.experiments.modified_ramsey import (
    ModifiedRamsey,
    build_control_variants,
    modified_ramsey_timing,
)
from qicklab.experiments.qubit_spec import QubitSpecSliceFF
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N
from qicklab.experiments.readout_optimize import QubitPulseOpt_wSingleShotFF, ReadOpt_wSingleShotFF
from qicklab.experiments.single_shot import SingleShotProgramFFMUX
from qicklab.experiments.t1 import T1FF
from qicklab.experiments.t1_single_shot import T1_SS
from qicklab.experiments.t2_echo import T2EMUX
from qicklab.experiments.t2_ramsey import T2R
from qicklab.experiments.transmission import CavitySpecFF
from qicklab.experiments.undriven_single_shot import UndrivenSingleShot
from qicklab.experiments.zero_span_parity import ZeroSpanParity
from qicklab.hardware.yoko import ramp_to
from qicklab.runs.active_reset import (
    calibrate_active_reset_readout,
    run_active_reset_verify,
    wire_reset_into_mr_cfg,
)
from qicklab.runs.auto_coherence import AUTO_COHERENCE_PARAMS, run_auto_coherence
from qicklab.runs.charge_dispersion import (
    run_charge_dispersion_quasicw,
    run_charge_dispersion_ramsey,
    run_two_tone_charge_dispersion_quasicw,
)
from qicklab.runs.charge_sweep import (
    choose_next_voltage,
    run_charge_sweep,
    run_charge_transmission_sweep,
)
from qicklab.runs.coherence import (
    run_t1,
    run_t1_t2e,
    run_t1_t2r_t2e,
    run_t2,
    run_t2e,
)
from qicklab.runs.interleave import run_interleaved_coherence
from qicklab.runs.modified_ramsey import run_modified_ramsey, run_modified_ramsey_control
from qicklab.runs.rabi import run_amplitude_rabi
from qicklab.runs.resonator import (
    run_chi_shift,
    run_constant_tone,
    run_constant_two_tone,
    run_transmission_fit,
    run_transmission_sweep,
)
from qicklab.runs.single_shot import (
    get_apriori_separator_from_singleshot,
    run_qubit_optimize,
    run_readout_optimize,
    run_single_shot,
    run_t1_ss,
    run_undriven_single_shot,
)
from qicklab.runs.spectroscopy import (
    run_spec_gain_length_sweep,
    run_trans_qubit_spec,
    run_two_tone_spec,
)
from qicklab.runs.sweet_spot import find_sweet_spot
from qicklab.runs.zero_span import run_zero_span_parity
from qicklab.runs.zero_span_validation import (
    build_evidence_report,
    run_contrast_vs_qubit_freq,
    run_control_suite,
    run_environment_sweep,
    run_modulation_check,
    run_static_contrast,
)

__all__ = [
    "AUTO_COHERENCE_PARAMS",
    "ActiveResetVerify",
    "AmplitudeRabiFF",
    "AmplitudeRabiFF_N",
    "CavitySpecFF",
    "ChargeDispersion",
    "ChargeDispersionQuasiCW",
    "ChiShift",
    "ConstantTwoTone",
    "Context",
    "KMeans",
    "ModifiedRamsey",
    "QubitPulseOpt_wSingleShotFF",
    "QubitSpecSliceFF",
    "ReadOpt_wSingleShotFF",
    "SingleShotProgramFFMUX",
    "SingleTone",
    "T1FF",
    "T1_SS",
    "T2EMUX",
    "T2R",
    "UndrivenSingleShot",
    "ZeroSpanParity",
    "acquire_with_retry",
    "analyze_charge_dispersion",
    "analyze_modified_ramsey_record",
    "analyze_parity_run",
    "build_context",
    "build_control_variants",
    "build_evidence_report",
    "calibrate_active_reset_readout",
    "calibrate_readout_from_labeled_shots",
    "choose_next_voltage",
    "choose_two_tone_freqs_from_lorentz_or_peaks",
    "chunked_acquire",
    "classify_and_average_iq",
    "compare_parity_controls",
    "cos_func",
    "curve_fit",
    "datetime",
    "estimate_noise_floor",
    "find_peaks",
    "find_sweet_spot",
    "find_two_tone_peaks",
    "fit_hanger_transmission",
    "fit_lorentzian_feature",
    "fit_rabi_cosine",
    "get_apriori_separator_from_singleshot",
    "hanger_model_db",
    "lorentzian_dip",
    "lorentzian_peak",
    "modified_ramsey_timing",
    "modulated_strobe_acquire",
    "pick_parity_drive_freq",
    "project_iq_onto_separator",
    "project_iq_signal",
    "ramp_to",
    "rebuild_singleshot_config",
    "run_active_reset_verify",
    "run_amplitude_rabi",
    "run_auto_coherence",
    "run_charge_dispersion_quasicw",
    "run_charge_dispersion_ramsey",
    "run_charge_sweep",
    "run_charge_transmission_sweep",
    "run_chi_shift",
    "run_constant_tone",
    "run_constant_two_tone",
    "run_contrast_vs_qubit_freq",
    "run_control_suite",
    "run_environment_sweep",
    "run_interleaved_coherence",
    "run_modified_ramsey",
    "run_modified_ramsey_control",
    "run_modulation_check",
    "run_qubit_optimize",
    "run_readout_optimize",
    "run_single_shot",
    "run_spec_gain_length_sweep",
    "run_static_contrast",
    "run_t1",
    "run_t1_ss",
    "run_t1_t2e",
    "run_t1_t2r_t2e",
    "run_t2",
    "run_t2e",
    "run_trans_qubit_spec",
    "run_transmission_fit",
    "run_transmission_sweep",
    "run_two_tone_charge_dispersion_quasicw",
    "run_two_tone_spec",
    "run_undriven_single_shot",
    "run_zero_span_parity",
    "sanity_dump",
    "save_two_tone_plot",
    "savgol_filter",
    "wire_reset_into_mr_cfg",
]
