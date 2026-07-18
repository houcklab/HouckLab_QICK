"""
qualang_tools-compatible progress reporting + live-plot helpers.

``progress_counter`` reproduces qualang_tools.results.progress_counter's output
(in-place '\\r' line: 'Progress: [#####...     ] 42.0% (elapsed time: 12.3s)') so
the console feel matches the OPX workflow.

``LiveFigure`` is the QICK analog of qualang_tools.plot.interrupt_on_close: a
live-updating matplotlib figure whose CLOSE event requests the acquisition loop
to stop -- experiments check ``.is_open`` each sweep iteration and break when the
operator closes the window (QUA: closing the figure halted the job).
"""

import time

import matplotlib.pyplot as plt


def progress_counter(iteration, total, progress_bar=True, percent=True, start_time=None):
    """VERBATIM port of qualang_tools.results.progress_counter (v0.18.1):
    'Progress: [###...   ] 12.3% (n=12/100) --> elapsed time: 45.67s' with
    end='\\r', plus a bare newline once the percent hits exactly 100."""
    current_percent = (iteration + 1) / total * 100

    progress = "Progress: "
    if progress_bar:
        bar = "#" * int(current_percent / 2)
        progress += "[" + bar + " " * (50 - len(bar)) + "] "
    if percent:
        progress += f"{current_percent:.1f}% (n={iteration + 1}/{total})"
    if start_time is not None:
        progress += f" --> elapsed time: {time.time() - start_time:.2f}s"

    print(progress, end="\r", flush=True)      # flush so PyCharm/piped consoles render the \r line
    if current_percent >= 100:
        print("", flush=True)


class LiveFigure:
    """Live-updating figure with interrupt-on-close semantics.

    Usage in an acquisition loop:
        live = LiveFigure(figsize=(9, 7)) if live_plot else None
        for i, ... in enumerate(...):
            ...acquire row...
            if live is not None:
                ...redraw artists on live.fig axes...
                live.refresh()
                if not live.is_open:
                    print("Live figure closed -- interrupting the sweep.")
                    break
    """

    def __init__(self, num=None, figsize=(9, 7), title=""):
        self.fig = plt.figure(num=num, figsize=figsize)
        if title:
            self.fig.suptitle(title)
        self._open = True
        try:
            self.fig.canvas.mpl_connect("close_event", self._on_close)
            plt.show(block=False)
        except Exception:
            # non-interactive backend (Agg): behave as an ordinary figure
            pass

    def _on_close(self, _event):
        # qualang_tools.plot.interrupt_on_close prints exactly this on close
        print("Execution stopped by user!")
        self._open = False

    @property
    def is_open(self):
        return self._open

    def refresh(self, pause=0.05):
        """Push pending draws to the screen (no-op on Agg)."""
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
