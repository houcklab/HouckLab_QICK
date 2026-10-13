# Frozen regression fixtures

`cstq03_legacy_runner.py.txt` is a byte-for-byte copy of
`WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/CSTQ03_BFC.py`
as of commit `0f0a51f` (git blob `94cc049016d9ffb7d27784fcfb5e4e2058f37775`).

**Never edit this file.** It is the ground truth for the parameters, flags and
dispatch order the regression golden was captured with. The driver reads it in
place of the live runner, so the golden keeps meaning the same thing after the
runner is moved, rewritten or deleted by the refactor. If the parameters must
change, that is a new fixture plus a deliberately regenerated golden, not an
edit here.

The `.txt` suffix keeps ruff and pytest from collecting it. The driver drops
its single `from ... import *` line and instead seeds the exec namespace with
the names that star-import would bind from the runs package named by the
driver's `RUNS_PACKAGE` constant (the only thing a post-refactor driver has to
change).

Check it is still intact with:

```
git hash-object tests/regression/fixtures/cstq03_legacy_runner.py.txt
# -> 94cc049016d9ffb7d27784fcfb5e4e2058f37775
```
