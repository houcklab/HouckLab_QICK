"""ExperimentSpec — frozen dataclass passed between the ExptUI tab and codegen.

Pure Python, no Qt imports. Importable from pytest without a display.

Two experiment kinds are supported:
  - "bsclean":     emits a BSClean_Correlations double-jump-1D script
                   (Run_Experiments/beamsplitter_clean_timing.py shape).
  - "mott_quench": emits a MottQuenchDynamics script
                   (Run_Experiments/mott_quench_basic.py shape).

Stage layout (column-by-column, left-to-right) is dynamic — held in
``stages: tuple[Stage, ...]``. Each Stage carries its kind, optional FF
group+entry selection (matching FFFrequenciesTab semantics), per-qubit
FF gain overrides, and the right-click gate placements.

Stage→FF-Qubits key mapping for BSClean overrides (used by codegen):

    kind "drive" (Drive-hold) → 'Gain_Pulse'
    kind "ramp"               → 'Gain_Expt'
    kind "dynamics"           → 'Gain_BS' AND 'Gain_Dynamics' (dual-write)
    kind "readout"            → 'Gain_Readout'

The dynamics dual-write matches build_config.py:239-240 — different
downstream experiment classes read different keys.

Backward compatibility: the original flat per-stage override fields
(``drive_hold_overrides`` etc.) remain on the spec and are honoured by
codegen as a merge layer on top of stage-derived overrides. This keeps
existing tests + GUI flows that constructed ExperimentSpec() with only
those fields working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal

GateKind = Literal["pi", "pi2_init", "measurement_pi2"]
StageKind = Literal["readout", "drive", "ramp", "dynamics"]


@dataclass(frozen=True)
class Gate:
    """A single right-click-placed gate on a qubit line within a stage.

    ``x_frac`` is the position within the stage's x-range, in [0.0, 1.0].
    Rendering uses it to place the gate-rectangle; codegen consumes only
    the (qubit, kind) pair and ignores position.
    """
    qubit: int
    kind: GateKind
    x_frac: float = 0.5


@dataclass(frozen=True)
class Stage:
    """One column in the ExptUI canvas.

    ``group``/``entry`` are the qubit_parameters.json selectors — empty
    string means "not selected" (UI shows the (none) sentinel).

    ``overrides``: {qubit_number: gain_int} per-qubit FF gain override.

    ``gates``: tuple of right-click-placed gates inside this stage's
    x-range.
    """
    name: str
    kind: StageKind
    group: str = ""
    entry: str = ""
    overrides: dict[int, int] = field(default_factory=dict)
    gates: tuple[Gate, ...] = ()


def _default_bsclean_stages() -> tuple[Stage, ...]:
    return (
        Stage(name="Drive-hold", kind="drive"),
        Stage(name="Ramp",       kind="ramp"),
        Stage(name="Dynamics",   kind="dynamics"),
        Stage(name="Readout",    kind="readout"),
    )


def _default_mott_stages() -> tuple[Stage, ...]:
    # mott_quench_basic.py uses Ramp_State + Dynamics_Point but no separate
    # drive-hold stage; the qubit pi/pi2 init pulses happen at the start of
    # _body. Layout: Init (drive) | Ramp | Dynamics | Readout.
    return (
        Stage(name="Init",     kind="drive"),
        Stage(name="Ramp",     kind="ramp"),
        Stage(name="Dynamics", kind="dynamics"),
        Stage(name="Readout",  kind="readout"),
    )


@dataclass(frozen=True)
class ExperimentSpec:
    """All inputs needed to emit a runnable script."""

    # --- experiment selector ---
    experiment_kind: Literal["bsclean", "mott_quench"] = "bsclean"

    # --- build_config selectors ---
    qubit_readout: tuple[int, ...] = (3, 4, 5, 6, 7, 8)
    # qubit_pulse: defaults to qubit_readout at the codegen layer when empty.
    # Used by mott_quench (Qubit_Pulse build_config arg); also drives
    # pi2_init_index resolution (index into this list of the pi2-init qubit).
    qubit_pulse: tuple[int, ...] = ()
    readout_point: str = "readout_3800"
    drive_pulses: tuple[str, ...] = ()          # opaque entry keys (BSClean only)
    ramp_state: str = ""
    dynamics_point: str = ""

    # --- dynamic stage layout ---
    stages: tuple[Stage, ...] = field(default_factory=_default_bsclean_stages)

    # --- per-qubit gain overrides (BSClean legacy flat layer) ---
    # These are MERGED on top of any same-kind stage.overrides at codegen
    # time. Kept for backward compatibility with the original spec API and
    # the existing BSClean test suite.
    drive_hold_overrides: dict[int, int] = field(default_factory=dict)
    ramp_overrides: dict[int, int] = field(default_factory=dict)
    dynamics_overrides: dict[int, int] = field(default_factory=dict)
    readout_overrides: dict[int, int] = field(default_factory=dict)

    # --- timing + sweep (BSClean) ---
    ramp_time: int = 1000
    reps: int = 50_000
    relax_delay: int = 180
    start: int = 0
    step: int = 8
    expts: int = 1000

    # --- 8-element FF-channel arrays (post-build_config overrides, BSClean) ---
    t_offset: tuple[int, ...] = (0,) * 8
    bs_samples: tuple[int, ...] = (0,) * 8
    intermediate_jump_samples: tuple[int, ...] = (0,) * 8
    intermediate_jump_gains: tuple[Optional[int], ...] = (None,) * 8

    # --- correlation analysis pairs (BSClean only) ---
    readout_pair_1: tuple[int, int] = (3, 4)
    readout_pair_2: tuple[int, int] = (3, 4)

    # --- mott_quench-only parameters ---
    samples_start: int = 0
    samples_end: int = 8000
    samples_num_points: int = 101
    measurement_pi2_phase: float = 0.0
