"""The same Bob on macOS, Windows and Linux: file names, folders, text encodings, look and shortcuts.

GitHub runs the whole suite on all three (.github/workflows/bob-tests.yml); these tests cover
what differs between them and can also be checked from any one of them.
"""
import os
import subprocess
import sys

import pytest

from Bob.core.sequence import Sequence
from Bob.library import build_library
from Bob.runner import save
from Bob.runner.export import export_python
from Bob.tests.test_export import BOB_PARENT

TEMPLATES = build_library.HERE / "templates"


def test_run_file_names_work_on_windows():
    seq = Sequence(name='Q3: T1 / ramsey? <v2> "final".')
    name = save.file_name(seq)
    assert not set(name) & set('<>:"/\\|?*') and not name.endswith((".", " "))
    assert save.file_name(Sequence(name="  ")) == "bob_run"
    assert save.file_name(Sequence(name="Mott quench")) == "Mott_quench"


@pytest.mark.parametrize("folder, system, ok", [
    ("Z:\\QSimMeasurements\\Measurements\\8QV1_Q0V\\", "posix", False),   # the station default, on a Mac
    ("Z:\\QSimMeasurements\\Measurements\\8QV1_Q0V\\", "nt", True),
    ("/Volumes/QSim/Measurements", "posix", True),
    ("/Volumes/QSim/Measurements", "nt", False),
    ("C:/Users/lab/data", "nt", True),
    ("", "posix", False),
])
def test_folders_this_computer_can_use(folder, system, ok):
    assert (save.folder_problem(folder, system) is None) == ok


@pytest.mark.skipif(os.name == "nt", reason="a drive path is valid on Windows")
def test_a_windows_save_folder_is_refused_clearly_on_mac_and_linux(tmp_path):
    with pytest.raises(OSError, match="Windows drive path"):
        save.run_folder("Z:\\QSimMeasurements\\", "x")
    assert not any(tmp_path.iterdir()) and not os.path.exists("Z:\\QSimMeasurements\\")


def test_exported_script_prints_on_a_windows_console(station, calib, tmp_path):
    """π and µ in names and messages must not crash a cp1252 console (Windows' default)."""
    seq = Sequence.load(TEMPLATES / "mott_quench.json")
    seq.name = "π/2 phase sweep, t in µs"
    path = export_python(seq, station, calib, tmp_path / "pi2.py")
    env = dict(os.environ, BOB_PATH=str(BOB_PARENT), PYTHONIOENCODING="cp1252")
    done = subprocess.run([sys.executable, str(path)], capture_output=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr.decode("cp1252", "replace")
    assert b"sweep points compile" in done.stdout


# ================================================================== the GUI
pytest.importorskip("PyQt5")


@pytest.mark.gui
def test_same_look_everywhere(qtbot, isolated_settings):
    from PyQt5.QtGui import QPalette
    from PyQt5.QtWidgets import QApplication, QStyleFactory
    from Bob.Bob_GUI import style
    from Bob.Bob_GUI.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    app = QApplication.instance()
    assert app.property("bob_look") == "Fusion" and "Fusion" in QStyleFactory.keys()
    assert app.palette().color(QPalette.Base).name().upper() == style.COLORS["bg"]
    assert app.palette().color(QPalette.Text).name().upper() == style.COLORS["text"]
    bar = w.statusBar()
    assert bar.height() <= 18 and not bar.isSizeGripEnabled()
    w.close()


@pytest.mark.gui
def test_shortcuts_are_written_the_platform_way(qtbot):
    from PyQt5.QtGui import QKeySequence
    from Bob.Bob_GUI import style
    text = style.shortcut_text("Ctrl+D")
    assert text == QKeySequence("Ctrl+D").toString(QKeySequence.NativeText)
    assert text == ("⌘D" if sys.platform == "darwin" else "Ctrl+D")
