import importlib
import sys
import types


def test_q3_seven_condition_runner_contract():
    sys.modules.setdefault("qick", types.SimpleNamespace(AveragerProgram=object))
    sys.modules.setdefault(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q",
        types.SimpleNamespace(discriminate_shots=lambda i, q, cal: i),
    )
    runner = importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "SevenPointApplesToApples"
    )
    cfg = runner.P6_7PT_APPLES_TO_APPLES
    assert cfg["decay_delays_us"] == [40.0, 80.0, 120.0, 160.0, 200.0]
    assert cfg["shots_per_condition"] == 180
    assert cfg["freq_min_ghz"] == 3.9
    assert cfg["freq_max_ghz"] == 4.3
    assert cfg["sync_slot_s"] == 210.0
    assert cfg["sync_session"] == "q3_q5_7pt_apples_20260915_v1"
