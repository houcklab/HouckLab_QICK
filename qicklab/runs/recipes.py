"""Step recipes: one keyword-only function per canonical step, each returning a `Step`.

`from qicklab.runs import recipes as R`; `PLAN = [R.transmission_fit(), R.t1(relax_delay=5000)]`.
A misspelt keyword raises TypeError. `Step.fn` is the run_* function; `Step.params` maps each
of its argument slots to the legacy-keyed dict that run_* reads (docs/running_a_session.md).

None means "resolved at run time" (`Step.arguments`): on a session-group key, the group's
value; on a device key, the pulse qubit's value (`Qubit.freq`, `Qubit.parity`); on an
optional key, left out so the run's own default applies. Library defaults are the CSTQ03
runner's values except FROZEN_DIFFERENCES. Per-step pages: docs/experiments/<step>.md.
"""

import copy
import functools
from dataclasses import dataclass

from qicklab.analysis.spectroscopy import MIN_PARTNER_SNR
from qicklab.core.session import GROUPS, Step
from qicklab.runs import groups as G
from qicklab.runs.active_reset import run_active_reset_verify
from qicklab.runs.auto_coherence import AUTO_COHERENCE_PARAMS, run_auto_coherence
from qicklab.runs.charge_dispersion import (
    run_charge_dispersion_quasicw,
    run_charge_dispersion_ramsey,
    run_two_tone_charge_dispersion_quasicw,
)
from qicklab.runs.charge_sweep import run_charge_sweep, run_charge_transmission_sweep
from qicklab.runs.coherence import run_t1, run_t1_t2e, run_t1_t2r_t2e, run_t2, run_t2e
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
from qicklab.runs.zero_span import run_zero_span_parity


@dataclass(frozen=True)
class _Slot:
    """One positional argument of a run_*: a session group (overrides) or the step's own value."""

    name: str
    keys: tuple = ()  # ((legacy key, keyword), ...) in legacy key order
    drop_none: frozenset = frozenset()  # own keys left out when None (the run's default applies)
    device: object = None  # (value, qubit) -> value with device-dependent Nones filled
    scalar: bool = False  # the slot is one keyword's value, not a dict
    output: bool = False  # the run writes into it: passed by identity, never copied


@dataclass(frozen=True)
class _Recipe:
    fn: object
    regime: str
    slots: tuple


_RECIPES = {}


def _register(name, fn, regime, *slots):
    _RECIPES[name] = _Recipe(fn, regime, slots)


def _resolve(recipe, params, qubit):
    """Step.resolve: group overrides without the Nones, own slots copied and device-resolved."""
    out = {}
    for slot in recipe.slots:
        value = params[slot.name]
        if slot.name in GROUPS:
            value = {k: v for k, v in value.items() if v is not None}
        elif isinstance(value, dict) and not slot.output:
            value = dict(value)
        if slot.device is not None and (slot.scalar or value is not None):
            value = slot.device(value, qubit)
        if slot.drop_none and isinstance(value, dict):
            value = {k: v for k, v in value.items() if v is not None or k not in slot.drop_none}
        out[slot.name] = value
    return out


def _step(name, values, **own):
    """The Step of recipe `name` from its keyword values; `own` supplies hand-built slots."""
    recipe = _RECIPES[name]
    params = {}
    for slot in recipe.slots:
        if slot.name in own:
            params[slot.name] = own[slot.name]
        elif slot.scalar:
            params[slot.name] = values[slot.keys[0][1]]
        else:
            params[slot.name] = {legacy: values[kw] for legacy, kw in slot.keys}
    return Step(
        name=name,
        fn=recipe.fn,
        regime=recipe.regime,
        needs=tuple(s.name for s in recipe.slots),
        params=params,
        resolve=functools.partial(_resolve, recipe),
        fill_groups=G.resolve,
    )


def _parity(qubit):
    return getattr(qubit, "parity", None)


def _need(step, what, value, hint):
    if value is None:
        raise ValueError(f"{step}: {what} is None and the pulse qubit has none ({hint})")
    return value


def _keys(*names):
    """((legacy, keyword), ...) for legacy keys whose keyword is their lower-case form."""
    return tuple((n, n.lower()) for n in names)


_CW = _Slot("cw_params", (("hold_s", "hold_s"),))


def constant_tone(*, hold_s=None):
    """CW resonator tone (SingleTone) until Enter, or for hold_s [s].

    docs/experiments/cw_tones.md
    """
    return _step("constant_tone", locals())


def constant_two_tone(*, hold_s=None):
    """CW resonator + qubit tones (ConstantTwoTone) until Enter, or for hold_s [s].

    The tone period is the tones group's tone_length. docs/experiments/cw_tones.md
    """
    return _step("constant_two_tone", locals())


_TRANSMISSION_OVERRIDES = _Slot("transmission", (("reps", "reps"), ("rounds", "rounds")))


def transmission_fit(*, reps=None, rounds=None):
    """Resonator sweep + hanger fit (CavitySpecFF); carries the fitted dip to pulse_freq.

    reps / rounds: hardware / software averages (None: the transmission group's).
    docs/experiments/transmission_fit.md
    """
    return _step("transmission_fit", locals())


def transmission_sweep(*, reps=None, rounds=None):
    """Resonator sweep (CavitySpecFF); carries the dip (or peak) to pulse_freq.

    reps / rounds: hardware / software averages (None: the transmission group's).
    docs/experiments/transmission_sweep.md
    """
    return _step("transmission_sweep", locals())


def chi_shift(
    *, reps=10, rounds=100, trans_span=1, trans_num_points=101, cavity_shift=0.2, relax_delay=4000
):
    """Resonator sweep with and without a pi pulse (ChiShift): dispersive shift.

    reps / rounds averages; trans_span [MHz]: sweep is pulse_freq + cavity_shift [MHz] +- span
    over trans_num_points; relax_delay [us]. Merged into the step's cfg.
    docs/experiments/chi_shift.md
    """
    return _step("chi_shift", locals())


_SPEC_PEAKS = (
    ("display", "display"),
    ("min_sep_MHz", "min_sep_mhz"),
    ("fit_window_mhz", "fit_window_mhz"),
    ("prominent_ratio", "prominent_ratio"),
)


def two_tone_spec(
    *,
    reps=None,
    rounds=None,
    gauss=None,
    sigma=None,
    gain=None,
    qubit_length=None,
    spec_span=None,
    spec_num_points=None,
    relax_delay=None,
    display=None,
    min_sep_mhz=None,
    fit_window_mhz=None,
    prominent_ratio=None,
):
    """Two-tone qubit spectroscopy (QubitSpecSliceFF) around the pulse qubit's frequency.

    Every keyword overrides the spec group's (None: the group's): see groups.spec for units.
    docs/experiments/two_tone_spec.md
    """
    return _step("two_tone_spec", locals())


def spec_gain_length_sweep(
    *,
    sweep_lengths=None,
    sweep_gains=None,
    reps=None,
    rounds=None,
    gauss=None,
    sigma=None,
    spec_span=None,
    spec_num_points=None,
    relax_delay=None,
    display=None,
    min_sep_mhz=None,
    fit_window_mhz=None,
    prominent_ratio=None,
):
    """Two-tone spec on the sweep_lengths [us] x sweep_gains [DAC] grid + saturation summary.

    Every keyword overrides the spec group's (None: the group's).
    docs/experiments/spec_gain_length_sweep.md
    """
    values = dict(locals())
    for kw in ("sweep_lengths", "sweep_gains"):
        if values[kw] is not None:
            values[kw] = list(values[kw])
    return _step("spec_gain_length_sweep", values)


def trans_qubit_spec(
    *,
    gain=None,
    relax_delay=None,
    reps=None,
    rounds=None,
    gauss=None,
    sigma=None,
    min_sep_mhz=None,
    fit_window_mhz=None,
    prominent_ratio=None,
    repetitions=None,
):
    """The two-tone spec repeated `repetitions` times (a time series of the qubit line).

    Spec keywords override the spec group's; repetitions overrides the coherence group's.
    docs/experiments/trans_qubit_spec.md
    """
    return _step("trans_qubit_spec", locals())


def _rabi_device(d, qubit):
    if d["qubit_freq"] is None:
        d["qubit_freq"] = _need(
            "amplitude_rabi", "qubit_freq", getattr(qubit, "freq", None), "pass qubit_freq= [MHz]"
        )
    return d


def amplitude_rabi(
    *,
    qubit_freq=None,
    max_gain=10000,
    number_of_steps=101,
    reps=10,
    rounds=10,
    relax_delay=3000,
    fit=False,
    flattop_relax_delay=8000,
):
    """Drive-amplitude sweep 0..max_gain [DAC] in number_of_steps (AmplitudeRabiFF[_N]): pi gain.

    qubit_freq [MHz] (None: the pulse qubit's freq); reps / rounds averages; relax_delay [us]
    (flattop_relax_delay [us] for a flat-top qubit); fit: cosine fit in the display.
    docs/experiments/amplitude_rabi.md
    """
    return _step("amplitude_rabi", locals())


_T1_KEYS = (
    ("T1_step", "t1_step"),
    ("T1_expts", "t1_expts"),
    ("T1_reps", "t1_reps"),
    ("T1_rounds", "t1_rounds"),
)
_T2R_KEYS = (
    ("T2_step", "t2_step"),
    ("T2_expts", "t2_expts"),
    ("T2_reps", "t2_reps"),
    ("T2_rounds", "t2_rounds"),
)
_ECHO_IN_COMBOS = _Slot(
    "echo",
    (
        ("T2_max_us", "t2e_max_us"),
        ("T2_expts", "t2e_expts"),
        ("T2_reps", "t2e_reps"),
        ("T2_rounds", "t2e_rounds"),
        ("freq_shift", "t2e_freq_shift"),
        ("relax_delay", "t2e_relax_delay"),
        ("num_pi_pulses", "num_pi_pulses"),
        ("rotation_angle", "rotation_angle"),
        ("min_max", "min_max"),
    ),
)


def t1(
    *,
    t1_step=None,
    t1_expts=None,
    t1_reps=None,
    t1_rounds=None,
    relax_delay=None,
    repetitions=None,
    plot_disp=None,
):
    """T1 (T1FF): pi pulse, wait, read. Keywords override the coherence group's (groups.coherence).

    plot_disp: show the plot (None: only when repetitions <= 1). docs/experiments/t1.md
    """
    return _step("t1", locals())


def t2_ramsey(
    *,
    t2_step=None,
    t2_expts=None,
    t2_reps=None,
    t2_rounds=None,
    freq_shift=None,
    relax_delay=None,
    repetitions=None,
    f_virt_mhz=None,
):
    """T2 Ramsey (T2R). Keywords override the coherence group's (groups.coherence).

    f_virt_mhz [MHz]: virtual detuning (None: 5 fringes per window). docs/experiments/t2_ramsey.md
    """
    return _step("t2_ramsey", locals())


def t2_echo(
    *,
    t2_max_us=None,
    t2_expts=None,
    t2_reps=None,
    t2_rounds=None,
    freq_shift=None,
    relax_delay=None,
    num_pi_pulses=None,
    rotation_angle=None,
    min_max=None,
    repetitions=None,
    plot_disp=None,
):
    """T2 echo / CPMG (T2EMUX). Keywords override the echo group's (groups.echo).

    plot_disp: show the plot (None: only when repetitions <= 1). docs/experiments/t2_echo.md
    """
    return _step("t2_echo", locals())


def t1_t2e(
    *,
    t1_step=None,
    t1_expts=None,
    t1_reps=None,
    t1_rounds=None,
    relax_delay=None,
    repetitions=None,
    t2e_max_us=None,
    t2e_expts=None,
    t2e_reps=None,
    t2e_rounds=None,
    t2e_freq_shift=None,
    t2e_relax_delay=None,
    num_pi_pulses=None,
    rotation_angle=None,
    min_max=None,
):
    """T1 then T2 echo, `repetitions` times. t1_* / relax_delay / repetitions override the
    coherence group's; t2e_* (the echo group's T2_* keys), num_pi_pulses, rotation_angle and
    min_max override the echo group's. docs/experiments/coherence_combos.md
    """
    return _step("t1_t2e", locals())


def t1_t2r_t2e(
    *,
    t1_step=None,
    t1_expts=None,
    t1_reps=None,
    t1_rounds=None,
    t2_step=None,
    t2_expts=None,
    t2_reps=None,
    t2_rounds=None,
    freq_shift=None,
    relax_delay=None,
    repetitions=None,
    f_virt_mhz=None,
    t2e_max_us=None,
    t2e_expts=None,
    t2e_reps=None,
    t2e_rounds=None,
    t2e_freq_shift=None,
    t2e_relax_delay=None,
    num_pi_pulses=None,
    rotation_angle=None,
    min_max=None,
):
    """T1, T2 echo, T2 Ramsey, `repetitions` times. t1_* / t2_* (Ramsey) / freq_shift /
    relax_delay / repetitions / f_virt_mhz override the coherence group's; t2e_* and the echo
    keywords override the echo group's (as in t1_t2e). docs/experiments/coherence_combos.md
    """
    return _step("t1_t2r_t2e", locals())


def single_shot(*, number_of_pulses=None, pi2_ss=None):
    """g/e IQ clouds, threshold and contrast (SingleShotProgramFFMUX), regime B.

    number_of_pulses (0: thermal mode) and pi2_ss override the single_shot group's.
    docs/experiments/single_shot.md
    """
    return _step("single_shot", locals())


_US = _Slot(
    "US_params",
    (
        ("Shots", "shots"),
        ("relax_delay", "relax_delay"),
        ("min_separation_sigma", "min_separation_sigma"),
        ("average_shots", "average_shots"),
        ("bin_sizes", "bin_sizes"),
        ("charge_sweep", "charge_sweep"),
        ("voltage_start", "voltage_start"),
        ("voltage_end", "voltage_end"),
        ("voltage_step", "voltage_step"),
        ("charge_settle_s", "charge_settle_s"),
        ("Repeat", "repeat"),
        ("plotDisp", "plot_disp"),
    ),
    drop_none=frozenset(
        {
            "Shots",
            "relax_delay",
            "min_separation_sigma",
            "average_shots",
            "bin_sizes",
            "voltage_start",
            "voltage_end",
            "voltage_step",
            "charge_settle_s",
            "Repeat",
            "plotDisp",
        }
    ),
)


def undriven_single_shot(
    *,
    shots=1_000_000,
    relax_delay=300,
    min_separation_sigma=2.0,
    average_shots=1,
    bin_sizes=(1, 2, 4, 8, 16, 32, 64),
    charge_sweep=False,
    voltage_start=0.0,
    voltage_end=0.05,
    voltage_step=0.005,
    charge_settle_s=1.0,
    repeat=1,
    plot_disp=True,
):
    """Single shots with the drive off (UndrivenSingleShot): IQ blobs and switching, regime B.

    shots; relax_delay [us] (None: the single_shot group's); min_separation_sigma: blob
    separation (combined sigma) to call two blobs; average_shots: consecutive shots averaged
    per time-series point; bin_sizes: rate-vs-averaging sweep. charge_sweep: one acquisition per
    bias np.arange(voltage_start, voltage_end, voltage_step) [V], charge_settle_s [s] after each
    ramp. repeat: whole acquisitions back to back; plot_disp: show the last.
    docs/experiments/undriven_single_shot.md
    """
    return _step("undriven_single_shot", locals())


_UNDRIVEN = undriven_single_shot  # interleaved_coherence's keyword of that name shadows it


def t1_single_shot(
    *,
    t1_step=80,
    t1_expts=100,
    reps=2000,
    angle=0,
    threshold=0,
    relax_delay=8000,
    calibrate_ss=True,
    repetitions=1,
):
    """T1 from thresholded single shots (T1_SS), regime B.

    t1_step [us] x t1_expts waits, reps shots per point, relax_delay [us]. calibrate_ss: take
    angle [rad] / threshold from a g / pi single_shot first (else the given ones).
    repetitions: back-to-back runs. docs/experiments/t1_single_shot.md
    """
    return _step("t1_single_shot", locals())


def readout_optimize(*, gain_start=3000, gain_stop=3600, gain_pts=7, span=0.1, trans_pts=21):
    """Single-shot contrast on a readout gain x frequency grid (ReadOpt_wSingleShotFF), regime B.

    gain_start..gain_stop [DAC] in gain_pts; span [MHz] around pulse_freq in trans_pts.
    docs/experiments/readout_optimize.md
    """
    return _step("readout_optimize", locals())


def qubit_optimize(
    *, q_gain_span=500, q_gain_pts=21, q_freq_span=2, q_freq_pts=21, number_of_pulses=1
):
    """Single-shot contrast on a qubit gain x frequency grid (QubitPulseOpt_wSingleShotFF), B.

    gain +- q_gain_span [DAC] in q_gain_pts; freq +- q_freq_span [MHz] in q_freq_pts;
    number_of_pulses per preparation (2 with the pi/2 gain optimises pi/2).
    docs/experiments/qubit_optimize.md
    """
    return _step("qubit_optimize", locals())


def active_reset_verify(
    *,
    n_verify_reads=5,
    verify_relax_delay=5.0,
    reps=2000,
    reset_cycles=1,
    reset_readout_relax_delay=5.0,
    post_reset_wait=0.0,
    relax_delay=3500,
    plot_disp=True,
    reset_read_latency_us=None,
):
    """Verify the measurement-based active reset (ActiveResetVerify), regime A.

    n_verify_reads readouts verify_relax_delay [us] apart after the reset; reps shots per
    condition; reset_cycles measure->feedback rounds; reset_readout_relax_delay [us] after each
    reset readout (>= ~6/kappa); post_reset_wait [us]; relax_delay [us] between reps;
    reset_read_latency_us [us] (None: the program's 0.5 us). docs/experiments/active_reset_verify.md
    """
    return _step("active_reset_verify", locals())


_MR_SEQUENCE = (
    ("tau_harmonic_k", "tau_harmonic_k"),
    ("use_pi_pulse", "use_pi_pulse"),
    ("flip_final_pi2", "flip_final_pi2"),
    ("symmetric_ramsey", "symmetric_ramsey"),
    ("max_drive_bandwidth_ratio", "max_drive_bandwidth_ratio"),
    ("use_active_reset", "use_active_reset"),
    ("reset_cycles", "reset_cycles"),
    ("reset_ground_below_threshold", "reset_ground_below_threshold"),
    ("reset_readout_relax_delay", "reset_readout_relax_delay"),
    ("reset_read_latency_us", "reset_read_latency_us"),
    ("post_reset_wait", "post_reset_wait"),
    ("readout_threshold", "readout_threshold"),
    ("ss_calib_shots", "ss_calib_shots"),
    ("ss_recalib_every_n_cycles", "ss_recalib_every_n_cycles"),
)
_MR_ANALYSIS = (
    ("expected_parity_dwell_ms", "expected_parity_dwell_ms"),
    ("drift_window_ms", "drift_window_ms"),
    ("hmm_symmetric", "hmm_symmetric"),
    ("hmm_bootstrap_samples", "hmm_bootstrap_samples"),
    ("hmm_fit_mapping", "hmm_fit_mapping"),
    ("mapping_p_e_state0", "mapping_p_e_state0"),
    ("mapping_p_e_state1", "mapping_p_e_state1"),
    ("mapping_probabilities_calibrated", "mapping_probabilities_calibrated"),
    ("hmm_min_emission_snr", "hmm_min_emission_snr"),
    ("hmm_kwargs", "hmm_kwargs"),
)
_MAPPING = (
    ("mapping_p_e_state0", "p_e_state0"),
    ("mapping_p_e_state1", "p_e_state1"),
    ("mapping_probabilities_calibrated", "calibrated"),
)


def _mapping_from_parity(d, parity):
    for key, attr in _MAPPING:
        if d.get(key) is None and parity is not None:
            d[key] = getattr(parity, attr)


def _mr_device(d, qubit):
    parity = _parity(qubit)
    if d["df"] is None:
        d["df"] = _need(
            "modified_ramsey",
            "df",
            getattr(parity, "df_mhz", None),
            "set Qubit.parity.df_mhz or pass df= [MHz]",
        )
    if d["f_ge"] is None:
        f_upper = getattr(parity, "f_upper_mhz", None)
        if f_upper is not None:
            d["f_ge"] = f_upper
        elif d["symmetric_ramsey"]:
            raise ValueError(
                "modified_ramsey: symmetric_ramsey=True needs the UPPER parity branch: set "
                "Qubit.parity.f_upper_mhz or pass f_ge= [MHz]; the qubit centre frequency is "
                "never used for it (docs/experiments/modified_ramsey.md)"
            )
    _mapping_from_parity(d, parity)
    return d


_MR = _Slot(
    "ModifiedRamsey_params",
    (
        ("df", "df"),
        ("f_ge", "f_ge"),
        ("f_ge_measured_at_V", "f_ge_measured_at_v"),
        ("require_f_ge_near_qubit", "require_f_ge_near_qubit"),
        ("num_cycles", "num_cycles"),
        ("use_apriori_separator", "use_apriori_separator"),
        ("mr_relax_delay", "mr_relax_delay"),
        ("mr_reps", "mr_reps"),
        ("average_n_shots", "average_n_shots"),
        ("parity_analysis_enabled", "parity_analysis_enabled"),
        ("validation_controls", "validation_controls"),
        ("validation_controls_every_n_cycles", "validation_controls_every_n_cycles"),
        ("control_tau_offset_frac", "control_tau_offset_frac"),
        ("control_detuning_mhz", "control_detuning_mhz"),
        *_MR_SEQUENCE,
        *_MR_ANALYSIS,
    ),
    drop_none=frozenset({"f_ge", "reset_read_latency_us", *(k for k, _ in _MAPPING)}),
    device=_mr_device,
)


def modified_ramsey(
    *,
    df=None,
    f_ge=None,
    f_ge_measured_at_v=None,
    require_f_ge_near_qubit=False,
    num_cycles=1,
    use_apriori_separator=True,
    mr_relax_delay=500.0,
    mr_reps=50000,
    average_n_shots=50,
    parity_analysis_enabled=False,
    validation_controls=("flip_final_pi2", "echo_null"),
    validation_controls_every_n_cycles=10,
    control_tau_offset_frac=None,
    control_detuning_mhz=None,
    tau_harmonic_k=1,
    use_pi_pulse=False,
    flip_final_pi2=False,
    symmetric_ramsey=True,
    max_drive_bandwidth_ratio=1.4,
    use_active_reset=True,
    reset_cycles=1,
    reset_ground_below_threshold=True,
    reset_readout_relax_delay=5.0,
    reset_read_latency_us=None,
    post_reset_wait=0.0,
    readout_threshold=None,
    ss_calib_shots=1000,
    ss_recalib_every_n_cycles=10,
    expected_parity_dwell_ms=2.5,
    drift_window_ms=200.0,
    hmm_symmetric=True,
    hmm_bootstrap_samples=0,
    hmm_fit_mapping=True,
    mapping_p_e_state0=None,
    mapping_p_e_state1=None,
    mapping_probabilities_calibrated=None,
    hmm_min_emission_snr=None,
    hmm_kwargs=None,
):
    """Fixed-tau charge-parity Ramsey record (ModifiedRamsey) + HMM rate, regime A.

    df [MHz] parity splitting, tau = tau_harmonic_k / (2 df) (None: Qubit.parity.df_mhz).
    f_ge [MHz] the UPPER branch (None: Qubit.parity.f_upper_mhz; with neither,
    symmetric_ramsey=True raises, False drives the qubit centre). f_ge_measured_at_v [V]:
    bias of that calibration (warns when moved); require_f_ge_near_qubit raises instead of warns.
    num_cycles records of mr_reps shots, mr_relax_delay [us] after each Ramsey readout;
    use_apriori_separator / ss_calib_shots / ss_recalib_every_n_cycles: SingleShot separator.
    average_n_shots: legacy threshold-plot averaging. parity_analysis_enabled: HMM/ACF analysis.
    validation_controls every validation_controls_every_n_cycles cycles, control_tau_offset_frac
    (None: the predicted null) and control_detuning_mhz [MHz] (None: auto).
    Sequence: use_pi_pulse (echo), flip_final_pi2 (+180 deg closing pi/2), symmetric_ramsey
    (drive at f_ge - df/2), max_drive_bandwidth_ratio (branch detuning / pi/2 Rabi rate cap).
    Active reset: use_active_reset, reset_cycles, reset_ground_below_threshold,
    reset_readout_relax_delay [us] (>= ~6/kappa), reset_read_latency_us [us] (None: 0.5),
    post_reset_wait [us], readout_threshold (None: from the separator).
    Analysis: expected_parity_dwell_ms [ms], drift_window_ms [ms], hmm_symmetric,
    hmm_bootstrap_samples, hmm_fit_mapping; mapping_p_e_state0 / _state1 / _calibrated
    (None: Qubit.parity, else 0.1 / 0.9 / False); hmm_min_emission_snr (None: 0.7);
    hmm_kwargs: extra fit_two_state_hmm keywords. docs/experiments/modified_ramsey.md
    """
    values = dict(locals())
    values["validation_controls"] = list(validation_controls)
    return _step("modified_ramsey", values)


def _mrc_device(d, qubit):
    parity = _parity(qubit)
    for key, attr in (("cd_max_mhz", "cd_max_mhz"), ("cd_period_mv", "cd_period_mv")):
        if d[key] is None:
            d[key] = _need(
                "modified_ramsey_control",
                key,
                getattr(parity, attr, None),
                f"set Qubit.parity.{attr} or pass {key}=",
            )
    _mapping_from_parity(d, parity)
    return d


_MRC_OWN = (
    ("df", "df"),
    ("dV", "dv"),
    ("voltage_min", "voltage_min"),
    ("voltage_max", "voltage_max"),
    ("max_voltage_tries", "max_voltage_tries"),
    ("num_cycles", "num_cycles"),
    ("SpecSpan", "spec_span"),
    ("SpecNumPoints", "spec_num_points"),
    ("reps", "reps"),
    ("rounds", "rounds"),
    ("relax_delay", "relax_delay"),
    ("sigma", "sigma"),
    ("gain", "gain"),
    ("qubit_length", "qubit_length"),
    ("cd_max_mhz", "cd_max_mhz"),
    ("cd_period_mv", "cd_period_mv"),
    ("sweet_spot_max_df_mhz", "sweet_spot_max_df_mhz"),
    ("mr_relax_delay", "mr_relax_delay"),
    ("mr_reps", "mr_reps"),
    ("hysteresis_low", "hysteresis_low"),
    ("hysteresis_high", "hysteresis_high"),
    ("window_ms", "window_ms"),
)
_MRC_INHERITED = _MR_SEQUENCE + _MR_ANALYSIS  # the Ramsey reads these from here without `ramsey`
_MRC = _Slot(
    "ModifiedRamsey_Control_params",
    _MRC_OWN + _MRC_INHERITED,
    drop_none=frozenset(k for k, _ in _MRC_INHERITED),
    device=_mrc_device,
)


def _mr_of_mrc_device(d, qubit):
    # MRC measures f_ge at its sweet spot and never reads this dict's f_ge: no upper-branch rule
    parity = _parity(qubit)
    if d["df"] is None:
        d["df"] = _need(
            "modified_ramsey_control",
            "the ramsey step's df",
            getattr(parity, "df_mhz", None),
            "set Qubit.parity.df_mhz or pass ramsey=R.modified_ramsey(df=...) [MHz]",
        )
    _mapping_from_parity(d, parity)
    return d


_MR_OF_MRC = _Slot("ModifiedRamsey_params", (), drop_none=_MR.drop_none, device=_mr_of_mrc_device)


def modified_ramsey_control(
    *,
    df=0.5,
    dv=0.0005,
    voltage_min=0.0,
    voltage_max=0.010,
    max_voltage_tries=1000,
    num_cycles=1,
    spec_span=1.0,
    spec_num_points=101,
    reps=10,
    rounds=10,
    relax_delay=1500,
    sigma=2,
    gain=700,
    qubit_length=2,
    cd_max_mhz=None,
    cd_period_mv=None,
    sweet_spot_max_df_mhz=0.1,
    mr_relax_delay=0.0,
    mr_reps=500,
    hysteresis_low=0.4,
    hysteresis_high=0.6,
    window_ms=0.1,
    ramsey=None,
    tau_harmonic_k=None,
    use_pi_pulse=None,
    flip_final_pi2=None,
    symmetric_ramsey=None,
    max_drive_bandwidth_ratio=None,
    use_active_reset=None,
    reset_cycles=None,
    reset_ground_below_threshold=None,
    reset_readout_relax_delay=None,
    reset_read_latency_us=None,
    post_reset_wait=None,
    readout_threshold=None,
    ss_calib_shots=None,
    ss_recalib_every_n_cycles=None,
    expected_parity_dwell_ms=None,
    drift_window_ms=None,
    hmm_symmetric=None,
    hmm_bootstrap_samples=None,
    hmm_fit_mapping=None,
    mapping_p_e_state0=None,
    mapping_p_e_state1=None,
    mapping_probabilities_calibrated=None,
    hmm_min_emission_snr=None,
    hmm_kwargs=None,
):
    """Two-tone search -> half-period step -> sweet spot -> modified Ramsey there, regime A.

    Search: accept a doublet of separation >= df [MHz], stepping dv [V] within
    voltage_min..voltage_max [V] (library values: the device has no voltage window), at most
    max_voltage_tries; num_cycles cycles. Spec: spec_span
    [MHz] / spec_num_points, reps / rounds, relax_delay [us], Gaussian sigma [us] at gain [DAC],
    qubit_length [us]. Dispersion S(V) = cd_max_mhz |cos(2 pi V / cd_period_mv)| (None:
    Qubit.parity). sweet_spot_max_df_mhz [MHz]: verified sweet spot. Ramsey: mr_reps shots,
    mr_relax_delay [us]; hysteresis_low / _high, window_ms [ms]: state trace. ramsey: the
    modified_ramsey Step whose sequence, df (None: Qubit.parity.df_mhz) and mapping the Ramsey
    uses; its f_ge is not used (f_ge is measured at the sweet spot), so symmetric_ramsey needs
    no f_upper here. ramsey None: these keywords (each None one takes the run's default).
    Sequence / analysis keywords as in modified_ramsey.
    docs/experiments/modified_ramsey_control.md
    """
    mr = None if ramsey is None else ramsey.params["ModifiedRamsey_params"]
    return _step("modified_ramsey_control", locals(), ModifiedRamsey_params=mr)


def _cd_quasicw_device(d, qubit):
    if d["probe_freq"] is None:
        d["probe_freq"] = _need(
            "charge_dispersion_quasicw",
            "probe_freq",
            getattr(_parity(qubit), "f_upper_mhz", None),
            "set Qubit.parity.f_upper_mhz or pass probe_freq= [MHz]",
        )
    return d


def _cd_ramsey_device(d, qubit):
    if d["df"] is None:  # left None: the run raises KeyError('df') (known issue)
        d["df"] = getattr(_parity(qubit), "df_mhz", None)
    return d


def two_tone_charge_dispersion_quasicw(
    *,
    df=0.5,
    dv=0.0005,
    voltage_min=0.0,
    voltage_max=0.010,
    max_voltage_tries=1000,
    num_cycles=1,
    use_upper_peak=True,
    center_peak_tol_mhz=0.05,
    min_partner_snr=MIN_PARTNER_SNR,
    spec_span=1.0,
    spec_num_points=101,
    reps=10,
    rounds=10,
    relax_delay=850,
    gauss=True,
    sigma=2,
    gain=500,
    qubit_length=2,
    qcw_repetitions=1000,
    qcw_relax_delay=850,
    expected_parity_dwell_ms=2.5,
    qcw_gauss=None,
    qcw_sigma=None,
    qcw_gain=None,
    min_sep_mhz=None,
    fit_window_mhz=None,
    prominent_ratio=None,
    charge_dispersion=None,
):
    """Find the parity doublet by stepping the bias, then quasi-CW shots on one peak, regime A.

    Search: separation >= df [MHz], dv [V] steps in voltage_min..voltage_max [V] (library
    values: the device has no voltage window), at most
    max_voltage_tries, num_cycles cycles; use_upper_peak picks the probed peak;
    center_peak_tol_mhz [MHz]; min_partner_snr: doublet partner significance (0: gate off).
    Spec: spec_span [MHz] / spec_num_points, reps / rounds, relax_delay [us], gauss / sigma [us]
    / gain [DAC] / qubit_length [us]. Quasi-CW: qcw_repetitions shots, qcw_relax_delay [us],
    expected_parity_dwell_ms [ms]; qcw_gauss / qcw_sigma / qcw_gain and min_sep_mhz /
    fit_window_mhz / prominent_ratio override the spec group's. charge_dispersion: dict that
    receives the chosen 'probe_freq' (legacy: shared with charge_dispersion_quasicw).
    docs/experiments/charge_dispersion.md
    """
    out = {} if charge_dispersion is None else charge_dispersion
    return _step("two_tone_charge_dispersion_quasicw", locals(), ChargeDispersion_params=out)


def charge_dispersion_quasicw(
    *,
    probe_freq=None,
    relax_delay=2000,
    repetitions=500,
    expected_parity_dwell_ms=2.5,
    gauss=None,
    sigma=None,
    gain=None,
):
    """Shot-resolved two-tone at probe_freq [MHz] (ChargeDispersionQuasiCW), regime A.

    probe_freq None: Qubit.parity.f_upper_mhz. repetitions shots, relax_delay [us],
    expected_parity_dwell_ms [ms]; gauss / sigma / gain override the spec group's.
    docs/experiments/charge_dispersion.md
    """
    return _step("charge_dispersion_quasicw", locals())


def charge_dispersion_ramsey(*, df=None, relax_delay=2000, repetitions=None):
    """Fixed-wait Ramsey parity readout (ChargeDispersion), regime A.

    df [MHz] (None: Qubit.parity.df_mhz; with neither the run raises KeyError('df'));
    relax_delay [us]; repetitions overrides the coherence group's.
    docs/experiments/charge_dispersion.md
    """
    return _step("charge_dispersion_ramsey", locals())


def _cd_period_device(value, qubit):
    if value is None:
        value = getattr(_parity(qubit), "cd_period_mv", None)
    return value


def charge_sweep(
    *,
    reps=None,
    rounds=None,
    gauss=None,
    sigma=None,
    gain=None,
    min_sep_mhz=None,
    fit_window_mhz=None,
    prominent_ratio=None,
    cd_period_mv=None,
):
    """Two-tone spec at every bias of the charge group (QubitSpecSliceFF) + splitting fit.

    Spec keywords override the spec group's. cd_period_mv [mV]: dispersion period for the
    grid-sampling check (None: Qubit.parity.cd_period_mv, else unchecked).
    docs/experiments/charge_sweep.md
    """
    return _step("charge_sweep", locals())


def charge_transmission_sweep(
    *,
    reps=20,
    rounds=20,
    span=None,
    num_points=None,
    fit=False,
    settle_s=0.0,
    voltage_start=None,
    voltage_end=None,
    voltage_step=None,
):
    """Resonator sweep at every charge bias (CavitySpecFF): dB heatmap + tracked dip, regime A.

    reps / rounds averages; span [MHz] / num_points (None: the transmission group's); fit:
    hanger fit per slice; settle_s [s] after each ramp; voltage_* [V] (None: the charge group's).
    docs/experiments/charge_transmission_sweep.md
    """
    return _step("charge_transmission_sweep", locals())


def interleaved_coherence(
    *, cycles=1, undriven_single_shot=True, t1=True, t2r=True, t2e=False, undriven=None
):
    """Loop of undriven single shot -> T1 -> T2R -> T2E (each switchable), `cycles` times.

    T1/T2R read the coherence group, T2E the echo group, the single-shot regime the
    single_shot group (one repetition each per cycle, no plots). undriven: the
    undriven_single_shot Step whose settings the loop uses (None: its defaults).
    docs/experiments/interleaved_coherence.md
    """
    us = (undriven if undriven is not None else _UNDRIVEN()).params["US_params"]
    return _step("interleaved_coherence", locals(), US_params=us)


_AC_KEYS = tuple((k, k.lower()) for k in AUTO_COHERENCE_PARAMS)


def _ac_device(d, qubit):
    if d["cd_period_mv"] is None:
        d["cd_period_mv"] = getattr(_parity(qubit), "cd_period_mv", None)
    return d


def auto_coherence(
    *,
    spec_span=1.0,
    spec_num_pts=101,
    spec_reps=10,
    spec_rounds=10,
    spec_relax_delay=1500,
    spec_sigma=2.0,
    spec_gain=700,
    spec_qubit_length=2.0,
    skip_sweet_spot_search=False,
    ss_search_df_trigger=0.5,
    ss_accept_sep=0.08,
    ss_dv=0.0005,
    ss_voltage_min=0.0,
    ss_voltage_max=0.01,
    ss_max_tries=200,
    cd_period_mv=None,
    calibrate_qubit_freq=True,
    freqcal_auto_gain=True,
    freqcal_min_snr=4.0,
    freqcal_gain_growth=1.8,
    freqcal_max_gain=30000,
    freqcal_max_gain_retries=5,
    rabi_max_gain=12000,
    rabi_num_steps=201,
    rabi_reps=15,
    rabi_rounds=15,
    rabi_relax_delay=3500,
    rabi_sigma=None,
    rabi_sigma_min=0.01,
    rabi_max_osc_peaks=3,
    rabi_max_sigma_retries=10,
    ss_shots=1000,
    ss_full_shots=2000,
    ss_relax_delay=3500,
    ss_readout_time=15,
    ss_adc_offset=1,
    ss_target_fidelity=0.7,
    ss_gain_pts=21,
    ss_max_scan_expansions=2,
    ss_gain_span_growth=1.8,
    ss_gain_span_frac=0.2,
    auto_readout_opt=True,
    readout_length_start=5.0,
    readout_length_stop=30.0,
    readout_length_pts=6,
    adc_offset_start=0.2,
    adc_offset_stop=3.0,
    adc_offset_pts=5,
    extended_pi_pi2_opt=False,
    pi_nsteps_list=(1, 3, 5, 7, 11),
    pi2_nsteps_list=(2, 6, 10, 14, 22),
    ext_gain_pts=51,
    ext_pi_gain_span_init=0.2,
    ext_pi2_gain_span_init=0.2,
    ext_gain_span_shrink=0.4,
    t1_step=40,
    t1_expts=60,
    t1_reps=20,
    t1_rounds=20,
    t1_relax_delay=3500,
    t1_repetitions=1,
    t1_expected_us=None,
    t2_step=0.1,
    t2_expts=201,
    t2_reps=20,
    t2_rounds=20,
    t2_relax_delay=3500,
    t2_repetitions=1,
    t2_freq_shift=0.0,
    t2_f_virt_mhz=None,
    t2e_max_us=200,
    t2e_expts=201,
    t2e_reps=25,
    t2e_rounds=25,
    t2e_relax_delay=3500,
    t2e_num_pi_pulses=1,
    t2e_repetitions=1,
):
    """Automated sweet spot -> f_ge -> Rabi -> readout / pi opt -> T1 / T2R / T2E, regime B.

    Keywords are the AUTO_COHERENCE_PARAMS keys in lower case, same defaults and units
    (MHz, us, V, mV, DAC): spec_* two-tone, ss_search_* / ss_dv / ss_voltage_* / ss_max_tries
    sweet-spot walk (skip_sweet_spot_search skips it; cd_period_mv None: Qubit.parity),
    freqcal_* f_ge re-centring (calibrate_qubit_freq), rabi_*, ss_* pi-gain single shots,
    readout_length_* / adc_offset_* readout opt (auto_readout_opt), extended_pi_pi2_opt with
    pi*_nsteps_list / ext_*, then t1_* / t2_* / t2e_*. docs/experiments/auto_coherence.md
    """
    values = dict(locals())
    for kw in ("pi_nsteps_list", "pi2_nsteps_list"):
        values[kw] = list(values[kw])
    return _step("auto_coherence", values)


ZSP_SUBDICTS = {  # legacy sub-dict -> defaults (legacy keys), the run's optional keys included
    "ZSP_ParityFreqs_Cached": {
        "lower_peak_MHz": None,
        "higher_peak_MHz": None,
        "which_to_park": "lower",
    },
    "ZSP_Separator_Cached": {"g_center": None, "e_center": None, "normal": None, "midpoint": None},
    "ZSP_ParitySpec_params": {
        "SpecSpan": 1.0,
        "SpecNumPoints": 201,
        "reps": 10,
        "rounds": 10,
        "relax_delay": 3500,
        "Gauss": True,
        "sigma": 2,
        "gain": 500,
        "qubit_length": 2,
        "min_sep_MHz": 0.2,
        "fit_window_mhz": 0.5,
        "prominent_ratio": 0.1,
        "min_partner_snr": MIN_PARTNER_SNR,
    },
    "ZSP_StrobeParams": {
        "sample_period_us": 20.0,
        "reps_per_chunk": 10000,
        "n_chunks": 60,
        "read_length": 5.0,
        "adc_trig_offset": 0.488,
    },
    "ZSP_DecimatedParams": {
        "capture_length_us": 100.0,
        "soft_avgs": 1,
        "n_captures": 1,
        "read_length": 80.0,
        "adc_trig_offset": 0.488,
        "allow_soft_avgs": False,
    },
    "ZSP_DriveParams": {"qubit_gain": None, "pulse_gain": None, "res_phase": 0},
    "ZSP_AnalysisParams": {
        "classifier_method": "apriori",
        "window_us": 1000.0,
        "k_sigma": 5.0,
        "step_us": None,
        "min_burst_duration_us": None,
        "analysis_bin_us": None,
        "save_plots": True,
    },
    "StaticContrast_params": {"freq_span_mhz": 2.0, "n_points": 41, "reps_per_point": 2000},
    "ContrastVsQubit_params": {
        "qfreq_span_mhz": 10.0,
        "n_points": 81,
        "doublet_sep_tol_MHz": None,
        "min_peak_snr": MIN_PARTNER_SNR,
    },
    "Modulation_params": {
        "modulation_freq_hz": 25,
        "n_periods": 10,
        "min_block_t": None,
        "min_abs_correlation": None,
        "min_snr": None,
    },
    "Control_params": {"variants": ["A", "B", "C", "D"], "detune_mhz": 50.0},
    "Environment_params": {"param_name": "power_dB", "values": [-10, -8, -6, -4]},
}
_ZSP_KEYS = (
    ("ZSP_RunMode", "run_mode"),
    ("ZSP_StartSrc", "start_src"),
    ("ZSP_RecalibrateParityFreqs", "recalibrate_parity_freqs"),
    ("ZSP_RecalibrateSeparator", "recalibrate_separator"),
    ("ZSP_ParityFreqs_Cached", "parity_freqs_cached"),
    ("ZSP_Separator_Cached", "separator_cached"),
    ("ZSP_ParitySpec_params", "parity_spec"),
    ("ZSP_StrobeParams", "strobe"),
    ("ZSP_DecimatedParams", "decimated"),
    ("ZSP_DriveParams", "drive"),
    ("ZSP_AnalysisParams", "analysis"),
    ("Validate_StaticContrast", "validate_static_contrast"),
    ("StaticContrast_params", "static_contrast"),
    ("Validate_ContrastVsQubitFreq", "validate_contrast_vs_qubit_freq"),
    ("ContrastVsQubit_params", "contrast_vs_qubit"),
    ("Validate_ModulationCheck", "validate_modulation_check"),
    ("Modulation_params", "modulation"),
    ("Validate_ControlSuite", "validate_control_suite"),
    ("Control_params", "control"),
    ("Validate_EnvironmentSweep", "validate_environment_sweep"),
    ("Environment_params", "environment"),
    ("Build_EvidenceReport", "build_evidence_report"),
)


def _zsp_device(p, qubit):
    # the run fills its caches in place: give it copies, keep the Step reusable
    p = {k: copy.deepcopy(v) if isinstance(v, dict) else v for k, v in p.items()}
    parity = _parity(qubit)
    cached = p["ZSP_ParityFreqs_Cached"]
    f_upper, df = getattr(parity, "f_upper_mhz", None), getattr(parity, "df_mhz", None)
    if f_upper is not None and df is not None:
        if cached["higher_peak_MHz"] is None:
            cached["higher_peak_MHz"] = f_upper
        if cached["lower_peak_MHz"] is None:
            cached["lower_peak_MHz"] = f_upper - df
    return p


def zero_span_parity(
    *,
    run_mode="strobe",
    start_src="internal",
    recalibrate_parity_freqs=True,
    recalibrate_separator=True,
    parity_freqs_cached=None,
    separator_cached=None,
    parity_spec=None,
    strobe=None,
    decimated=None,
    drive=None,
    analysis=None,
    validate_static_contrast=False,
    static_contrast=None,
    validate_contrast_vs_qubit_freq=False,
    contrast_vs_qubit=None,
    validate_modulation_check=False,
    modulation=None,
    validate_control_suite=False,
    control=None,
    validate_environment_sweep=False,
    environment=None,
    build_evidence_report=False,
):
    """Zero-span charge-parity record (ZeroSpanParity) + analysis and validation stages, B.

    run_mode "strobe" | "decimated"; start_src "internal" | "external"; recalibrate_parity_freqs
    (narrow spec first) / recalibrate_separator (g/e single shots first). The dict keywords
    update ZSP_SUBDICTS[<legacy name>] (legacy keys; an unknown key raises TypeError):
    parity_freqs_cached (lower/higher_peak_MHz [MHz], None: Qubit.parity), separator_cached,
    parity_spec, strobe (sample_period_us [us], reps_per_chunk, n_chunks, read_length [us],
    adc_trig_offset [us]), decimated, drive (qubit_gain / pulse_gain [DAC], None: the qubit's;
    res_phase: phase register), analysis, and the validate_* stages' static_contrast,
    contrast_vs_qubit, modulation, control, environment. docs/experiments/zero_span_parity.md
    """
    values = dict(locals())
    for legacy, kw in _ZSP_KEYS:
        if legacy in ZSP_SUBDICTS:
            given = values[kw] or {}
            unknown = sorted(set(given) - set(ZSP_SUBDICTS[legacy]))
            if unknown:
                raise TypeError(
                    f"zero_span_parity({kw}=...): unknown keys {unknown}; "
                    f"known: {sorted(ZSP_SUBDICTS[legacy])}"
                )
            values[kw] = copy.deepcopy({**ZSP_SUBDICTS[legacy], **given})
    return _step("zero_span_parity", values)


_register("constant_tone", run_constant_tone, "A", _CW)
_register("constant_two_tone", run_constant_two_tone, "A", _CW)
_register("transmission_fit", run_transmission_fit, "A", _TRANSMISSION_OVERRIDES)
_register("transmission_sweep", run_transmission_sweep, "A", _TRANSMISSION_OVERRIDES)
_register(
    "chi_shift",
    run_chi_shift,
    "A",
    _Slot(
        "ChiShift_params",
        (
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("TransSpan", "trans_span"),
            ("TransNumPoints", "trans_num_points"),
            ("cavity_shift", "cavity_shift"),
            ("relax_delay", "relax_delay"),
        ),
    ),
)
_register(
    "two_tone_spec",
    run_two_tone_spec,
    "A",
    _Slot(
        "spec",
        (
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("Gauss", "gauss"),
            ("sigma", "sigma"),
            ("gain", "gain"),
            ("qubit_length", "qubit_length"),
            ("SpecSpan", "spec_span"),
            ("SpecNumPoints", "spec_num_points"),
            ("relax_delay", "relax_delay"),
            *_SPEC_PEAKS,
        ),
    ),
)
_register(
    "spec_gain_length_sweep",
    run_spec_gain_length_sweep,
    "A",
    _Slot(
        "spec",
        (
            ("sweep_lengths", "sweep_lengths"),
            ("sweep_gains", "sweep_gains"),
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("Gauss", "gauss"),
            ("sigma", "sigma"),
            ("SpecSpan", "spec_span"),
            ("SpecNumPoints", "spec_num_points"),
            ("relax_delay", "relax_delay"),
            *_SPEC_PEAKS,
        ),
    ),
)
_register(
    "trans_qubit_spec",
    run_trans_qubit_spec,
    "A",
    _Slot(
        "spec",
        (
            ("gain", "gain"),
            ("relax_delay", "relax_delay"),
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("Gauss", "gauss"),
            ("sigma", "sigma"),
            *_SPEC_PEAKS[1:],
        ),
    ),
    _Slot("coherence", (("repetitions", "repetitions"),)),
)
_register(
    "amplitude_rabi",
    run_amplitude_rabi,
    "A",
    _Slot(
        "Amplitude_Rabi_params",
        (
            ("qubit_freq", "qubit_freq"),
            ("max_gain", "max_gain"),
            ("number_of_steps", "number_of_steps"),
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("relax_delay", "relax_delay"),
            ("fit", "fit"),
            ("flattop_relax_delay", "flattop_relax_delay"),
        ),
        device=_rabi_device,
    ),
)
_register(
    "t1",
    run_t1,
    "A",
    _Slot(
        "coherence",
        (
            *_T1_KEYS,
            ("relax_delay", "relax_delay"),
            ("repetitions", "repetitions"),
            ("plotDisp", "plot_disp"),
        ),
    ),
)
_register(
    "t2_ramsey",
    run_t2,
    "A",
    _Slot(
        "coherence",
        (
            *_T2R_KEYS,
            ("freq_shift", "freq_shift"),
            ("relax_delay", "relax_delay"),
            ("repetitions", "repetitions"),
            ("f_virt_mhz", "f_virt_mhz"),
        ),
    ),
)
_register(
    "t2_echo",
    run_t2e,
    "A",
    _Slot(
        "echo",
        (
            ("T2_max_us", "t2_max_us"),
            ("T2_expts", "t2_expts"),
            ("T2_reps", "t2_reps"),
            ("T2_rounds", "t2_rounds"),
            ("freq_shift", "freq_shift"),
            ("relax_delay", "relax_delay"),
            ("num_pi_pulses", "num_pi_pulses"),
            ("rotation_angle", "rotation_angle"),
            ("min_max", "min_max"),
            ("repetitions", "repetitions"),
            ("plotDisp", "plot_disp"),
        ),
    ),
)
_register(
    "t1_t2e",
    run_t1_t2e,
    "A",
    _Slot(
        "coherence",
        (*_T1_KEYS, ("relax_delay", "relax_delay"), ("repetitions", "repetitions")),
    ),
    _ECHO_IN_COMBOS,
)
_register(
    "t1_t2r_t2e",
    run_t1_t2r_t2e,
    "A",
    _Slot(
        "coherence",
        (
            *_T1_KEYS,
            *_T2R_KEYS,
            ("freq_shift", "freq_shift"),
            ("relax_delay", "relax_delay"),
            ("repetitions", "repetitions"),
            ("f_virt_mhz", "f_virt_mhz"),
        ),
    ),
    _ECHO_IN_COMBOS,
)
_register(
    "interleaved_coherence",
    run_interleaved_coherence,
    "A",
    _Slot(
        "Interleave_params",
        (
            ("cycles", "cycles"),
            ("UndrivenSingleShot", "undriven_single_shot"),
            ("T1", "t1"),
            ("T2R", "t2r"),
            ("T2E", "t2e"),
        ),
    ),
    _Slot("US_params", (), drop_none=_US.drop_none),
    _Slot("coherence"),
    _Slot("echo"),
    _Slot("single_shot"),
)
_register(
    "auto_coherence",
    run_auto_coherence,
    "B",
    _Slot("AutoCoherence_override_params", _AC_KEYS, device=_ac_device),
)
_register(
    "single_shot",
    run_single_shot,
    "B",
    _Slot("single_shot", (("number_of_pulses", "number_of_pulses"), ("pi2_SS", "pi2_ss"))),
)
_register("undriven_single_shot", run_undriven_single_shot, "B", _US)
_register(
    "t1_single_shot",
    run_t1_ss,
    "B",
    _Slot(
        "T1SS_params",
        (
            ("T1_step", "t1_step"),
            ("T1_expts", "t1_expts"),
            ("reps", "reps"),
            ("angle", "angle"),
            ("threshold", "threshold"),
            ("relax_delay", "relax_delay"),
            ("calibrate_SS", "calibrate_ss"),
            ("repetitions", "repetitions"),
        ),
    ),
    _Slot("single_shot"),
)
_register(
    "readout_optimize",
    run_readout_optimize,
    "B",
    _Slot("SS_R_params", _keys("gain_start", "gain_stop", "gain_pts", "span", "trans_pts")),
)
_register(
    "qubit_optimize",
    run_qubit_optimize,
    "B",
    _Slot(
        "SS_Q_params",
        _keys("q_gain_span", "q_gain_pts", "q_freq_span", "q_freq_pts", "number_of_pulses"),
    ),
    _Slot("single_shot"),
)
_register(
    "active_reset_verify",
    run_active_reset_verify,
    "A",
    _Slot(
        "ActiveResetVerify_params",
        (
            *_keys(
                "n_verify_reads",
                "verify_relax_delay",
                "reps",
                "reset_cycles",
                "reset_readout_relax_delay",
                "post_reset_wait",
                "relax_delay",
            ),
            ("plotDisp", "plot_disp"),
            ("reset_read_latency_us", "reset_read_latency_us"),
        ),
        drop_none=frozenset({"reset_read_latency_us"}),
    ),
)
_register("modified_ramsey", run_modified_ramsey, "A", _MR)
_register("modified_ramsey_control", run_modified_ramsey_control, "A", _MRC, _MR_OF_MRC)
_register(
    "two_tone_charge_dispersion_quasicw",
    run_two_tone_charge_dispersion_quasicw,
    "A",
    _Slot(
        "TwoToneChargeDispersion_params",
        (
            ("df", "df"),
            ("dV", "dv"),
            ("voltage_min", "voltage_min"),
            ("voltage_max", "voltage_max"),
            ("max_voltage_tries", "max_voltage_tries"),
            ("num_cycles", "num_cycles"),
            ("use_upper_peak", "use_upper_peak"),
            ("center_peak_tol_mhz", "center_peak_tol_mhz"),
            ("SpecSpan", "spec_span"),
            ("SpecNumPoints", "spec_num_points"),
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("relax_delay", "relax_delay"),
            ("Gauss", "gauss"),
            ("sigma", "sigma"),
            ("gain", "gain"),
            ("qubit_length", "qubit_length"),
            ("qcw_repetitions", "qcw_repetitions"),
            ("qcw_relax_delay", "qcw_relax_delay"),
            ("min_partner_snr", "min_partner_snr"),
            ("expected_parity_dwell_ms", "expected_parity_dwell_ms"),
        ),
    ),
    _Slot(
        "spec",
        (
            ("Gauss", "qcw_gauss"),
            ("sigma", "qcw_sigma"),
            ("gain", "qcw_gain"),
            *_SPEC_PEAKS[1:],
        ),
    ),
    _Slot("ChargeDispersion_params", (), output=True),
)
_register(
    "charge_dispersion_quasicw",
    run_charge_dispersion_quasicw,
    "A",
    _Slot(
        "ChargeDispersion_params",
        _keys("probe_freq", "relax_delay", "repetitions", "expected_parity_dwell_ms"),
        device=_cd_quasicw_device,
    ),
    _Slot("spec", (("Gauss", "gauss"), ("sigma", "sigma"), ("gain", "gain"))),
)
_register(
    "charge_dispersion_ramsey",
    run_charge_dispersion_ramsey,
    "A",
    _Slot("coherence", (("repetitions", "repetitions"),)),
    _Slot(
        "ChargeDispersion_params",
        (("df", "df"), ("relax_delay", "relax_delay")),
        drop_none=frozenset({"df"}),
        device=_cd_ramsey_device,
    ),
)
_register(
    "charge_sweep",
    run_charge_sweep,
    "A",
    _Slot(
        "spec",
        (
            ("reps", "reps"),
            ("rounds", "rounds"),
            ("Gauss", "gauss"),
            ("sigma", "sigma"),
            ("gain", "gain"),
            *_SPEC_PEAKS[1:],
        ),
    ),
    _Slot(
        "cd_period_mv", (("cd_period_mv", "cd_period_mv"),), scalar=True, device=_cd_period_device
    ),
)
_register(
    "charge_transmission_sweep",
    run_charge_transmission_sweep,
    "A",
    _Slot(
        "ChargeTransmission_params",
        _keys(
            "reps",
            "rounds",
            "span",
            "num_points",
            "fit",
            "settle_s",
            "voltage_start",
            "voltage_end",
            "voltage_step",
        ),
    ),
)
_register(
    "zero_span_parity",
    run_zero_span_parity,
    "B",
    _Slot("zero_span_params", _ZSP_KEYS, device=_zsp_device),
)

# canonical step name -> recipe (docs/experiments/README.md#index)
STEPS = {name: globals()[name] for name in _RECIPES}

# step -> {slot: ((legacy key, keyword), ...)}; the dict and scalar keywords of each slot
LEGACY_KEYS = {
    name: {s.name: s.keys for s in recipe.slots if s.keys} for name, recipe in _RECIPES.items()
}

# step -> {keyword: why the library default differs from the CSTQ03 runner's value}
FROZEN_DIFFERENCES = {
    "amplitude_rabi": {"qubit_freq": "None = the pulse qubit's freq (runner: its Frequency)"},
    "modified_ramsey": {
        "df": "None = Qubit.parity.df_mhz (runner: 1, a placeholder)",
        "f_ge": "None = Qubit.parity.f_upper_mhz (runner: 3754.5 = Q2's centre)",
        "num_cycles": "1 record (runner: 1000)",
        "control_tau_offset_frac": "None = the predicted null (runner: 0.25, before F39)",
        "mapping_p_e_state0": "None = Qubit.parity, else the run's 0.1 (runner: 0.1)",
        "mapping_p_e_state1": "None = Qubit.parity, else the run's 0.9 (runner: 0.9)",
        "mapping_probabilities_calibrated": "None = Qubit.parity, else False (runner: False)",
    },
    "modified_ramsey_control": {
        "num_cycles": "1 (runner: 1000)",
        "cd_max_mhz": "None = Qubit.parity.cd_max_mhz (runner: 0.682)",
        "cd_period_mv": "None = Qubit.parity.cd_period_mv (runner: 4.37)",
    },
    "two_tone_charge_dispersion_quasicw": {"num_cycles": "1 (runner: 1000)"},
    "charge_dispersion_quasicw": {
        "probe_freq": "None = Qubit.parity.f_upper_mhz (runner: 2306.567327)"
    },
    "charge_transmission_sweep": {
        "voltage_start": "None = the charge group's (runner: 0)",
        "voltage_end": "None = the charge group's (runner: 0.05)",
        "voltage_step": "None = the charge group's (runner: 0.005)",
    },
    "undriven_single_shot": {"repeat": "1 pass (runner: 10000, ~36 days at 1e6 shots)"},
    "t1_single_shot": {"repetitions": "1 run (runner: 3000)"},
    "interleaved_coherence": {"cycles": "1 cycle (runner: 10000)"},
    "auto_coherence": {
        kw: "AUTO_COHERENCE_PARAMS default (runner overrides it)"
        for kw in (
            "skip_sweet_spot_search",
            "calibrate_qubit_freq",
            "ss_gain_span_frac",
            "ss_gain_pts",
            "t1_step",
            "t1_repetitions",
            "t2_expts",
            "t2_repetitions",
            "t2e_max_us",
            "t2e_repetitions",
        )
    },
}

_NO_WINDOW = "the device has no voltage-window field (design.md Device model); runner's value"
_SEARCH_GAIN = (
    "search-spectroscopy gain the runner sets apart from the spec group's 800; one "
    "Qubit.spec_gain cannot hold both (the spec group's gain resolves from it)"
)

# step -> {keyword: why a value design.md lists as device-dependent (voltage window, spec gain)
# stays a concrete library value}. OPEN DESIGN DECISION awaiting sign-off:
# docs/running_a_session.md#values-the-device-does-not-carry
LIBRARY_DEVICE_VALUES = {
    "modified_ramsey_control": {
        "voltage_min": _NO_WINDOW,
        "voltage_max": _NO_WINDOW,
        "gain": _SEARCH_GAIN,
    },
    "two_tone_charge_dispersion_quasicw": {
        "voltage_min": _NO_WINDOW,
        "voltage_max": _NO_WINDOW,
        "gain": _SEARCH_GAIN,
    },
    "auto_coherence": {
        "ss_voltage_min": _NO_WINDOW,
        "ss_voltage_max": _NO_WINDOW,
        "spec_gain": _SEARCH_GAIN,
    },
    "zero_span_parity": {"parity_spec.gain": _SEARCH_GAIN},
}
