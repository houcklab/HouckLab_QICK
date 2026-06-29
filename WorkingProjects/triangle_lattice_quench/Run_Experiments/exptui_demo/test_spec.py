"""Pytest for ExperimentSpec defaults + immutability.

No Qt, no hardware.
"""
from __future__ import annotations

import dataclasses

import pytest

from WorkingProjects.triangle_lattice_quench.Run_Experiments.exptui_demo.spec import (
    ExperimentSpec,
)


def test_defaults_match_brief():
    s = ExperimentSpec()
    assert s.qubit_readout == (3, 4, 5, 6, 7, 8)
    assert s.readout_point == "readout_3800"
    assert s.drive_pulses == ()
    assert s.drive_hold_overrides == {}
    assert s.ramp_overrides == {}
    assert s.dynamics_overrides == {}
    assert s.readout_overrides == {}
    assert len(s.t_offset) == 8
    assert len(s.bs_samples) == 8
    assert len(s.intermediate_jump_samples) == 8
    assert len(s.intermediate_jump_gains) == 8
    assert s.readout_pair_1 == (3, 4)
    assert s.readout_pair_2 == (3, 4)


def test_spec_is_frozen():
    s = ExperimentSpec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.ramp_time = 9999  # type: ignore[misc]


def test_replace_returns_new_spec_without_aliasing():
    s = ExperimentSpec()
    s2 = dataclasses.replace(s, dynamics_overrides={3: 5000})
    # Original spec's dict is still empty (no aliasing of the default_factory dict).
    assert s.dynamics_overrides == {}
    assert s2.dynamics_overrides == {3: 5000}


def test_adding_a_drive_pulse_via_replace_preserves_order():
    s = ExperimentSpec()
    s2 = dataclasses.replace(s, drive_pulses=("3_4Q_readout",))
    s3 = dataclasses.replace(s2, drive_pulses=s2.drive_pulses + ("5_4Q_readout",))
    assert s3.drive_pulses == ("3_4Q_readout", "5_4Q_readout")
