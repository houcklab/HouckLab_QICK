# devices/archive

Device files of finished cooldowns, `<NAME>_<YYYY_MM_DD>.py` (the cooldown start date, with
underscores so the file stays importable), each holding the `DEVICE` that cooldown used. They are
the record of what each cooldown ran with: never edited, never deleted, never imported by live
sessions. The matching session runner, when it is kept, goes to
`runners/archive/<NAME>_<YYYY_MM_DD>_session.py`. How to archive a device:
[docs/adding_a_device.md](../../docs/adding_a_device.md#5-end-of-cooldown-archive).

| file | what |
|---|---|
| `CSTQ03_2026_10_01.py` | CSTQ03 in the 2026-10-01 BFC cooldown (archived 2026-10-29), the values of the legacy runner `runners/CSTQ03_BFC.py` at its deletion. The regression golden (`tests/regression/driver_plan.py`) and the session tests replay with it, so it must stay byte-for-byte as archived. Runner: `runners/archive/CSTQ03_2026_10_01_session.py`. |
| `CSTQ03_v2b.py` | CSTQ03's earlier "v2b nu cell" parameter set (no date recorded, so `cooldown="v2b"`), the unused `Qubit_Parameters_v2b` table of the legacy runner `runners/CSTQ03_BFC.py` (deleted in phase 5b); `DEVICE.legacy_parameters()` reproduces that table. History: [docs/devices/CSTQ03.md](../../docs/devices/CSTQ03.md#archived-v2b-nu-cell-parameter-set). |

`__init__.py` makes the folder importable for the tests (`tests/test_device.py`, the golden
harness); live code under `qicklab/`, `devices/` and `runners/` outside the archive folders never
imports it (`test_no_session_code_imports_the_archive`).
