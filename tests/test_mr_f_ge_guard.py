"""Hardware-free tests of the f_ge-on-qubit guard of run_modified_ramsey (F42).

The configured doublet centre ``f_ge - df/2`` must lie on the qubit whose pi/2, pi gains
and SingleShot separator are used (``ctx.qubit_frequency_center``). Off it the run warns
by default and raises with ``require_f_ge_near_qubit=True``, before any acquisition. See
docs/experiments/modified_ramsey.md (f_ge must sit on the pulsed qubit).

    python -m pytest tests/test_mr_f_ge_guard.py
"""

import pytest

import qicklab.runs.modified_ramsey as mr_runs
from qicklab.runs.modified_ramsey import check_f_ge_near_qubit
from tests.test_run_modified_ramsey_controls import _Ctx, _FakeMR, _params, fakes  # noqa: F401


def test_on_qubit_is_silent(capsys):
    out = check_f_ge_near_qubit(4186.7, 2.7, 4186.7, 0.04, strict=True)
    assert out["on_qubit"] and not out["bias_moved"]
    assert out["doublet_centre_mhz"] == pytest.approx(4185.35)
    assert out["offset_mhz"] == pytest.approx(-1.35)
    assert out["tolerance_mhz"] == pytest.approx(13.5)  # 5*df beats 2 MHz and 1/(4 sigma)
    assert "WARNING" not in capsys.readouterr().out


def test_tolerance_terms():
    # the 2 MHz floor: narrow doublet, long pulses
    assert check_f_ge_near_qubit(5000.0, 0.1, 5000.0, 1.0)["tolerance_mhz"] == pytest.approx(2.0)
    # the pulse-bandwidth term 1/(4 sigma): sigma = 0.08 us -> 3.125 MHz
    inside = check_f_ge_near_qubit(5003.1, 0.2, 5000.0, 0.08)  # centre 5003.0
    assert inside["tolerance_mhz"] == pytest.approx(3.125) and inside["on_qubit"]
    outside = check_f_ge_near_qubit(5003.3, 0.2, 5000.0, 0.08)  # centre 5003.2
    assert not outside["on_qubit"]
    # the centre, not f_ge, is compared: f_ge = upper branch sits df/2 above the qubit
    assert check_f_ge_near_qubit(5005.0, 10.0, 5000.0, 1.0)["offset_mhz"] == pytest.approx(0.0)


def test_frozen_runner_values_warn_but_do_not_raise(capsys):
    # CSTQ03 runner: Qubit_Pulse = 5 at 2651 MHz (sigma 0.08 us), f_ge = 3754.5 (Q2), df = 1
    out = check_f_ge_near_qubit(3754.5, 1.0, 2651.0, 0.08, qubit_pulse=5)
    assert not out["on_qubit"]
    assert out["offset_mhz"] == pytest.approx(1103.0)
    text = capsys.readouterr().out
    assert "WARNING" in text
    for value in ("3754.5", "2651.0", "3754.0000", "+1103.0000", "Qubit_Pulse=5"):
        assert value in text


def test_strict_raises_with_both_values():
    with pytest.raises(ValueError, match=r"3754\.0000 MHz, \+1103\.0000 MHz from .* 2651\.0"):
        check_f_ge_near_qubit(3754.5, 1.0, 2651.0, 0.08, qubit_pulse=5, strict=True)


@pytest.mark.parametrize("current_v, moved", [(0.125, False), (0.12505, False), (0.126, True)])
def test_bias_provenance_warns_only(capsys, current_v, moved):
    out = check_f_ge_near_qubit(
        4186.7, 2.7, 4186.7, 0.04, strict=True, measured_at_v=0.125, current_v=current_v
    )
    assert out["bias_moved"] is moved and out["on_qubit"]
    assert ("measured at 0.125 V" in capsys.readouterr().out) is moved


def test_run_raises_before_any_acquisition(fakes, tmp_path, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(
        mr_runs, "get_apriori_separator_from_singleshot", lambda ctx, **k: calls.append(1)
    )
    monkeypatch.setattr(mr_runs, "calibrate_active_reset_readout", lambda ctx: calls.append(2))
    params = _params(f_ge=3754.5, require_f_ge_near_qubit=True, use_active_reset=True)
    with pytest.raises(ValueError, match="require_f_ge_near_qubit"):
        mr_runs.run_modified_ramsey(_Ctx(str(tmp_path) + "/", sigma=0.04), params)
    assert calls == [] and _FakeMR.instances == []


def test_run_warns_by_default_and_records_bias(fakes, tmp_path, capsys):  # noqa: F811
    params = _params(f_ge=3754.5, f_ge_measured_at_V=0.2, validation_controls=[])
    mr_runs.run_modified_ramsey(_Ctx(str(tmp_path) + "/", sigma=0.04), params)
    text = capsys.readouterr().out
    assert "WARNING: ModifiedRamsey f_ge=3754.5" in text
    assert "measured at 0.2 V but the bias now reads 0.125 V" in text
    (parent,) = _FakeMR.instances
    assert parent.cfg["f_ge_measured_at_V"] == 0.2


def test_run_without_provenance_leaves_cfg_unchanged(fakes, tmp_path):  # noqa: F811
    mr_runs.run_modified_ramsey(
        _Ctx(str(tmp_path) + "/", sigma=0.04), _params(validation_controls=[])
    )
    (parent,) = _FakeMR.instances
    assert "f_ge_measured_at_V" not in parent.cfg
