from pathlib import Path
import sys


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
    t1_equivalence_q3 as benchmark,
)


benchmark.EXCURSION_GAIN = -20000.0
benchmark.OUTPUT_TAG = "T1_flux_ramp_equivalence"
benchmark.RAISE_ON_FAILURE = True


if __name__ == "__main__":
    benchmark.main()
