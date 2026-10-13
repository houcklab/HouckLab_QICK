"""Helpers shared by the qicklab.twpa scripts (docs/experiments/twpa.md)."""

import datetime as _dt
import os


def timestamped_paths(save_dir, run_tag):
    """Create save_dir; return ``<save_dir>/<%Y%m%d_%H%M%S>_<run_tag>`` + ``.npz`` / ``.png``."""
    os.makedirs(save_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(save_dir, f"{stamp}_{run_tag}")
    return base + ".npz", base + ".png"
