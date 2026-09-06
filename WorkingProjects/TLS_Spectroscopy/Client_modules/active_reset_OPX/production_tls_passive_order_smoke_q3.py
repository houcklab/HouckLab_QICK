import json
from datetime import datetime
from pathlib import Path
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    acquire_passive_flux_spectroscopy_grid,
)


QUBIT = "q3"


def acquire_grid(soc, soccfg, cfg, *, order, dc_gains, hold_times_us):
    read_frequencies = np.full(len(dc_gains), float(cfg["read_pulse_freq"]))
    return acquire_passive_flux_spectroscopy_grid(
        soc,
        soccfg,
        cfg,
        frequencies_mhz=np.asarray(cfg["smoke_frequencies_mhz"], dtype=float),
        dc_gains=np.asarray(dc_gains, dtype=float),
        hold_times_us=np.asarray(hold_times_us, dtype=float),
        read_frequencies_mhz=read_frequencies,
        order=order,
        baseline_rearm_us=10.0,
        post_readout_reset_us=10.0,
        readout_after_park=False,
    )


def main():
    now = datetime.now()
    output = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_TLS_passive_order_smoke"
    )
    output.mkdir(parents=True, exist_ok=False)
    soc, soccfg = makeProxy()
    cfg = ProductionResetSession.passive().apply(BaseConfig)
    cfg.update({
        "shots": 2,
        "reps": 2,
        "qubit_pulse_style": "const",
        "qubit_length": 0.5,
        "qubit_gain": max(500, int(round(cfg["qubit_pi_gain"] * 0.7))),
        "smoke_frequencies_mhz": float(cfg["qubit_freq"]) + np.array([-0.5, 0.0, 0.5]),
    })
    park = int(round(float(cfg.get("ff_park_gain", 0) or 0)))
    dc_values = np.array([park, int(np.clip(park + 100, -32768, 32767))])

    step2_i, step2_q, step2_meta = acquire_grid(
        soc,
        soccfg,
        cfg,
        order="shot_frequency_dc_time",
        dc_gains=dc_values,
        hold_times_us=[2.0],
    )
    step3_i, step3_q, step3_meta = acquire_grid(
        soc,
        soccfg,
        cfg,
        order="shot_frequency_dc_time",
        dc_gains=dc_values[1:],
        hold_times_us=[0.5, 1.0, 2.0],
    )
    step4_i, step4_q, step4_meta = acquire_grid(
        soc,
        soccfg,
        cfg,
        order="shot_dc_frequency_time",
        dc_gains=dc_values,
        hold_times_us=[1.0, 2.0],
    )

    expected = {
        "step2": ((3, 2, 1, 2), "shot_frequency_dc_time"),
        "step3": ((3, 1, 3, 2), "shot_frequency_dc_time"),
        "step4": ((3, 2, 2, 2), "shot_dc_frequency_time"),
    }
    acquired = {
        "step2": (step2_i, step2_q, step2_meta),
        "step3": (step3_i, step3_q, step3_meta),
        "step4": (step4_i, step4_q, step4_meta),
    }
    for name, (i_values, q_values, metadata) in acquired.items():
        shape, order = expected[name]
        if i_values.shape != shape or q_values.shape != shape:
            raise RuntimeError(f"{name} returned the wrong IQ shape")
        if metadata["order"] != order:
            raise RuntimeError(f"{name} returned the wrong acquisition order")
        if not np.all(np.isfinite(i_values)) or not np.all(np.isfinite(q_values)):
            raise RuntimeError(f"{name} returned non-finite IQ")

    result = {
        "status": "pass",
        "output": str(output),
        "park_gain": park,
        "dc_values": dc_values.tolist(),
        "persistent_park": bool(cfg["opx_persistent_park"]),
        "hard_flux_steps": bool(cfg["opx_hard_flux_steps"]),
        "readout_thermalization_us": 10.0,
        "step2": step2_meta,
        "step3": step3_meta,
        "step4": step4_meta,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    np.savez(
        output / "raw_iq.npz",
        frequencies_mhz=cfg["smoke_frequencies_mhz"],
        dc_values=dc_values,
        step2_i=step2_i,
        step2_q=step2_q,
        step3_i=step3_i,
        step3_q=step3_q,
        step4_i=step4_i,
        step4_q=step4_q,
    )
    print(f"status=pass output={output}")
    print(f"step2 order={step2_meta['order']} records={step2_meta['records']}")
    print(f"step3 order={step3_meta['order']} records={step3_meta['records']}")
    print(f"step4 order={step4_meta['order']} records={step4_meta['records']}")


if __name__ == "__main__":
    main()
