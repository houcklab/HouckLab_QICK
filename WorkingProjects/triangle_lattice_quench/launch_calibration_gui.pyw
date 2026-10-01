"""Desktop-shortcut launcher for the calibration GUI.

Shortcut target:
    <venv>\\Scripts\\pythonw.exe "<abs path to this file>"

Two things this buys over ``pythonw -m triangle_lattice_quench...``:

  * The import root is derived from ``__file__``, so the shortcut's "Start in"
    field is irrelevant — launching from anywhere works.
  * ``pythonw`` has no console, so a failure is otherwise completely silent.
    Anything that goes wrong is written to a log next to this file AND shown
    in a Windows dialog.
"""
import sys
import traceback
from pathlib import Path

# WorkingProjects/ is the import root (this file lives one level below it).
WORKING_PROJECTS = Path(__file__).resolve().parents[1]
if str(WORKING_PROJECTS) not in sys.path:
    sys.path.insert(0, str(WORKING_PROJECTS))

LOG_PATH = Path(__file__).resolve().with_name("calibration_gui_error.log")


def _report(what: str, detail: str) -> None:
    """Write the failure to LOG_PATH, then show it in a dialog.

    ctypes is used rather than a Qt dialog so this still works when the
    failure IS PyQt (or anything else) failing to import. Log first, so a
    dialog that cannot be shown does not lose the traceback.
    """
    body = (
        f"{what}\n\n"
        f"interpreter : {sys.executable}\n"
        f"import root : {WORKING_PROJECTS}\n"
        f"log file    : {LOG_PATH}\n\n"
        f"{detail}"
    )
    try:
        LOG_PATH.write_text(body, encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes
        # MB_ICONERROR; truncated because MessageBoxW clips very long strings.
        ctypes.windll.user32.MessageBoxW(
            None, body[-1800:], "Calibration GUI failed to start", 0x10
        )
    except Exception:
        pass


def main() -> int:
    try:
        from triangle_lattice_quench.Run_Experiments.calibration_gui.main_window import (
            main as gui_main,
        )
    except Exception:
        _report("Could not import the calibration GUI.", traceback.format_exc())
        return 1

    try:
        gui_main()
    except Exception:
        _report("The GUI crashed after starting.", traceback.format_exc())
        return 1

    # Clean run: drop a stale log so the file never misleads on the next launch.
    try:
        LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
