
import sys
import time

import matplotlib.pyplot as plt


def progress_counter(iteration, total, progress_bar=True, percent=True, start_time=None):
    current_percent = (iteration + 1) / total * 100
    if iteration <= 0:
        progress_counter._last_pct = -1

    progress = "Progress: "
    if progress_bar:
        bar = "#" * int(current_percent / 2)
        progress += "[" + bar + " " * (50 - len(bar)) + "] "
    if percent:
        progress += f"{current_percent:.1f}% (n={iteration + 1}/{total})"
    if start_time is not None:
        progress += f" --> elapsed time: {time.time() - start_time:.2f}s"

    is_tty = False
    try:
        is_tty = bool(sys.stdout.isatty())
    except Exception:
        is_tty = False

    if is_tty:
        print(progress, end="\r", flush=True)
        if current_percent >= 100:
            print("", flush=True)
    else:
        pct = int(current_percent)
        if pct != progress_counter._last_pct or current_percent >= 100:
            progress_counter._last_pct = pct
            print(progress, flush=True)


progress_counter._last_pct = -1


class LiveFigure:

    def __init__(self, num=None, figsize=(9, 7), title=""):
        self.fig = plt.figure(num=num, figsize=figsize)
        if title:
            self.fig.suptitle(title)
        self._open = True
        try:
            self.fig.canvas.mpl_connect("close_event", self._on_close)
            plt.show(block=False)
        except Exception:
            pass

    def _on_close(self, _event):
        print("Execution stopped by user!")
        self._open = False

    @property
    def is_open(self):
        return self._open

    def refresh(self, pause=0.05):
        try:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
            plt.pause(pause)
        except Exception:
            self._open = False

    def savefig(self, path):
        self.fig.savefig(path)

    def close(self):
        try:
            plt.close(self.fig)
        except Exception:
            pass
