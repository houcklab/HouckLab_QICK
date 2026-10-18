# AGENTS.md: guidance for Codex working in this repository

History and decisions of the 2026-10 refactor: `docs/dev/refactor-2026-10/HANDOFF.md` (a record, not a prerequisite).

## What this repo is

`qicklab` is the Houck Lab QM-team package for measuring superconducting qubits with a Xilinx
RFSoC running QICK (tProc v1, client `qick==0.2.334`); the production chip is CSTQ03. A device
file holds one chip's measured numbers, a `Session` picks the qubits, the bias and the shared
settings, and a `PLAN` is an ordered list of steps (`R.t1()`, `R.single_shot()`, ...) that `run()`
executes. Each step wraps an experiment class that compiles a tProc program, acquires, fits,
plots and saves `.h5` + `.png` + `.json`. User docs start at `docs/README.md`, developer docs at
`docs/architecture.md`; where code and docs disagree, the code wins. Active topic: zero-span
charge-parity switching (`docs/experiments/zero_span_parity.md`).

## Layout

```
qicklab/              the package; layers in import order, lowest first
  hardware/           rfsoc (Pyro4 proxy), board (BASE_CONFIG), yoko, attenuator, sc5510a, pnax, synthhd
  core/               ExperimentClass, device, session, params (registry), config, context, io, fakes
  analysis/           offline fits, IQ processing, parity classifiers (never imports qick)
  experiments/        one module per family: QICK program + ExperimentClass subclass
  runs/               run_* (one per step), groups.py (G, session groups), recipes.py (R, STEPS)
  twpa/               standalone TWPA bias / pump / sweep scripts
devices/              <NAME>.py: one frozen DEVICE per chip and cooldown; archive/ for past cooldowns
runners/              <device>_session.py: SESSION, STEP, PLAN (the file a researcher edits)
scripts/gen_docs.py   parameter registry -> docs/parameters.md and the step pages' recipe tables
tests/                regression/ (golden), refactor/ (equivalence gate), test_*.py, hardware/
docs/                 user and developer docs; dev/refactor-2026-10/ is the refactor record
pyproject.toml        dependencies (qick pin), ruff and pytest configuration
```

## Tests and what each family proves

From the repo root with `.venv` active (`PYTHONUTF8=1` on a Windows console). No hardware needed.

```
python -m compileall -q qicklab devices runners tests
ruff check --select F qicklab runners tests devices      # the lint gate; ruff format what you touch
python -m pytest tests/test_imports.py tests/test_layering.py tests/test_program_timing.py
python -m pytest tests                                   # everything, incl. the golden (~14 min)
python -m pytest tests/regression                        # golden only, both drivers (~30 min on a 16 GB PC; ~15 min per driver with REGRESSION_DRIVERS=qicklab or =plan)
REGRESSION_LABELS=RunT1 REGRESSION_VARIANTS=A python -m pytest tests/regression
python docs/dev/refactor-2026-10/tools/diff_labels.py RunT1 --variants A   # leaf diff vs golden
python scripts/gen_docs.py --check                       # generated docs up to date?
```

- `tests/regression/`: `golden_cstq03.json` fingerprints, per run label and synthetic board (A,
  B), every tProc program, cfg dict, yoko write and saved-data digest. `driver_qicklab.py` replays
  the labels through the legacy call shapes (`build_context`, `run_*`) and is the only writer;
  `driver_plan.py` replays them through `Session` + PLAN and only compares. `REGRESSION_UPDATE=1`
  rewrites the golden (only the selected labels / variants). See `tests/regression/README.md`.
- `tests/refactor/`: equivalence gate of the move out of the legacy tree (commit `0f0a51f`).
  `symbol_map.py` maps every legacy top-level statement to its new home; the checker proves the
  bodies identical. A frozen record: change it only with a row the commit justifies.
- `tests/test_program_timing.py`: pinned tProc schedule and readout-window integers, both boards.
- `tests/test_layering.py`: the layering rule below, checked on the source.
- `tests/test_params_registry.py`: every cfg key, recipe / group keyword and device field is in
  `qicklab/core/params.py`, cross-checked against the code and the golden.
- `tests/test_gen_docs.py`: `scripts/gen_docs.py` is idempotent on the committed docs; rerun it
  after changing the registry, a recipe, a group or the device model.
- `tests/test_agent_docs.py`: CLAUDE.md = AGENTS.md below line 1; paths quoted here and in README exist.
- the other `tests/test_*.py`: unit tests (fits, analysis, recipes, session, device, save formats);
  `tests/hardware/` holds hardware-in-the-loop scripts, run by hand on the lab network only.

## Rules

- The golden stays byte-identical. A commit that changes it justifies every changed leaf class in
  its message (`docs/dev/refactor-2026-10/tools/classify_golden.py` lists them). Never edit the
  golden or `tests/regression/fixtures/` by hand; set `REGRESSION_UPDATE` only in such a commit.
- Bug fixes are separate commits, one bug each, never mixed with a refactor.
- Experiment class names, cfg key names (`Read_Indeces`, `qubit_gain`, ...) and data paths
  (`outerFolder + path`, timestamp formats) stay unchanged; `build_context` / `run_*` keep working.
- `qick==0.2.334` exactly: the golden stores `qick.get_version()`; never regenerate it on another.
- 16 GB PC: one golden capture at a time (pytest of the regression tests, a driver, diff_labels).
- No hardware access at import time.
- No AI attribution trailers in commit messages (no Co-Authored-By, no session link): 2026-10-15.

## Layering

`hardware < core < analysis < experiments < runs < twpa`: a module imports only its own layer or a
lower one. `analysis` never imports qick; no function-local project imports; `qicklab/__init__.py`
is empty; device files import only `qicklab.core.device`. Enforced by `tests/test_layering.py`.

## Running a session

`runners/CSTQ03_session.py` builds `SESSION = Session(DEVICE, qubit_readout=..., qubit_pulse=...,
bias_v=...)`, a `STEP` dict of recipes and `PLAN = [...]`. `run(SESSION, PLAN)` connects (RFSoC over
Pyro4, charge yoko), validates the device against the board and runs the steps in order.
`run(SESSION, plan, dry_run=True)` (`--dry-run`) compiles every program against the fakes in
`qicklab/core/fakes.py`, saves to a temp folder and plays nothing. Dry-run a short plan: the
committed PLAN (10^6-shot `undriven_single_shot`, `repeat=10000`) takes ~12 min to hit the guard.
Guides: `docs/running_a_session.md`, `docs/parameters.md` (every knob, units, defaults).

## Adding a device

Copy `devices/CSTQ03.py` to `devices/<NAME>.py` (one `DEVICE`) and the session runner to
`runners/<NAME>_session.py`, then dry-run a plan. Measured values are recorded with
`qicklab.core.io.record_calibration` (appends a line to the qubit's `calibrations.jsonl` and prints
a paste-ready `Qubit(...)`). At the end of a cooldown, copy the file into `devices/archive/` before
editing it. Guide: `docs/adding_a_device.md`.

## Physics conventions to preserve

- Register values come from the QICK helpers (`freq2reg`, `us2cycles`, `deg2reg`), never by hand.
- Gaussian envelopes are 4 sigma long (`add_gauss(..., length=4 * sigma)`, in cycles).
- The resonator tone covers the ADC window, `length = adc_trig_offset + readout_length`
  (`qicklab.core.readout.cover_readout_window`); see `docs/concepts/readout_window.md`.
- Symmetric Modified Ramsey (`symmetric_ramsey=True`) drives midway between the parity branches,
  at f_ge - df/2, f_ge the UPPER branch. `R.modified_ramsey` raises without `f_upper_mhz` (in
  `ParityParams`) or `f_ge=`; legacy `run_modified_ramsey` still defaults f_ge to the qubit centre.
- Units: MHz, us, DAC units 0..32767 unless noted (`docs/concepts/timing_and_units.md`).

## History and branch state

- `docs/dev/refactor-2026-10/`: `HANDOFF.md` (commit log, decisions), `design.md` (spec), audits
  in `docs/dev/refactor-2026-10/audit/`, review findings in `docs/dev/refactor-2026-10/review/findings.json`.
- Branch `qicklab_refactor` (from `bfc_code` at `0f0a51f`), to be fast-forwarded into `bfc_code`.
  `main` is the lab's older tree (none of it is here); legacy code: `git show 0f0a51f:<path>`.
