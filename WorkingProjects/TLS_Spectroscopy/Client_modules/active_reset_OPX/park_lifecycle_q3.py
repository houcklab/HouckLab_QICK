from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        _repo_root = parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import NpEncoder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy


QUBIT = "q3"
PARK_GAIN = None
CENTER_FREQUENCY_MHZ = None
EXCURSION_TOWARD_ZERO_DAC = 2000
EXCURSION_HOLD_US = 20.0
FREQUENCY_HALF_SPAN_MHZ = 8.0
FREQUENCY_STEP_MHZ = 0.25
SHOTS = 100
INTERLEAVE_ROUNDS = 4
SPECTROSCOPY_GAIN = 15000
SPECTROSCOPY_LENGTH_US = 0.5
PASSIVE_RESET_US = 400.0
MAX_RETURN_ERROR_MHZ = 0.5
EDGE_GUARD_MHZ = 1.0


def _feature(trace, frequency_mhz):
    supported = np.asarray(trace["supported"], dtype=bool)
    selected = np.asarray(trace["selected_frequency_ghz"], dtype=float) * 1e3
    edge = np.minimum(selected - frequency_mhz[0], frequency_mhz[-1] - selected)
    return {
        "frequency_mhz": selected,
        "supported": supported,
        "edge_distance_mhz": edge,
    }


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from qick import RAveragerProgram

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import interleaved_average, suppress_stdout
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.trace_extraction import extract_trace_from_map

    class ParkRoundTripSpecProgram(RAveragerProgram):
        def initialize(self):
            cfg = self.cfg
            self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
            self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
            ff_pulse.declare_ff(self)
            for channel in cfg["ro_chs"]:
                self.declare_readout(
                    ch=channel,
                    length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                    freq=cfg["read_pulse_freq"],
                    gen_ch=cfg["res_ch"],
                )
            self.q_page = self.ch_page(cfg["qubit_ch"])
            self.q_freq = self.sreg(cfg["qubit_ch"], "freq")
            self.frequency_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="const",
                freq=self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"]),
                phase=0,
                gain=cfg["qubit_gain"],
                length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
            )
            set_readout_pulse(
                self,
                self.freq2reg(
                    cfg["read_pulse_freq"],
                    gen_ch=cfg["res_ch"],
                    ro_ch=cfg["ro_chs"][0],
                ),
            )
            self.park_segments = ff_pulse.build_park_hold(
                self, hold_us=ff_pulse.flux_settle_us(cfg)
            )
            self.excursion_segments = ff_pulse.build_ramp_hold_ramp(
                self,
                hold_us=cfg["lifecycle_excursion_hold_us"],
                ff_gain=cfg["lifecycle_excursion_gain"],
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                dt_def_us=cfg.get("dt_pulsedef", 0.002),
            )
            self.synci(200)

        def body(self):
            cfg = self.cfg
            ff_pulse.play_park_up(self, self.park_segments)
            if cfg["lifecycle_do_excursion"]:
                ff_pulse.play_ramp_up_hold(
                    self,
                    self.excursion_segments,
                    dt_play_us=cfg.get("dt_pulseplay", 5.0),
                )
                ff_pulse.play_ramp_down(self, self.excursion_segments)
                self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
            self.measure(
                pulse_ch=cfg["res_ch"],
                adcs=cfg["ro_chs"],
                adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                wait=True,
                syncdelay=self.us2cycles(0.01),
            )
            ff_pulse.play_park_down(self, self.park_segments)
            self.sync_all(self.us2cycles(cfg["relax_delay"]))

        def update(self):
            self.mathi(self.q_page, self.q_freq, self.q_freq, "+", self.frequency_step)

    park_gain = int(BaseConfig["ff_park_gain"] if PARK_GAIN is None else PARK_GAIN)
    if park_gain == 0:
        raise ValueError("PARK_GAIN must be nonzero")
    center_mhz = float(
        BaseConfig.get("qubit_pi_freq", BaseConfig["qubit_freq"])
        if CENTER_FREQUENCY_MHZ is None
        else CENTER_FREQUENCY_MHZ
    )
    direction = -1 if park_gain > 0 else 1
    excursion_gain = park_gain + direction * int(EXCURSION_TOWARD_ZERO_DAC)
    intervals = int(np.ceil(2.0 * FREQUENCY_HALF_SPAN_MHZ / FREQUENCY_STEP_MHZ))
    frequency_mhz = np.linspace(
        center_mhz - FREQUENCY_HALF_SPAN_MHZ,
        center_mhz + FREQUENCY_HALF_SPAN_MHZ,
        intervals + 1,
    )
    cfg = dict(BaseConfig)
    cfg.update({
        "start": float(frequency_mhz[0]),
        "step": float(frequency_mhz[1] - frequency_mhz[0]),
        "expts": int(frequency_mhz.size),
        "reps": int(SHOTS),
        "relax_delay": float(PASSIVE_RESET_US),
        "qubit_pulse_style": "const",
        "qubit_gain": int(SPECTROSCOPY_GAIN),
        "qubit_length": float(SPECTROSCOPY_LENGTH_US),
        "lifecycle_excursion_gain": int(excursion_gain),
        "lifecycle_excursion_hold_us": float(EXCURSION_HOLD_US),
    })
    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_park_lifecycle"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"
    metadata = {
        "created": now.isoformat(),
        "source_commit": source_commit,
        "qubit": QUBIT,
        "park_gain_dac": park_gain,
        "excursion_gain_dac": excursion_gain,
        "excursion_hold_us": float(EXCURSION_HOLD_US),
        "frequency_mhz": frequency_mhz,
        "shots": int(SHOTS),
        "interleave_rounds": int(INTERLEAVE_ROUNDS),
        "max_return_error_mhz": float(MAX_RETURN_ERROR_MHZ),
        "config": cfg,
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, cls=NpEncoder, indent=2, sort_keys=True) + "\n"
    )
    soc, soccfg = makeProxy()
    assembly_saved = set()

    def run_arm(index, reps):
        run_cfg = dict(cfg)
        run_cfg["lifecycle_do_excursion"] = bool(index)
        run_cfg["reps"] = int(reps)
        with suppress_stdout():
            program = ParkRoundTripSpecProgram(soccfg, run_cfg)
        name = "round_trip" if index else "park_only"
        if name not in assembly_saved:
            assembly = program.asm()
            (output_dir / f"{name}.asm").write_text(assembly)
            binary = np.asarray(program.compile(), dtype=np.uint64)
            (output_dir / f"{name}.asm.sha256").write_text(
                hashlib.sha256(binary.tobytes()).hexdigest() + "\n"
            )
            assembly_saved.add(name)
        with suppress_stdout():
            _, avgi, avgq = program.acquire(
                soc, load_pulses=True, progress=False
            )
        return np.asarray(avgi[0][0]) + 1j * np.asarray(avgq[0][0])

    try:
        complex_iq = interleaved_average(
            run_arm,
            2,
            int(SHOTS),
            rounds=int(INTERLEAVE_ROUNDS),
        ).T
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    magnitude_db = 20.0 * np.log10(np.abs(complex_iq) + 1e-12)
    phase_rad = np.angle(complex_iq)
    options = {
        "trace_tracking_mode": "independent_slices",
        "trace_polarity": "auto",
        "trace_max_jump_mhz": 4.0,
        "trace_local_fit_half_window_mhz": 4.0,
        "trace_smoothing_window_points": 7,
        "trace_smoothing_polyorder": 2,
        "trace_use_smoothed_frequency": False,
    }
    axes = np.arange(2, dtype=float)
    magnitude_trace = extract_trace_from_map(
        magnitude_db,
        frequency_mhz / 1e3,
        axes,
        center_mhz / 1e3,
        center_mhz / 1e3,
        FREQUENCY_HALF_SPAN_MHZ / 1e3,
        **options,
    )
    phase_trace = extract_trace_from_map(
        phase_rad,
        frequency_mhz / 1e3,
        axes,
        center_mhz / 1e3,
        center_mhz / 1e3,
        FREQUENCY_HALF_SPAN_MHZ / 1e3,
        **options,
    )
    magnitude_feature = _feature(magnitude_trace, frequency_mhz)
    phase_feature = _feature(phase_trace, frequency_mhz)
    phase_error = float(np.abs(np.diff(phase_feature["frequency_mhz"]))[0])
    supported = bool(np.all(phase_feature["supported"]))
    edge_clear = bool(np.all(phase_feature["edge_distance_mhz"] > EDGE_GUARD_MHZ))
    passed = supported and edge_clear and phase_error <= MAX_RETURN_ERROR_MHZ
    summary = {
        "status": "pass" if passed else "fail",
        "park_lifecycle_consistent": passed,
        "phase_return_error_mhz": phase_error,
        "phase_frequency_mhz": phase_feature["frequency_mhz"],
        "phase_supported": phase_feature["supported"],
        "phase_edge_distance_mhz": phase_feature["edge_distance_mhz"],
        "magnitude_frequency_mhz": magnitude_feature["frequency_mhz"],
        "magnitude_supported": magnitude_feature["supported"],
        "maximum_return_error_mhz": float(MAX_RETURN_ERROR_MHZ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, cls=NpEncoder, indent=2, sort_keys=True) + "\n"
    )
    np.savez_compressed(
        output_dir / "raw.npz",
        complex_iq=complex_iq,
        magnitude_db=magnitude_db,
        phase_rad=phase_rad,
        frequency_mhz=frequency_mhz,
    )
    fig, axes_plot = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    names = ("park only", "park, excursion, park")
    for index, name in enumerate(names):
        axes_plot[0].plot(frequency_mhz, magnitude_db[:, index], label=name)
        axes_plot[1].plot(frequency_mhz, phase_rad[:, index], label=name)
    axes_plot[0].set_ylabel("Magnitude [dB]")
    axes_plot[1].set_ylabel("Phase [rad]")
    axes_plot[1].set_xlabel("Qubit drive frequency [MHz]")
    axes_plot[0].legend()
    axes_plot[1].legend()
    fig.suptitle(f"{QUBIT} bounded park lifecycle: {summary['status']}")
    fig.tight_layout()
    fig.savefig(output_dir / "park_lifecycle.png", dpi=160)
    plt.close(fig)
    print(f"status={summary['status']}")
    print(f"phase_return_error_mhz={phase_error:.6f}")
    print(f"output={output_dir}")
    if not passed:
        raise RuntimeError("park lifecycle measurement failed its return-to-park gate")


if __name__ == "__main__":
    main()
