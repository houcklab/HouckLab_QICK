"""CSTQ03 measurement routines, extracted from the monolithic CSTQ03_BFC.py runner.

Each `run_*` takes `(ctx, params...)` and reproduces one of the original `if RunX:`
blocks.
"""

from datetime import datetime

from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter
from sklearn.cluster import KMeans

from qicklab.experiments.active_reset_verify import ActiveResetVerify
from qicklab.experiments.charge_dispersion import ChargeDispersion, ChargeDispersionQuasiCW
from qicklab.experiments.chi_shift import ChiShift
from qicklab.experiments.cw_tones import ConstantTwoTone, SingleTone
from qicklab.experiments.modified_ramsey import ModifiedRamsey, build_control_variants
from qicklab.experiments.qubit_spec import QubitSpecSliceFF
from qicklab.experiments.rabi import AmplitudeRabiFF, AmplitudeRabiFF_N
from qicklab.experiments.readout_optimize import QubitPulseOpt_wSingleShotFF, ReadOpt_wSingleShotFF
from qicklab.experiments.single_shot import SingleShotProgramFFMUX
from qicklab.experiments.t1 import T1FF
from qicklab.experiments.t1_single_shot import T1_SS
from qicklab.experiments.t2_echo import T2EMUX
from qicklab.experiments.transmission import CavitySpecFF
from qicklab.experiments.zero_span_parity import ZeroSpanParity
from qicklab.runs.interleave import run_interleaved_coherence
from qicklab.runs.zero_span import run_zero_span_parity
from qicklab.runs.zero_span_validation import (
    build_evidence_report,
    run_contrast_vs_qubit_freq,
    run_control_suite,
    run_environment_sweep,
    run_modulation_check,
    run_static_contrast,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ModifiedRamseyParity import (
    analyze_modified_ramsey_record,
    calibrate_readout_from_labeled_shots,
    compare_parity_controls,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import (
    analyze_parity_run,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAutoCoherence import (
    AUTO_COHERENCE_PARAMS,
    find_sweet_spot,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mUndrivenSingleShot import (
    UndrivenSingleShot,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import (
    acquire_with_retry,
    analyze_charge_dispersion,
    choose_next_voltage,
    choose_two_tone_freqs_from_lorentz_or_peaks,
    chunked_acquire,
    classify_and_average_iq,
    cos_func,
    estimate_noise_floor,
    find_two_tone_peaks,
    fit_hanger_transmission,
    fit_lorentzian_feature,
    fit_rabi_cosine,
    hanger_model_db,
    lorentzian_dip,
    lorentzian_peak,
    modulated_strobe_acquire,
    pick_parity_drive_freq,
    project_iq_onto_separator,
    project_iq_signal,
    ramp_to,
    save_two_tone_plot,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.basic import (
    run_amplitude_rabi,
    run_chi_shift,
    run_constant_tone,
    run_constant_two_tone,
    run_spec_gain_length_sweep,
    run_trans_qubit_spec,
    run_transmission_fit,
    run_transmission_sweep,
    run_two_tone_spec,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.calibration import (
    calibrate_active_reset_readout,
    get_apriori_separator_from_singleshot,
    wire_reset_into_mr_cfg,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.charge_parity import (
    modified_ramsey_timing,
    run_charge_dispersion_quasicw,
    run_charge_dispersion_ramsey,
    run_charge_sweep,
    run_charge_transmission_sweep,
    run_modified_ramsey,
    run_modified_ramsey_control,
    run_two_tone_charge_dispersion_quasicw,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.coherence import (
    run_auto_coherence,
    run_t1,
    run_t1_ss,
    run_t1_t2e,
    run_t1_t2r_t2e,
    run_t2,
    run_t2e,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.context import (
    Context,
    build_context,
    rebuild_singleshot_config,
    sanity_dump,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Runners.runs.singleshot import (
    run_active_reset_verify,
    run_qubit_optimize,
    run_readout_optimize,
    run_single_shot,
    run_undriven_single_shot,
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
