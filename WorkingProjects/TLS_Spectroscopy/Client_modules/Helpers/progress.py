import sys
import time

import matplotlib.pyplot as plt

_RED = "\033[38;2;255;45;45m"
_DIMRED = "\033[38;2;96;18;18m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_FULL = "█"
_PARTIAL = " ▏▎▍▌▋▊▉"
_EMPTY = "─"


def _fmt_time(sec):
    sec = int(max(0, sec))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m{sec % 60:02d}s"
    return f"{sec // 3600}h{(sec % 3600) // 60:02d}m"


def _red_bar(frac, width, tick):
    frac = max(0.0, min(1.0, frac))
    filled = frac * width
    whole = int(filled)
    bar = _FULL * whole
    if whole < width:
        bar += _PARTIAL[int((filled - whole) * 8)]
        bar += _EMPTY * (width - whole - 1)
    spin = _SPIN[tick % len(_SPIN)] if frac < 1.0 else "✔"
    return f"{_RED}{_BOLD}{spin}{_RESET} {_RED}▕{bar}{_RESET}{_DIMRED}▏{_RESET}"


def progress_counter(iteration, total, progress_bar=True, percent=True, start_time=None,
                     label="", width=34):
    total = max(1, int(total))
    n = int(iteration) + 1
    frac = n / total
    if iteration <= 0:
        progress_counter._last_pct = -1
        progress_counter._tick = 0
    progress_counter._tick += 1

    head = f"{label} " if label else ""
    parts = [head + _red_bar(frac, width, progress_counter._tick)] if progress_bar else [head.rstrip()]
    if percent:
        parts.append(f"{_RED}{frac * 100:5.1f}%{_RESET}")
    parts.append(f"({n}/{total})")
    if start_time is not None:
        elapsed = time.time() - start_time
        eta = elapsed * (1 - frac) / frac if frac > 0 else 0.0
        parts.append(f"{_fmt_time(elapsed)} elapsed" + (f" · ETA {_fmt_time(eta)}" if frac < 1.0 else ""))
    line = "  ".join(parts)

    is_tty = False
    try:
        is_tty = bool(sys.stdout.isatty())
    except Exception:
        is_tty = False

    if is_tty:
        sys.stdout.write("\r\033[K" + line)
        sys.stdout.flush()
        if frac >= 1.0:
            sys.stdout.write("\n")
            sys.stdout.flush()
    else:
        pct = int(frac * 100)
        if pct != progress_counter._last_pct or frac >= 1.0:
            progress_counter._last_pct = pct
            plain = line
            for code in (_RED, _DIMRED, _BOLD, _RESET):
                plain = plain.replace(code, "")
            print(plain, flush=True)


progress_counter._last_pct = -1
progress_counter._tick = 0


def enable_red_tqdm():
    try:
        from tqdm import std as _std
    except Exception:
        return
    if getattr(_std.tqdm, "_red_patched", False):
        return
    _orig = _std.tqdm.__init__

    def _init(self, *args, **kwargs):
        kwargs.setdefault("colour", "#ff2d2d")
        _orig(self, *args, **kwargs)

    try:
        _std.tqdm.__init__ = _init
        _std.tqdm._red_patched = True
    except Exception:
        pass


enable_red_tqdm()


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
