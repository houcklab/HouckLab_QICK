"""Running a sequence on the RFSoC off the GUI thread.

The worker takes a copy of the sequence, so editing during a run changes nothing in it.
Each point is written to the run's .h5 as soon as it is measured (runner/save.py) and then
sent to the GUI with the ``point`` signal; the Data tab draws it. The board's own config is
saved with the run and compared with the station's saved copy. A simulated run uses
runner/simulate.py in place of the board. Stop finishes the current point, closes the file
and marks it as stopped.
"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from ..config.snapshot import make_snapshot
from ..runner.experiment import BobExperiment
from ..runner.save import RunWriter, board_config_text, check_board_config, file_name, run_folder


class RunWorker(QThread):
    started_run = pyqtSignal(str)            # the .h5 path, once the file exists
    point = pyqtSignal(int, object)          # sweep index, {key: one value per read-out qubit}
    finished_run = pyqtSignal(str, str)      # status, .h5 path ("" when nothing was saved)
    board_checked = pyqtSignal(str)          # how the board's live config compares with the station's

    def __init__(self, seq, station, calib, folder: str, connect, program_class=None, simulated: bool = False):
        super().__init__()
        self.seq, self.station, self.calib = seq.clone(), station, calib
        self.folder, self.connect, self.program_class = folder, connect, program_class
        self.simulated = simulated
        self.exp = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self.exp is not None:
            self.exp.stop()

    def run(self):
        n = self.seq.settings.n_points()
        try:
            run_folder(self.folder, file_name(self.seq))      # fail on an unwritable folder before connecting
        except Exception as exc:
            self.finished_run.emit(f"not started: cannot save to {self.folder} ({exc})", "")
            return
        try:
            soc, soccfg = self.connect(self.station)
        except Exception as exc:
            self.finished_run.emit(f"not started: could not connect to the RFSoC ({exc})", "")
            return
        if self._stop_requested:
            self.finished_run.emit("not started: stopped before the first point", "")
            return
        board = None if self.simulated else board_config_text(soccfg)
        check = "simulated run: no board" if self.simulated else check_board_config(self.station, board)
        if not self.simulated:
            self.board_checked.emit(check)
        writer = RunWriter(self.folder, self.seq, make_snapshot(self.seq, self.station, self.calib, max_points=1),
                           board_config=board, board_check=check, simulated=self.simulated,
                           station=self.station, calib=self.calib)
        self.started_run.emit(str(writer.path))
        self.exp = BobExperiment(self.seq, self.station, self.calib, soc, soccfg, program_class=self.program_class)
        if self._stop_requested:
            self.exp.stop()
        self.exp.on_resolved(writer.write_resolved)
        self.exp.on_point(writer.write_point)
        self.exp.on_point(lambda k, pt, data: self.point.emit(k, data))
        status = "complete"
        try:
            self.exp.run(snapshot=False)
            if self.exp.stopped and writer.points_done < n:
                status = f"stopped after {writer.points_done} of {n} points"
        except Exception as exc:
            status = f"failed after {writer.points_done} of {n} points: {exc}"
        finally:
            path = writer.close(status)
        self.finished_run.emit(status, str(path))
