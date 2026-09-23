"""Hardware-free checks for production-path post-return spectroscopy on q3."""

import json

import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import ParkLandingSpec as spec


def test_plan_uses_fixed_full_return_and_short_long_holds():
    settings = spec.plan({})
    assert settings["return_prefix_us"] == [1.0, 5.0, 25.0]
    assert settings["target_holds_us"] == [2.0, 100.0]
    assert settings["recovery_us"] == 40.0
    assert settings["probe_offsets_mhz"][0] == -30.0
    assert settings["probe_offsets_mhz"][-1] == 30.0


def test_plan_rejects_readout_after_full_return():
    with pytest.raises(ValueError, match="recovery"):
        spec.plan({"Q3_PARK_LANDING_TIMINGS_US": "1,5,50"})


def test_result_rows_keep_park_target_and_iq_separate():
    states = np.asarray([
        [[0, 0], [0, 0]], [[1, 1], [1, 1]],
        [[0, 0], [0, 0]], [[1, 1], [1, 1]],
    ], dtype=float)
    iq_i = np.arange(16.0).reshape(4, 2, 2)
    iq_q = np.zeros_like(iq_i)
    rows = spec.result_rows(
        states, iq_i, iq_q, probe_frequency_ghz=4.367,
        return_prefix_us=5.0, park_frequency_ghz=4.367,
        target_frequency_ghz=4.055, holds_us=(2.0, 100.0), shots=2,
    )
    assert len(rows) == 4
    assert rows[0]["target_kind"] == "park"
    assert rows[2]["target_kind"] == "target"
    assert rows[2]["hold_us"] == 2.0
    assert rows[2]["P0"] == pytest.approx(0.0)
    assert rows[2]["P1"] == pytest.approx(1.0)
    assert rows[2]["iq_I_P1"] == pytest.approx(6.5)


def test_plan_cli_is_hardware_free(capsys):
    assert spec.main(["--plan"]) == 0
    assert json.loads(capsys.readouterr().out)["hardware_access"] is False
