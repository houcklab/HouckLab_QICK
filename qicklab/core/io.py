"""Run-level file output: timestamped names, npz + config-json records, cycle summaries."""

import json
import os
from datetime import datetime

import numpy as np


def timestamp():
    """Wall-clock stamp used in run-level file names (%Y_%m_%d_%H_%M_%S)."""
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


def save_record(base, cfg, /, **arrays):
    """Write `<base>.npz` (arrays, keys in call order) and `<base>_config.json` (cfg)."""
    np.savez(base + ".npz", **arrays)
    with open(base + "_config.json", "w") as f:
        json.dump(cfg, f, indent=2, default=float)


def save_cycle_summary(save_dir, rows):
    """Write the per-cycle summary rows to `<save_dir>/CycleSummary_<timestamp>.json`."""
    summary_path = os.path.join(save_dir, f"CycleSummary_{timestamp()}.json")
    with open(summary_path, "w") as f:
        json.dump(rows, f, indent=2, default=float)
