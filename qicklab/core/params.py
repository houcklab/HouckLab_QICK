"""Parameter registry: every knob a user sets or an experiment reads, with units and meaning.

`PARAMS[(key, scope)]` is a `Param`. The scope says where the value is typed:
  "device"           a device-file field, key "<Class>.<field>" (`Qubit.freq`, `Setup.yoko_addr`)
  "session"          a `Session(...)` argument other than the groups (`qubit_pulse`, `bias_v`)
  "session:<group>"  a keyword of `G.<group>(...)` (qicklab.runs.groups)
  "recipe:<step>"    a keyword of `R.<step>(...)` (qicklab.runs.recipes); a key of one of
                     zero_span_parity's dict keywords is "<keyword>.<legacy key>"
  "cfg"              a key of the flat experiment cfg dict, as recorded per class in the
                     regression golden (`cfg_access`), or present only in the saved cfg
                     records (RECORD_ONLY_CFG: provenance the run functions set)
  "cfg:<variant>"    the same cfg key with a second meaning, for the classes in its read_by
A word that means two things gets one entry per scope (`relax_delay` in session:coherence vs
`mr_relax_delay` in recipe:modified_ramsey; cfg `qubit_gain` = spec gain vs cfg:single_shot
`qubit_gain` = pi gain). docs/parameters.md is generated from this table (scripts/gen_docs.py);
tests/test_params_registry.py checks it against the golden, the recipes, the groups and the
device model.
"""

from dataclasses import dataclass, replace

# Allowed `units` words; a composite value lists one per part ("GHz, dBm, index").
# "1" = dimensionless count or ratio; "a.u." = normalised IQ; "ADC units" = raw accumulated IQ;
# "flag" = bool; "text" = a string or a choice; "index" = a channel, port or qubit number;
# "dict" / "object" = a structured value whose entries are listed separately or in `meaning`.
UNITS = frozenset(
    {
        "1",
        "a.u.",
        "ADC units",
        "DAC units",
        "phase register units",
        "tProc cycles",
        "MHz",
        "GHz",
        "Hz",
        "us",
        "ms",
        "s",
        "V",
        "mV",
        "uA",
        "dB",
        "dBm",
        "rad",
        "shots",
        "points",
        "flag",
        "text",
        "index",
        "dict",
        "object",
    }
)
LAYERS = ("hardware", "core", "analysis", "experiments", "runs", "twpa")
SCOPE_FAMILIES = ("device", "session", "recipe", "cfg")


@dataclass(frozen=True)
class Param:
    """One registry entry; `read_by` names the classes / functions that consume the value."""

    key: str
    scope: str
    units: str
    meaning: str
    layer: str
    read_by: tuple = ()
    notes: str = ""


PARAMS = {}


def scope_family(scope):
    """'recipe:t1' -> 'recipe', 'cfg:single_shot' -> 'cfg', 'device' -> 'device'."""
    return scope.split(":", 1)[0]


def entries(family=None, scope=None):
    """Registry entries, optionally only one scope family or one exact scope, sorted."""
    out = [
        p
        for p in PARAMS.values()
        if (family is None or scope_family(p.scope) == family)
        and (scope is None or p.scope == scope)
    ]
    return sorted(out, key=lambda p: (p.scope, p.key.lower(), p.key))


def cfg_entries(key):
    """Every cfg-family entry of `key` ("cfg" first, then its variants)."""
    return [p for p in entries("cfg") if p.key == key]


def _names(spec):
    return tuple(spec.split()) if isinstance(spec, str) else tuple(spec)


def _add(key, scope, units, meaning, layer, read_by=(), notes=""):
    if (key, scope) in PARAMS:
        raise ValueError(f"duplicate parameter {(key, scope)}")
    if scope_family(scope) not in SCOPE_FAMILIES:
        raise ValueError(f"{(key, scope)}: unknown scope family")
    if layer not in LAYERS:
        raise ValueError(f"{(key, scope)}: unknown layer {layer!r}")
    if not units or any(u.strip() not in UNITS for u in units.split(",")):
        raise ValueError(f"{(key, scope)}: units {units!r} not in UNITS")
    PARAMS[(key, scope)] = Param(key, scope, units, meaning, layer, _names(read_by), notes)


def _recipe(step, keywords, *, own=None, inherit=None, layer="runs"):
    """Register R.<step>'s keywords (space-separated), read by STEP_FUNCTIONS[step].

    Each keyword takes, in order: own[kw] = (units, meaning[, layer[, notes]]); inherit[kw] =
    (scope, key[, notes]), whose units / meaning / layer it copies (notes default: "None: the
    <group> group's <key>"); _KW[kw].
    """
    own, inherit = own or {}, inherit or {}
    fn = STEP_FUNCTIONS[step]
    for kw in keywords.split():
        if kw in own:
            spec = own[kw]
        elif kw in inherit:
            scope, key, *note = inherit[kw]
            src = PARAMS[(key, scope)]
            notes = note[0] if note else f"None: the {scope.split(':')[1]} group's {key}"
            spec = (src.units, src.meaning, src.layer, notes)
        else:
            spec = _KW[kw]
        units, meaning = spec[0], spec[1]
        kw_layer = spec[2] if len(spec) > 2 else layer
        notes = spec[3] if len(spec) > 3 else ""
        _add(kw, f"recipe:{step}", units, meaning, kw_layer, (fn,), notes)


def _from(scope, *keywords, rename=None):
    """{keyword: (scope, key)} for keywords inherited unchanged (rename: keyword -> key)."""
    out = {kw: (scope, kw) for kw in keywords}
    for kw, key in (rename or {}).items():
        out[kw] = (scope, key)
    return out


# The tables below are hand-aligned data (one row per parameter): kept out of the formatter.
# fmt: off

# ---------------------------------------------------------------------------------------------
# device: devices/<NAME>.py (qicklab.core.device)

_DEVICE = (
    # (key, units, meaning, layer, read_by, notes)
    ("Device.name", "text", "chip name; recorded in every saved file's provenance", "core",
     "connect io.start_session record_calibration", ""),
    ("Device.cooldown", "text", "cooldown date or label of this device file", "core",
     "io.start_session record_calibration", ""),
    ("Device.data_root", "text", "data root; qubit q saves under <data_root>/Q{q}//", "core",
     "Device.folder Device.legacy_parameters", "byte-identical to the legacy QubitFolders"),
    ("Device.qubits", "object", "{1: Qubit, ..., N: Qubit}, stored read-only", "core",
     "Session Device.legacy_parameters Device.validate", "keys must be 1..N"),
    ("Device.setup", "object", "instrument endpoints and board overrides (a Setup)", "core",
     "connect", ""),
    ("Device.cavity_min", "flag", "resonator shows as a transmission dip (True) or a peak",
     "core", "connect build_context run_transmission_sweep", ""),
    ("Device.readout_window", "object", "regime-A readout window (a ReadoutWindow)", "core",
     "Device.window connect", "per-qubit Readout.window overrides it"),
    ("Device.ss_window", "object", "regime-B (single-shot) readout window (a ReadoutWindow)",
     "core", "Device.window Session.groups", "per-qubit Readout.ss_window overrides it"),
    ("ReadoutWindow.length_us", "us", "ADC integration window (cfg readout_length)", "core",
     "connect Session.groups", "the resonator tone lasts adc_offset_us + length_us"),
    ("ReadoutWindow.adc_offset_us", "us", "delay from tone start to ADC trigger "
     "(cfg adc_trig_offset)", "core", "connect Session.groups", ""),
    ("Readout.freq", "MHz", "readout resonator frequency (cfg pulse_freq)", "core",
     "Device.legacy_parameters Device.validate", ""),
    ("Readout.gain", "DAC units", "readout tone gain (cfg pulse_gain), 0..32767", "core",
     "Device.legacy_parameters Device.validate", ""),
    ("Readout.window", "object", "regime-A window override for this resonator", "core",
     "Device.window", "None: Device.readout_window"),
    ("Readout.ss_window", "object", "regime-B window override for this resonator", "core",
     "Device.window", "None: Device.ss_window"),
    ("Readout.kappa_mhz", "MHz", "resonator linewidth kappa/2pi; the active-reset readout "
     "delay should be >= ~6/kappa", "core", "Device.validate",
     "validated only; no step reads it yet"),
    ("Qubit.freq", "MHz", "qubit centre frequency (cfg f_ge / qubit_freq)", "core",
     "Device.legacy_parameters Device.validate recipes.amplitude_rabi", ""),
    ("Qubit.gain", "DAC units", "pi-pulse gain (cfg pi_gain; qubit_gain in regime B)", "core",
     "Device.legacy_parameters Device.validate", ""),
    ("Qubit.sigma", "us", "Gaussian sigma of the qubit pulses (envelope 4 sigma)", "core",
     "Device.legacy_parameters Device.validate", ""),
    ("Qubit.readout", "object", "this qubit's readout resonator (a Readout)", "core",
     "Device.legacy_parameters Device.window", ""),
    ("Qubit.pi2_gain", "DAC units", "pi/2-pulse gain (cfg pi2_gain)", "core",
     "Qubit.effective_pi2_gain Device.validate", "None: gain // 2"),
    ("Qubit.flattop_length", "us", "flat segment of a flat-top pulse (cfg flattop_length)",
     "core", "Device.legacy_parameters Device.validate", "None: plain Gaussian"),
    ("Qubit.spec_gain", "DAC units", "spectroscopy drive gain the spec steps play", "core",
     "groups.resolve Device.validate", "fills the spec group's gain when that is None"),
    ("Qubit.bias_v", "V", "preferred charge-line bias of this qubit", "core", (),
     "documentation field: no code reads it yet (Session.bias_v sets the bias)"),
    ("Qubit.t1_us", "us", "last measured T1", "core", (),
     "documentation field: no code reads it yet"),
    ("Qubit.parity", "object", "charge-parity calibration (a ParityParams) or None", "core",
     "recipes Device.validate", "the parity steps resolve df / f_upper / cd_* from it"),
    ("Qubit.notes", "text", "free-text notes on this qubit", "core", (),
     "documentation field: no code reads it"),
    ("ParityParams.df_mhz", "MHz", "parity branch splitting", "core",
     "recipes.modified_ramsey recipes.modified_ramsey_control recipes.charge_dispersion_ramsey "
     "recipes.zero_span_parity",
     "modified_ramsey tau = tau_harmonic_k / (2 df)"),
    ("ParityParams.f_upper_mhz", "MHz", "UPPER parity branch (not the doublet centre)", "core",
     "recipes.modified_ramsey recipes.charge_dispersion_quasicw recipes.zero_span_parity",
     "symmetric_ramsey needs it; the lower branch is f_upper - df"),
    ("ParityParams.cd_max_mhz", "MHz", "peak charge dispersion of S(V) = cd_max |cos(2 pi "
     "(V - V0) / T)|", "core", "recipes.modified_ramsey_control", ""),
    ("ParityParams.cd_period_mv", "mV", "period T of that fit, in mV of yoko voltage", "core",
     "recipes.modified_ramsey_control recipes.charge_sweep recipes.auto_coherence", ""),
    ("ParityParams.p_e_state0", "1", "Ramsey mapping P(e | parity state 0)", "core",
     "recipes.modified_ramsey recipes.modified_ramsey_control", ""),
    ("ParityParams.p_e_state1", "1", "Ramsey mapping P(e | parity state 1)", "core",
     "recipes.modified_ramsey recipes.modified_ramsey_control", ""),
    ("ParityParams.calibrated", "flag", "True once the mapping comes from a calibration",
     "core", "recipes.modified_ramsey recipes.modified_ramsey_control", ""),
    ("Setup.rfsoc_host", "text", "RFSoC Pyro4 nameserver host", "hardware",
     "connect makeProxy", ""),
    ("Setup.rfsoc_port", "index", "RFSoC Pyro4 nameserver port", "hardware",
     "connect makeProxy", ""),
    ("Setup.rfsoc_name", "text", "QICK server name registered on the nameserver", "hardware",
     "connect makeProxy", ""),
    ("Setup.yoko_addr", "text", "VISA address of the charge-line yoko (voltage mode)",
     "hardware", "connect open_charge_yoko", ""),
    ("Setup.board_overrides", "dict", "keys merged over BASE_CONFIG (nqz, qubit_nqz, "
     "cavity_winding_*, trig_*)", "hardware", "Setup.board_config Device.validate",
     "connect refuses a non-empty dict: build_context does not apply it yet"),
    ("Setup.ff_qubits", "dict", "fast-flux channel map (metadata only)", "hardware", "connect",
     "None: hardware.board.FF_QUBITS; connect refuses another value yet"),
    ("Setup.twpa", "object", "TWPA instruments (a TwpaSetup) or None", "twpa", (),
     "documentation field: the qicklab.twpa scripts still use their own constants"),
    ("TwpaSetup.yoko_addr", "text", "VISA address of the TWPA bias yoko (current mode)",
     "twpa", (), "documentation field (qicklab.twpa.set_bias.TWPA_YOKO_ADDRESS is used)"),
    ("TwpaSetup.synth_port", "text", "serial port of the SynthHD pump synthesizer", "twpa", (),
     "documentation field"),
    ("TwpaSetup.pnax_addr", "text", "VISA address of the PNA-X", "twpa", (),
     "documentation field"),
    ("TwpaSetup.pump", "GHz, dBm, index", "pump operating point (frequency, power, synth "
     "channel)", "twpa", (), "documentation field"),
    ("TwpaSetup.bias_ua", "uA", "TWPA DC bias target", "twpa", (), "documentation field"),
)
for _key, _units, _meaning, _layer, _read_by, _notes in _DEVICE:
    _add(_key, "device", _units, _meaning, _layer, _read_by, _notes)

# ---------------------------------------------------------------------------------------------
# session: Session(...) arguments (qicklab.core.session) other than the groups

_SESSION = (
    # (key, units, meaning, read_by, notes)
    ("device", "object", "the Device (devices/<NAME>.py) this session measures",
     "connect Session.qubit", ""),
    ("qubit_readout", "index", "qubit whose resonator is read: readout freq, gain, window and "
     "data folder", "connect Session.groups", "legacy Qubit_Readout"),
    ("qubit_pulse", "index", "qubit that is driven: freq, pi gain, sigma; recipes resolve "
     "device values from it", "connect Session.qubit", "legacy Qubit_Pulse"),
    ("bias_v", "V", "charge-line yoko voltage set at connect (cfg current_voltage)",
     "connect build_context", "legacy start_voltage"),
    ("yoko_fixed", "flag", "hold the bias: charge_sweep repeats the spectroscopy over time",
     "connect run_charge_sweep", ""),
    ("interactive_plots", "flag", "show plots in windows", "connect",
     "no effect yet (warns): importing qicklab.analysis selects the Agg backend"),
)
for _key, _units, _meaning, _read_by, _notes in _SESSION:
    _add(_key, "session", _units, _meaning, "core", _read_by, _notes)

# ---------------------------------------------------------------------------------------------
# session:<group>: G.<group>(...) keywords (qicklab.runs.groups)

_GROUP_READERS = {
    "transmission": "build_context run_transmission_fit run_transmission_sweep "
                    "run_charge_transmission_sweep",
    "spec": "build_context run_two_tone_spec run_spec_gain_length_sweep run_trans_qubit_spec "
            "run_two_tone_charge_dispersion_quasicw run_charge_dispersion_quasicw "
            "run_charge_sweep",
    "charge": "build_context run_charge_sweep run_charge_transmission_sweep",
    "tones": "build_context run_constant_two_tone ConstantTwoTone",
    "coherence": "run_t1 run_t2 run_t1_t2e run_t1_t2r_t2e run_trans_qubit_spec "
                 "run_interleaved_coherence run_charge_dispersion_ramsey",
    "echo": "run_t2e run_t1_t2e run_t1_t2r_t2e run_interleaved_coherence",
    "single_shot": "rebuild_singleshot_config run_single_shot run_t1_ss run_qubit_optimize "
                   "run_interleaved_coherence",
}

_GROUPS = {
    # group: ((keyword, units, meaning, layer, notes), ...)
    "transmission": (
        ("reps", "shots", "hardware averages per frequency point", "runs", ""),
        ("rounds", "1", "software repeats of each point's program", "runs", ""),
        ("num_points", "points", "frequency points of the resonator sweep (cfg TransNumPoints)",
         "runs", ""),
        ("span", "MHz", "half-width: the sweep is pulse_freq +- span (cfg TransSpan)", "runs",
         ""),
    ),
    "spec": (
        ("qubit_gain", "DAC units", "drive gain of the regime-A base config (cfg qubit_gain): "
         "constant_two_tone and the Gauss=False charge steps", "runs",
         "not the gain two_tone_spec plays (that is `gain`)"),
        ("spec_span", "MHz", "half-width: the two-tone sweep is qubit freq +- spec_span",
         "runs", "cfg SpecSpan; build_context derives start / step from it"),
        ("spec_num_points", "points", "frequency points of the two-tone sweep", "runs",
         "cfg SpecNumPoints / expts"),
        ("qubit_length", "us", "length of the const drive pulse (gauss=False)", "runs", ""),
        ("reps", "shots", "hardware averages per frequency point", "runs", ""),
        ("rounds", "1", "software repeats of the program", "runs", ""),
        ("gauss", "flag", "play a Gaussian of `sigma` instead of a const pulse", "runs",
         "cfg Gauss"),
        ("sigma", "us", "Gaussian sigma of the spec drive (gauss=True)", "runs", ""),
        ("gain", "DAC units", "drive gain the spectroscopy steps play", "runs",
         "None: Qubit.spec_gain, else 800"),
        ("relax_delay", "us", "wait after each shot before the next", "runs", ""),
        ("display", "flag", "show the spectroscopy fit plot", "runs", ""),
        ("min_sep_mhz", "MHz", "smallest separation accepted as a parity doublet", "analysis",
         "legacy min_sep_MHz"),
        ("fit_window_mhz", "MHz", "Lorentzian fit window around each peak", "analysis", ""),
        ("prominent_ratio", "1", "second-peak height threshold, fraction of the first",
         "analysis", ""),
        ("sweep_lengths", "us", "drive lengths of the spec_gain_length_sweep grid", "runs", ""),
        ("sweep_gains", "DAC units", "drive gains of the spec_gain_length_sweep grid", "runs",
         ""),
    ),
    "charge": (
        ("voltage_start", "V", "first bias of the charge grid np.arange(start, end, step)",
         "runs", ""),
        ("voltage_end", "V", "end of the charge grid (excluded)", "runs", ""),
        ("voltage_step", "V", "step of the charge grid", "runs", ""),
    ),
    "tones": (
        ("tone_length", "us", "repetition period of constant_two_tone's periodic tones",
         "runs", "capped at the 16-bit length register (65535 cycles)"),
    ),
    "coherence": (
        ("t1_step", "us", "T1 wait step", "runs", "legacy T1_step"),
        ("t1_expts", "points", "T1 wait points", "runs", ""),
        ("t1_reps", "shots", "T1 hardware averages per point", "runs", ""),
        ("t1_rounds", "1", "T1 software repeats", "runs", ""),
        ("t2_step", "us", "Ramsey delay step", "runs", "legacy T2_step"),
        ("t2_expts", "points", "Ramsey delay points", "runs", ""),
        ("t2_reps", "shots", "Ramsey hardware averages per point", "runs", ""),
        ("t2_rounds", "1", "Ramsey software repeats", "runs", ""),
        ("freq_shift", "MHz", "real detuning of the Ramsey pi/2 pulses from f_ge", "runs", ""),
        ("relax_delay", "us", "wait after each shot before the next", "runs", ""),
        ("repetitions", "1", "back-to-back runs, each its own files", "runs",
         "also the loop count of trans_qubit_spec and charge_dispersion_ramsey"),
    ),
    "echo": (
        ("t2_max_us", "us", "total echo time of the last point", "runs", "legacy T2_max_us"),
        ("t2_expts", "points", "echo delay points", "runs", ""),
        ("t2_reps", "shots", "hardware averages per point", "runs", ""),
        ("t2_rounds", "1", "software repeats", "runs", ""),
        ("freq_shift", "MHz", "detuning of the echo pulses from f_ge", "runs", ""),
        ("relax_delay", "us", "wait after each shot before the next", "runs", ""),
        ("num_pi_pulses", "1", "refocusing pi pulses: 1 = Hahn echo, more = CPMG (keep odd)",
         "runs", ""),
        ("rotation_angle", "rad", "fixed IQ rotation of the display", "analysis",
         "None: fitted per run"),
        ("min_max", "a.u.", "fixed (ground, excited) levels that normalise the display",
         "analysis", "None: not normalised"),
        ("repetitions", "1", "back-to-back runs, each its own files", "runs", ""),
    ),
    "single_shot": (
        ("shots", "shots", "single shots per prepared state (cfg shots; programs set reps)",
         "runs", "legacy Shots"),
        ("readout_time", "us", "regime-B ADC integration window (cfg readout_length)", "runs",
         "None: the readout qubit's ss_window; legacy Readout_Time"),
        ("adc_offset", "us", "regime-B tone-start-to-ADC-trigger delay (cfg adc_trig_offset)",
         "runs", "None: the readout qubit's ss_window; legacy ADC_Offset"),
        ("qubit_pulse", "index", "qubits whose pi gains / freqs enter the regime-B config",
         "runs", "None: [Session.qubit_pulse]; legacy Qubit_Pulse"),
        ("number_of_pulses", "1", "pi pulses in the |e> preparation (0: thermal mode)", "runs",
         ""),
        ("relax_delay", "us", "wait after each shot before the next", "runs", ""),
        ("pi2_ss", "flag", "prepare with the pi/2 gain instead of the pi gain", "runs",
         "legacy pi2_SS"),
    ),
}
for _group, _rows in _GROUPS.items():
    for _key, _units, _meaning, _layer, _notes in _rows:
        _add(_key, f"session:{_group}", _units, _meaning, _layer, _GROUP_READERS[_group], _notes)

# ---------------------------------------------------------------------------------------------
# recipe:<step>: R.<step>(...) keywords (qicklab.runs.recipes)

# step -> the run_* its Step calls (qicklab.runs.recipes._register)
STEP_FUNCTIONS = {
    "constant_tone": "run_constant_tone",
    "constant_two_tone": "run_constant_two_tone",
    "transmission_fit": "run_transmission_fit",
    "transmission_sweep": "run_transmission_sweep",
    "chi_shift": "run_chi_shift",
    "two_tone_spec": "run_two_tone_spec",
    "spec_gain_length_sweep": "run_spec_gain_length_sweep",
    "trans_qubit_spec": "run_trans_qubit_spec",
    "amplitude_rabi": "run_amplitude_rabi",
    "t1": "run_t1",
    "t2_ramsey": "run_t2",
    "t2_echo": "run_t2e",
    "t1_t2e": "run_t1_t2e",
    "t1_t2r_t2e": "run_t1_t2r_t2e",
    "interleaved_coherence": "run_interleaved_coherence",
    "auto_coherence": "run_auto_coherence",
    "single_shot": "run_single_shot",
    "undriven_single_shot": "run_undriven_single_shot",
    "t1_single_shot": "run_t1_ss",
    "readout_optimize": "run_readout_optimize",
    "qubit_optimize": "run_qubit_optimize",
    "active_reset_verify": "run_active_reset_verify",
    "modified_ramsey": "run_modified_ramsey",
    "modified_ramsey_control": "run_modified_ramsey_control",
    "two_tone_charge_dispersion_quasicw": "run_two_tone_charge_dispersion_quasicw",
    "charge_dispersion_quasicw": "run_charge_dispersion_quasicw",
    "charge_dispersion_ramsey": "run_charge_dispersion_ramsey",
    "charge_sweep": "run_charge_sweep",
    "charge_transmission_sweep": "run_charge_transmission_sweep",
    "zero_span_parity": "run_zero_span_parity",
}

# keyword -> (units, meaning[, layer]) for words several recipes use in the same sense
_KW = {
    "reps":                     ("shots", "hardware averages per point"),
    "rounds":                   ("1", "software repeats of the program, averaged in Python"),
    "search_rounds":            ("1", "software repeats of each search spectrum"),
    "relax_delay":              ("us", "wait after each shot before the next"),
    "repetitions":              ("1", "back-to-back runs, each its own files"),
    "plot_disp":                ("flag", "show the plot"),
    "fit":                      ("flag", "fit the data in the display"),
    "hold_s":                   ("s", "keep the tones on this long (None: until Enter)"),
    "dv":                       ("V", "bias step of the doublet search (legacy dV)"),
    "voltage_min":              ("V", "lower end of the bias search window"),
    "voltage_max":              ("V", "upper end of the bias search window"),
    "max_voltage_tries":        ("1", "bias steps tried before the search gives up"),
    "spec_span":                ("MHz", "half-width of the two-tone sweep around the qubit "
                                 "frequency"),
    "spec_num_points":          ("points", "frequency points of the two-tone sweep"),
    "sigma":                    ("us", "Gaussian sigma of the spectroscopy drive"),
    "gain":                     ("DAC units", "spectroscopy drive gain"),
    "qubit_length":             ("us", "length of the const spectroscopy pulse"),
    "gauss":                    ("flag", "Gaussian spectroscopy pulse instead of a const one"),
    "expected_parity_dwell_ms": ("ms", "expected parity dwell time; sets the analysis time "
                                 "scales", "analysis"),
    "min_partner_snr":          ("1", "significance (noise sigma) the weaker parity line "
                                 "needs; 0 switches the gate off", "analysis"),
}

# modified_ramsey keywords (units, meaning, layer, notes); modified_ramsey_control inherits
# the sequence / reset / analysis ones
_MR = {
    "df":                       ("MHz", "parity branch splitting; tau = tau_harmonic_k / (2 df)",
                                 "runs", "None: Qubit.parity.df_mhz (raises without it)"),
    "f_ge":                     ("MHz", "UPPER parity branch the Ramsey drives (cfg f_ge)",
                                 "runs", "None: Qubit.parity.f_upper_mhz; with neither, "
                                 "symmetric_ramsey=True raises"),
    "f_ge_measured_at_v":       ("V", "bias at which f_ge was calibrated (warns when moved)",
                                 "runs", ""),
    "require_f_ge_near_qubit":  ("flag", "raise instead of warn when f_ge is far from the "
                                 "qubit frequency", "runs", ""),
    "num_cycles":               ("1", "records taken back to back", "runs", ""),
    "use_apriori_separator":    ("flag", "classify with a fresh SingleShot g/e separator",
                                 "runs", ""),
    "mr_relax_delay":           ("us", "wait after each Ramsey readout (cfg mr_relax_delay)",
                                 "runs", "not relax_delay: the MR program reads mr_relax_delay"),
    "mr_reps":                  ("shots", "shots per record (cfg reps)", "runs", ""),
    "average_n_shots":          ("shots", "bin size of the legacy hard-threshold plot only",
                                 "analysis", "keep well below one dwell"),
    "parity_analysis_enabled":  ("flag", "run the HMM / ACF / PSD parity analysis", "analysis",
                                 ""),
    "validation_controls":      ("text", "control sequences interleaved with the record "
                                 "(flip_final_pi2, echo_null, drive_off, drive_detuned, "
                                 "tau_offset)", "runs", ""),
    "validation_controls_every_n_cycles": ("1", "cycles between control runs", "runs", ""),
    "control_tau_offset_frac":  ("1", "tau_offset control: fractional tau change", "runs",
                                 "None: the predicted null next to the programmed tau"),
    "control_detuning_mhz":     ("MHz", "drive_detuned control: drive detuning", "runs",
                                 "None: +df"),
    "tau_harmonic_k":           ("1", "odd harmonic k of tau = k / (2 df)", "runs", ""),
    "use_pi_pulse":             ("flag", "add an echo pi pulse in the middle of the Ramsey",
                                 "runs", ""),
    "flip_final_pi2":           ("flag", "close with a +180 deg pi/2 (inverts the mapping)",
                                 "runs", ""),
    "symmetric_ramsey":         ("flag", "drive at f_ge - df/2, midway between the branches",
                                 "runs", "needs the upper branch f_ge"),
    "max_drive_bandwidth_ratio": ("1", "cap on branch detuning / pi/2 Rabi rate", "runs", ""),
    "use_active_reset":         ("flag", "measurement-based reset before each Ramsey", "runs",
                                 ""),
    "reset_cycles":             ("1", "measure -> conditional pi rounds per reset", "runs", ""),
    "reset_ground_below_threshold": ("flag", "ground state lies below the I threshold", "runs",
                                     "from the separator calibration"),
    "reset_readout_relax_delay": ("us", "wait after each reset readout (>= ~6/kappa)", "runs",
                                  ""),
    "reset_read_latency_us":    ("us", "settle between reset readout and feedback pulse",
                                 "runs", "None: the program's 0.5 us floor; can raise it, "
                                 "never lower it"),
    "post_reset_wait":          ("us", "wait after the reset before the sequence", "runs", ""),
    "readout_threshold":        ("a.u.", "single-shot I threshold of the reset decision "
                                 "(normalised I)", "runs", "None: from the separator; "
                                 "core.active_reset scales it by the readout window"),
    "ss_calib_shots":           ("shots", "shots of the SingleShot separator calibration",
                                 "runs", ""),
    "ss_recalib_every_n_cycles": ("1", "cycles between separator recalibrations", "runs", ""),
    "expected_parity_dwell_ms": ("ms", "expected parity dwell time; sets the analysis time "
                                 "scales", "analysis", ""),
    "drift_window_ms":          ("ms", "window of the drift tracking in the analysis",
                                 "analysis", ""),
    "hmm_symmetric":            ("flag", "fit one switching rate for both directions",
                                 "analysis", ""),
    "hmm_bootstrap_samples":    ("1", "bootstrap resamples for the HMM rate error (0: none)",
                                 "analysis", ""),
    "hmm_fit_mapping":          ("flag", "fit the mapping probabilities with the rate",
                                 "analysis", ""),
    "mapping_p_e_state0":       ("1", "P(e | parity state 0), seed or fixed value", "analysis",
                                 "None: Qubit.parity.p_e_state0, else 0.1"),
    "mapping_p_e_state1":       ("1", "P(e | parity state 1), seed or fixed value", "analysis",
                                 "None: Qubit.parity.p_e_state1, else 0.9"),
    "mapping_probabilities_calibrated": ("flag", "the mapping comes from a calibration",
                                         "analysis", "None: Qubit.parity.calibrated, else "
                                         "False"),
    "hmm_min_emission_snr":     ("1", "emission SNR below which the HMM rate is flagged",
                                 "analysis", "None: 0.7"),
    "hmm_kwargs":               ("dict", "extra fit_two_state_hmm keywords", "analysis", ""),
}

# auto_coherence keywords: the AUTO_COHERENCE_PARAMS keys in lower case
_AC = {
    "spec_span":              ("MHz", "half-width of the two-tone sweep around the qubit centre"),
    "spec_num_pts":           ("points", "frequency points per spec run"),
    "spec_reps":              ("shots", "spec hardware averages per point"),
    "spec_rounds":            ("1", "spec software repeats"),
    "spec_relax_delay":       ("us", "spec wait between shots"),
    "spec_sigma":             ("us", "Gaussian sigma of the spec drive"),
    "spec_gain":              ("DAC units", "spec drive gain"),
    "spec_qubit_length":      ("us", "const spec pulse length (unused when Gaussian)"),
    "skip_sweet_spot_search": ("flag", "skip stage 1: keep the qubit freq and the bias"),
    "ss_search_df_trigger":   ("MHz", "peak separation that flags 'off the sweet spot'"),
    "ss_accept_sep":          ("MHz", "separation small enough to call the sweet spot"),
    "ss_dv":                  ("V", "bias step per search attempt (legacy ss_dV)"),
    "ss_voltage_min":         ("V", "lower end of the sweet-spot search window"),
    "ss_voltage_max":         ("V", "upper end of the sweet-spot search window"),
    "ss_max_tries":           ("1", "search attempts before giving up"),
    "cd_period_mv":           ("mV", "charge-dispersion period; enables the half-period step",
                               "runs", "None: Qubit.parity.cd_period_mv, else no half-period "
                               "step"),
    "calibrate_qubit_freq":   ("flag", "re-centre f_ge on a two-tone spec before the Rabi"),
    "freqcal_auto_gain":      ("flag", "raise the spec gain when the peak is weak"),
    "freqcal_min_snr":        ("1", "peak SNR below which the gain is raised"),
    "freqcal_gain_growth":    ("1", "spec gain multiplier per retry"),
    "freqcal_max_gain":       ("DAC units", "highest spec gain the retries may reach"),
    "freqcal_max_gain_retries": ("1", "gain retries at most"),
    "rabi_max_gain":          ("DAC units", "last gain of the Rabi sweep"),
    "rabi_num_steps":         ("points", "Rabi gain points"),
    "rabi_reps":              ("shots", "Rabi hardware averages per point"),
    "rabi_rounds":            ("1", "Rabi software repeats"),
    "rabi_relax_delay":       ("us", "Rabi wait between shots"),
    "rabi_sigma":             ("us", "Rabi pulse sigma", "runs", "None: Qubit.sigma"),
    "rabi_sigma_min":         ("us", "lower bound of the automatic sigma reduction"),
    "rabi_max_osc_peaks":     ("1", "more Rabi peaks than this: sigma x 0.7 and retry"),
    "rabi_max_sigma_retries": ("1", "sigma reductions at most"),
    "ss_shots":               ("shots", "shots per gain point of the pi-gain scan"),
    "ss_full_shots":          ("shots", "shots of the final fidelity measurement"),
    "ss_relax_delay":         ("us", "single-shot wait between shots"),
    "ss_readout_time":        ("us", "single-shot ADC window"),
    "ss_adc_offset":          ("us", "single-shot adc_trig_offset"),
    "ss_target_fidelity":     ("1", "minimum acceptable single-shot contrast"),
    "ss_gain_pts":            ("points", "gain points of the pi-gain scan"),
    "ss_max_scan_expansions": ("1", "re-centre / expand when the best gain is on the edge"),
    "ss_gain_span_growth":    ("1", "span multiplier per edge-hit expansion"),
    "ss_gain_span_frac":      ("1", "half-width of the pi-gain scan, fraction of the pi gain"),
    "auto_readout_opt":       ("flag", "run the readout_length x adc_offset optimisation"),
    "readout_length_start":   ("us", "shortest readout window tried"),
    "readout_length_stop":    ("us", "longest readout window tried"),
    "readout_length_pts":     ("points", "readout-window values"),
    "adc_offset_start":       ("us", "smallest ADC trigger offset tried"),
    "adc_offset_stop":        ("us", "largest ADC trigger offset tried"),
    "adc_offset_pts":         ("points", "ADC-offset values"),
    "extended_pi_pi2_opt":    ("flag", "error-amplified pi / pi2 gain optimisation"),
    "pi_nsteps_list":         ("1", "odd pulse counts N of the pi optimisation"),
    "pi2_nsteps_list":        ("1", "pulse counts N = 2(2k+1) of the pi/2 optimisation"),
    "ext_gain_pts":           ("points", "gain points per N step"),
    "ext_pi_gain_span_init":  ("1", "initial half-width, fraction of the pi gain"),
    "ext_pi2_gain_span_init": ("1", "initial half-width, fraction of the pi/2 gain"),
    "ext_gain_span_shrink":   ("1", "span multiplier after each N step"),
    "t1_step":                ("us", "T1 wait step"),
    "t1_expts":               ("points", "T1 wait points"),
    "t1_reps":                ("shots", "T1 hardware averages per point"),
    "t1_rounds":              ("1", "T1 software repeats"),
    "t1_relax_delay":         ("us", "T1 wait between shots"),
    "t1_repetitions":         ("1", "consecutive T1 runs"),
    "t1_expected_us":         ("us", "expected T1 for the pre-flight timing check", "runs",
                               "None: no check"),
    "t2_step":                ("us", "Ramsey delay step"),
    "t2_expts":               ("points", "Ramsey delay points"),
    "t2_reps":                ("shots", "Ramsey hardware averages per point"),
    "t2_rounds":              ("1", "Ramsey software repeats"),
    "t2_relax_delay":         ("us", "Ramsey wait between shots"),
    "t2_repetitions":         ("1", "consecutive Ramsey runs"),
    "t2_freq_shift":          ("MHz", "real detuning of the Ramsey pi/2 pulses"),
    "t2_f_virt_mhz":          ("MHz", "virtual detuning", "runs", "None: 5 fringes per window"),
    "t2e_max_us":             ("us", "total echo time of the last point"),
    "t2e_expts":              ("points", "echo delay points"),
    "t2e_reps":               ("shots", "echo hardware averages per point"),
    "t2e_rounds":             ("1", "echo software repeats"),
    "t2e_relax_delay":        ("us", "echo wait between shots"),
    "t2e_num_pi_pulses":      ("1", "refocusing pi pulses (odd)"),
    "t2e_repetitions":        ("1", "consecutive echo runs"),
}

# zero_span_parity keywords; the keys of its dict keywords follow in _ZSP_SUB
_ZSP = {
    "run_mode":                   ("text", "acquisition path: 'strobe' (per-rep IQ) or "
                                   "'decimated' (raw trace)"),
    "start_src":                  ("text", "tProc start source: 'internal' or 'external'"),
    "recalibrate_parity_freqs":   ("flag", "run the narrow parity spectroscopy first"),
    "recalibrate_separator":      ("flag", "run the g/e SingleShot calibration first"),
    "parity_freqs_cached":        ("dict", "cached parity frequencies (parity_freqs_cached.*)"),
    "separator_cached":           ("dict", "cached g/e separator (separator_cached.*)"),
    "parity_spec":                ("dict", "narrow parity spectroscopy (parity_spec.*)"),
    "strobe":                     ("dict", "strobe-mode settings (strobe.*)"),
    "decimated":                  ("dict", "decimated-mode settings (decimated.*)"),
    "drive":                      ("dict", "drive / readout gains of the record (drive.*)"),
    "analysis":                   ("dict", "switch-rate analysis settings (analysis.*)"),
    "validate_static_contrast":   ("flag", "stage 1: probe-frequency contrast sweep"),
    "static_contrast":            ("dict", "stage-1 settings (static_contrast.*)"),
    "validate_contrast_vs_qubit_freq": ("flag", "stage 2: drive-frequency contrast sweep"),
    "contrast_vs_qubit":          ("dict", "stage-2 settings (contrast_vs_qubit.*)"),
    "validate_modulation_check":  ("flag", "stage 3: square-wave drive modulation check"),
    "modulation":                 ("dict", "stage-3 settings (modulation.*)"),
    "validate_control_suite":     ("flag", "stage 8: instrument controls"),
    "control":                    ("dict", "stage-8 settings (control.*)"),
    "validate_environment_sweep": ("flag", "stage 7: environment sweep"),
    "environment":                ("dict", "stage-7 settings (environment.*)"),
    "build_evidence_report":      ("flag", "write EVIDENCE.md from the stage results"),
}
_ZSP_SUB = {
    # keyword: {legacy key: (units, meaning, notes)}
    "parity_freqs_cached": {
        "lower_peak_MHz":  ("MHz", "lower parity branch", "None: f_upper - df of Qubit.parity"),
        "higher_peak_MHz": ("MHz", "upper parity branch", "None: Qubit.parity.f_upper_mhz"),
        "which_to_park":   ("text", "parity branch to drive: 'lower' or 'higher'", ""),
    },
    "separator_cached": {
        "g_center": ("a.u.", "g cloud centre (I, Q)", "None: measured when recalibrating"),
        "e_center": ("a.u.", "e cloud centre (I, Q)", "None: measured when recalibrating"),
        "normal":   ("a.u.", "separator normal e - g", "None: measured when recalibrating"),
        "midpoint": ("a.u.", "separator midpoint (g + e) / 2",
                     "None: measured when recalibrating"),
    },
    "parity_spec": {
        "SpecSpan":        ("MHz", "half-width of the narrow spectroscopy", ""),
        "SpecNumPoints":   ("points", "its frequency points", ""),
        "reps":            ("shots", "its hardware averages per point", ""),
        "rounds":          ("1", "its software repeats", ""),
        "relax_delay":     ("us", "its wait between shots", ""),
        "Gauss":           ("flag", "Gaussian spectroscopy pulse", ""),
        "sigma":           ("us", "its Gaussian sigma", ""),
        "gain":            ("DAC units", "its drive gain", ""),
        "qubit_length":    ("us", "its const pulse length", ""),
        "min_sep_MHz":     ("MHz", "smallest separation accepted as a doublet", ""),
        "fit_window_mhz":  ("MHz", "Lorentzian fit window per peak", ""),
        "prominent_ratio": ("1", "second-peak height threshold, fraction of the first", ""),
        "min_partner_snr": ("1", "significance the weaker parity line needs (0: gate off)",
                            ""),
    },
    "strobe": {
        "sample_period_us": ("us", "one IQ sample per period", "floor: offset + window + 1 us"),
        "reps_per_chunk":   ("shots", "samples per program", "<= 2e7, not bounded by avg_maxlen"),
        "n_chunks":         ("1", "programs stitched into the record",
                             "each boundary is a dead gap"),
        "read_length":      ("us", "ADC window", ""),
        "adc_trig_offset":  ("us", "tone-start-to-ADC-trigger delay", ""),
    },
    "decimated": {
        "capture_length_us": ("us", "tone length per capture", ""),
        "soft_avgs":         ("1", "captures averaged", "must stay 1 unless allow_soft_avgs"),
        "n_captures":        ("1", "captures stitched into the record", ""),
        "read_length":       ("us", "ADC window", ""),
        "adc_trig_offset":   ("us", "tone-start-to-ADC-trigger delay", ""),
        "allow_soft_avgs":   ("flag", "opt in to averaging captures", ""),
    },
    "drive": {
        "qubit_gain": ("DAC units", "parity drive gain", "None: the pi gain (regime B)"),
        "pulse_gain": ("DAC units", "readout gain", "None: the device readout gain"),
        "res_phase":  ("phase register units", "readout phase",
                       "0 default: a calibrated phase is not used"),
    },
    "analysis": {
        "classifier_method":     ("text", "'apriori_gmm', 'apriori_midpoint' or 'kmeans'",
                                  "legacy 'apriori' = 'apriori_gmm'"),
        "window_us":             ("us", "sliding window of the switch rate", ""),
        "k_sigma":               ("1", "burst threshold in sigma", ""),
        "step_us":               ("us", "window stride", "None: window_us // 2"),
        "min_burst_duration_us": ("us", "drop shorter bursts", "None: keep all"),
        "analysis_bin_us":       ("us", "mean-bin the samples before classifying",
                                  "None: no binning"),
        "save_plots":            ("flag", "write the analysis PNGs", ""),
    },
    "static_contrast": {
        "freq_span_mhz":  ("MHz", "stage-1 probe-frequency span", ""),
        "n_points":       ("points", "stage-1 frequency points", ""),
        "reps_per_point": ("shots", "stage-1 samples per point", ""),
    },
    "contrast_vs_qubit": {
        "qfreq_span_mhz":      ("MHz", "stage-2 drive-frequency span", ""),
        "n_points":            ("points", "stage-2 frequency points", ""),
        "doublet_sep_tol_MHz": ("MHz", "tolerance on the stage-2 pair separation",
                                "None: max(25 % of the splitting, 2 grid steps)"),
        "min_peak_snr":        ("1", "contrast SNR a stage-2 peak needs to refine the drive "
                                "frequency", ""),
    },
    "modulation": {
        "modulation_freq_hz":  ("Hz", "stage-3 square-wave frequency", ""),
        "n_periods":           ("1", "stage-3 periods", ""),
        "min_block_t":         ("1", "stage-3 gate on |block_t|", "None: flag only"),
        "min_abs_correlation": ("1", "stage-3 gate on |correlation|", "None: flag only"),
        "min_snr":             ("1", "stage-3 gate on the SNR", "None: flag only"),
    },
    "control": {
        "variants":   ("text", "stage-8 controls to run (A, B, C, D)", ""),
        "detune_mhz": ("MHz", "stage-8 far detuning of control B", ""),
    },
    "environment": {
        "param_name": ("text", "stage-7 swept environment parameter", ""),
        "values":     ("dB", "stage-7 values of that parameter", "units of the default power_dB"),
    },
}

_SPEC = _from("session:spec", *(
    "reps rounds gauss sigma gain qubit_length spec_span spec_num_points relax_delay display "
    "min_sep_mhz fit_window_mhz prominent_ratio sweep_lengths sweep_gains").split())
_COH = _from("session:coherence", *(
    "t1_step t1_expts t1_reps t1_rounds t2_step t2_expts t2_reps t2_rounds freq_shift "
    "relax_delay repetitions").split())
_ECHO = _from("session:echo", *(
    "t2_max_us t2_expts t2_reps t2_rounds freq_shift relax_delay num_pi_pulses rotation_angle "
    "min_max repetitions").split())
_ECHO_T2E = _from("session:echo", "num_pi_pulses", "rotation_angle", "min_max", rename={
    "t2e_max_us": "t2_max_us", "t2e_expts": "t2_expts", "t2e_reps": "t2_reps",
    "t2e_rounds": "t2_rounds", "t2e_freq_shift": "freq_shift", "t2e_relax_delay": "relax_delay"})
_TRANS = _from("session:transmission", "reps", "rounds")
_PLOT_DISP = {"plot_disp": ("flag", "show the plot", "runs", "None: only when repetitions <= 1")}
_F_VIRT = {"f_virt_mhz": ("MHz", "virtual detuning: phase advance of the second pi/2 per point",
                          "runs", "None: 5 fringes per window")}

_recipe("constant_tone", "hold_s")
_recipe("constant_two_tone", "hold_s")
_recipe("transmission_fit", "reps rounds", inherit=_TRANS)
_recipe("transmission_sweep", "reps rounds", inherit=_TRANS)
_recipe("chi_shift", "reps rounds trans_span trans_num_points cavity_shift relax_delay", own={
    "rounds":           ("1", "ignored: ChiProgram forces cfg rounds = 1", "runs",
                         "written into the cfg, then overwritten while the program is built"),
    "trans_span":       ("MHz", "half-width of the sweep around pulse_freq + cavity_shift"),
    "trans_num_points": ("points", "frequency points of the sweep"),
    "cavity_shift":     ("MHz", "offset of the sweep centre from pulse_freq"),
})
_recipe("two_tone_spec",
        "reps rounds gauss sigma gain qubit_length spec_span spec_num_points relax_delay "
        "display min_sep_mhz fit_window_mhz prominent_ratio", inherit=_SPEC)
_recipe("spec_gain_length_sweep",
        "sweep_lengths sweep_gains reps rounds gauss sigma spec_span spec_num_points "
        "relax_delay display min_sep_mhz fit_window_mhz prominent_ratio", inherit=_SPEC)
_recipe("trans_qubit_spec",
        "gain relax_delay reps rounds gauss sigma min_sep_mhz fit_window_mhz prominent_ratio "
        "repetitions", inherit={**_SPEC, "repetitions": ("session:coherence", "repetitions")})
_recipe("amplitude_rabi",
        "qubit_freq max_gain number_of_steps reps rounds relax_delay fit flattop_relax_delay",
        own={
    "qubit_freq":          ("MHz", "drive frequency", "runs", "None: Qubit.freq"),
    "rounds":              ("1", "software repeats of the program, averaged in Python", "runs",
                            "flat-top qubit (AmplitudeRabiFF_N): folded into reps, rounds = 1"),
    "max_gain":            ("DAC units", "last gain of the sweep from 0"),
    "number_of_steps":     ("points", "gain points of the sweep"),
    "fit":                 ("flag", "cosine fit in the display"),
    "flattop_relax_delay": ("us", "relax_delay used when the qubit has a flat-top pulse"),
})
_recipe("t1", "t1_step t1_expts t1_reps t1_rounds relax_delay repetitions plot_disp",
        own=_PLOT_DISP, inherit=_COH)
_recipe("t2_ramsey",
        "t2_step t2_expts t2_reps t2_rounds freq_shift relax_delay repetitions f_virt_mhz",
        own=_F_VIRT, inherit=_COH)
_recipe("t2_echo",
        "t2_max_us t2_expts t2_reps t2_rounds freq_shift relax_delay num_pi_pulses "
        "rotation_angle min_max repetitions plot_disp", own=_PLOT_DISP, inherit=_ECHO)
_recipe("t1_t2e",
        "t1_step t1_expts t1_reps t1_rounds relax_delay repetitions t2e_max_us t2e_expts "
        "t2e_reps t2e_rounds t2e_freq_shift t2e_relax_delay num_pi_pulses rotation_angle "
        "min_max", inherit={**_COH, **_ECHO_T2E})
_recipe("t1_t2r_t2e",
        "t1_step t1_expts t1_reps t1_rounds t2_step t2_expts t2_reps t2_rounds freq_shift "
        "relax_delay repetitions f_virt_mhz t2e_max_us t2e_expts t2e_reps t2e_rounds "
        "t2e_freq_shift t2e_relax_delay num_pi_pulses rotation_angle min_max",
        own=_F_VIRT, inherit={**_COH, **_ECHO_T2E})
_recipe("interleaved_coherence", "cycles undriven_single_shot t1 t2r t2e undriven", own={
    "cycles":               ("1", "cycles of undriven single shot -> T1 -> T2R -> T2E"),
    "undriven_single_shot": ("flag", "run the undriven single shot in each cycle"),
    "t1":                   ("flag", "run T1 in each cycle"),
    "t2r":                  ("flag", "run T2 Ramsey in each cycle"),
    "t2e":                  ("flag", "run T2 echo in each cycle"),
    "undriven":             ("object", "the R.undriven_single_shot Step whose settings the "
                             "loop uses", "runs", "None: its defaults"),
})
_recipe("auto_coherence", " ".join(_AC), own=_AC)
_recipe("single_shot", "number_of_pulses pi2_ss",
        inherit=_from("session:single_shot", "number_of_pulses", "pi2_ss"))
_recipe("undriven_single_shot",
        "shots relax_delay min_separation_sigma average_shots bin_sizes charge_sweep "
        "voltage_start voltage_end voltage_step charge_settle_s repeat plot_disp", own={
    "shots":                ("shots", "undriven single shots per acquisition"),
    "relax_delay":          ("us", "wait after each shot before the next", "runs",
                             "None: the single_shot group's relax_delay"),
    "min_separation_sigma": ("1", "blob separation (combined sigma) to call two blobs",
                             "analysis"),
    "average_shots":        ("shots", "consecutive shots averaged per time-series point",
                             "analysis"),
    "bin_sizes":            ("shots", "averaging sizes of the rate-vs-averaging panel",
                             "analysis"),
    "charge_sweep":         ("flag", "one acquisition per bias of the voltage_* grid"),
    "voltage_start":        ("V", "first bias of np.arange(voltage_start, voltage_end, "
                             "voltage_step)"),
    "voltage_end":          ("V", "end of the bias grid (excluded)"),
    "voltage_step":         ("V", "step of the bias grid"),
    "charge_settle_s":      ("s", "wait after each bias ramp"),
    "repeat":               ("1", "whole acquisitions back to back, each its own files",
                             "runs", "legacy Repeat"),
    "plot_disp":            ("flag", "show the last acquisition's plot"),
})
_recipe("t1_single_shot",
        "t1_step t1_expts reps angle threshold relax_delay calibrate_ss repetitions", own={
    "t1_step":      ("us", "T1 wait step"),
    "t1_expts":     ("points", "T1 wait points"),
    "reps":         ("shots", "single shots per wait point"),
    "angle":        ("rad", "IQ rotation that puts g -> e on I", "runs",
                     "replaced by the calibration when calibrate_ss"),
    "threshold":    ("a.u.", "I threshold between the g and e clouds", "runs",
                     "replaced by the calibration when calibrate_ss"),
    "calibrate_ss": ("flag", "take angle / threshold from a g / pi single_shot first"),
})
_recipe("readout_optimize", "gain_start gain_stop gain_pts span trans_pts", own={
    "gain_start": ("DAC units", "first readout gain of the grid"),
    "gain_stop":  ("DAC units", "last readout gain of the grid"),
    "gain_pts":   ("points", "readout gain points"),
    "span":       ("MHz", "full width of the readout-frequency scan, centred on pulse_freq"),
    "trans_pts":  ("points", "readout frequency points"),
})
_recipe("qubit_optimize", "q_gain_span q_gain_pts q_freq_span q_freq_pts number_of_pulses", own={
    "q_gain_span":      ("DAC units", "half-width of the qubit-gain scan around the pi gain"),
    "q_gain_pts":       ("points", "qubit gain points"),
    "q_freq_span":      ("MHz", "half-width of the qubit-frequency scan"),
    "q_freq_pts":       ("points", "qubit frequency points"),
    "number_of_pulses": ("1", "pulses per preparation (2 with the pi/2 gain optimises pi/2)"),
})
_recipe("active_reset_verify",
        "n_verify_reads verify_relax_delay reps reset_cycles reset_readout_relax_delay "
        "post_reset_wait relax_delay plot_disp reset_read_latency_us", own={
    "n_verify_reads":     ("1", "readouts after the reset that verify it"),
    "verify_relax_delay": ("us", "wait between the verification readouts"),
    "reps":               ("shots", "shots per condition"),
    **{k: _MR[k] for k in ("reset_cycles", "reset_readout_relax_delay", "reset_read_latency_us",
                           "post_reset_wait")},
})
_recipe("modified_ramsey", " ".join(_MR), own=_MR)
_MR_INHERITED = (
    "tau_harmonic_k use_pi_pulse flip_final_pi2 symmetric_ramsey max_drive_bandwidth_ratio "
    "use_active_reset reset_cycles reset_ground_below_threshold reset_readout_relax_delay "
    "reset_read_latency_us post_reset_wait readout_threshold ss_calib_shots "
    "ss_recalib_every_n_cycles expected_parity_dwell_ms drift_window_ms hmm_symmetric "
    "hmm_bootstrap_samples hmm_fit_mapping mapping_p_e_state0 mapping_p_e_state1 "
    "mapping_probabilities_calibrated hmm_min_emission_snr hmm_kwargs").split()
_recipe("modified_ramsey_control",
        "df dv voltage_min voltage_max max_voltage_tries num_cycles spec_span spec_num_points "
        "reps rounds relax_delay sigma gain qubit_length cd_max_mhz cd_period_mv "
        "sweet_spot_max_df_mhz mr_relax_delay mr_reps hysteresis_low hysteresis_high window_ms "
        "ramsey " + " ".join(_MR_INHERITED), own={
    "df":                    ("MHz", "peak separation that triggers the Strategy-A "
                              "half-period bias jump (qubit off the sweet spot)", "runs",
                              "auto_coherence ss_search_df_trigger; only with cd_period_mv; "
                              "the Ramsey's own df comes from ramsey / Qubit.parity.df_mhz"),
    "dv":                    ("V", "Strategy-B step of the bias walk toward the smallest "
                              "doublet separation (legacy dV)", "runs",
                              "auto_coherence ss_dv (legacy ss_dV)"),
    "voltage_min":           ("V", "lower end of the sweet-spot bias walk", "runs",
                              "auto_coherence ss_voltage_min"),
    "voltage_max":           ("V", "upper end of the sweet-spot bias walk", "runs",
                              "auto_coherence ss_voltage_max"),
    "max_voltage_tries":     ("1", "Strategy-B hard step limit (one pass of the bias window "
                              "usually ends the walk first)", "runs",
                              "auto_coherence ss_max_tries"),
    "num_cycles":            ("1", "search + Ramsey cycles"),
    "rounds":                _KW["search_rounds"],
    "relax_delay":           ("us", "search-spectroscopy wait between shots"),
    "sigma":                 ("us", "Gaussian sigma of the search spectroscopy"),
    "gain":                  ("DAC units", "search-spectroscopy drive gain"),
    "qubit_length":          ("us", "search-spectroscopy pulse length"),
    "cd_max_mhz":            ("MHz", "peak charge dispersion of S(V)", "runs",
                              "None: Qubit.parity.cd_max_mhz (raises without it)"),
    "cd_period_mv":          ("mV", "charge-dispersion period", "runs",
                              "None: Qubit.parity.cd_period_mv (raises without it)"),
    "sweet_spot_max_df_mhz": ("MHz", "sweet spot accepted when the doublet separation is "
                              "below this (or a single peak)", "runs",
                              "auto_coherence ss_accept_sep"),
    "mr_relax_delay":        _MR["mr_relax_delay"][:2],
    "mr_reps":               _MR["mr_reps"][:2],
    "hysteresis_low":        ("1", "lower hysteresis threshold of the diagnostic "
                              "moving-average state plot", "analysis", "None: 0.4"),
    "hysteresis_high":       ("1", "upper hysteresis threshold of the diagnostic "
                              "moving-average state plot", "analysis", "None: 0.6"),
    "window_ms":             ("ms", "moving-average window of the diagnostic state plot",
                              "analysis", "None: 0.1"),
    "ramsey":                ("object", "the R.modified_ramsey Step whose sequence, df and "
                              "mapping the Ramsey uses (its f_ge is not used)", "runs",
                              "None: the keywords below"),
}, inherit={
    kw: ("recipe:modified_ramsey", kw,
         _MR[kw][3] if _MR[kw][3].startswith("None: Qubit.parity") else "None: the run's default")
    for kw in _MR_INHERITED
})
_recipe("two_tone_charge_dispersion_quasicw",
        "df dv voltage_min voltage_max max_voltage_tries num_cycles use_upper_peak "
        "center_peak_tol_mhz min_partner_snr spec_span spec_num_points reps rounds relax_delay "
        "gauss sigma gain qubit_length qcw_repetitions qcw_relax_delay expected_parity_dwell_ms "
        "qcw_gauss qcw_sigma qcw_gain min_sep_mhz fit_window_mhz prominent_ratio "
        "charge_dispersion", own={
    "df":                  ("MHz", "smallest doublet separation accepted by the search"),
    "num_cycles":          ("1", "search -> quasi-CW cycles"),
    "rounds":              _KW["search_rounds"],
    "use_upper_peak":      ("flag", "probe the upper peak (else the lower)"),
    "center_peak_tol_mhz": ("MHz", "tolerance on the probed peak's position"),
    "qcw_repetitions":     ("shots", "quasi-CW shots on the chosen peak"),
    "qcw_relax_delay":     ("us", "quasi-CW wait between shots"),
    "charge_dispersion":   ("dict", "dict that receives the chosen 'probe_freq'", "runs",
                            "legacy: shared with charge_dispersion_quasicw"),
}, inherit={
    **_from("session:spec", "min_sep_mhz", "fit_window_mhz", "prominent_ratio"),
    **_from("session:spec", rename={"qcw_gauss": "gauss", "qcw_sigma": "sigma",
                                    "qcw_gain": "gain"}),
})
_recipe("charge_dispersion_quasicw",
        "probe_freq relax_delay repetitions expected_parity_dwell_ms gauss sigma gain", own={
    "probe_freq":  ("MHz", "fixed drive frequency of the quasi-CW shots", "runs",
                    "None: Qubit.parity.f_upper_mhz"),
    "repetitions": ("shots", "quasi-CW shots in the record (cfg reps)"),
}, inherit=_from("session:spec", "gauss", "sigma", "gain"))
_recipe("charge_dispersion_ramsey", "df relax_delay repetitions", own={
    "df": ("MHz", "parity branch splitting; the fixed Ramsey wait follows from it", "runs",
           "None: Qubit.parity.df_mhz; with neither the run raises KeyError"),
}, inherit={"repetitions": ("session:coherence", "repetitions")})
_recipe("charge_sweep",
        "reps rounds gauss sigma gain min_sep_mhz fit_window_mhz prominent_ratio cd_period_mv",
        own={"cd_period_mv": ("mV", "dispersion period for the grid-sampling check", "runs",
                              "None: Qubit.parity.cd_period_mv, else unchecked")},
        inherit=_SPEC)
_recipe("charge_transmission_sweep",
        "reps rounds span num_points fit settle_s voltage_start voltage_end voltage_step", own={
    "fit":      ("flag", "hanger fit per bias slice"),
    "settle_s": ("s", "wait after each bias ramp"),
}, inherit={
    **_from("session:transmission", "span", "num_points"),
    **_from("session:charge", "voltage_start", "voltage_end", "voltage_step"),
})
_recipe("zero_span_parity", " ".join(_ZSP), own=_ZSP)
for _kw, _sub in _ZSP_SUB.items():
    for _key, (_units, _meaning, _notes) in _sub.items():
        _add(f"{_kw}.{_key}", "recipe:zero_span_parity", _units, _meaning,
             "analysis" if _kw == "analysis" else "runs", ("run_zero_span_parity",), _notes)

# ---------------------------------------------------------------------------------------------
# cfg: the experiment cfg dict. read_by = the classes the golden records reading or writing it
# (tests/regression/golden_cstq03.json, cfg_access, both boards); a "cfg:<variant>" entry
# holds the same key's other meaning for the classes it lists.

_ALL = (
    "ActiveResetVerify AmplitudeRabiFF CavitySpecFF ChargeDispersionQuasiCW ChiShift "
    "ConstantTwoTone ModifiedRamsey QubitPulseOpt_wSingleShotFF QubitSpecSliceFF "
    "ReadOpt_wSingleShotFF SingleShotProgramFFMUX SingleTone T1FF T1_SS T2EMUX T2R "
    "UndrivenSingleShot ZeroSpanParity").split()


def _but(*names):
    return tuple(c for c in _ALL if c not in names)


_PULSED = _but("CavitySpecFF", "SingleTone", "UndrivenSingleShot")
_SS_OPT = "QubitPulseOpt_wSingleShotFF ReadOpt_wSingleShotFF SingleShotProgramFFMUX"
_TRIG = "AmplitudeRabiFF T1FF T2EMUX " + _SS_OPT
_WINDING = "AmplitudeRabiFF ChargeDispersionQuasiCW QubitSpecSliceFF T1FF"
_FREQ_SWEEP = "ChargeDispersionQuasiCW QubitSpecSliceFF"
_WAIT_SWEEP = "T1FF T1_SS T2EMUX T2R"
_RESET = "ActiveResetVerify ModifiedRamsey"
_ARV, _MRC, _ZSPC = "ActiveResetVerify", "ModifiedRamsey", "ZeroSpanParity"
_ROPT, _QOPT = "ReadOpt_wSingleShotFF", "QubitPulseOpt_wSingleShotFF"

_CFG = (
    # (key, scope, units, meaning, layer, read_by, notes)
    # board wiring (hardware.board.BASE_CONFIG)
    ("res_ch", "cfg", "index", "readout DAC generator channel", "hardware", _ALL, "0"),
    ("qubit_ch", "cfg", "index", "qubit drive DAC generator channel", "hardware", _PULSED, "1"),
    ("ro_chs", "cfg", "index", "ADC readout channels (one entry)", "hardware", _ALL, "[0]"),
    ("nqz", "cfg", "1", "Nyquist zone of the readout DAC", "hardware", _ALL, "2"),
    ("qubit_nqz", "cfg", "1", "Nyquist zone of the qubit DAC", "hardware", _PULSED, "1"),
    ("mixer_freq", "cfg", "MHz", "readout DAC mixer (NCO) frequency", "hardware",
     "CavitySpecFF ChargeDispersionQuasiCW ChiShift ConstantTwoTone QubitSpecSliceFF "
     "SingleTone ZeroSpanParity", "0.0"),
    ("cavity_LO", "cfg", "Hz", "external readout LO; 0 = none (frequencies are absolute)",
     "hardware", "CavitySpecFF ChiShift ConstantTwoTone", ""),
    ("cavity_winding_freq", "cfg", "us", "cable winding correction: electrical delay "
     "multiplying pulse_freq [MHz]", "hardware", _WINDING, "0 = off"),
    ("cavity_winding_offset", "cfg", "rad", "cable winding correction: phase offset",
     "hardware", _WINDING, "0 = off"),
    ("trig_buffer_start", "cfg", "us", "pin-0 trigger lead before a qubit pulse", "hardware",
     _TRIG, "0.02"),
    ("trig_buffer_end", "cfg", "us", "pin-0 trigger tail after a qubit pulse", "hardware",
     _TRIG, "0.02"),
    ("trig_delay", "cfg", "us", "trigger-output-to-DAC latency compensation", "hardware",
     _TRIG, "0.082"),
    # readout
    ("pulse_freq", "cfg", "MHz", "readout tone frequency", "experiments", _but(_ZSPC),
     "carry-over: transmission_fit / _sweep write the fitted dip back; sweeps leave their "
     "last point in the saved cfg"),
    ("pulse_gain", "cfg", "DAC units", "readout tone gain", "experiments", _ALL,
     "ReadOpt_wSingleShotFF writes each grid gain into it"),
    ("length", "cfg", "us", "readout tone length (adc_trig_offset + readout_length)",
     "experiments", _but("ConstantTwoTone", _ZSPC), ""),
    ("readout_length", "cfg", "us", "ADC integration window", "experiments",
     _but("ConstantTwoTone", "SingleTone", _ZSPC),
     "regime A: the readout window; regime B: the single-shot window"),
    ("adc_trig_offset", "cfg", "us", "delay from tone start to ADC trigger", "experiments",
     _but("ConstantTwoTone", "SingleTone"), ""),
    ("res_phase", "cfg", "phase register units", "readout tone phase", "experiments",
     _but("CavitySpecFF", "ChiShift", "ConstantTwoTone", "SingleTone"),
     "carry-over: the active-reset calibration writes the phase that puts g-e on I"),
    ("read_length", "cfg", "us", "zero-span ADC window", "experiments", _ZSPC,
     "ZeroSpanParity's own name for readout_length"),
    ("read_pulse_freq", "cfg", "MHz", "zero-span readout tone frequency", "experiments", _ZSPC,
     "written by the stage-1 contrast sweep"),
    ("cav_relax_delay", "cfg", "us", "wait after each resonator-sweep readout", "experiments",
     "CavitySpecFF ChiShift", "30 (build_context)"),
    ("TransSpan", "cfg", "MHz", "half-width of the resonator sweep around its centre",
     "experiments", "CavitySpecFF ChiShift", ""),
    ("TransNumPoints", "cfg", "points", "frequency points of the resonator sweep",
     "experiments", "CavitySpecFF ChiShift " + _ROPT, ""),
    ("cavity_shift", "cfg", "MHz", "offset of the chi-shift sweep centre from pulse_freq",
     "experiments", "ChiShift", ""),
    ("pulse_01", "cfg", "flag", "chi shift: this sweep plays the pi pulse", "experiments",
     "ChiShift", "set by the experiment per sweep"),
    # qubit drive
    ("f_ge", "cfg", "MHz", "qubit drive frequency", "experiments",
     "ActiveResetVerify AmplitudeRabiFF T1FF T1_SS T2EMUX T2R " + _SS_OPT,
     "QubitPulseOpt_wSingleShotFF writes each grid frequency into it"),
    ("f_ge", "cfg:modified_ramsey", "MHz", "UPPER parity branch; the lower is f_ge - df",
     "experiments", _MRC, "never the qubit centre when symmetric_ramsey"),
    ("qubit_freq", "cfg", "MHz", "qubit drive frequency (regime-A name)", "experiments",
     "ChiShift ConstantTwoTone", ""),
    ("qubit_gain", "cfg", "DAC units", "spectroscopy drive gain", "experiments",
     "ChargeDispersionQuasiCW ConstantTwoTone QubitSpecSliceFF",
     "regime A: the spec group's qubit_gain; the spec steps overwrite it with the spec gain"),
    ("qubit_gain", "cfg:single_shot", "DAC units", "pi gain of the |e> preparation (the pi/2 "
     "gain with pi2_SS)", "experiments", _SS_OPT,
     "regime B: Qubit.gain; QubitPulseOpt_wSingleShotFF writes each grid gain into it"),
    ("qubit_gain", "cfg:rabi", "DAC units", "Rabi drive gain of the current point (one "
     "program per gain)", "experiments", "AmplitudeRabiFF_N",
     "flat-top Rabi: written per point from the gain_start / gain_end / gainNumPoints grid"),
    ("qubit_gain", "cfg:zero_span", "DAC units", "CW parity-drive gain", "experiments", _ZSPC,
     "drive.qubit_gain, else the pi gain; the validation stages rewrite it"),
    ("pi_gain", "cfg", "DAC units", "pi-pulse gain", "experiments",
     "ActiveResetVerify ChiShift ModifiedRamsey T1FF T1_SS T2EMUX", ""),
    ("pi2_gain", "cfg", "DAC units", "pi/2-pulse gain", "experiments",
     "ModifiedRamsey T2EMUX T2R", ""),
    ("sigma", "cfg", "us", "Gaussian sigma of the qubit pulse (envelope 4 sigma)",
     "experiments", "ActiveResetVerify AmplitudeRabiFF ChiShift ModifiedRamsey "
     "QubitSpecSliceFF T1FF T1_SS T2EMUX T2R " + _SS_OPT,
     "QubitSpecSliceFF: the spec Gaussian (Gauss=True)"),
    ("flattop_length", "cfg", "us", "flat segment of a flat-top qubit pulse (None: Gaussian)",
     "experiments", "AmplitudeRabiFF ChiShift ModifiedRamsey T1FF T2EMUX " + _SS_OPT, ""),
    ("qubit_length", "cfg", "us", "length of the const spectroscopy pulse", "experiments",
     _FREQ_SWEEP, ""),
    ("Gauss", "cfg", "flag", "Gaussian spectroscopy pulse instead of a const one",
     "experiments", _FREQ_SWEEP, ""),
    ("qubit_pulse_style", "cfg", "text", "qubit pulse shape ('arb' in regime B)",
     "experiments", _QOPT + " " + _ROPT, "gates the overlap-error map"),
    ("tone_length", "cfg", "us", "repetition period of the CW tones", "experiments",
     "ConstantTwoTone", "from the tones group"),
    ("parity_drive_freq", "cfg", "MHz", "zero-span CW parity-drive frequency", "experiments",
     _ZSPC, "the parked parity branch; refined by validation stage 2"),
    # averaging and sweeps
    ("reps", "cfg", "shots", "hardware averages per point (tProc loop of one program)",
     "experiments", "AmplitudeRabiFF CavitySpecFF ChiShift QubitSpecSliceFF T1FF T2EMUX T2R",
     "AveragerProgram reads it at construction"),
    ("reps", "cfg:single_shot", "shots", "single shots, one IQ point each", "experiments",
     "ActiveResetVerify ChargeDispersionQuasiCW ModifiedRamsey T1_SS UndrivenSingleShot "
     "ZeroSpanParity " + _SS_OPT,
     "single-shot programs set it from shots; ZeroSpanParity from reps_per_chunk"),
    ("rounds", "cfg", "1", "software repeats of the program, averaged in Python",
     "experiments", _but("ConstantTwoTone", "SingleTone"),
     "forced to 1 by the single-shot programs (raw buffers keep only the last round), "
     "ChiProgram, the quasi-CW record and AmplitudeRabiFF_N (which folds it into reps)"),
    ("soft_avgs", "cfg", "1", "QICK software-average count", "experiments",
     "ActiveResetVerify CavitySpecFF ChiShift ModifiedRamsey T1_SS UndrivenSingleShot "
     "ZeroSpanParity " + _SS_OPT,
     "probed by qick's acquire (rounds wins when both exist); ZSP decimated: captures averaged"),
    ("shots", "cfg", "shots", "single shots per prepared state", "experiments",
     _SS_OPT + " UndrivenSingleShot", "the programs copy it into reps"),
    ("relax_delay", "cfg", "us", "wait after each shot before the next", "experiments",
     "ActiveResetVerify AmplitudeRabiFF ChargeDispersionQuasiCW ChiShift QubitSpecSliceFF "
     "T1FF T1_SS T2EMUX T2R UndrivenSingleShot " + _SS_OPT,
     "ModifiedRamsey reads mr_relax_delay instead"),
    ("expts", "cfg", "points", "points of the tProc register sweep", "experiments",
     "AmplitudeRabiFF " + _FREQ_SWEEP + " " + _WAIT_SWEEP, ""),
    ("start", "cfg", "MHz", "first frequency of the spectroscopy sweep", "experiments",
     _FREQ_SWEEP, "regime A: qubit_freq - SpecSpan; quasi-CW: the probe frequency"),
    ("start", "cfg:gain_sweep", "DAC units", "first gain of the Rabi sweep", "experiments",
     "AmplitudeRabiFF", ""),
    ("start", "cfg:wait_sweep", "us", "first wait of the coherence sweep", "experiments",
     _WAIT_SWEEP, "0 in every run: T1FF / T2EMUX / T2R load it into the wait register "
     "unconverted"),
    ("step", "cfg", "MHz", "frequency step of the spectroscopy sweep", "experiments",
     _FREQ_SWEEP, "2 SpecSpan / SpecNumPoints; 0 in quasi-CW"),
    ("step", "cfg:gain_sweep", "DAC units", "gain step of the Rabi sweep", "experiments",
     "AmplitudeRabiFF", ""),
    ("step", "cfg:wait_sweep", "us", "wait step of the coherence sweep", "experiments",
     _WAIT_SWEEP, "T2EMUX: step of the total echo time, split over num_pi_pulses + 1 waits"),
    ("Pulse", "cfg", "flag", "this acquisition plays the |e> preparation", "experiments",
     _SS_OPT, "set by the experiment: False for the g cloud, True for e"),
    ("number_of_pulses", "cfg", "1", "pi pulses in the |e> preparation (0: thermal mode)",
     "experiments", _SS_OPT, ""),
    ("Read_Indeces", "cfg", "index", "readout qubit index (misspelling kept)", "experiments",
     "SingleShotProgramFFMUX UndrivenSingleShot", ""),
    ("Qubit_number", "cfg", "index", "readout qubit, in the plot title and file name",
     "experiments", "T1FF", ""),
    ("Qubit_number", "cfg:rabi", "index", "pulse qubit, in the file name", "experiments",
     "AmplitudeRabiFF_N", "run_amplitude_rabi sets it to the pulse qubit"),
    ("rotation_angle", "cfg", "rad", "fixed IQ rotation of the display", "experiments",
     "T1FF T2EMUX", "absent: fitted per run"),
    ("min_max", "cfg", "a.u.", "fixed (ground, excited) display normalisation", "experiments",
     "T1FF T2EMUX", ""),
    ("variable_wait", "cfg", "us", "T1_SS: wait of the current point", "experiments", "T1_SS",
     "set by the experiment per point"),
    ("Excited_PulseT1", "cfg", "flag", "T1_SS: this pass plays the pi pulse", "experiments",
     "T1_SS", "set by the experiment"),
    ("num_pi_pulses", "cfg", "1", "refocusing pi pulses of the echo (odd)", "experiments",
     "T2EMUX", ""),
    ("f_virt_mhz", "cfg", "MHz", "virtual detuning of the Ramsey", "experiments", "T2R",
     "the realised value after register rounding"),
    ("phase_step", "cfg", "phase register units", "per-point phase advance of the second "
     "pi/2", "experiments", "T2R", "derived from f_virt_mhz"),
    # readout / qubit optimisation grids
    ("cav_gain_Start", "cfg", "DAC units", "first readout gain of the grid", "experiments",
     _ROPT, ""),
    ("cav_gain_Stop", "cfg", "DAC units", "last readout gain of the grid", "experiments",
     _ROPT, ""),
    ("cav_gain_Points", "cfg", "points", "readout gain points", "experiments", _ROPT, ""),
    ("trans_freq_start", "cfg", "MHz", "first readout frequency of the grid", "experiments",
     _ROPT, ""),
    ("trans_freq_stop", "cfg", "MHz", "last readout frequency of the grid", "experiments",
     _ROPT, ""),
    ("pulse_gains", "cfg", "1", "current readout gain as a fraction of 32000", "experiments",
     _ROPT, "set by the experiment per grid point"),
    ("qubit_gain_Start", "cfg", "DAC units", "first qubit gain of the grid", "experiments",
     _QOPT, ""),
    ("qubit_gain_Stop", "cfg", "DAC units", "last qubit gain of the grid", "experiments",
     _QOPT, ""),
    ("qubit_gain_Points", "cfg", "points", "qubit gain points", "experiments", _QOPT, ""),
    ("qubit_freq_start", "cfg", "MHz", "first qubit frequency of the grid", "experiments",
     _QOPT, ""),
    ("qubit_freq_stop", "cfg", "MHz", "last qubit frequency of the grid", "experiments",
     _QOPT, ""),
    ("QubitNumPoints", "cfg", "points", "qubit frequency points", "experiments", _QOPT, ""),
    # undriven single shot
    ("blob_min_separation_sigma", "cfg", "1", "blob separation (combined sigma) to call two "
     "blobs", "experiments", "UndrivenSingleShot", "from the recipe's min_separation_sigma"),
    ("shot_average", "cfg", "shots", "consecutive shots averaged per time-series point",
     "experiments", "UndrivenSingleShot", "from the recipe's average_shots"),
    ("ts_bin_sizes", "cfg", "shots", "averaging sizes of the rate-vs-averaging panel",
     "experiments", "UndrivenSingleShot", "from the recipe's bin_sizes"),
    ("charge_sweep", "cfg", "flag", "one acquisition per bias of voltage_start/end/step",
     "experiments", "UndrivenSingleShot", ""),
    # modified Ramsey and active reset
    ("df", "cfg", "MHz", "parity branch splitting", "experiments", _MRC,
     "ChargeDispersion waits 1/df between its pi/2 pulses"),
    ("ramsey_tau_us", "cfg", "us", "Ramsey free-evolution time tau", "experiments", _MRC,
     "tau_harmonic_k / (2 df); the tau_offset control rewrites it"),
    ("ramsey_drive_freq_mhz", "cfg", "MHz", "Ramsey drive frequency", "experiments", _MRC,
     "absent: f_ge - df/2 (symmetric) or f_ge; the drive_detuned control sets it"),
    ("mr_relax_delay", "cfg", "us", "wait after each Ramsey readout", "experiments", _MRC, ""),
    ("mr_control_type", "cfg", "text", "control sequence of this record (absent: the "
     "measurement)", "experiments", _MRC, "saved as an h5 code"),
    ("symmetric_ramsey", "cfg", "flag", "drive midway between the branches", "experiments",
     _MRC, ""),
    ("use_pi_pulse", "cfg", "flag", "echo pi pulse in the middle of the Ramsey",
     "experiments", _MRC, ""),
    ("flip_final_pi2", "cfg", "flag", "close with a +180 deg pi/2", "experiments", _MRC, ""),
    ("max_drive_bandwidth_ratio", "cfg", "1", "cap on branch detuning / pi/2 Rabi rate",
     "experiments", _MRC, "the drive_detuned control lifts it"),
    ("use_active_reset", "cfg", "flag", "measurement-based reset before each sequence",
     "experiments", _RESET, ""),
    ("reset_cycles", "cfg", "1", "measure -> conditional pi rounds per reset", "experiments",
     _RESET, ""),
    ("reset_ground_below_threshold", "cfg", "flag", "ground state lies below the I threshold",
     "experiments", _RESET, ""),
    ("reset_readout_relax_delay", "cfg", "us", "wait after each reset readout",
     "experiments", _RESET, ">= ~6/kappa"),
    ("reset_read_latency_us", "cfg", "us", "settle between reset readout and feedback pulse",
     "core", _RESET, "read by core.active_reset; can raise the 0.5 us floor, never lower it"),
    ("post_reset_wait", "cfg", "us", "wait after the reset before the sequence",
     "experiments", _RESET, ""),
    ("readout_threshold", "cfg", "a.u.", "single-shot I threshold of the reset decision "
     "(normalised I)", "experiments", _RESET, "from the separator unless given; "
     "core.active_reset scales it by the readout window into the raw tProc compare"),
    ("reset_force_pi", "cfg", "flag", "always play the reset pi pulse (feedback test)",
     "experiments", _ARV, ""),
    ("prep_excited", "cfg", "flag", "prepare |e> before the reset", "experiments", _ARV, ""),
    ("n_verify_reads", "cfg", "1", "readouts after the reset that verify it", "experiments",
     _ARV, ""),
    ("verify_relax_delay", "cfg", "us", "wait between the verification readouts",
     "experiments", _ARV, ""),
    ("g_center", "cfg", "a.u.", "g cloud centre (I, Q) of the bisector classifier",
     "experiments", _ARV, "from the active-reset readout calibration"),
    ("e_center", "cfg", "a.u.", "e cloud centre (I, Q) of the bisector classifier",
     "experiments", _ARV, "from the active-reset readout calibration"),
    # zero span
    ("mode", "cfg", "text", "zero-span acquisition path: 'strobe' or 'decimated'",
     "experiments", _ZSPC, "from run_mode"),
    ("start_src", "cfg", "text", "tProc start source: 'internal' or 'external'",
     "experiments", _ZSPC, ""),
    ("sample_period_us", "cfg", "us", "strobe sample period", "experiments", _ZSPC, ""),
    ("reps_per_chunk", "cfg", "shots", "strobe samples per program", "experiments", _ZSPC,
     "the validation stages rewrite it"),
    ("device", "cfg", "text", "device name in the validation sidecar", "experiments", _ZSPC,
     "read by zero_span_validation; run_zero_span_parity never sets it (always None)"),
)
for _row in _CFG:
    _add(*_row)

# cfg entries the golden's cfg_access cannot record for their reader: the reading (or writing)
# code path runs in no regression label, or it writes a plain dict before the class's recording
# dict exists (build_control_variants). Some of these keys still appear in saved cfgs (the
# run functions carry them on ctx.config). Each cites the qicklab/experiments, qicklab/analysis
# or qicklab/runs file in which the AST lint finds its literal cfg subscript.
UNRECORDED_CFG = {
    ("Qubit_number", "cfg:rabi"): "rabi.py: AmplitudeRabiFF_N.save_data (flat-top Rabi)",
    ("qubit_gain", "cfg:rabi"): "rabi.py: AmplitudeRabiFF_N.acquire gain loop (flat-top Rabi)",
    ("gain_start", "cfg"): "rabi.py: AmplitudeRabiFF_N gain grid (flat-top Rabi)",
    ("gain_end", "cfg"): "rabi.py: AmplitudeRabiFF_N gain grid (flat-top Rabi)",
    ("gainNumPoints", "cfg"): "rabi.py: AmplitudeRabiFF_N gain grid (flat-top Rabi)",
    ("capture_length_us", "cfg"): "zero_span_parity.py: decimated mode",
    ("n_captures", "cfg"): "zero_span_parity.py: decimated mode",
    ("allow_soft_avgs", "cfg"): "zero_span_parity.py: decimated mode",
    ("charge_settle_s", "cfg"): "undriven_single_shot.py: charge_sweep=True",
    ("voltage_start", "cfg"): "undriven_single_shot.py: charge_sweep=True",
    ("voltage_end", "cfg"): "undriven_single_shot.py: charge_sweep=True",
    ("voltage_step", "cfg"): "undriven_single_shot.py: charge_sweep=True",
    ("current_voltage", "cfg"): "undriven_single_shot.py: charge_sweep=True",
    ("thermal_pi_calibration", "cfg"): "single_shot.py: number_of_pulses=0 (thermal mode)",
    ("thermal_e_center", "cfg"): "single_shot.py: number_of_pulses=0 (thermal mode)",
    ("thermal_tail_md2_threshold", "cfg"): "readout.py: classify_thermal_tail (thermal mode)",
    ("thermal_tail_sigma_threshold", "cfg"): "readout.py: classify_thermal_tail (thermal mode)",
    ("aborted", "cfg"): "t1_single_shot.py, undriven_single_shot.py: an interrupted sweep",
    ("points_completed", "cfg"): "t1_single_shot.py: an interrupted sweep",
    ("sweep_completed", "cfg"): "undriven_single_shot.py: an interrupted charge sweep",
    ("mr_control_tau_offset_frac", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_control_detuning_mhz", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_p_e_upper", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_p_e_lower", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_contrast", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_residual_ratio", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_null_control_valid", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_contrast_ratio", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_inverted_mapping_expected", "cfg"): "modified_ramsey.py: build_control_variants",
    ("mr_predicted_reset_pi_transfer", "cfg"): "modified_ramsey.py: build_control_variants",
    ("f_ge_measured_at_V", "cfg"): "runs/modified_ramsey.py: build_modified_ramsey_cfg, only "
    "when the recipe sets f_ge_measured_at_v",
    ("separator_probe_freq", "cfg"): "runs/zero_span.py: stage 1 re-derives the separator "
    "(recalibrate_separator=True and a better probe found)",
    ("parity_drive_freq_stage2_fit_center", "cfg"): "runs/zero_span.py: stage 2, only when "
    "the Lorentzian fit ran and passed",
    ("parity_drive_freq_stage2_fit_se", "cfg"): "runs/zero_span.py: stage 2, only when the "
    "Lorentzian fit ran and passed",
}

_RABI_N, _US, _SS = "AmplitudeRabiFF_N", "UndrivenSingleShot", "SingleShotProgramFFMUX"
_CONTROL_RECORD = "written into the control's cfg for the saved record; no code reads it back"
_UNRECORDED = (
    # (key, units, meaning, read_by, notes); scope "cfg"
    ("gain_start", "DAC units", "first gain of the flat-top (software) Rabi sweep", _RABI_N, ""),
    ("gain_end", "DAC units", "last gain of the flat-top Rabi sweep", _RABI_N, ""),
    ("gainNumPoints", "points", "gain points of the flat-top Rabi sweep", _RABI_N, ""),
    ("capture_length_us", "us", "decimated: tone length per capture", _ZSPC, ""),
    ("n_captures", "1", "decimated: captures stitched into the record", _ZSPC, ""),
    ("allow_soft_avgs", "flag", "decimated: opt in to averaging captures", _ZSPC, ""),
    ("charge_settle_s", "s", "wait after each bias ramp of the charge sweep", _US, ""),
    ("voltage_start", "V", "first bias of the charge sweep", _US, ""),
    ("voltage_end", "V", "end of the charge sweep (excluded)", _US, ""),
    ("voltage_step", "V", "step of the charge sweep", _US, ""),
    ("current_voltage", "V", "charge-line bias this file was taken at; the charge sweep "
     "restores it afterwards", _US, "build_context sets Session.bias_v; the charge, "
     "charge-dispersion, single-shot and Modified Ramsey runs set it per point"),
    ("thermal_pi_calibration", "flag", "thermal mode: acquire a pi-pulse |e> reference", _SS,
     "default True"),
    ("thermal_e_center", "a.u.", "thermal mode: fixed |e> centre when there is no pi "
     "reference", _SS, ""),
    ("thermal_tail_md2_threshold", "1", "thermal mode: Mahalanobis d^2 from the |g> blob above "
     "which a shot is a tail candidate", _SS + " classify_thermal_tail", "default 6.0"),
    ("thermal_tail_sigma_threshold", "1", "thermal mode: a shot is excited when its projection "
     "exceeds median + k sigma; this is k", _SS + " classify_thermal_tail", "default 2.5"),
    ("aborted", "text", "repr of the error that interrupted the sweep", "T1_SS " + _US,
     "set on the partial save"),
    ("points_completed", "1", "wait points finished before the interruption", "T1_SS",
     "set on the partial save"),
    ("sweep_completed", "1", "biases finished before the interruption", _US,
     "set on the partial save"),
    ("mr_control_tau_offset_frac", "1", "tau_offset control: realised fractional tau change",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_control_detuning_mhz", "MHz", "drive_detuned control: drive detuning",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_predicted_p_e_upper", "1", "predicted P(e) on the upper branch",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_predicted_p_e_lower", "1", "predicted P(e) on the lower branch",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_predicted_contrast", "1", "predicted parity contrast", "build_control_variants",
     _CONTROL_RECORD),
    ("mr_predicted_residual_ratio", "1", "predicted null residual over the measurement "
     "contrast", "build_control_variants", _CONTROL_RECORD),
    ("mr_null_control_valid", "flag", "the control is a valid null for this pulse length",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_predicted_contrast_ratio", "1", "predicted signed contrast ratio to the measurement",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_inverted_mapping_expected", "flag", "the control should invert the mapping",
     "build_control_variants", _CONTROL_RECORD),
    ("mr_predicted_reset_pi_transfer", "1", "predicted reset-pi transfer at the detuned drive",
     "build_control_variants", _CONTROL_RECORD),
)
for _key, _units, _meaning, _read_by, _notes in _UNRECORDED:
    _add(_key, "cfg", _units, _meaning, "experiments", _read_by, _notes)

# Experiment classes no regression label builds, so the golden has no cfg_access for them:
# {class: (file, its QICK program class, why no label reaches it)}. Their read_by rows come
# from the code instead: the literal cfg keys of the class and its program (the AST lint),
# core.readout.cover_readout_window (adc_trig_offset, length, readout_length, res_ch, ro_chs)
# and qick's AveragerProgram (reps, rounds, soft_avgs). tests/test_params_registry.py checks
# that these and the golden's recorded classes are every ExperimentClass under
# qicklab/experiments, and that every literal key of the class and its program is listed.
UNREACHED_CLASSES = {
    "AmplitudeRabiFF_N": ("rabi.py", "AmplitudeRabiPointProg",
                          "flat-top Rabi: run_amplitude_rabi with a flat-top qubit pulse; "
                          "no label has one"),
    "ChargeDispersion": ("charge_dispersion.py", "ChargeDispersionProgram",
                         "run_charge_dispersion_ramsey: RunChargeDispersionRamsey raises "
                         "KeyError 'df' before the class is built"),
}
_UNREACHED_READS = {
    # class: the cfg keys it reads in their plain "cfg" meaning (its cfg:<variant> and
    # UNRECORDED_CFG rows name it already)
    "AmplitudeRabiFF_N": (
        "res_ch qubit_ch ro_chs nqz qubit_nqz cavity_winding_freq cavity_winding_offset "
        "trig_buffer_start trig_buffer_end trig_delay pulse_freq pulse_gain length "
        "readout_length adc_trig_offset res_phase f_ge sigma flattop_length reps rounds "
        "soft_avgs relax_delay"),
    "ChargeDispersion": (
        "res_ch qubit_ch ro_chs nqz qubit_nqz pulse_freq pulse_gain length readout_length "
        "adc_trig_offset res_phase f_ge pi2_gain sigma df reps rounds soft_avgs relax_delay"),
}
for _cls, _cfg_keys in _UNREACHED_READS.items():
    for _key in _cfg_keys.split():
        _p = PARAMS[(_key, "cfg")]
        PARAMS[(_key, "cfg")] = replace(_p, read_by=(*_p.read_by, _cls))

# cfg keys that are in the saved .json / .h5 cfg (the golden's experiments[].cfg) but that no
# experiment class reads or writes (no cfg_access record): the run functions or the config
# builders set them as provenance, or read them on ctx.config before the class is built.
# read_by names those functions. tests/test_params_registry.py checks that RECORD_ONLY_CFG is
# exactly the saved keys without a cfg_access record.
_SPEC_RUNS = ("build_context run_charge_dispersion_quasicw run_two_tone_charge_dispersion_quasicw "
              "run_modified_ramsey_control run_zero_span_parity _acquire_spec")
_SS_BUILD = "rebuild_singleshot_config _sync_cfg_to_selected_qubit _run_single_shot_at_gain"
_ZSP_RUN, _MR_RUN = "run_zero_span_parity", "run_modified_ramsey"
_ZSP_STAGE = "zero-span validation provenance; set only when that stage runs"
_RECORD = (
    # (key, units, meaning, layer, read_by, notes); scope "cfg"
    # regime-A base config (core.context.build_context)
    ("SpecSpan", "MHz", "half-width of the two-tone sweep (qubit freq +- SpecSpan)", "core",
     _SPEC_RUNS, "the spec group's spec_span; the classes read the start / step / expts "
     "derived from it"),
    ("SpecNumPoints", "points", "frequency points of the two-tone sweep", "core", _SPEC_RUNS,
     "the spec group's spec_num_points; the classes read expts"),
    ("cavity_min", "flag", "resonator shows as a transmission dip (True) or a peak", "core",
     "build_context", "Device.cavity_min; the transmission runs read ctx.cavity_min"),
    ("FF_Qubits", "dict", "fast-flux line map {qubit: {channel, delay_time}} of the board",
     "core", "build_context rebuild_singleshot_config",
     "carried for the saved record; no program of this package plays fast flux"),
    # regime-B config (core.config.rebuild_singleshot_config)
    ("f_ges", "MHz", "regime B: frequencies of the qubits in qubit_pulse, one per qubit",
     "core", _SS_BUILD, "the programs play f_ge (the first entry)"),
    ("qubit_gains", "DAC units", "regime B: pi gains of the qubits in qubit_pulse, one per "
     "qubit", "core", _SS_BUILD, "the programs play qubit_gain (the first entry)"),
    ("pi2_SS", "flag", "single shot prepares with the pi/2 gain instead of the pi gain",
     "core", "rebuild_singleshot_config _step_pi2_ss run_qubit_optimize "
     "_run_single_shot_at_gain", "the single_shot group's pi2_ss; the run swaps qubit_gain "
     "for the pi/2 gain before building the class"),
    ("read_pulse_style", "text", "readout pulse shape of the regime-B config ('const')",
     "core", "rebuild_singleshot_config _run_single_shot_at_gain",
     "no program reads it: the readout is always a const pulse"),
    # charge sweep, bias held (runs.charge_sweep yoko_fixed)
    ("nominal_voltage", "V", "grid voltage of this slice while the bias is held", "runs",
     "_record_hold", "the held level is current_voltage"),
    ("repeat_index", "1", "repeat number of this slice while the bias is held", "runs",
     "_record_hold", ""),
    ("acq_time", "text", "local ISO wall-clock time of this slice", "runs", "_record_hold",
     ""),
    # interleaved coherence (runs.interleave)
    ("interleave_run_id", "text", "timestamp that ties the files of one interleaved run",
     "runs", "run_interleaved_coherence", ""),
    ("interleave_cycle", "1", "cycle of the interleaved run (0-based)", "runs",
     "run_interleaved_coherence", ""),
    ("interleave_cycles_total", "1", "cycles of the interleaved run", "runs",
     "run_interleaved_coherence", ""),
    ("interleave_step", "text", "step of the interleaved cycle that saved this file", "runs",
     "run_interleaved_coherence", ""),
    # modified Ramsey (runs.modified_ramsey)
    ("mr_tau_harmonic_k", "1", "odd harmonic k of the Ramsey wait tau = k / (2 df)", "runs",
     "build_modified_ramsey_cfg", "the recipe's tau_harmonic_k; the class reads ramsey_tau_us"),
    ("modified_ramsey_timing", "dict", "modelled per-rep schedule of the Modified Ramsey "
     "program (experiments.modified_ramsey.modified_ramsey_timing)", "runs",
     "run_modified_ramsey run_modified_ramsey_control", "excludes initialize(), tProc "
     "latency and transfer"),
    ("mr_parent_record", "text", "the .h5 of the measurement this control belongs to",
     "runs", _MR_RUN, "set on the control runs only"),
    ("mr_parent_cycle_idx", "1", "cycle of the measurement this control belongs to", "runs",
     _MR_RUN, "set on the control runs only"),
    # zero-span parity (runs.zero_span)
    ("n_chunks", "1", "strobe: programs stitched into one record", "runs", _ZSP_RUN,
     "copied from strobe.n_chunks; core.acquisition.chunked_acquire takes it as an argument"),
    ("parity_freq_source", "text", "how the parked parity branch was chosen ('cached' or "
     "the spectroscopy's selection path)", "runs", _ZSP_RUN, ""),
    ("parity_peak_sep_MHz", "MHz", "parity doublet splitting (measured or from the cached "
     "branches)", "runs", _ZSP_RUN, "stage 2 reads it back as the expected splitting"),
    ("parity_partner_snr", "1", "SNR of the partner line of the measured doublet", "runs",
     _ZSP_RUN, "None with cached frequencies"),
    ("read_pulse_freq_nominal", "MHz", "stage 1: readout frequency before the contrast "
     "sweep (the resonator centre)", "runs", _ZSP_RUN, _ZSP_STAGE),
    ("read_pulse_freq_source", "text", "stage 1: where read_pulse_freq came from "
     "('resonator_center', 'resonator_center_cached_separator', 'stage1_static_contrast')",
     "runs", _ZSP_RUN, _ZSP_STAGE),
    ("parity_drive_freq_unrefined", "MHz", "stage 2: parity drive frequency before the "
     "refinement", "runs", _ZSP_RUN, _ZSP_STAGE),
    ("parity_stage2_doublet", "text", "stage 2: the lines match the cached doublet "
     "('matched', 'mismatch' or 'unknown')", "runs", _ZSP_RUN, _ZSP_STAGE),
    ("parity_stage2_peak_sep_MHz", "MHz", "stage 2: splitting of the measured lines", "runs",
     _ZSP_RUN, _ZSP_STAGE),
    ("parity_drive_freq_stage2_snr", "1", "stage 2: SNR of the line the drive moves to",
     "runs", _ZSP_RUN, _ZSP_STAGE),
    ("parity_drive_freq_refined", "flag", "stage 2 moved the parity drive onto the "
     "measured line", "runs", _ZSP_RUN, _ZSP_STAGE + "; read back for the shift report"),
    ("modulation_correlation", "1", "stage 3: peak normalised cross-correlation of the "
     "state score with the drive modulation", "runs", _ZSP_RUN, _ZSP_STAGE),
    ("modulation_snr", "1", "stage 3: |level on - level off| over the pooled score spread",
     "runs", _ZSP_RUN, _ZSP_STAGE),
    ("modulation_block_t", "1", "stage 3: Welch t of the on-block vs off-block mean scores",
     "runs", _ZSP_RUN, _ZSP_STAGE),
    ("modulation_gate_passed", "flag", "stage 3: the modulation gate passed", "runs",
     _ZSP_RUN, _ZSP_STAGE),
)
for _key, _units, _meaning, _layer, _read_by, _notes in _RECORD:
    _add(_key, "cfg", _units, _meaning, _layer, _read_by, _notes)
RECORD_ONLY_CFG = frozenset(_row[0] for _row in _RECORD)

# provenance the run functions write into the saved record's cfg on code paths no regression
# label reaches (cited in UNRECORDED_CFG)
_RUN_UNRECORDED = (
    # (key, units, meaning, read_by, notes); scope "cfg", layer "runs"
    ("f_ge_measured_at_V", "V", "bias at which the Modified Ramsey df and f_ge were measured",
     "build_modified_ramsey_cfg", "the recipe's f_ge_measured_at_v; saved only when set; a "
     "different current bias only warns"),
    ("separator_probe_freq", "MHz", "stage 1: readout frequency at which the g/e separator "
     "was re-derived", _ZSP_RUN, _ZSP_STAGE + "; only when stage 1 recalibrates it"),
    ("parity_drive_freq_stage2_fit_center", "MHz", "stage 2: centre of the Lorentzian fit "
     "near the assigned line", _ZSP_RUN, _ZSP_STAGE + "; only when the fit ran and passed"),
    ("parity_drive_freq_stage2_fit_se", "MHz", "stage 2: standard error of that fit centre",
     _ZSP_RUN, _ZSP_STAGE + "; only when the fit ran and passed"),
)
for _key, _units, _meaning, _read_by, _notes in _RUN_UNRECORDED:
    _add(_key, "cfg", _units, _meaning, "runs", _read_by, _notes)

# fmt: on
