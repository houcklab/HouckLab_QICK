import csv
from datetime import datetime
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


_source = Path(__file__).resolve()
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        _repo_root = _parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.ringdown import (
    delay_cycle_axis,
)


try:
    from qick import RAveragerProgram
    _qick_import_error = None
except Exception as exc:
    _qick_import_error = exc

    class RAveragerProgram:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("QICK is unavailable on this computer") from _qick_import_error


QUBIT = "q3"
DELAY_START_US = 0.0
DELAY_STOP_US = 12.0
DELAY_STEP_US = 0.1
SHOTS_PER_DELAY_PER_DIRECTION = 300
PROBE_LENGTH_US = 0.25
CLEARANCE_US = 100.0
BASELINE_GUARD_US = 0.5
PARK_PREROLL_US = 400.0
NOISE_SIGMA = 3.0
CONSECUTIVE_NOISE_POINTS = 5
TIMING_RESOLUTION_US = 0.1


def emit_persistent_park(
    prog,
    *,
    ff_ch,
    park_gain,
    length_cycles,
    preroll_cycles,
):
    if int(park_gain) != 0:
        prog.set_pulse_registers(
            ch=int(ff_ch),
            freq=0,
            style="const",
            phase=0,
            stdysel="last",
            gain=int(park_gain),
            length=int(length_cycles),
        )
        prog.pulse(ch=int(ff_ch))
    prog.sync_all(int(preroll_cycles))


def emit_ringdown_pair(
    prog,
    *,
    res_ch,
    ro_chs,
    adc_trig_offset_cycles,
    wait_page,
    wait_register,
    baseline_guard_cycles,
    clearance_cycles,
):
    prog.trigger(
        adcs=list(ro_chs),
        adc_trig_offset=int(adc_trig_offset_cycles),
    )
    prog.wait_all(0)
    prog.sync_all(int(baseline_guard_cycles))
    prog.pulse(ch=int(res_ch))
    prog.sync_all(0)
    prog.sync(int(wait_page), int(wait_register))
    prog.trigger(
        adcs=list(ro_chs),
        adc_trig_offset=int(adc_trig_offset_cycles),
    )
    prog.wait_all(0)
    prog.sync_all(int(clearance_cycles))


class ResonatorRingdownProgram(RAveragerProgram):
    def initialize(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
            allocate_named_registers,
        )

        cfg = self.cfg
        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg.get("mixer_freq", 0.0),
            ro_ch=cfg["ro_chs"][0],
        )
        self.declare_gen(ch=cfg["ff_ch"], nqz=cfg.get("ff_nqz", 1))
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ro_ch,
                freq=cfg["read_pulse_freq"],
                length=self.us2cycles(cfg["ringdown_probe_length_us"], ro_ch=ro_ch),
                gen_ch=cfg["res_ch"],
            )
        read_frequency = self.freq2reg(
            cfg["read_pulse_freq"],
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0],
        )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=read_frequency,
            phase=self.deg2reg(cfg.get("res_phase", 0.0), gen_ch=cfg["res_ch"]),
            gain=int(cfg["read_pulse_gain"]),
            length=self.us2cycles(
                cfg["ringdown_pump_length_us"], gen_ch=cfg["res_ch"]
            ),
        )
        self.wait_page = self.ch_page(cfg["res_ch"])
        self.wait_register = allocate_named_registers(
            self,
            self.wait_page,
            ("ringdown_wait",),
        )["ringdown_wait"]
        self.delay_cycles = delay_cycle_axis(
            cfg["ringdown_axis_min_us"],
            cfg["ringdown_axis_step_us"],
            cfg["expts"],
            cfg["ringdown_descending"],
            self.us2cycles,
        )
        self.start_cycles = int(self.delay_cycles[0])
        self.step_cycles = int(self.delay_cycles[1] - self.delay_cycles[0])
        self.regwi(
            self.wait_page,
            self.wait_register,
            self.start_cycles,
        )
        emit_persistent_park(
            self,
            ff_ch=cfg["ff_ch"],
            park_gain=cfg.get("ff_park_gain", 0),
            length_cycles=3,
            preroll_cycles=self.us2cycles(cfg["ringdown_park_preroll_us"]),
        )

    def body(self):
        cfg = self.cfg
        emit_ringdown_pair(
            self,
            res_ch=cfg["res_ch"],
            ro_chs=cfg["ro_chs"],
            adc_trig_offset_cycles=self.us2cycles(cfg["adc_trig_offset"]),
            wait_page=self.wait_page,
            wait_register=self.wait_register,
            baseline_guard_cycles=self.us2cycles(cfg["ringdown_baseline_guard_us"]),
            clearance_cycles=self.us2cycles(cfg["ringdown_clearance_us"]),
        )

    def update(self):
        self.mathi(
            self.wait_page,
            self.wait_register,
            self.wait_register,
            "+",
            self.step_cycles,
        )

    def acquire_pairs(self, soc, progress=False):
        super().acquire(
            soc,
            load_pulses=True,
            readouts_per_experiment=2,
            save_experiments=[0, 1],
            start_src="internal",
            progress=progress,
        )
        expts = int(self.cfg["expts"])
        reps = int(self.cfg["reps"])
        length = int(self.us2cycles(
            self.cfg["ringdown_probe_length_us"],
            ro_ch=self.cfg["ro_chs"][0],
        ))
        i_values = np.asarray(self.di_buf[0], dtype=float).reshape(expts, reps, 2) / length
        q_values = np.asarray(self.dq_buf[0], dtype=float).reshape(expts, reps, 2) / length
        delays_us = np.asarray(
            [self.cycles2us(int(value)) for value in self.delay_cycles],
            dtype=float,
        )
        return {
            "delays_us": delays_us,
            "baseline_i": i_values[:, :, 0],
            "baseline_q": q_values[:, :, 0],
            "residual_i": i_values[:, :, 1],
            "residual_q": q_values[:, :, 1],
        }


def _output_directory(outer_folder):
    now = datetime.now()
    day = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_resonator_ringdown"
    output.mkdir(parents=True, exist_ok=False)
    return output, now


def _write_json(path, values):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
        json_safe,
    )

    Path(path).write_text(json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n")


def _write_csv(path, delays, result):
    fields = (
        "programmed_delay_us",
        "observation_window_start_us",
        "observation_window_end_us",
        "coherent_i",
        "coherent_q",
        "coherent_amplitude",
        "coherent_sem",
        "coherent_snr",
        "energy_excess",
        "energy_sem",
        "energy_snr",
        "fit_amplitude",
    )
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, delay in enumerate(delays):
            sem = float(result["coherent_sem"][index])
            amplitude = float(result["coherent_amplitude"][index])
            energy = float(result["energy_excess"][index])
            energy_sem = float(result["energy_sem"][index])
            writer.writerow({
                "programmed_delay_us": float(delay),
                "observation_window_start_us": float(
                    delay + result["observation_offset_us"]
                ),
                "observation_window_end_us": float(
                    delay
                    + result["observation_offset_us"]
                    + result["probe_length_us"]
                ),
                "coherent_i": float(result["coherent_i"][index]),
                "coherent_q": float(result["coherent_q"][index]),
                "coherent_amplitude": amplitude,
                "coherent_sem": sem,
                "coherent_snr": amplitude / sem if sem > 0 else math.inf,
                "energy_excess": energy,
                "energy_sem": energy_sem,
                "energy_snr": abs(energy) / energy_sem if energy_sem > 0 else math.inf,
                "fit_amplitude": float(result["predicted_amplitude"][index]),
            })


def _plot(path, delays, result):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    delays = np.asarray(delays, dtype=float)
    amplitude = np.asarray(result["coherent_amplitude"], dtype=float)
    sem = np.asarray(result["coherent_sem"], dtype=float)
    coherent_snr = np.divide(
        amplitude,
        sem,
        out=np.full_like(amplitude, np.nan),
        where=sem > 0,
    )
    energy = np.asarray(result["energy_excess"], dtype=float)
    energy_sem = np.asarray(result["energy_sem"], dtype=float)
    energy_snr = np.divide(
        np.abs(energy),
        energy_sem,
        out=np.full_like(energy, np.nan),
        where=energy_sem > 0,
    )
    fig, axes = plt.subplots(4, 1, figsize=(9, 12), constrained_layout=True, sharex=True)
    axes[0].errorbar(delays, amplitude, yerr=sem, fmt=".", capsize=2, label="measured")
    predicted = np.asarray(result["predicted_amplitude"], dtype=float)
    if np.any(np.isfinite(predicted)):
        axes[0].plot(delays, predicted, "-", label="exponential fit")
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Coherent residual amplitude")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].plot(delays, result["coherent_i"], ".-", label="I")
    axes[1].plot(delays, result["coherent_q"], ".-", label="Q")
    axes[1].set_ylabel("Pump minus baseline IQ")
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    axes[2].errorbar(delays, energy, yerr=energy_sem, fmt=".", capsize=2)
    axes[2].axhline(0.0, color="black", linestyle="--")
    axes[2].set_ylabel("Excess IQ energy")
    axes[2].grid(alpha=0.25)
    axes[3].plot(delays, coherent_snr, ".-", label="coherent")
    axes[3].plot(delays, energy_snr, ".-", label="energy")
    axes[3].axhline(NOISE_SIGMA, color="black", linestyle="--")
    axes[3].set_xlabel("Programmed delay after readout pulse (us)")
    axes[3].set_ylabel("Residual SNR")
    axes[3].legend()
    axes[3].grid(alpha=0.25)
    selected = result["programmed_noise_floor_delay_us"]
    if selected is not None:
        for axis in axes:
            axis.axvline(float(selected), color="red", linestyle="--")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _direction_config(base_config, start_us, step_us, points):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
        readout_drive_length_us,
    )

    cfg = dict(base_config)
    endpoint_us = float(start_us) + float(step_us) * (int(points) - 1)
    cfg.update({
        "reps": int(SHOTS_PER_DELAY_PER_DIRECTION),
        "shots": int(SHOTS_PER_DELAY_PER_DIRECTION),
        "expts": int(points),
        "start": 0,
        "step": 1,
        "ringdown_axis_min_us": float(min(start_us, endpoint_us)),
        "ringdown_axis_step_us": float(abs(step_us)),
        "ringdown_descending": bool(step_us < 0),
        "ringdown_probe_length_us": float(PROBE_LENGTH_US),
        "ringdown_pump_length_us": float(readout_drive_length_us(base_config)),
        "ringdown_clearance_us": float(CLEARANCE_US),
        "ringdown_baseline_guard_us": float(BASELINE_GUARD_US),
        "ringdown_park_preroll_us": float(PARK_PREROLL_US),
    })
    return cfg


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
        BaseConfig,
        outerFolder,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.ringdown import (
        analyze_ringdown,
        combine_ringdown_sweeps,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
        readout_drive_length_us,
    )

    output_dir, created = _output_directory(outerFolder)
    print(f"output={output_dir}")
    points = int(round((DELAY_STOP_US - DELAY_START_US) / DELAY_STEP_US)) + 1
    directions = (
        ("ascending", DELAY_START_US, DELAY_STEP_US),
        ("descending", DELAY_STOP_US, -DELAY_STEP_US),
    )
    soc, soccfg = makeProxy()
    sweeps = []
    started = time.monotonic()
    try:
        for name, start_us, step_us in directions:
            cfg = _direction_config(BaseConfig, start_us, step_us, points)
            program = ResonatorRingdownProgram(soccfg, cfg)
            sweep = program.acquire_pairs(soc, progress=True)
            sweep["direction"] = name
            sweeps.append(sweep)
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    elapsed_s = time.monotonic() - started
    combined = combine_ringdown_sweeps(sweeps)
    np.savez_compressed(
        output_dir / "raw_iq.npz",
        delays_us=combined["delays_us"],
        baseline_i=combined["baseline_i"],
        baseline_q=combined["baseline_q"],
        residual_i=combined["residual_i"],
        residual_q=combined["residual_q"],
    )
    result = analyze_ringdown(
        combined["delays_us"],
        combined["baseline_i"],
        combined["baseline_q"],
        combined["residual_i"],
        combined["residual_q"],
        sigma=NOISE_SIGMA,
        consecutive=CONSECUTIVE_NOISE_POINTS,
        timing_resolution_us=TIMING_RESOLUTION_US,
        observation_offset_us=float(BaseConfig["adc_trig_offset"]),
        probe_length_us=PROBE_LENGTH_US,
    )
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"
    metadata = {
        "created": created.isoformat(),
        "source_commit": source_commit,
        "qick_version": str(qick.__version__),
        "qubit": QUBIT,
        "elapsed_s": elapsed_s,
        "read_pulse_freq_mhz": float(BaseConfig["read_pulse_freq"]),
        "read_pulse_gain_dac": int(BaseConfig["read_pulse_gain"]),
        "readout_integration_us": float(BaseConfig["read_length"]),
        "readout_generator_us": float(readout_drive_length_us(BaseConfig)),
        "probe_length_us": PROBE_LENGTH_US,
        "adc_trig_offset_us": float(BaseConfig["adc_trig_offset"]),
        "observation_window_relative_to_programmed_delay_us": [
            float(BaseConfig["adc_trig_offset"]),
            float(BaseConfig["adc_trig_offset"] + PROBE_LENGTH_US),
        ],
        "park_gain_dac": int(BaseConfig.get("ff_park_gain", 0)),
        "park_mode": "persistent_hard_step",
        "park_step_minimum_cycles": 3,
        "delay_start_us": DELAY_START_US,
        "delay_stop_us": DELAY_STOP_US,
        "delay_step_us": DELAY_STEP_US,
        "shots_per_delay_per_direction": SHOTS_PER_DELAY_PER_DIRECTION,
        "directions": [name for name, _, _ in directions],
        "clearance_us": CLEARANCE_US,
        "noise_sigma": NOISE_SIGMA,
        "consecutive_noise_points": CONSECUTIVE_NOISE_POINTS,
    }
    _write_json(output_dir / "metadata.json", metadata)
    _write_json(output_dir / "result.json", result)
    _write_csv(output_dir / "ringdown.csv", combined["delays_us"], result)
    _plot(output_dir / "ringdown.png", combined["delays_us"], result)
    print(f"status={result['status']}")
    print(f"field_tau_us={result['field_tau_us']}")
    print(f"photon_tau_us={result['photon_tau_us']}")
    print(f"programmed_noise_floor_delay_us={result['programmed_noise_floor_delay_us']}")
    print(f"noise_floor_delay_us={result['noise_floor_delay_us']}")
    print(f"recommended_thermalization_us={result['recommended_thermalization_us']}")


if __name__ == "__main__":
    main()
