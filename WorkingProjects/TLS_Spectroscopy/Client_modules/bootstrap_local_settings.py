import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
while ROOT.parent != ROOT and not (ROOT / "WorkingProjects").is_dir():
    ROOT = ROOT.parent
if not (ROOT / "WorkingProjects").is_dir():
    raise RuntimeError("Could not find the HouckLab_QICK repository root")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.local_settings import (
    copy_local_scratch,
    snapshot_source_local_overrides,
)


CLIENT_ROOT = Path(__file__).resolve().parent

SOURCE_PATHS = (
    CLIENT_ROOT / "Calib" / "initialize.py",
    CLIENT_ROOT / "Runners" / "GateCalibration.py",
    CLIENT_ROOT / "Runners" / "SingleQubitCoherence.py",
    CLIENT_ROOT / "Runners" / "TLSSpectroscopy.py",
)

SCRATCH_SOURCE = (
    CLIENT_ROOT / "active_reset_OPX" / "transmission_timing_q3.py"
)
SCRATCH_TARGET = CLIENT_ROOT / "active_reset_OPX" / "test.local.py"


def main():
    for source in SOURCE_PATHS:
        snapshot_source_local_overrides(source)
    copy_local_scratch(SCRATCH_SOURCE, SCRATCH_TARGET)


if __name__ == "__main__":
    main()
