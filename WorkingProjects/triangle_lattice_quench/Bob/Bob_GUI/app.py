"""Launch Bob:  python -m Bob.Bob_GUI [sequence.json]

Run from the folder that contains Bob/ (WorkingProjects/triangle_lattice_quench/).
"""
from __future__ import annotations

import sys
from pathlib import Path


def install_error_handler(parent) -> None:
    """Report unexpected errors in a dialog and keep Bob open.

    By default PyQt5 ends the program when Python code called from Qt raises, which would lose
    unsaved work. The traceback still goes to the terminal; repeats of the same error within a
    few seconds (e.g. from repainting) are not shown again.
    """
    import time
    import traceback
    from PyQt5.QtWidgets import QMessageBox
    last = {"text": None, "t": 0.0}

    def handler(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(text)
        now = time.monotonic()
        if text == last["text"] and now - last["t"] < 5:
            return
        last.update(text=text, t=now)
        box = QMessageBox(QMessageBox.Critical, "Unexpected error",
                          f"Bob hit an unexpected error and kept running:\n\n{exc_type.__name__}: {exc}\n\n"
                          "Your sequence is still open. To be safe, save it under a new name (Save as). "
                          "Please report this with the details below.", QMessageBox.Ok, parent)
        box.setDetailedText(text)
        box.exec_()

    sys.excepthook = handler


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName("Bob")
    app.setOrganizationName("HouckLab")
    from . import style
    app.setFont(style.ui_font(13))
    from .main_window import MainWindow
    win = MainWindow()
    install_error_handler(win)
    if len(argv) > 1 and Path(argv[1]).exists():
        win.bob.open_path(argv[1])
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
