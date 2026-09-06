from time import perf_counter

PROCESS_STARTED = perf_counter()

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parent
while ROOT.parent != ROOT and not (ROOT / "WorkingProjects").is_dir():
    ROOT = ROOT.parent
if not (ROOT / "WorkingProjects").is_dir():
    ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
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
SHOT_COUNTS = (20, 200, 1000)
FREQUENCY_POINTS = 201
FREQUENCY_SPAN_MHZ = 6.0
READOUT_US = 5.0
THERMALIZATION_US = 10.0
QICK_MEASURE_SYNC_US = 0.01


def main():
    import_and_startup_s = perf_counter() - PROCESS_STARTED

    connection_started = perf_counter()
    soc, soccfg = makeProxy()
    connection_s = perf_counter() - connection_started

    cfg = ProductionResetSession.passive().apply(dict(BaseConfig))
    cfg.update(
        {
            "read_length": READOUT_US,
            "read_pulse_length": READOUT_US,
            "adc_trig_offset": 0.0,
            "readout_guard_us": 0.0,
            "readout_thermalization_us": THERMALIZATION_US,
            "relax_delay": THERMALIZATION_US,
            "opx_inter_shot_delay_us": THERMALIZATION_US,
        }
    )

    center_mhz = float(cfg["read_pulse_freq"])
    frequencies_mhz = np.linspace(
        center_mhz - FREQUENCY_SPAN_MHZ / 2.0,
        center_mhz + FREQUENCY_SPAN_MHZ / 2.0,
        FREQUENCY_POINTS,
    )

    runs = []

    for shots in SHOT_COUNTS:
        run_cfg = dict(cfg)
        run_cfg["shots"] = int(shots)
        run_cfg["reps"] = int(shots)

        started = perf_counter()

        i_values, q_values, telemetry = acquire_passive_readout_grid(
            soc,
            soccfg,
            run_cfg,
            frequencies_mhz=frequencies_mhz,
            values=[run_cfg["read_pulse_gain"]],
            kind="readout_gain",
        )

        experiment_wall_s = perf_counter() - started
        expected_shape = (FREQUENCY_POINTS, 1, int(shots))

        if i_values.shape != expected_shape or q_values.shape != expected_shape:
            raise RuntimeError(
                f"unexpected IQ shapes {i_values.shape}, {q_values.shape}; "
                f"expected {expected_shape}"
            )

        if not bool(telemetry.get("resident_handshake", False)):
            raise RuntimeError("resident RFSoC readout was not used")

        signal = np.mean(
            i_values[:, 0, :] + 1j * q_values[:, 0, :],
            axis=1,
        )
        magnitude = np.abs(signal)
        dip_index = int(np.argmin(magnitude))
        records = int(telemetry["records"])

        programmed_sequence_s = records * (
            readout_drive_length_us(run_cfg)
            + readout_thermalization_us(run_cfg)
            + QICK_MEASURE_SYNC_US
        ) * 1e-6

        server_timing = {
            str(key): float(value)
            for key, value in telemetry.get("server_timing_s", {}).items()
        }

        runs.append(
            {
                "shots": int(shots),
                "records": records,
                "experiment_wall_s": experiment_wall_s,
                "programmed_sequence_s": programmed_sequence_s,
                "wall_to_programmed_ratio": (
                    experiment_wall_s / programmed_sequence_s
                ),
                "wall_us_per_record": (
                    1e6 * experiment_wall_s / records
                ),
                "excess_us_per_record": (
                    1e6
                    * (experiment_wall_s - programmed_sequence_s)
                    / records
                ),
                "server_timing_s": server_timing,
                "client_and_serialization_s": (
                    experiment_wall_s
                    - float(server_timing.get("acquisition_s", 0.0))
                ),
                "controller_programs": int(
                    telemetry["controller_programs"]
                ),
                "readout_reconfigurations": int(
                    telemetry.get("readout_reconfigurations", 0)
                ),
                "order": str(telemetry["order"]),
                "dip_frequency_mhz": float(
                    frequencies_mhz[dip_index]
                ),
                "trace_fractional_span": float(
                    (np.max(magnitude) - np.min(magnitude))
                    / max(float(np.median(magnitude)), 1e-15)
                ),
            }
        )

    result = {
        "platform": "QICK",
        "qubit": QUBIT,
        "python_import_and_startup_s": import_and_startup_s,
        "controller_connection_s": connection_s,
        "frequency_points": FREQUENCY_POINTS,
        "frequency_span_mhz": FREQUENCY_SPAN_MHZ,
        "frequency_step_mhz": float(
            frequencies_mhz[1] - frequencies_mhz[0]
        ),
        "readout_us": readout_drive_length_us(cfg),
        "thermalization_us": readout_thermalization_us(cfg),
        "qick_measure_sync_us": QICK_MEASURE_SYNC_US,
        "readout_gain_dac": int(cfg["read_pulse_gain"]),
        "park_gain_dac": int(cfg.get("ff_park_gain", 0)),
        "runs": runs,
    }

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()