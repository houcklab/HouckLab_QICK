# Refactor equivalence gate (phase 3a)

Phase 3a moves the legacy tree
(`WorkingProjects/QM_Team/qubit_measurements/Client_modules`, frozen at commit
`0f0a51f`) into `qicklab/` without changing behaviour. This folder lets you show that the
move is purely mechanical, symbol by symbol. The regression golden
(`tests/regression`) checks what reaches the hardware. This gate checks the code that
produces it.

| File | Role |
|---|---|
| `symbol_map.py` | Plain data: one `Entry` per top-level statement of each of the 52 legacy files (593 rows), plus `FILE_PHASE` and `LAYOUT_MODULES`. |
| `equivalence.py` | The checker, with a CLI. |
| `test_symbol_map.py` | Invariants of the table. Needs only git, never `qicklab/`. |
| `test_equivalence.py` | Ledger (always), old-vs-new check (once `qicklab/` exists), checker self-test (`slow`). |
| `conftest.py` | `legacy_root`: one temporary `git worktree` of `0f0a51f` per session. |

```
python -m tests.refactor.equivalence --phase 3a-i     # after commit 4 (whole-file moves)
python -m tests.refactor.equivalence --phase 3a-ii    # after commit 5 (splits): everything
python -m tests.refactor.equivalence                  # check whatever exists, skip the rest
python -m tests.refactor.equivalence --ledger-only    # table vs legacy tree only
python -m tests.refactor.equivalence --self-test      # validate the checker itself (~40 s)
python -m pytest tests/refactor -q                    # all of the above as tests
REFACTOR_PHASE=3a-ii python -m pytest tests/refactor  # make the pytest gate strict
```

Options: `-v` also prints warnings and skips. `--json out.json` dumps every finding.
`--static` skips imports. `--legacy-root DIR` reuses an existing checkout instead of
making a worktree. The command exits non-zero on any `FAIL`.

## The table (`symbol_map.py`)

`Entry(old_module, old_qualname, new_module, new_name, kind, phase, note, final_module, final_name)`

- **old_qualname** is the statement key from `equivalence.statement_keys`:
  - the name, for a def, class or single assignment
  - `a,b` for a tuple assignment
  - `<main>` for `if __name__ == "__main__"`
  - `<if:TEST>` and `<expr:CALL>` for other module-level statements, for example
    `<expr:matplotlib.use('Agg')>`, `<expr:os.add_dll_directory(os.getcwd())>`, and
    the runner's `<if:RunT1>`

  `<module>` stands for a file's docstring and imports. 3a rewrites those (explicit
  imports, no star). It does not move them.
- **new_module / new_name**: where the statement lives *after 3a*, with a verbatim body.
- **kind**:
  - `moved` and `renamed`: 3a moves it. `renamed` changes only the top-level name.
  - `deleted`: 3b removes it. The note cites the audit.
  - `merged`: the note gives a `proof:`.
    - In phase 3a-*, this is an AST-identical duplicate that a file merge forces onto
      one name. Keep one copy. `test_symbol_map` re-checks the proof.
    - In 3b, it stays verbatim at `new_*` through 3a, and a 3b commit merges it into
      `final_*`.
  - `main_to_test`: an inline self-test or the offline test script. It becomes a pytest
    module, so its body may change and the AST check skips it.
- **phase**:
  - `3a-i`: a whole file goes to one module (commit 4).
  - `3a-ii`: utils, analyze_*, mAutoCoherence, mT2R, mUndrivenSingleShot and the
    runs/basic, calibration, coherence, singleshot, charge_parity and context files are
    split (commit 5).
  - `3b`: deletions and merges.

  `FILE_PHASE` gives the move phase of each file.
- **final_***: where the symbol ends up after 3b, if that differs. Examples:
  `Amplitude_IQ` becomes `analysis.iq.min_q_range_phase` and `setatten` becomes
  `hardware.attenuator.set_attenuation`. 3a does not need these.

Collisions resolved with distinct names (all `renamed` in 3a unless stated):

| legacy | 3a name | why |
|---|---|---|
| `mAmplitudeRabiFF_noUpdate.AmplitudeRabiFFProg` | `experiments.rabi.AmplitudeRabiPointProg` | two `AmplitudeRabiFFProg` in `rabi.py` |
| `mT1_SS.T1Program` | `experiments.t1_single_shot.T1SingleShotProgram` | vs `mT1FF.T1Program` |
| `utils.fit_rabi_cosine` | `analysis.fitting.fit_rabi_cosine_gridsearch` | the local P/2 `fit_rabi_cosine` (rabi.py) is the one actually used |
| `mUndrivenSingleShot.rate_vs_bin_size` / `autocorrelation_rate` | `analysis.rates.rate_vs_bin_size_us` / `autocorrelation_rate_us` | vs MRP `rate_vs_bin_size` (seconds) |
| `hist_analysis_opt.hist_process` | `analysis.readout.hist_process_per_class` | `merged` in 3b into `hist_process(normalize="per_class")` |
| `mAutoCoherence.run_auto_coherence` | `runs.auto_coherence._run_auto_coherence` | the `runs/coherence` wrapper of the same name lands in the same module (it already imports it as `_run_auto_coherence`) |
| `charge_parity._charge_sweep_voltages` | `runs.charge_sweep.charge_sweep_voltages` | the design names it as public |
| `makeProxy` / `MakeFile` / `NpEncoder` / `BaseConfig` / `FF_Qubits` | `make_proxy` / `H5File` / `NumpyJSONEncoder` / `BASE_CONFIG` / `FF_QUBITS` | design names; keep the old names as aliases (`makeProxy = make_proxy`) |
| `mAmplitudeRabiFF_noUpdate.cos_func`, `.fit_rabi_cosine` | `experiments.rabi.cos_func`, `.fit_rabi_cosine` | `merged` (3a): AST-identical to the mAmplitudeRabiFF copies |

Placements forced by import cycles (deviations from the design text):

- `transition_matrix_2state` goes to `analysis.rates`, not `analysis.hmm`, because
  `fit_two_state_hmm` calls `simulate_telegraph_trace`, which calls it.
- `runs.sweet_spot` holds only `find_sweet_spot`. `_stage_sweet_spot_search` and
  `_choose_next_voltage` stay in `runs.auto_coherence`, because `find_sweet_spot` needs
  `AUTO_COHERENCE_PARAMS` and `run_auto_coherence` needs the stage.
- The design's `analysis/telegraph.py` is split as the layout lists it, into
  `analysis.hmm`, `analysis.rates`, `analysis.dwell` and `analysis.undriven`.

## What each check proves

**(a) Legacy source of truth.** `0f0a51f` is checked out into a temporary
`git worktree`, which is always removed afterwards. It is imported from its own
`sys.path` entry, in a `sys.modules` session that is restored afterwards. The new tree is
then imported in a second session. Third-party modules (qick, numpy, ...) are shared, so
object identity across the two sides means something. The checker never imports these,
and checks them statically instead:
- the legacy runner (`CSTQ03_BFC.py` runs a session at import)
- `runners/*`
- `tests/*`
- anything that fails to import (reported as `WARN [import]`)

**(b) AST equality.** For every `moved` or `renamed` entry, and every
`merged`/`deleted` entry that is still present, the checker compares the old and new
statement after:
- removing imports (anywhere, including function-local imports) and docstrings
  (comments are not in the AST);
- respelling every global name that refers to a project symbol as that symbol's *new*
  name, on both sides. Aliases resolve to their target, so `makeProxy()` (alias) and
  `make_proxy()` compare equal. Which names are global comes from `symtable`, so a
  local that happens to share a name is never touched.

Everything else must match exactly: constants, strings (including cfg keys such as
`"Read_Indeces"`), attribute names, keyword names, default arguments and operator order.
Passing proves that the body, signature and decorators are textually the legacy ones,
modulo the declared renames.

**(c) Binding check.** Equal ASTs are not enough. The same text can mean something else
when a name binds to a different object. The legacy code is full of star imports, so for
every compared symbol the checker resolves each free global name it loads on both sides.
This covers class bodies, methods, nested functions, lambdas, comprehensions, default
values and decorators. Each name resolves at runtime from the module's globals, or from
the static namespace model for static-only modules. The two sides must have the same
origin:
- **project code:** the same canonical location, mapped through the table, and the same
  normalised AST hash;
- **stdlib / third-party:** the same object (identity) or the same
  `__module__.__qualname__`;
- **builtins:** identity;
- **missing on both sides:** equal, so a latent `NameError` is preserved and not
  silently fixed.

This catches the hazards the audit found:
- `mAmplitudeRabiFF.AmplitudeRabiFF` must call the local P/2 `fit_rabi_cosine`, not the
  utils grid-search one;
- `runs/singleshot.run_active_reset_verify` uses `datetime.now()` with `datetime` bound to
  the *class* (leaked from `utils`' `from datetime import datetime`);
- `runs/coherence` gets `time`, and `mSpecSliceFF` gets `curve_fit`, only through
  `utils`' star export.

Module dunders (`__file__`, `__name__`, ...) compare by role. If a symbol that uses
`__file__` changes directory, you get a `WARN`. `verify_ModifiedRamsey_timing._REPO_ROOT`
does this: its `parents[N]` must be adjusted when it moves to `tests/hardware/`.

**(d) Ledger.** Every top-level statement of every legacy module has exactly one
entry, there are no stale entries, and every file is covered. `test_symbol_map` adds:
- no two symbols share a 3a destination or a final destination unless all but one are
  `merged` with a proof;
- every destination is in `LAYOUT_MODULES` (the design layout plus the transitional
  runner and the test destinations);
- every 3a merge proof `AST-identical to X` holds on the legacy tree.

**Structure.** A missing new module is a `FAIL` under `--phase`. Without `--phase` it is
a `SKIP`. A missing symbol is a `FAIL`. A 3b-`deleted`/`merged` symbol that is already
absent is a `WARN` in 3a. A name bound twice at top level of a new module is a `FAIL`,
because the earlier binding is dead at runtime and would hide behind a passing AST
comparison.

**Self-test** (`--self-test`, `test_checker_self_test`):
- *identity*: legacy@0f0a51f against a copy of itself (the files leave the working tree
  during 3a). It must pass: 541 AST + 541 bindings.
- *constant*: `ramp_to(step=0.001→0.002)` in a temp copy must fail. It does, with an AST
  failure on `ramp_to` and binding failures in all 5 callers.
- *shadow*: a single appended `from ...utils import fit_rabi_cosine` in mAmplitudeRabiFF
  must fail in the binding check only. It does: exactly `AmplitudeRabiFF`, with 0 AST
  failures.

## How the 3a agent must use it

1. Before starting, run `python -m pytest tests/refactor -q`. It must be green.
2. Write each new module from the table: statements in legacy order, bodies verbatim,
   and only the `renamed` names changed (keep the aliases the notes ask for). Write
   explicit imports that reproduce the legacy binding of every name. The binding check
   tells you when an import binds the wrong thing.
3. Run `python -m tests.refactor.equivalence --phase 3a-i`, then `--phase 3a-ii`. Every
   `FAIL` must be fixed in the new code.
   - `FAIL [ast]` prints a diff of the normalised old/new source.
   - `FAIL [binding]` prints both origins of each differing name.

   Read every `WARN`: import fallbacks, `__file__`, and symbols already deleted.
4. Do not edit `symbol_map.py` to make a failure go away. Only change it for a real
   placement decision, and record the reason in `note`. `test_symbol_map` must stay
   green, and its proof check re-verifies any new 3a merge.
5. 3b and later edit bodies on purpose. Use `--phase 3b` for the structural checks only
   (deleted symbols gone, merge targets present). For behaviour, rely on the golden and
   the adversarial review.

Limits:
- Static resolution, used for the runner, `tests/*` and modules that fail to import,
  models imports, star imports (honouring `__all__`), defs, assignments and simple
  aliases. It does not model dynamic `globals()` tricks.
- The binding check only looks at names a symbol loads.
- Attribute access on project modules (`mod.func`) is compared textually.
