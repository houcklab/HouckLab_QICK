"""
DEPRECATED -- superseded by Runners/AutoTune.py.

This was the linear-pipeline tuner.  It has been replaced by a calibration GRAPH that
iterates to a fixed point (Experiments/mAutoTuner.py), which fixes defects this file
cannot: its convergence test used the residual at the gain-sweep minimum (a decoherence
floor, so it reported FAILED on good pulses), it never measured T1 / chi / kappa, it had
no outer loop, and its readout optimization had no ionization gate.

Run this instead:

    python WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/AutoTune.py

The old implementation remains in git history (and in Experiments/mAutoPiTuner.py) if a
comparison is ever needed.
"""

import sys

MSG = __doc__.strip()

if __name__ == "__main__":
    print("=" * 78)
    print(MSG)
    print("=" * 78)
    sys.exit(1)
