"""Export a sequence as a runnable Python script.

The script holds the experiment's inputs in readable form and calls Bob to build and run it:

* the sequence's blocks, as saved by Bob
* the experiment settings (reps, rounds, relax delay, sweep axes), editable at the top
* only the calibration values the sequence reads, copied from qubit_parameters.json at
  export time, so the script reproduces the same experiment after the file changes

The station is loaded by name when the script runs, so corrections made at the lab (channel
delays, drive offset, the hardware_verified flag) apply to every exported script.

The exporter checks its own output: the frozen calibration must give the same compiled
program as the full file before anything is written.
"""
from __future__ import annotations

import datetime
import textwrap
from pathlib import Path

import numpy as np

from .. import __version__
from ..compiler.tlq_backend import compile_sequence
from ..config.calib_drift import used_values
from ..config.calibration import CalibrationStore
from ..config.station import Station
from ..config.summary import summarize
from ..core.sequence import Sequence
from .script import hardware_ready


class ExportError(Exception):
    pass


def frozen_calibration(used: dict) -> dict:
    """Nested dict rebuilt from flattened leaf paths, e.g. {"a/b/c": 1} -> {"a": {"b": {"c": 1}}}."""
    out: dict = {}
    for path, value in used.items():
        node = out
        keys = path.split("/")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
    return out


def _same_program(a, b) -> bool:
    return (a is not None and b is not None and a.ff.shape == b.ff.shape and np.allclose(a.ff, b.ff)
            and [(d.qubit, d.t_us, d.freq_mhz, d.gain) for d in a.drives]
            == [(d.qubit, d.t_us, d.freq_mhz, d.gain) for d in b.drives])


def py_literal(obj, indent: int = 0, width: int = 100) -> str:
    """Python source for plain data (dicts, lists, numbers, strings), one item per line when long."""
    flat = repr(obj)
    if len(flat) + indent <= width or not isinstance(obj, (dict, list, tuple)) or not obj:
        return flat
    pad, inner = " " * indent, " " * (indent + 4)
    if isinstance(obj, dict):
        items = [f"{inner}{k!r}: {py_literal(v, indent + 4, width)}," for k, v in obj.items()]
        return "{\n" + "\n".join(items) + f"\n{pad}}}"
    open_, close = ("[", "]") if isinstance(obj, list) else ("(", ")")
    items = [f"{inner}{py_literal(v, indent + 4, width)}," for v in obj]
    return open_ + "\n" + "\n".join(items) + f"\n{pad}{close}"


def script_text(seq: Sequence, station: Station, calib: CalibrationStore, source: str = "",
                filename: str = "this_file.py") -> str:
    """The exported script as a string. Raises ExportError if the sequence does not compile."""
    compiled, res, problems = compile_sequence(seq, station, calib)
    errors = [str(p) for p in problems if p.level == "error"]
    if compiled is None or errors:
        raise ExportError("The sequence has errors; fix them before exporting:\n  " + "\n  ".join(errors or
                          ["it does not compile"]))
    frozen = frozen_calibration(used_values(res))
    check, _, _ = compile_sequence(seq, station, CalibrationStore(frozen, calib.path, calib.sha256))
    if not _same_program(compiled, check):
        raise ExportError("Internal error: the frozen calibration does not reproduce the program.")

    s = seq.settings
    blocks = {k: v for k, v in seq.to_dict().items() if k not in ("settings", "calibration", "summary")}
    files = _absolute_waveform_files(blocks)
    sweeps = {a.name: (a.start, a.stop, a.points, a.unit) for a in s.sweeps}
    reasons = hardware_ready(station)
    status = ("    The station is marked as verified at the lab." if not reasons else
              "    Not yet ready for --run (checked at export; --run checks again):\n" +
              "\n".join(_wrap(f"- {r}.", 88, "      ", "    ") for r in reasons))
    if files:
        status += "\n    Plays waveform files from disk; keep them where they are:\n" + \
                  "\n".join(f"      {f}" for f in files)
    summary = summarize(seq, res, station.n_channels)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    name = Path(source).name if source else "(unsaved sequence)"
    return TEMPLATE.format(
        title=seq.name, version=__version__, stamp=stamp, source=name,
        summary=_wrap(summary, 92), status=status, station=station.name, filename=filename,
        calib_path=Path(calib.path).name if calib.path else "(none)", sha=(calib.sha256 or "")[:12],
        reps=int(s.reps), rounds=int(s.rounds), relax=repr(s.relax_delay_us), save_folder=repr(s.save_folder or ""),
        sweeps=py_literal(sweeps), sequence=py_literal(blocks), calibration=py_literal(frozen),
        calib_full_path=repr(calib.path or ""), calib_sha=repr(calib.sha256 or ""),
        n_points=s.n_points(),
    )


def _absolute_waveform_files(blocks: dict) -> list:
    """Rewrite relative waveform-file paths (Dynamics, mode = file) as absolute, in place, so the script
    finds them from any folder. Relative paths are resolved the way Bob did when it compiled: from the
    current folder. Returns the paths."""
    files = []
    for b in blocks.get("blocks", []):
        src = b.get("fields", {}).get("waveform_file")
        mode = b.get("fields", {}).get("mode", {}).get("value")
        if mode == "file" and isinstance(src, dict) and src.get("value"):
            path = str(Path(src["value"]).expanduser().resolve())
            src["value"] = path
            files.append(path)
    return files


def export_python(seq: Sequence, station: Station, calib: CalibrationStore, path, source: str = "") -> Path:
    path = Path(path)
    path.write_text(script_text(seq, station, calib, source, filename=path.name), encoding="utf-8")
    return path


def _wrap(text: str, width: int, indent: str = "", first: str = "") -> str:
    return "\n".join(textwrap.wrap(text, width, initial_indent=first, subsequent_indent=indent))


TEMPLATE = '''"""{title}: exported from Bob {version} on {stamp} (from {source}).

{summary}

HOW TO RUN
    Keep this file anywhere inside WorkingProjects/triangle_lattice_quench/ (it finds the Bob
    folder in its own folder or a parent), or set BOB_PATH to the folder that contains Bob/.
    Use the bob_qsim environment (see Bob/README.md).

    Check only (no hardware; compiles all {n_points} sweep points):
        python {filename}
    Also plot the flux and drives at sweep point 0:
        python {filename} --plot 0
    Run on the RFSoC; each point is saved as it is measured and plotted live:
        python {filename} --run
    The same run on a simulated board (no RFSoC, made-up data, saved under _simulated/):
        python {filename} --run --simulate
    Plot a saved run again:
        python {filename} --show-data <run>_data.h5

    Data goes to SAVE_FOLDER below, or the station's outer_folder when it is blank, or --out FOLDER.
    Add --no-plot to run without the live figure.

STATUS
{status}

WHAT IS IN THIS FILE
    REPS ... SAVE_FOLDER   experiment settings; safe to edit
    SEQUENCE          the blocks, exactly as Bob saved them; edit in Bob and re-export
    CALIBRATION       the calibration values this experiment reads, frozen from {calib_path}
                      (sha256 {sha}...) at export; later changes to that file do not apply here
    The station ({station}) is read from Bob/library/stations when the script runs.
"""
import argparse
import os
import sys
from pathlib import Path


def _add_bob_to_path():
    here = Path(__file__).resolve().parent
    for folder in [os.environ.get("BOB_PATH"), Path.cwd(), here, *here.parents]:
        if folder and (Path(folder) / "Bob" / "__init__.py").exists():
            sys.path.insert(0, str(folder))
            return
    sys.exit("Cannot find the Bob folder. Keep this script inside triangle_lattice_quench/, "
             "or set BOB_PATH to the folder that contains Bob/.")


# ---------------------------------------------------------------------------- settings (editable)
REPS = {reps}
ROUNDS = {rounds}
RELAX_DELAY_US = {relax}    # None = the station default
# sweep axes, outermost first: name: (start, stop, points, unit)
SWEEPS = {sweeps}
SAVE_FOLDER = {save_folder}    # "" = the station's outer_folder

# ---------------------------------------------------------------------------- frozen inputs
STATION = "{station}"
CALIBRATION_SOURCE = {calib_full_path}
CALIBRATION_SHA256 = {calib_sha}

SEQUENCE = {sequence}

CALIBRATION = {calibration}


def build():
    """The sequence, station and calibration this script describes."""
    from Bob.config.calibration import CalibrationStore
    from Bob.config.settings import ExperimentSettings, SweepAxis
    from Bob.config.station import Station
    from Bob.core.sequence import Sequence
    seq = Sequence.from_dict(SEQUENCE)
    seq.settings = ExperimentSettings(reps=REPS, rounds=ROUNDS, relax_delay_us=RELAX_DELAY_US,
                                      sweeps=[SweepAxis(n, *v) for n, v in SWEEPS.items()],
                                      save_folder=SAVE_FOLDER)
    return seq, Station.load(STATION), CalibrationStore(CALIBRATION, CALIBRATION_SOURCE, CALIBRATION_SHA256)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plot", type=int, metavar="POINT", help="plot the flux and drives at this sweep point")
    parser.add_argument("--run", action="store_true", help="run on the RFSoC and save the data")
    parser.add_argument("--out", help="folder to save under (default: SAVE_FOLDER, else the station's outer_folder)")
    parser.add_argument("--no-plot", action="store_true", help="run without the live plot")
    parser.add_argument("--simulate", action="store_true",
                        help="with --run: use the simulated board (no RFSoC, made-up data)")
    parser.add_argument("--show-data", metavar="FILE", help="plot a saved run (its _data.h5 file)")
    parser.add_argument("--i-know-it-is-unverified", action="store_true",
                        help="run even though the station is not marked as verified at the lab")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # Windows consoles: print µ and π instead of failing
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    _add_bob_to_path()
    from Bob.runner import script
    if args.show_data:
        script.show_data(args.show_data)
        return 0
    seq, station, calib = build()
    if args.run:
        script.run(seq, station, calib, out_folder=args.out, override=args.i_know_it_is_unverified,
                   live_plot=not args.no_plot, simulate=args.simulate)
        return 0
    ok = script.check(seq, station, calib)
    if args.plot is not None:
        script.plot(seq, station, calib, args.plot)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
'''
