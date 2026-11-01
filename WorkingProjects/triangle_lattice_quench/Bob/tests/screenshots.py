"""Screenshots of Bob on this computer, to check how it looks on each OS.

    python -m Bob.tests.screenshots <folder>        (from the folder that contains Bob/)

Opens the Mott quench template offscreen and saves: the main window, the Data tab after a
simulated run, and the Experiment tab. GitHub runs this on macOS, Windows and Linux and keeps
the pictures with each run (Actions tab -> the run -> Artifacts). Nothing connects to an RFSoC.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main(out: str) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("BOB_SETTINGS_FILE", str(Path(tempfile.mkdtemp()) / "bob_settings.ini"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv[:1])
    from Bob.Bob_GUI import style
    from Bob.Bob_GUI.app_settings import app_settings
    from Bob.Bob_GUI.main_window import MainWindow
    from Bob.config.settings import SweepAxis
    from Bob.library import build_library
    from Bob.tests.conftest import FIXTURE_CALIB
    app.setFont(style.ui_font(13))
    app_settings().setValue("calibration_path", str(FIXTURE_CALIB))
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    w = MainWindow()
    w.resize(1500, 920)
    w.show()
    bob = w.bob
    bob.open_path(str(build_library.HERE / "templates" / "mott_quench.json"), as_template=True)
    st = type(bob.ctl.seq.settings).from_dict(bob.ctl.seq.settings.to_dict())
    st.sweeps = [SweepAxis("t_dyn", 0.0, 2.3251, 61, "µs")]
    st.reps, st.save_folder = 200, tempfile.mkdtemp()
    bob.ctl.set_settings(st)
    bob.ctl.select(bob.ctl.seq.segments[1].id)
    bob.ctl.refresh_now()

    def grab(name):
        app.processEvents()
        w.grab().save(str(out_dir / f"{tag}_{name}.png"))

    def main_window():
        grab("main")
        bob.topbar.sim_btn.setChecked(True)
        bob.run()
        QTimer.singleShot(200, wait)

    def wait():
        if bob._run is not None:
            QTimer.singleShot(100, wait)
            return
        grab("data_tab")
        bob.dock.setCurrentWidget(bob.settings_scroll)
        QTimer.singleShot(200, lambda: (grab("experiment_tab"), app.quit()))

    QTimer.singleShot(500, main_window)
    app.exec_()
    print(f"saved {len(list(out_dir.glob(tag + '_*.png')))} screenshots to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "bob_screenshots"))
