from types import SimpleNamespace

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
    AcquisitionTimeout,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import production


def test_prepare_reset_session_retries_zero_progress_transport_timeout(
    monkeypatch, tmp_path
):
    """A transient tProc launch failure must not abort a week-long scan startup."""
    calls = []
    bundle = SimpleNamespace(to_dict=lambda: {"schema_version": 1})
    streamer = SimpleNamespace(
        running=True,
        readout_running=lambda: streamer.running,
        stop_readout=lambda: setattr(streamer, "running", False),
    )
    soc = SimpleNamespace(streamer=streamer)

    monkeypatch.setattr(production, "CALIBRATION_SHOTS", 40)
    monkeypatch.setattr(production, "latest_park_history_result", lambda *_: None)
    monkeypatch.setattr(production, "save_calibration", lambda *_: None)
    monkeypatch.setattr(production, "save_raw_calibration", lambda *_: None)
    monkeypatch.setattr(production, "validate_confident_calibration", lambda *_a, **_k: None)

    def acquire(*_args, **_kwargs):
        calls.append("attempt")
        if len(calls) == 1:
            raise AcquisitionTimeout(
                "OPX reset block timed out after 5 s (0/40 complete shots)",
                completed_shots=0,
                partial_records=[],
            )
        assert not streamer.running
        return bundle, {"payload": {}, "loop": {}}

    monkeypatch.setattr(production, "acquire_calibration", acquire)

    session = production.prepare_reset_session(
        "active",
        outer_folder=tmp_path,
        qubit="q3",
        base_cfg={"qubit_pi_freq": 4367.292},
        soc=soc,
        soccfg={},
        purpose="test",
        now="2026_09_14_20_30_00",
    )

    assert calls == ["attempt", "attempt"]
    assert session.runtime_mode == "opx_unbounded"
    assert session.calibration_output.name.endswith("_attempt_2")
