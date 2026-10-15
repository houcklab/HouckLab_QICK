"""AutoCoherence refuses a cross-qubit session (F82).

The pipeline takes the drive frequency, pi gain, sigma and flat-top from the Qubit_Readout
entry, while T1/Rabi/single-shot use Qubit_Pulse; with Qubit_Pulse != Qubit_Readout it would
calibrate a drive no other step uses. run_auto_coherence now raises before any soc call.
No hardware: a fake ctx whose soc fails on any attribute access.
"""

import types

import pytest

import qicklab.runs.auto_coherence as ac


class _NoSoc:
    def __getattr__(self, name):
        raise AssertionError(f"soc.{name} touched before the qubit guard")


def _ctx(pulse, readout):
    return types.SimpleNamespace(
        soc=_NoSoc(),
        soccfg=_NoSoc(),
        working_config=dict,
        outerFolder="unused",
        Qubit_Pulse=pulse,
        Qubit_Readout=readout,
        Qubit_Parameters={},
        yoko=None,
    )


def test_cross_qubit_session_is_refused(monkeypatch):
    called = []
    monkeypatch.setattr(ac, "_run_auto_coherence", lambda **kw: called.append(kw))
    with pytest.raises(ValueError, match=r"Qubit_Pulse \(6\) != Qubit_Readout \(5\)"):
        ac.run_auto_coherence(_ctx(6, 5), {})
    assert called == []


@pytest.mark.parametrize("pulse, readout", [(5, 5), ("5", 5), (5, "5")])
def test_same_qubit_runs(monkeypatch, pulse, readout):
    called = []
    monkeypatch.setattr(ac, "_run_auto_coherence", lambda **kw: called.append(kw) or {})
    ac.run_auto_coherence(_ctx(pulse, readout), {"T1_step": 5})
    assert len(called) == 1
    assert called[0]["qubit_readout"] == readout
    assert called[0]["auto_params"] == {"T1_step": 5}
