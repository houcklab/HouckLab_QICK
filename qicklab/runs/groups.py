"""Session-wide parameter groups: the legacy dicts several steps (and the config builders) share.

`from qicklab.runs import groups as G`; `Session(..., coherence=G.coherence(relax_delay=3000))`.
Each function is keyword-only (a misspelt keyword raises TypeError) and returns the
legacy-keyed dict the run_* functions and build_context / rebuild_singleshot_config read.
A value left at None is resolved by the session from the device (noted per parameter):
`resolve(groups, qubit)` fills the pulse qubit's values (FROM_QUBIT); every recipe Step calls it
when it builds its arguments (`Step.fill_groups`). Library defaults are the
CSTQ03 runner's values except FROZEN_DIFFERENCES.
docs/running_a_session.md#shared-groups
"""

from qicklab.core import session

# group -> ((legacy key, keyword), ...) in the legacy dict's key order
KEYS = {
    "transmission": (
        ("reps", "reps"),
        ("rounds", "rounds"),
        ("num_points", "num_points"),
        ("span", "span"),
    ),
    "spec": (
        ("qubit_gain", "qubit_gain"),
        ("SpecSpan", "spec_span"),
        ("SpecNumPoints", "spec_num_points"),
        ("qubit_length", "qubit_length"),
        ("reps", "reps"),
        ("rounds", "rounds"),
        ("Gauss", "gauss"),
        ("sigma", "sigma"),
        ("gain", "gain"),
        ("relax_delay", "relax_delay"),
        ("display", "display"),
        ("min_sep_MHz", "min_sep_mhz"),
        ("fit_window_mhz", "fit_window_mhz"),
        ("prominent_ratio", "prominent_ratio"),
        ("sweep_lengths", "sweep_lengths"),
        ("sweep_gains", "sweep_gains"),
    ),
    "charge": (
        ("voltage_start", "voltage_start"),
        ("voltage_end", "voltage_end"),
        ("voltage_step", "voltage_step"),
    ),
    "tones": (("tone_length", "tone_length"),),
    "coherence": (
        ("T1_step", "t1_step"),
        ("T1_expts", "t1_expts"),
        ("T1_reps", "t1_reps"),
        ("T1_rounds", "t1_rounds"),
        ("T2_step", "t2_step"),
        ("T2_expts", "t2_expts"),
        ("T2_reps", "t2_reps"),
        ("T2_rounds", "t2_rounds"),
        ("freq_shift", "freq_shift"),
        ("relax_delay", "relax_delay"),
        ("repetitions", "repetitions"),
    ),
    "echo": (
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
    ),
    "single_shot": (
        ("Shots", "shots"),
        ("Readout_Time", "readout_time"),
        ("ADC_Offset", "adc_offset"),
        ("Qubit_Pulse", "qubit_pulse"),
        ("number_of_pulses", "number_of_pulses"),
        ("relax_delay", "relax_delay"),
        ("pi2_SS", "pi2_ss"),
    ),
}

# group -> {keyword: why the library default differs from the CSTQ03 runner's value}
FROZEN_DIFFERENCES = {
    "spec": {"gain": "None = Qubit.spec_gain, else 800 (runner: 800)"},
    "coherence": {"repetitions": "1 run (runner: 1000 back-to-back T1/T2 sets)"},
    "echo": {"repetitions": "1 run (runner: 3000)"},
    "single_shot": {
        "readout_time": "None = the device's ss_window (runner: 15 us, the CSTQ03 ss_window)",
        "adc_offset": "None = the device's ss_window (runner: 0.3 us, the CSTQ03 ss_window)",
        "qubit_pulse": "None = [the session's qubit_pulse] (runner: [Qubit_Pulse])",
    },
}

# group -> {legacy key: (Qubit attribute, value when the qubit has none)}: the None defaults
# `resolve` fills from the pulse qubit (an explicit group value is kept)
FROM_QUBIT = {"spec": {"gain": ("spec_gain", 800)}}


def _legacy(group, values):
    return {legacy: values[kw] for legacy, kw in KEYS[group]}


def transmission(*, reps=20, rounds=20, num_points=201, span=5):
    """Resonator sweep (Transmission_params): regime-A base config, transmission_fit/_sweep.

    reps: hardware averages per point (one tProc program); rounds: software repeats of it.
    num_points: frequency points; span [MHz]: the sweep is pulse_freq +- span.
    """
    return _legacy("transmission", locals())


def spec(
    *,
    qubit_gain=1000,
    spec_span=10,
    spec_num_points=201,
    qubit_length=50,
    reps=20,
    rounds=10,
    gauss=False,
    sigma=2,
    gain=None,
    relax_delay=2500,
    display=True,
    min_sep_mhz=0.2,
    fit_window_mhz=0.5,
    prominent_ratio=0.1,
    sweep_lengths=tuple(range(10, 101, 10)),
    sweep_gains=tuple(range(200, 5001, 100)),
):
    """Two-tone spectroscopy (Spec_relevant_params): regime-A base config and every spec step.

    qubit_gain [DAC]: drive gain of the regime-A base config (CW / flat-spec steps); gain [DAC]:
    drive gain the spec steps play (None: the pulse qubit's Qubit.spec_gain, else 800).
    spec_span [MHz]: sweep is qubit freq +- spec_span over spec_num_points.
    qubit_length [us]: const drive length (gauss=False); gauss=True plays a Gaussian of sigma [us].
    reps / rounds: hardware / software averages. relax_delay [us] between shots.
    display: show the fit plot. min_sep_mhz [MHz]: smallest doublet separation accepted;
    fit_window_mhz [MHz]: Lorentzian fit window per peak; prominent_ratio: second-peak height
    threshold (fraction of the first). sweep_lengths [us] x sweep_gains [DAC]: the
    spec_gain_length_sweep grid.
    """
    out = _legacy("spec", locals())
    out["sweep_lengths"] = list(sweep_lengths)
    out["sweep_gains"] = list(sweep_gains)
    return out


def charge_range(*, voltage_start=0.0, voltage_end=0.05, voltage_step=0.005):
    """Charge-bias grid (charge_params) [V]: np.arange(start, end, step), end excluded.

    Merged into the regime-A base config; read by charge_sweep and charge_transmission_sweep.
    """
    return _legacy("charge", locals())


def tones(*, tone_length=151):
    """CW tones (tl): tone_length [us], the repetition period of constant_two_tone's tones."""
    return _legacy("tones", locals())


def coherence(
    *,
    t1_step=5,
    t1_expts=100,
    t1_reps=20,
    t1_rounds=20,
    t2_step=0.1,
    t2_expts=100,
    t2_reps=20,
    t2_rounds=20,
    freq_shift=0.0,
    relax_delay=3000,
    repetitions=1,
):
    """T1 / T2 Ramsey (T1T2_params): t1, t2_ramsey, the combos, trans_qubit_spec, interleave.

    t1_step [us] x t1_expts wait points; t2_step [us] x t2_expts Ramsey delays; *_reps / *_rounds
    hardware / software averages. freq_shift [MHz]: real detuning of the Ramsey pi/2 pulses.
    relax_delay [us] between shots. repetitions: back-to-back runs (also trans_qubit_spec's and
    charge_dispersion_ramsey's repeat count).
    """
    return _legacy("coherence", locals())


def echo(
    *,
    t2_max_us=20,
    t2_expts=121,
    t2_reps=25,
    t2_rounds=25,
    freq_shift=0.0,
    relax_delay=500,
    num_pi_pulses=1,
    rotation_angle=None,
    min_max=None,
    repetitions=1,
):
    """T2 echo (T2E_params): t2_echo, t1_t2e, t1_t2r_t2e, interleaved_coherence.

    t2_max_us [us] total echo time over t2_expts points; t2_reps / t2_rounds averages.
    freq_shift [MHz]: detuning of the pulses. relax_delay [us]. num_pi_pulses: odd (CPMG).
    rotation_angle [rad] / min_max: fixed display normalisation (None: fitted per run).
    repetitions: back-to-back runs.
    """
    return _legacy("echo", locals())


def single_shot(
    *,
    shots=1000,
    readout_time=None,
    adc_offset=None,
    qubit_pulse=None,
    number_of_pulses=1,
    relax_delay=6000,
    pi2_ss=False,
):
    """Single-shot readout (SS_params): the regime-B config builder and the single-shot steps.

    shots per state. readout_time [us] ADC window and adc_offset [us] trigger delay: None = the
    device's ss_window. qubit_pulse: qubits whose pi gains / freqs enter the config (None = the
    session's qubit_pulse). number_of_pulses: pi pulses in the e preparation. relax_delay [us].
    pi2_ss: prepare with the pi/2 gain instead of the pi gain.
    """
    out = _legacy("single_shot", locals())
    if qubit_pulse is not None:
        out["Qubit_Pulse"] = [qubit_pulse] if isinstance(qubit_pulse, int) else list(qubit_pulse)
    return out


def resolve(groups, qubit):
    """`groups` ({name: dict}) as fresh dicts with the FROM_QUBIT Nones filled from `qubit`.

    Precedence: library value < Qubit attribute < a value set on the group (or a step override).
    The single_shot window / qubit_pulse Nones need the device and session: not filled here.
    """
    out = {}
    for name, values in groups.items():
        values = dict(values)
        for key, (attr, fallback) in FROM_QUBIT.get(name, {}).items():
            if values.get(key) is None:
                own = getattr(qubit, attr, None)
                values[key] = fallback if own is None else own
        out[name] = values
    return out


# session group name -> its function (Session(charge=charge_range(...)), ...)
BUILDERS = {
    "transmission": transmission,
    "spec": spec,
    "charge": charge_range,
    "tones": tones,
    "coherence": coherence,
    "echo": echo,
    "single_shot": single_shot,
}

session.register_group_builders(BUILDERS)  # Session's library defaults (core cannot import runs)
