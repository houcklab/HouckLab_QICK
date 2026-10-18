# devices/archive

Device files of finished cooldowns, `<NAME>_<cooldown>.py`, each holding the `DEVICE` that
cooldown used. They are the record of what each cooldown ran with: never edited, never deleted,
never imported by sessions. How to archive a device: [docs/adding_a_device.md](../../docs/adding_a_device.md#5-end-of-cooldown-archive).

| file | what |
|---|---|
| `CSTQ03_v2b.py` | CSTQ03's earlier "v2b nu cell" parameter set (no date recorded, so `cooldown="v2b"`), the unused `Qubit_Parameters_v2b` table of the legacy runner `runners/CSTQ03_BFC.py` (deleted in phase 5b); `DEVICE.legacy_parameters()` reproduces that table. History: [docs/devices/CSTQ03.md](../../docs/devices/CSTQ03.md#archived-v2b-nu-cell-parameter-set). |

`__init__.py` only makes the folder importable for the smoke test in `tests/test_device.py`; an
archive file named `<NAME>_<YYYY-MM-DD>.py` is a record, not a module to import.
