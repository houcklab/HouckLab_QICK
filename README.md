# HouckLab_QICK: qicklab

This is the repository for the Houck lab RFSOC code.

`qicklab` is the Houck Lab QM-team package for measuring superconducting qubits with a Xilinx
RFSoC board running [QICK](https://github.com/openquantumhardware/qick) (tProc v1, client
`qick==0.2.334`). It covers resonator and qubit spectroscopy, Rabi, T1 / T2* / T2E, single-shot
readout, active reset and charge-parity switching (Modified Ramsey, undriven single shot,
zero-span). A device file (`devices/CSTQ03.py`) holds one chip's measured numbers; a session
script (`runners/CSTQ03_session.py`) picks the qubits and the bias and lists the steps to run;
every step compiles a tProc program, acquires, fits, plots and saves `.h5` + `.png` + `.json`.

## Quick start

Python 3.11 or newer. Run everything from the repo root (no install step is needed):

```
git clone -b qicklab_refactor https://github.com/houcklab/HouckLab_QICK.git
cd HouckLab_QICK
python -m venv .venv
.venv\Scripts\activate
pip install -r docs/dev/refactor-2026-10/requirements-test.txt
python -m pytest tests/test_imports.py tests/test_layering.py
```

The activate line is for Windows (cmd or PowerShell; in PowerShell it runs `Activate.ps1`); on
macOS / Linux use `source .venv/bin/activate`. The requirements file pins `qick==0.2.334`,
numpy, scipy and the rest. The two test files take seconds; `python -m pytest tests` runs
everything, including the regression golden (about 14 minutes). Then, in `python`, a dry run on
the fake board (compiles every program, plays nothing, about 3 s):

```python
from runners.CSTQ03_session import SESSION
from qicklab.core.session import run
from qicklab.runs import recipes as R
run(SESSION, [R.amplitude_rabi(), R.single_shot()], dry_run=True)
```

On the lab network, `python -m runners.CSTQ03_session` runs the `PLAN` in
`runners/CSTQ03_session.py` on the RFSoC (over Pyro4) and the charge yoko. Check a plan offline
with short steps first, as above. `--dry-run` runs the plan as committed on the fake board, but its
one step (`undriven_single_shot`, a million shots, `repeat=10000`) analyses 41 records before the
dry-run guard stops it and reports it `INCOMPLETE`: about 12 minutes, not seconds. For a quick
check of that step use `R.undriven_single_shot(shots=10_000, repeat=2)`; see
[Dry run](docs/running_a_session.md#dry-run).

## Documentation

- [docs/README.md](docs/README.md): the index and the reading path (concepts, experiments, glossary).
- [docs/running_a_session.md](docs/running_a_session.md): the session file, plans, overrides, dry run, where data lands.
- [docs/adding_a_device.md](docs/adding_a_device.md): writing `devices/<NAME>.py`, calibration write-back, archiving a cooldown.
- [docs/parameters.md](docs/parameters.md): every knob with units, default and meaning (generated from the code).
- [docs/architecture.md](docs/architecture.md): package layout, layering, regression harness (for developers).

## Status

Branch `qicklab_refactor` is the 2026-10 rewrite of the lab's QM-team code (`bfc_code` at
`0f0a51f`) into this package; it is to be fast-forwarded into `bfc_code`. The regression golden
(`tests/regression/golden_cstq03.json`) fingerprints every tProc program, cfg dict, yoko write
and saved-data digest the CSTQ03 runner produced on two synthetic boards, and the test suite
replays it through both the legacy call shapes and the `Session` + PLAN API, so a change that
alters what reaches the hardware or what is saved cannot pass unnoticed. The history and
decisions are in [docs/dev/refactor-2026-10/HANDOFF.md](docs/dev/refactor-2026-10/HANDOFF.md).

## Lab context

Houck Lab, Princeton. The measurements run on a Xilinx RFSoC with the open-source QICK firmware,
reached over Pyro4 from a Windows lab PC that also drives the yokos, attenuators and TWPA
instruments ([docs/hardware.md](docs/hardware.md)). The current chip is CSTQ03
([docs/devices/CSTQ03.md](docs/devices/CSTQ03.md)).
