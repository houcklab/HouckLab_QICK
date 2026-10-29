# archive

Code that is no longer used by any measurement but is kept for reference. Nothing here is part
of the `qicklab` package: it is not installed, not imported, not linted and not tested, and it
may need edits to run again (imports, paths). Git history keeps the earlier versions too.

| file | what | archived |
|---|---|---|
| `hardware/sc5510a.py` | Pyro5 client for the remote SignalCore SC5510A generators (was `qicklab.hardware.sc5510a`). Server code: `https://github.com/NPdL-SQTeam/sc5510a-py`; it needs Pyro5 and a server PC running `start_nameserver.py` and `start_instrument_server.py` (default host `192.168.0.102`, port 9090, object prefix `SC5510A#`, env `SC5510A_SERVER_HOST`). | 2026-10-29: the TWPA pump is the Windfreak SynthHD only (`qicklab.hardware.synthhd`); no step used the SC5510A. |

To bring a file back, move it into `qicklab/` at its old path, restore its rows in
`tests/refactor/symbol_map.py` to `moved` and its optional dependency in `pyproject.toml`.
