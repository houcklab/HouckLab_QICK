"""Pytest for ExptUI codegen safety gates + drive-pulse JSON validation.

One passing case (full happy-path script generation) plus one failing case
per gate. No Qt, no hardware, no soccfg.
"""

from __future__ import annotations

import pytest

from WorkingProjects.triangle_lattice_quench.Run_Experiments.exptui_demo.spec import ExperimentSpec
from WorkingProjects.triangle_lattice_quench.Run_Experiments.exptui_demo.codegen import (
    generate_script, validate_against_json,
)


def _ok_spec(**overrides) -> ExperimentSpec:
    """Minimal valid spec; tests override one field at a time to fail a gate."""
    base = dict(
        qubit_readout=(3, 4, 5, 6, 7, 8),
        readout_point="readout_3800",
        drive_pulses=("3_4Q_readout",),
        ramp_state="6Q_highest",
        dynamics_point="Q1_quench",
        ramp_time=1000,
        reps=400,
        relax_delay=180,
        start=0,
        step=8,
        expts=71,
        t_offset=(0,) * 8,
        bs_samples=(0,) * 8,
        intermediate_jump_samples=(0,) * 8,
        intermediate_jump_gains=(None,) * 8,
        readout_pair_1=(3, 4),
        readout_pair_2=(5, 6),
    )
    base.update(overrides)
    return ExperimentSpec(**base)


# --- Happy path -----------------------------------------------------------

def test_generate_script_happy_path():
    """No gate fails; generated text contains the build_config call,
    the BSClean_Correlations dispatch, and the readout-pair literals."""
    spec = _ok_spec(
        dynamics_overrides={3: 5000},      # exercises the dual-write
        drive_hold_overrides={4: -2000},
        ramp_overrides={5: 1234},
        readout_overrides={6: 7777},
    )
    text = generate_script(spec)
    assert "build_config(" in text
    assert "BSClean_Correlations(" in text
    assert "'readout_pair_1': [3, 4]" in text
    assert "'readout_pair_2': [5, 6]" in text
    # Dynamics dual-write present.
    assert "config['FF_Qubits']['3']['Gain_BS']" in text
    assert "config['FF_Qubits']['3']['Gain_Dynamics']" in text
    # Other-stage single-write present.
    assert "config['FF_Qubits']['4']['Gain_Pulse'] = -2000" in text
    assert "config['FF_Qubits']['5']['Gain_Expt'] = 1234" in text
    assert "config['FF_Qubits']['6']['Gain_Readout'] = 7777" in text


# --- Gate 1: gain override range -----------------------------------------

def test_gate1_gain_override_out_of_range():
    spec = _ok_spec(dynamics_overrides={3: 40000})  # > 32766
    with pytest.raises(ValueError, match="dynamics_overrides override Q3 gain"):
        generate_script(spec)


# --- Gate 2: ramp_time >= 3 ----------------------------------------------

def test_gate2_ramp_time_too_small():
    spec = _ok_spec(ramp_time=2)
    with pytest.raises(ValueError, match="ramp_time"):
        generate_script(spec)


# --- Gate 3: FF arrays non-negative integers -----------------------------

def test_gate3_t_offset_negative():
    spec = _ok_spec(t_offset=(0, 0, -1, 0, 0, 0, 0, 0))
    with pytest.raises(ValueError, match=r"t_offset\[2\]"):
        generate_script(spec)


# --- Gate 4: sweep params ------------------------------------------------

def test_gate4_step_zero():
    spec = _ok_spec(step=0)
    with pytest.raises(ValueError, match="step"):
        generate_script(spec)


def test_gate4_reps_zero():
    spec = _ok_spec(reps=0)
    with pytest.raises(ValueError, match="reps"):
        generate_script(spec)


# --- Gate 5: Qubit_Readout ----------------------------------------------

def test_gate5_qubit_2_rejected():
    spec = _ok_spec(qubit_readout=(2, 3, 4, 5, 6, 7))
    with pytest.raises(ValueError, match="Qubit_Readout entry 2"):
        generate_script(spec)


def test_gate5_too_few_qubits():
    spec = _ok_spec(qubit_readout=(3, 4, 5))
    with pytest.raises(ValueError, match="at least 4"):
        generate_script(spec)


def test_gate5_duplicates():
    spec = _ok_spec(qubit_readout=(3, 3, 4, 5))
    with pytest.raises(ValueError, match="unique"):
        generate_script(spec)


# --- Gate 6: readout_pair_1 / readout_pair_2 ----------------------------

def test_gate6_pair_wrong_size():
    spec = _ok_spec(readout_pair_1=(3,))
    with pytest.raises(ValueError, match="readout_pair_1 must have exactly 2"):
        generate_script(spec)


def test_gate6_pair_not_in_readout():
    # 8 is valid in default set but NOT in Qubit_Readout below.
    spec = _ok_spec(
        qubit_readout=(3, 4, 5, 6),
        readout_pair_1=(3, 8),
        readout_pair_2=(3, 4),
    )
    with pytest.raises(ValueError, match=r"readout_pair_1 entry 8"):
        generate_script(spec)


# --- Gate 7: length-8 arrays --------------------------------------------

def test_gate7_t_offset_wrong_length():
    spec = _ok_spec(t_offset=(0, 0, 0))
    with pytest.raises(ValueError, match="t_offset must have length 8"):
        generate_script(spec)


def test_gate7_intermediate_jump_gains_wrong_length():
    spec = _ok_spec(intermediate_jump_gains=(None, None, None))
    with pytest.raises(ValueError, match="intermediate_jump_gains must have length 8"):
        generate_script(spec)


# --- Gate 8: drive-pulse keys exist in JSON ----------------------------

def test_gate8_missing_drive_pulse_key():
    spec = _ok_spec(drive_pulses=("nonexistent_label",))
    jd = {
        "drive_groups": {"some_grp": {"entries": {"real_label": {}}}},
        "readout_groups": {"readout_3800": {"entries": {"3": {}, "4": {}, "5": {}, "6": {}}}},
    }
    with pytest.raises(ValueError, match="nonexistent_label"):
        validate_against_json(spec, jd)


def test_gate8_passes_when_key_in_drive_groups():
    spec = _ok_spec(drive_pulses=("real_label",))
    jd = {
        "drive_groups": {"some_grp": {"entries": {"real_label": {}}}},
        "readout_groups": {"readout_3800": {"entries": {"3": {}, "4": {}, "5": {}, "6": {}, "7": {}, "8": {}}}},
    }
    validate_against_json(spec, jd)  # should not raise


def test_gate8_passes_when_key_in_readout_groups():
    # build_config._resolve_drive falls back to readout_groups — match that.
    spec = _ok_spec(drive_pulses=("3_4Q_readout",))
    jd = {
        "drive_groups": {},
        "readout_groups": {
            "readout_3800": {"entries": {"3_4Q_readout": {}, "3": {}, "4": {}, "5": {}, "6": {}, "7": {}, "8": {}}},
        },
    }
    validate_against_json(spec, jd)  # should not raise


def test_gate8_rejects_qubit_not_in_readout_group():
    # Empty drive_pulses so the drive-pulse check passes vacuously; we only
    # want to exercise the Qubit_Readout-vs-readout-group check here.
    spec = _ok_spec(qubit_readout=(3, 4, 5, 6), drive_pulses=())
    jd = {
        "drive_groups": {},
        "readout_groups": {"readout_3800": {"entries": {"3": {}, "4": {}, "5": {}}}},
    }
    with pytest.raises(ValueError, match=r"Qubit_Readout entries \[6\]"):
        validate_against_json(spec, jd)
