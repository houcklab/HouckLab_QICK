"""The runners forward ``reset_read_latency_us`` from the step params to the program cfg.

Replays the CSTQ03 fixture through the regression capture driver (fake board A, no
hardware) with the key set in ModifiedRamsey_params, ModifiedRamsey_Control_params and
ActiveResetVerify_params, and checks that every reset-ON experiment cfg carries it.
Without the forwarding the program silently used the 0.5 us default.
"""

import importlib

import pytest

from tests.regression import capture as core

pytestmark = pytest.mark.slow


def _set(dict_name, **values):
    def apply(ns):
        ns[dict_name].update(values)

    return apply


CASES = {
    # label: (runner flag, override, latency set)
    "RunModifiedRamsey[latency]": (
        "RunModifiedRamsey",
        _set("ModifiedRamsey_params", reset_read_latency_us=1.0),
        1.0,
    ),
    # MRC ships with the reset off and reset_readout_relax_delay = 1.0 us. Since F41 its
    # Ramsey is the modified_ramsey sequence built by build_modified_ramsey_cfg with the
    # separator-derived readout_threshold, so the reset-ON program compiles like MR's.
    "RunModifiedRamsey_Control[latency]": (
        "RunModifiedRamsey_Control",
        _set(
            "ModifiedRamsey_Control_params",
            sweet_spot_max_df_mhz=1e9,
            use_active_reset=True,
            reset_read_latency_us=0.7,
        ),
        0.7,
    ),
    "RunActiveResetVerify[latency]": (
        "RunActiveResetVerify",
        _set("ActiveResetVerify_params", reset_read_latency_us=1.0),
        1.0,
    ),
}


@pytest.fixture(scope="module")
def captured(request):
    driver = importlib.import_module("tests.regression.driver_qicklab")
    saved = dict(driver.OVERRIDES)
    for label, (flag, override, _) in CASES.items():
        driver.OVERRIDES[label] = ((flag,), override)
    try:
        yield core.capture_variants(driver.capture_all, list(CASES), ("A",))["A"]
    finally:
        driver.OVERRIDES.clear()
        driver.OVERRIDES.update(saved)
        core._ACTIVE.undo()  # restore the real library for later test modules


@pytest.mark.parametrize("label", list(CASES))
def test_params_latency_reaches_program_cfg(captured, label):
    latency = CASES[label][2]
    result = captured[label]
    assert result["outcome"]["status"] in ("completed", "stopped_at_budget"), result["outcome"]
    reset_on = [e for e in result["experiments"] if (e.get("cfg") or {}).get("use_active_reset")]
    assert reset_on, "no reset-ON experiment was captured"
    for exp in reset_on:
        assert exp["cfg"]["reset_read_latency_us"] == latency
        assert exp["hw"]["digest"] is not None  # the program compiled with that cfg
    assert any("reset_read_latency_us" in a["read"] for a in result["cfg_access"].values())
