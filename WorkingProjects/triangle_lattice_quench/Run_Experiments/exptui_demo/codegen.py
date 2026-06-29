"""Codegen + safety-gate validation for ExptUI.

Pure Python, no Qt. Importable from pytest.

``generate_script(spec) -> str`` enforces hardware/measurement-engineer
preflight gates and dispatches by ``spec.experiment_kind``:

  - "bsclean":     mirrors Run_Experiments/beamsplitter_clean_timing.py
                   (BSClean_Correlations double-jump-1D branch).
  - "mott_quench": mirrors Run_Experiments/mott_quench_basic.py
                   (MottQuenchDynamics).

On ANY gate failure raises ``ValueError`` with a human-readable message
naming the failing constraint; no file is written.

``validate_against_json(spec, jd)`` is a separate check that requires the
loaded ``qubit_parameters.json`` dict; called by the tab BEFORE
``generate_script`` so the UI can show a clear error before any file is
written.
"""

from __future__ import annotations

from .spec import ExperimentSpec, Stage, Gate


# ---------------------------------------------------------------------------
# Safety gates — each raises ValueError with a specific human-readable message.
# ---------------------------------------------------------------------------

# Hardware-engineer: DAC gain registers are signed 16-bit; the ramp/BS
# experiment code clamps at +/-32766 (not 32767) before writing to the
# generator register. Match that limit here.
GAIN_LIMIT = 32766

# Hardware-engineer: qubit 2 has no JSON entry in readout_3800 ("broken").
# Fallback when JSON unavailable: hard-coded {1,3,4,5,6,7,8} per the
# hardware-engineer brief.
DEFAULT_VALID_READOUT_QUBITS = {1, 3, 4, 5, 6, 7, 8}

# Sentinel for "no pi/2-init placed" — out-of-range index so the loop in
# MottQuenchBasicProgram._body (mMottQuench.py:65) never matches it and
# every qubit gets the full pi pulse. Documented at the call site.
NO_PI2_INIT_SENTINEL = -1


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _check_int(name: str, val, lo=None, hi=None) -> None:
    _require(isinstance(val, int) and not isinstance(val, bool),
             f"{name} must be int, got {type(val).__name__}: {val!r}")
    if lo is not None:
        _require(val >= lo, f"{name} = {val} must be >= {lo}")
    if hi is not None:
        _require(val <= hi, f"{name} = {val} must be <= {hi}")


def _check_8_array(name: str, arr, allow_none=False) -> None:
    _require(hasattr(arr, "__len__") and len(arr) == 8,
             f"{name} must have length 8 (got {len(arr) if hasattr(arr,'__len__') else '?'})")
    for i, v in enumerate(arr):
        if allow_none and v is None:
            continue
        _require(isinstance(v, int) and not isinstance(v, bool),
                 f"{name}[{i}] must be int{' or None' if allow_none else ''}, got {type(v).__name__}: {v!r}")
        if not allow_none:
            _require(v >= 0, f"{name}[{i}] = {v} must be >= 0")


def _check_overrides(stage: str, overrides: dict, valid_qs: set[int]) -> None:
    for q, g in overrides.items():
        _require(isinstance(q, int) and q in valid_qs,
                 f"{stage} override key {q!r} must be one of {sorted(valid_qs)}")
        _check_int(f"{stage} override Q{q} gain", g, lo=-GAIN_LIMIT, hi=GAIN_LIMIT)


def _merged_overrides(spec: ExperimentSpec, kind: str) -> dict[int, int]:
    """Merge stage-derived overrides for ``kind`` with the legacy flat
    fields. Stage overrides win on conflict (newer UI path)."""
    flat = {
        "drive":    dict(spec.drive_hold_overrides),
        "ramp":     dict(spec.ramp_overrides),
        "dynamics": dict(spec.dynamics_overrides),
        "readout":  dict(spec.readout_overrides),
    }.get(kind, {})
    merged = dict(flat)
    for st in spec.stages:
        if st.kind == kind:
            merged.update(st.overrides)
    return merged


def _qubit_pulse_list(spec: ExperimentSpec) -> list[int]:
    """Qubit_Pulse list with the documented default = Qubit_Readout."""
    qp = list(spec.qubit_pulse) if spec.qubit_pulse else list(spec.qubit_readout)
    return qp


def _all_gates(spec: ExperimentSpec) -> list[tuple[int, Gate]]:
    """Return (stage_index, gate) for every gate across all stages."""
    out: list[tuple[int, Gate]] = []
    for i, st in enumerate(spec.stages):
        for g in st.gates:
            out.append((i, g))
    return out


def _resolve_pi2_init_index(spec: ExperimentSpec) -> int:
    """Find the unique pi2-init gate in the pre-dynamics prefix and return
    its index into Qubit_Pulse. Returns NO_PI2_INIT_SENTINEL when none was
    placed. Raises ValueError when more than one is found."""
    pre_dyn_pi2: list[Gate] = []
    for i, st in enumerate(spec.stages):
        if st.kind == "dynamics":
            break
        for g in st.gates:
            if g.kind == "pi2_init":
                pre_dyn_pi2.append(g)
    _require(len(pre_dyn_pi2) <= 1,
             f"At most one pi/2-init gate may be placed across the "
             f"pre-dynamics section; found {len(pre_dyn_pi2)}: "
             f"{[g.qubit for g in pre_dyn_pi2]}")
    if not pre_dyn_pi2:
        return NO_PI2_INIT_SENTINEL
    q = pre_dyn_pi2[0].qubit
    qp = _qubit_pulse_list(spec)
    _require(q in qp,
             f"pi/2-init qubit Q{q} is not in Qubit_Pulse {qp}; cannot "
             f"resolve pi2_init_index.")
    return qp.index(q)


# ---------------------------------------------------------------------------
# Preflight gates (BSClean — preserved verbatim from the original codegen).
# ---------------------------------------------------------------------------

def _preflight_gates_bsclean(spec: ExperimentSpec) -> None:
    """Original BSClean preflight gates 1-7. Gate 8 is JSON-dependent."""

    # Gate 1: every FF gain override integer in [-GAIN_LIMIT, GAIN_LIMIT].
    qr = list(spec.qubit_readout)
    valid_qs = set(qr) if qr else DEFAULT_VALID_READOUT_QUBITS
    for kind in ("drive", "ramp", "dynamics", "readout"):
        _check_overrides(f"{kind}_overrides",
                         _merged_overrides(spec, kind), valid_qs)

    # Gate 2: ramp_time >= 3, integer.
    _check_int("ramp_time", spec.ramp_time, lo=3)

    # Gate 3: t_offset, bs_samples, intermediate_jump_samples integers >= 0.
    _check_8_array("t_offset",                  spec.t_offset)
    _check_8_array("bs_samples",                spec.bs_samples)
    _check_8_array("intermediate_jump_samples", spec.intermediate_jump_samples)

    # Gate 4: start >= 0, step >= 1, expts >= 1, reps >= 1, relax_delay >= 0.
    _check_int("start",       spec.start,       lo=0)
    _check_int("step",        spec.step,        lo=1)
    _check_int("expts",       spec.expts,       lo=1)
    _check_int("reps",        spec.reps,        lo=1)
    _check_int("relax_delay", spec.relax_delay, lo=0)

    # Gate 5: Qubit_Readout — unique ints in valid set; length >= 4.
    _require(len(qr) >= 4,
             f"Qubit_Readout must have at least 4 entries for "
             f"BSClean_Correlations (got {len(qr)})")
    _require(len(qr) == len(set(qr)),
             f"Qubit_Readout must be unique ints, got {qr}")
    for q in qr:
        _require(isinstance(q, int) and q in DEFAULT_VALID_READOUT_QUBITS,
                 f"Qubit_Readout entry {q!r} not in {sorted(DEFAULT_VALID_READOUT_QUBITS)} "
                 f"(no JSON entry for Q2 in readout_3800; for other readout groups "
                 f"call validate_against_json(spec, jd) first)")

    # Gate 6: readout_pair_1 / readout_pair_2 — exactly 2 ints each, both
    # members of Qubit_Readout.
    qr_set = set(qr)
    for name in ("readout_pair_1", "readout_pair_2"):
        pair = getattr(spec, name)
        _require(hasattr(pair, "__len__") and len(pair) == 2,
                 f"{name} must have exactly 2 entries (got {len(pair) if hasattr(pair,'__len__') else '?'})")
        for v in pair:
            _require(isinstance(v, int),
                     f"{name} entries must be int, got {type(v).__name__}: {v!r}")
            _require(v in qr_set,
                     f"{name} entry {v} must be a member of Qubit_Readout {qr}")

    # Gate 7: length-8 alignment of the FF-channel arrays.
    _require(len(spec.t_offset) == 8,                  "t_offset must have length 8")
    _require(len(spec.bs_samples) == 8,                "bs_samples must have length 8")
    _require(len(spec.intermediate_jump_samples) == 8, "intermediate_jump_samples must have length 8")
    _require(len(spec.intermediate_jump_gains) == 8,   "intermediate_jump_gains must have length 8")
    _check_8_array("intermediate_jump_gains", spec.intermediate_jump_gains, allow_none=True)


# ---------------------------------------------------------------------------
# Preflight gates (Mott).
# ---------------------------------------------------------------------------

def _preflight_gates_mott(spec: ExperimentSpec) -> None:
    qr = list(spec.qubit_readout)
    valid_qs = set(qr) if qr else DEFAULT_VALID_READOUT_QUBITS
    for kind in ("drive", "ramp", "dynamics", "readout"):
        _check_overrides(f"{kind}_overrides",
                         _merged_overrides(spec, kind), valid_qs)

    _check_int("reps",               spec.reps,               lo=1)
    _check_int("samples_start",      spec.samples_start,      lo=0)
    _check_int("samples_end",        spec.samples_end,        lo=1)
    _check_int("samples_num_points", spec.samples_num_points, lo=2)
    _require(spec.samples_end > spec.samples_start,
             f"samples_end ({spec.samples_end}) must be > samples_start ({spec.samples_start})")

    qp = _qubit_pulse_list(spec)
    _require(len(qp) >= 1, "Qubit_Pulse (or Qubit_Readout fallback) must be non-empty for mott_quench")
    for q in qp:
        _require(isinstance(q, int) and q in DEFAULT_VALID_READOUT_QUBITS,
                 f"Qubit_Pulse entry {q!r} not in {sorted(DEFAULT_VALID_READOUT_QUBITS)}")

    _require(len(qr) >= 1, "Qubit_Readout must be non-empty for mott_quench")
    for q in qr:
        _require(isinstance(q, int) and q in DEFAULT_VALID_READOUT_QUBITS,
                 f"Qubit_Readout entry {q!r} not in {sorted(DEFAULT_VALID_READOUT_QUBITS)}")

    # Pre-dynamics: at most one pi2-init. Validate every gate's qubit is in
    # Qubit_Pulse so codegen's .index() call cannot fail downstream.
    _resolve_pi2_init_index(spec)
    for _i, g in _all_gates(spec):
        _require(g.kind in ("pi", "pi2_init", "measurement_pi2"),
                 f"Unknown gate kind {g.kind!r}")
        _require(isinstance(g.qubit, int),
                 f"Gate qubit must be int, got {type(g.qubit).__name__}: {g.qubit!r}")


def validate_against_json(spec: ExperimentSpec, jd: dict) -> None:
    """Gate 8 — drive-pulse keys exist somewhere in the loaded JSON.

    Behavior unchanged for BSClean. For mott_quench: also validates that
    each Qubit_Pulse integer has a corresponding entry in drive_groups or
    readout_groups (build_config wraps the int with ``str(P)`` and looks
    up that entry key).
    """
    known: set[str] = set()
    for ns in ("drive_groups", "readout_groups"):
        for grp in jd.get(ns, {}).values():
            if isinstance(grp, dict):
                known.update(grp.get("entries", {}).keys())

    # BSClean-style opaque drive_pulses list.
    missing = [k for k in spec.drive_pulses if k not in known]
    if missing:
        raise ValueError(
            f"Drive pulse labels not found in qubit_parameters.json under "
            f"drive_groups or readout_groups: {missing}"
        )

    # Qubit_Readout validation against the actual readout group.
    rgroups = jd.get("readout_groups", {})
    if spec.readout_point not in rgroups:
        raise ValueError(
            f"readout_point {spec.readout_point!r} not found in "
            f"readout_groups (available: {list(rgroups.keys())})"
        )
    valid = {int(k) for k in rgroups[spec.readout_point].get("entries", {}).keys()
             if k.isdigit()}
    bad = [q for q in spec.qubit_readout if q not in valid]
    if bad:
        raise ValueError(
            f"Qubit_Readout entries {bad} not present in readout group "
            f"{spec.readout_point!r} (valid: {sorted(valid)})"
        )

    # Mott-only: Qubit_Pulse entries must resolve as drive entries.
    if spec.experiment_kind == "mott_quench":
        qp = _qubit_pulse_list(spec)
        missing_qp = [q for q in qp if str(q) not in known]
        if missing_qp:
            raise ValueError(
                f"Qubit_Pulse entries {missing_qp} have no matching entry in "
                f"drive_groups or readout_groups (build_config looks up "
                f"str(q) as the entry key)."
            )


# ---------------------------------------------------------------------------
# Codegen — emits a runnable script.
# ---------------------------------------------------------------------------

def _fmt_list(values) -> str:
    return "[" + ", ".join(repr(v) for v in values) + "]"


def _emit_bsclean_overrides(spec: ExperimentSpec) -> str:
    """Emit the post-build_config override block for the BSClean script.

    Each override line writes the gain int to the canonical FF_Qubits key
    for that stage kind. Dynamics writes BOTH ``Gain_BS`` and
    ``Gain_Dynamics`` (see spec.py docstring).
    """
    chunks: list[str] = []

    def _stage(label: str, key: str, overrides: dict[int, int]) -> None:
        if not overrides:
            return
        chunks.append(f"# --- {label} stage overrides ---")
        for q in sorted(overrides):
            chunks.append(f"config['FF_Qubits']['{q}']['{key}'] = {overrides[q]}")
        chunks.append("")

    drive_ovr    = _merged_overrides(spec, "drive")
    ramp_ovr     = _merged_overrides(spec, "ramp")
    dynamics_ovr = _merged_overrides(spec, "dynamics")
    readout_ovr  = _merged_overrides(spec, "readout")

    _stage("Drive-hold", "Gain_Pulse",   drive_ovr)
    _stage("Ramp",       "Gain_Expt",    ramp_ovr)
    if dynamics_ovr:
        chunks.append("# --- Dynamics stage overrides (Gain_BS == Gain_Dynamics) ---")
        for q in sorted(dynamics_ovr):
            g = dynamics_ovr[q]
            chunks.append(f"config['FF_Qubits']['{q}']['Gain_BS']       = {g}")
            chunks.append(f"config['FF_Qubits']['{q}']['Gain_Dynamics'] = {g}")
        chunks.append("")
    _stage("Readout",    "Gain_Readout", readout_ovr)

    return "\n".join(chunks)


def _generate_bsclean(spec: ExperimentSpec) -> str:
    _preflight_gates_bsclean(spec)
    overrides_block = _emit_bsclean_overrides(spec)
    qr   = list(spec.qubit_readout)
    drv  = list(spec.drive_pulses)
    rp1  = list(spec.readout_pair_1)
    rp2  = list(spec.readout_pair_2)

    return f'''"""Auto-generated by ExptUI_demo.codegen.generate_script.

Mirrors the BSClean_Correlations branch of
``Run_Experiments/beamsplitter_clean_timing.py`` — multi-qubit fast-flux
beamsplitter pulse with current-correlation analysis on two readout pairs.
"""
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mBSDoubleJump_CleanTiming import \\
    BSClean_Correlations

from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
from matplotlib import pyplot as plt

soc, soccfg = makeProxy()

# --- build_config selectors ---
Qubit_Readout  = {_fmt_list(qr)}
Qubit_Pulse    = {_fmt_list(drv)}
Ramp_State     = {spec.ramp_state!r}
Dynamics_Point = {spec.dynamics_point!r}

config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point,
                      Readout_Point={spec.readout_point!r})
config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg)

{overrides_block}
# --- Shared double-jump parameters ---
double_jump_base = {{
    'reps': {spec.reps},
    'ramp_time': {spec.ramp_time},
    't_offset':                  config.get('t_offset', {_fmt_list(list(spec.t_offset))}),
    'relax_delay': {spec.relax_delay},
    'start': {spec.start}, 'step': {spec.step}, 'expts': {spec.expts},
    'intermediate_jump_samples': config.get('ij_samples', {_fmt_list(list(spec.intermediate_jump_samples))}),
    'intermediate_jump_gains':   config.get('ij_gains',   {_fmt_list(list(spec.intermediate_jump_gains))}),
    'bs_samples':                config.get('pad_bs',    {_fmt_list(list(spec.bs_samples))}),
}}

# --- BSClean_Correlations 1D dispatch ---
double_jump_1d_dict = {{
    'reps': {spec.reps},
    'start': {spec.start}, 'step': {spec.step}, 'expts': {spec.expts},
    'readout_pair_1': {_fmt_list(rp1)},
    'readout_pair_2': {_fmt_list(rp2)},
}}

config = config | double_jump_1d_dict
BSClean_Correlations(path="BSClean_Correlations", outerFolder=outerFolder,
                     cfg=config | double_jump_base,
                     soc=soc, soccfg=soccfg).acquire_display(plotDisp=True, block=False)

print(config)
plt.show()
'''


def _emit_mott_overrides(spec: ExperimentSpec) -> str:
    """Same override semantics as BSClean — MottQuenchBasic reads Gain_Pulse /
    Gain_Expt / Gain_Readout for the FF arrays (mMottQuench.py:139-141)."""
    chunks: list[str] = []

    def _stage(label: str, key: str, overrides: dict[int, int]) -> None:
        if not overrides:
            return
        chunks.append(f"# --- {label} stage overrides ---")
        for q in sorted(overrides):
            chunks.append(f"config['FF_Qubits']['{q}']['{key}'] = {overrides[q]}")
        chunks.append("")

    _stage("Init",       "Gain_Pulse",   _merged_overrides(spec, "drive"))
    _stage("Ramp",       "Gain_Expt",    _merged_overrides(spec, "ramp"))
    dynamics_ovr = _merged_overrides(spec, "dynamics")
    if dynamics_ovr:
        chunks.append("# --- Dynamics stage overrides (Gain_BS == Gain_Dynamics) ---")
        for q in sorted(dynamics_ovr):
            g = dynamics_ovr[q]
            chunks.append(f"config['FF_Qubits']['{q}']['Gain_BS']       = {g}")
            chunks.append(f"config['FF_Qubits']['{q}']['Gain_Dynamics'] = {g}")
        chunks.append("")
    _stage("Readout",    "Gain_Readout", _merged_overrides(spec, "readout"))
    return "\n".join(chunks)


def _generate_mott(spec: ExperimentSpec) -> str:
    _preflight_gates_mott(spec)

    qr = list(spec.qubit_readout)
    qp = _qubit_pulse_list(spec)
    pi2_idx = _resolve_pi2_init_index(spec)
    overrides_block = _emit_mott_overrides(spec)

    # If pi2_idx == NO_PI2_INIT_SENTINEL (-1), MottQuenchBasicProgram._body
    # (mMottQuench.py:65) never matches and every qubit gets the full pi
    # pulse — i.e. the no-superposition init case. Comment in the emitted
    # script so the runner knows.
    pi2_comment = (
        f"  # No pi/2-init gate placed; sentinel {NO_PI2_INIT_SENTINEL} disables superposition init "
        f"(every qubit gets full pi)."
        if pi2_idx == NO_PI2_INIT_SENTINEL else
        f"  # pi/2-init on Qubit_Pulse[{pi2_idx}] = Q{qp[pi2_idx]}"
    )

    return f'''"""Auto-generated by ExptUI_demo.codegen.generate_script.

Mirrors ``Run_Experiments/mott_quench_basic.py`` — Mott qsf protocol with
a pi/2 init on the chosen qubit (if any), full-pi init on the rest,
ramp/dynamics evolution, and pi/2 measurement-basis rotation.
"""
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mMottQuench import MottQuenchDynamics
import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy

soc, soccfg = makeProxy()

Qubit_Readout = {_fmt_list(qr)}
Qubit_Pulse   = {_fmt_list(qp)}
Ramp_State    = {spec.ramp_state!r}
Dynamics_Point = {spec.dynamics_point!r}

config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point)
config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg)

{overrides_block}
quench_base_dict = {{'reps': {spec.reps}, 'pi2_init_index': {pi2_idx}}}
{pi2_comment}

quench_dynamics_dict = {{
    'samples_start': {spec.samples_start}, 'samples_end': {spec.samples_end},
    'samples_num_points': {spec.samples_num_points},
    'measurement_pi2_phase': {spec.measurement_pi2_phase},
}}

MottQuenchDynamics(outerFolder=outerFolder,
                   cfg=config | quench_base_dict | quench_dynamics_dict,
                   soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

print(config)
plt.show()
'''


def generate_script(spec: ExperimentSpec) -> str:
    """Dispatch on experiment_kind. Raises ValueError on any preflight fail."""
    if spec.experiment_kind == "bsclean":
        return _generate_bsclean(spec)
    if spec.experiment_kind == "mott_quench":
        return _generate_mott(spec)
    raise ValueError(f"Unknown experiment_kind: {spec.experiment_kind!r}")
