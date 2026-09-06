import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    readout_drive_length_us,
    readout_thermalization_us,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
    ProductionResetSession,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.qua_order import (
    acquire_passive_readout_grid,
)


QUBIT = "q3"
SHOTS = 200
FREQUENCY_POINTS = 201
FREQUENCY_SPAN_MHZ = 6.0
READOUT_INTEGRATION_US = 5.0
READOUT_THERMALIZATION_US = 10.0
QICK_MEASURE_SYNC_US = 0.01


def main():
    started = perf_counter()
    soc, soccfg = makeProxy()
    connection_s = perf_counter() - started
    cfg = ProductionResetSession.passive().apply(BaseConfig)
    cfg.update(
        {
            "shots": SHOTS,
            "reps": SHOTS,
            "read_length": READOUT_INTEGRATION_US,
            "read_pulse_length": READOUT_INTEGRATION_US,
            "adc_trig_offset": 0.0,
            "readout_guard_us": 0.0,
            "readout_thermalization_us": READOUT_THERMALIZATION_US,
            "relax_delay": READOUT_THERMALIZATION_US,
        }
    )
    center = float(cfg["read_pulse_freq"])
    frequencies = np.linspace(
        center - FREQUENCY_SPAN_MHZ / 2,
        center + FREQUENCY_SPAN_MHZ / 2,
        FREQUENCY_POINTS,
    )
    started = perf_counter()
    i_values, q_values, telemetry = acquire_passive_readout_grid(
        soc,
        soccfg,
        cfg,
        frequencies_mhz=frequencies,
        values=[cfg["read_pulse_gain"]],
        kind="readout_gain",
    )
    wall_s = perf_counter() - started
    if int(telemetry.get("server_batches", 0)) != 1:
        raise RuntimeError("RFSoC batch acquisition was not used")
    if not bool(telemetry.get("resident_handshake", False)):
        raise RuntimeError("RFSoC resident acquisition was not used")
    signal = np.mean(i_values[:, 0, :] + 1j * q_values[:, 0, :], axis=1)
    dip = float(frequencies[int(np.argmin(np.abs(signal)))])
    records = int(telemetry["records"])
    controller_sequence_s = records * (
        readout_drive_length_us(cfg)
        + readout_thermalization_us(cfg)
        + QICK_MEASURE_SYNC_US
    ) * 1e-6
    now = datetime.now()
    output = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_QICK_transmission_batch_timing"
    )
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "platform": "QICK",
        "qubit": QUBIT,
        "controller_connection_s": connection_s,
        "experiment_wall_s": wall_s,
        "estimated_controller_sequence_s": controller_sequence_s,
        "wall_to_controller_ratio": wall_s / controller_sequence_s,
        "wall_ms_per_record": 1e3 * wall_s / records,
        "shots": SHOTS,
        "frequency_points": FREQUENCY_POINTS,
        "frequency_span_mhz": FREQUENCY_SPAN_MHZ,
        "frequency_step_mhz": float(frequencies[1] - frequencies[0]),
        "records": records,
        "host_programs": int(telemetry["host_programs"]),
        "controller_programs": int(telemetry["controller_programs"]),
        "readout_reconfigurations": int(
            telemetry.get("readout_reconfigurations", 0)
        ),
        "server_batches": int(telemetry["server_batches"]),
        "resident_handshake": bool(telemetry.get("resident_handshake", False)),
        "server_timing_s": telemetry.get("server_timing_s", {}),
        "ready_polls": int(telemetry.get("ready_polls", 0)),
        "frequency_update_mode": telemetry.get(
            "frequency_update_mode", "unknown"
        ),
        "generator_update_mode": telemetry.get(
            "generator_update_mode", "unknown"
        ),
        "order": telemetry["order"],
        "readout_integration_us": float(cfg["read_length"]),
        "readout_drive_us": readout_drive_length_us(cfg),
        "post_readout_thermalization_us": readout_thermalization_us(cfg),
        "dip_frequency_mhz": dip,
    }
    (output / "timing.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    np.savez(
        output / "raw_iq.npz",
        frequencies_mhz=frequencies,
        i=i_values,
        q=q_values,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"output={output}")


if __name__ == "__main__":
    main()
