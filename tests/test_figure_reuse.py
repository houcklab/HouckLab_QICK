"""Every saved PNG shows one run only: a display never draws over a figure an earlier run left open.

Sessions run on the Agg backend (docs/running_a_session.md#plots), so plt.show(block=True)
returns at once and a plotDisp figure stays open; a display that reused a fixed figure number
(plt.figure(figNum), subplots(num=)) then drew over the previous run: in run_qubit_loop the
second qubit's TransmissionFF png carried the first qubit's curves, two_tone_spec's IQ png the
transmission's, and so on. Here
run_qubit_loop runs a PLAN on two qubits on the fake board with plt.show a no-op and no figure
ever closed by the test; every artist in a saved figure must come from the experiment that saved
it.

    python -m pytest tests/test_figure_reuse.py
"""

import matplotlib

matplotlib.use("Agg")

import dataclasses
import os
import time

import matplotlib.figure
import matplotlib.pyplot as plt
import pytest
import pyvisa

import qicklab.core.session as session_module
from devices.archive.CSTQ03_2026_10_01 import DEVICE
from qicklab.core import context as context_module
from qicklab.core import fakes
from qicklab.core.experiment import ExperimentClass
from qicklab.core.session import Session, run_qubit_loop
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

pytestmark = pytest.mark.filterwarnings("ignore")  # Device.validate, fits on synthetic data

# displays that reused a figure number (transmission, qubit_spec, chi_shift, hist_process via
# single_shot, the T1 / T2E Q and T2R FFT figures) next to ones that leave theirs open
PLAN = [
    R.transmission_fit(),
    R.two_tone_spec(spec_num_points=51),
    R.amplitude_rabi(number_of_steps=51),
    R.chi_shift(trans_num_points=21, rounds=2),
    R.t1_t2r_t2e(),
    R.single_shot(),
]


def _artists(fig):
    out = list(fig.texts) + list(fig.legends)
    for ax in fig.axes:
        out += [*ax.lines, *ax.collections, *ax.images, *ax.patches, *ax.texts]
    return out


def test_looped_qubits_save_only_their_own_curves(monkeypatch, tmp_path):
    monkeypatch.setattr(context_module, "makeProxy", fakes.fake_make_proxy)
    monkeypatch.setattr(pyvisa, "ResourceManager", fakes.FakeResourceManager)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(plt, "show", lambda *a, **k: None)  # returns, the figure stays open
    monkeypatch.setattr(plt, "pause", lambda *a, **k: None)

    # the run an artist belongs to: (qubit, step, experiment count)
    run = {"qubit": None, "step": None, "n": 0}
    real_run_step = session_module._run_step

    def run_step(ctx, step, label=""):
        run.update(qubit=ctx.session.qubit_readout, step=step.name)
        return real_run_step(ctx, step, label)

    real_init = ExperimentClass.__init__

    def init(self, *args, **kwargs):
        run["n"] += 1
        real_init(self, *args, **kwargs)

    owner, saves, leaks = {}, [], []

    def savefig(fig, fname, *args, **kwargs):
        key = (run["qubit"], run["step"], run["n"])
        name = os.path.basename(str(fname))
        saves.append((key, name))
        for art in _artists(fig):
            first = owner.setdefault(art, key)
            if first != key:
                leaks.append(f"{name} (Q{key[0]} {key[1]}) holds a {type(art).__name__} of {first}")

    monkeypatch.setattr(session_module, "_run_step", run_step)
    monkeypatch.setattr(ExperimentClass, "__init__", init)
    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", savefig)

    device = dataclasses.replace(DEVICE, data_root=str(tmp_path / "data").replace("\\", "/"))
    session = Session(
        device,
        5,
        5,
        transmission=G.transmission(span=3, num_points=41, reps=2, rounds=2),
        coherence=G.coherence(repetitions=1),
        echo=G.echo(repetitions=1),
    )
    open_before = set(plt.get_fignums())
    try:
        run_qubit_loop(session, PLAN, (2, 5), cycles=1)
    finally:
        for num in set(plt.get_fignums()) - open_before:
            plt.close(num)

    # not vacuous: every step saved a figure on both qubits
    saved = {(q, step) for (q, step, _), _ in saves}
    assert saved == {(q, s.name) for q in (2, 5) for s in PLAN}, sorted(saved)
    assert not leaks, "\n".join(leaks[:20])
