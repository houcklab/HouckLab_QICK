import json
from datetime import datetime
from pathlib import Path

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    acquire_passive_optimizer_grid,
    acquire_passive_pulse_grid,
    acquire_passive_readout_grid,
)


QUBIT = "q3"


def main():
    now = datetime.now()
    output = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_gate_passive_order_smoke"
    )
    output.mkdir(parents=True, exist_ok=False)
    soc, soccfg = makeProxy()
    base = ProductionResetSession.passive().apply(BaseConfig)
    read_frequency = float(base["read_pulse_freq"])
    read_gain = int(base["read_pulse_gain"])
    qubit_frequency = float(base["qubit_pi_freq"])
    qubit_gain = int(base["qubit_pi_gain"])
    read_frequencies = read_frequency + np.array([-0.10, 0.0, 0.10])
    read_gains = np.rint(read_gain * np.array([0.9, 1.0, 1.1])).astype(int)
    qubit_frequencies = qubit_frequency + np.array([-0.25, 0.0, 0.25])
    qubit_gains = np.rint(qubit_gain * np.array([0.9, 1.1])).astype(int)
    park_gain = int(base.get("ff_park_gain", 0) or 0)
    flux_gains = np.array([park_gain, park_gain + 100], dtype=int)

    read_cfg = {**base, "shots": 2, "reps": 2}
    trans_i, trans_q, trans_meta = acquire_passive_readout_grid(
        soc,
        soccfg,
        read_cfg,
        frequencies_mhz=read_frequencies,
        values=[read_gain],
        kind="readout_gain",
    )
    sweep_i, sweep_q, sweep_meta = acquire_passive_readout_grid(
        soc,
        soccfg,
        read_cfg,
        frequencies_mhz=read_frequencies[:2],
        values=read_gains,
        kind="readout_gain",
    )
    flux_i, flux_q, flux_meta = acquire_passive_readout_grid(
        soc,
        soccfg,
        read_cfg,
        frequencies_mhz=read_frequencies[:2],
        values=flux_gains,
        kind="flux_gain",
    )

    spec_cfg = {
        **base,
        "shots": 3,
        "reps": 3,
        "qubit_pulse_style": "const",
        "qubit_length": 1.0,
        "qubit_gain": max(500, int(round(qubit_gain / 10))),
    }
    spec_i, spec_q, spec_meta = acquire_passive_pulse_grid(
        soc,
        soccfg,
        spec_cfg,
        frequencies_mhz=qubit_frequencies,
        gains=[spec_cfg["qubit_gain"]],
        pulses=1,
    )

    optimizer_cfg = {
        **base,
        "shots": 8,
        "reps": 8,
        "relax_delay": 400.0,
    }
    qubit_opt_i, qubit_opt_q, qubit_opt_meta = acquire_passive_optimizer_grid(
        soc,
        soccfg,
        optimizer_cfg,
        frequencies_mhz=qubit_frequencies[[0, 2]],
        gains=qubit_gains,
        kind="qubit",
        drive_pulses=1,
        drive_gain=qubit_gain,
    )
    read_opt_i, read_opt_q, read_opt_meta = acquire_passive_optimizer_grid(
        soc,
        soccfg,
        optimizer_cfg,
        frequencies_mhz=read_frequencies[[0, 2]],
        gains=read_gains[[0, 2]],
        kind="readout",
        drive_pulses=1,
        drive_gain=qubit_gain,
    )

    metadata = {
        "status": "pass",
        "output": str(output),
        "transmission": trans_meta,
        "transmission_sweep": sweep_meta,
        "transmission_vs_flux": flux_meta,
        "qubit_spectroscopy": spec_meta,
        "qubit_optimizer": qubit_opt_meta,
        "readout_optimizer": read_opt_meta,
    }
    (output / "result.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )
    np.savez(
        output / "raw_iq.npz",
        read_frequencies_mhz=read_frequencies,
        read_gains=read_gains,
        qubit_frequencies_mhz=qubit_frequencies,
        qubit_gains=qubit_gains,
        flux_gains=flux_gains,
        transmission_i=trans_i,
        transmission_q=trans_q,
        transmission_sweep_i=sweep_i,
        transmission_sweep_q=sweep_q,
        transmission_vs_flux_i=flux_i,
        transmission_vs_flux_q=flux_q,
        qubit_spectroscopy_i=spec_i,
        qubit_spectroscopy_q=spec_q,
        qubit_optimizer_i=qubit_opt_i,
        qubit_optimizer_q=qubit_opt_q,
        readout_optimizer_i=read_opt_i,
        readout_optimizer_q=read_opt_q,
    )
    print(f"status=pass output={output}")
    for name, values in metadata.items():
        if isinstance(values, dict):
            print(f"{name} order={values['order']} records={values['records']}")


if __name__ == "__main__":
    main()
