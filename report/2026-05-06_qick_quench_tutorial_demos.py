"""Companion demos for `2026-05-06_qick_quench_tutorial.tex`.

Each demo is a function. Demos that don't need an RFSoC run as-is. Demos
that do are gated on `NEEDS_HARDWARE` and skipped by default.

Run from the project root with:

    .venv\\Scripts\\python.exe report/2026-05-06_qick_quench_tutorial_demos.py

Or pick one demo:

    .venv\\Scripts\\python.exe report/2026-05-06_qick_quench_tutorial_demos.py demo_3
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from pprint import pformat

import numpy as np
import matplotlib

# Use a non-Qt backend so demos work in headless contexts.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NEEDS_HARDWARE = False  # flip to True if you have a connected RFSoC

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = REPO_ROOT / "Archive"
QUENCH_ROOT = REPO_ROOT / "WorkingProjects" / "triangle_lattice_quench"

# The demos import `WorkingProjects.*`, which is rooted at the repo top —
# this file lives under `report/`, so push the repo root onto sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Demo 1: open and inspect a saved .h5 from a previous run
# ---------------------------------------------------------------------------

def demo_1_inspect_h5() -> None:
    """Walk every key of an h5 dataset, print shapes, plot one trace.

    The repo ships old example data under `Archive/Basil/Client_modules/
    ZCollected_Data/`. Pick any .h5 file there if no fresh data is present.
    """
    import h5py
    candidates = sorted(ARCHIVE.glob("**/dataAmpRabi_*/dataAmpRabi*_data.h5"))
    if not candidates:
        print("[demo_1] No example .h5 found under Archive/. "
              "Point `path` below at a recent run instead.")
        return
    path = candidates[0]
    print(f"[demo_1] Opening {path.relative_to(REPO_ROOT)}")
    with h5py.File(path, "r") as f:
        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                print(f"  {name:50s}  shape={obj.shape}  dtype={obj.dtype}")
        f.visititems(visit)
        # Common shape: avgi, avgq, x_pts. Try to plot.
        for ki in ("data/avgi", "avgi"):
            if ki in f:
                avgi = f[ki][...]
                break
        else:
            avgi = None
        for kx in ("data/x_pts", "x_pts"):
            if kx in f:
                x = f[kx][...]
                break
        else:
            x = None
        if avgi is not None and x is not None:
            fig, ax = plt.subplots()
            ax.plot(x, avgi, ".-")
            ax.set_xlabel("x_pts (saved unit)")
            ax.set_ylabel("avgi")
            ax.set_title(path.name)
            out = Path(__file__).with_suffix("").parent / "demo1_plot.png"
            fig.savefig(out)
            print(f"[demo_1] Saved plot to {out.name}")


# ---------------------------------------------------------------------------
# Demo 2: build a tProc dump without hardware
# ---------------------------------------------------------------------------

def demo_2_tproc_dump() -> None:
    """Compile a tiny QICK program and print its instruction listing.

    Uses a saved cfg dict to construct a `QickConfig` without contacting the
    RFSoC. The compile step is offline; you can read what your `_body` will
    actually emit on the tProc.
    """
    from qick import QickConfig
    from qick.asm_v2 import AveragerProgramV2

    # A minimal soccfg dict — only the fields QickConfig needs to validate
    # the program. Keep this in sync with your real soccfg if you want the
    # numbers to match what the FPGA would compute.
    soccfg_dict = {
        "fs_proc": 350.0, "tproc": {"fs": 350.0, "f_dds": 350.0,
                                     "pmem_size": 16384, "dmem_size": 4096},
        "gens": [
            *([{"type": "axis_signal_gen_v6", "fs": 9830.4, "f_fabric": 614.4,
                "samps_per_clk": 16, "maxv": 32766,
                "b_dac": 16}] * 8),  # 8 FF DACs (channels 0..7)
            {"type": "axis_sg_mux4_v3", "fs": 9830.4, "f_fabric": 614.4,
             "samps_per_clk": 16, "maxv": 32766, "b_dac": 16},  # res_ch=8
            {"type": "axis_signal_gen_v6", "fs": 6881.28, "f_fabric": 430.08,
             "samps_per_clk": 16, "maxv": 32766, "b_dac": 16},  # qubit_ch=9
        ],
        "readouts": [{"type": "axis_pfb_readout_v3", "fs": 4423.68, "f_dds": 4423.68,
                      "f_fabric": 276.48, "trigger_bit": 0, "tproc_ctrl": 0,
                      "b_dds": 32}],
        "iqs": [], "ddrs": [], "tprocs": [{"fs": 350.0, "f_dds": 350.0,
                                            "pmem_size": 16384, "dmem_size": 4096}],
    }
    soccfg = QickConfig(soccfg_dict)

    class TinyProg(AveragerProgramV2):
        def _initialize(self, cfg):
            self.declare_gen(ch=cfg["qubit_ch"], nqz=2,
                             mixer_freq=cfg["qubit_mixer_freq"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit_gauss",
                           sigma=cfg["sigma"], length=4 * cfg["sigma"])
            self.add_pulse(ch=cfg["qubit_ch"], name="pi_pulse",
                           style="arb", envelope="qubit_gauss",
                           freq=cfg["qubit_freqs"][0],
                           phase=90, gain=cfg["qubit_gains"][0])

        def _body(self, cfg):
            self.pulse(ch=cfg["qubit_ch"], name="pi_pulse", t=0)
            self.delay_auto(0.05)

    cfg = {
        "qubit_ch": 9, "qubit_mixer_freq": 4000, "qubit_nqz": 2,
        "qubit_freqs": [200.0], "qubit_gains": [0.3], "sigma": 0.03,
        "reps": 10, "relax_delay": 50,
    }
    try:
        prog = TinyProg(soccfg, cfg=cfg, reps=cfg["reps"],
                        final_delay=cfg["relax_delay"], initial_delay=10.0)
        listing = prog.asm()
        print("[demo_2] Compiled tProc listing (first 40 lines):")
        for line in listing.splitlines()[:40]:
            print("  " + line)
    except Exception as exc:
        print(f"[demo_2] Could not compile (your QickConfig fields may not "
              f"match the version of qick you have): {exc}")


# ---------------------------------------------------------------------------
# Demo 3: cfg builder walkthrough
# ---------------------------------------------------------------------------

def demo_3_cfg_walkthrough() -> None:
    """Build the cfg dict the calibration GUI feeds to every stage and
    print every key. Compares single-qubit vs two-qubit chevron cfgs.
    """
    from WorkingProjects.triangle_lattice_quench.Run_Experiments import calibration_gui as cg

    state = cg.CalibState()
    # Inject some realistic per-qubit values so the cfg has interesting numbers
    state.qubit_parameters["3"]["Readout"]["Frequency"] = 7511.0
    state.qubit_parameters["3"]["Readout"]["Gain"] = 1800
    state.qubit_parameters["3"]["Readout"]["angle"] = 0.357
    state.qubit_parameters["3"]["Readout"]["threshold"] = -0.142
    state.qubit_parameters["3"]["Readout"]["ne_contrast"] = 0.05
    state.qubit_parameters["3"]["Readout"]["ng_contrast"] = 0.03
    state.qubit_parameters["3"]["Qubit"]["Frequency"] = 3597.6
    state.qubit_parameters["3"]["Qubit"]["Gain"] = 4365
    state.qubit_parameters["3"]["Qubit"]["sigma"] = 0.07
    state.target_qubit = 3

    cfg = state.build_single_qubit_config({"reps": 200})
    print("[demo_3] build_single_qubit_config — keys:")
    for k in sorted(cfg):
        v = cfg[k]
        if isinstance(v, list) and len(v) > 8:
            v = f"[{len(v)} elements]"
        elif isinstance(v, np.ndarray):
            v = f"ndarray shape={v.shape}"
        print(f"  {k:25s}  {v!r:.80s}")

    cfg2 = state.build_two_qubit_chevron_config(
        q_i=3, q_j=5, sweep_qubit=5,
        overrides={"gainStart": -1000, "gainStop": 1000, "gainNumPoints": 11},
    )
    print("\n[demo_3] build_two_qubit_chevron_config — selected keys:")
    for k in ("Qubit_Readout_List", "ro_chs", "qubit_FF_index", "res_freqs",
              "qubit_freqs", "angle", "threshold"):
        print(f"  {k:25s}  {cfg2[k]!r}")
    print(f"  {'confusion_matrix':25s}  {cfg2['confusion_matrix']}")


# ---------------------------------------------------------------------------
# Demo 4: FF crosstalk math (visualise compensated waveforms)
# ---------------------------------------------------------------------------

def demo_4_ff_crosstalk() -> None:
    """Build a compensated FF ramp and plot all 8 channel waveforms.

    Without crosstalk compensation, ramping the flux on Q3 would also detune
    Q2 and Q4. The compensation matrix injects opposite-sign pulses on those
    channels so the *net* detuning is only on Q3. The demo shows what those
    8 simultaneous waveforms look like.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers

    # The CompensatedRampArrays signature is:
    #     CompensatedRampArrays(cfg, key_from, key_initial, key_to, n_samples)
    # We need a cfg with FF_Qubits and the relevant Gain_* labels.
    n_qubits = 8
    cfg = {
        "fast_flux_chs": list(range(n_qubits)),
        "FF_Qubits": {
            str(i + 1): {
                "channel": i,
                "delay_time": 0.0,
                "Gain_Pulse":   2886 if i == 0 else 0,
                "ramp_initial_gain": 2886 if i == 0 else 0,
                "Gain_Expt":    0,
                "Gain_BS":      0,
                "Gain_Dynamics": 0,
                "Gain_Readout": 0,
            }
            for i in range(n_qubits)
        },
        "expt_samples_ramp": 200,
    }
    try:
        arrays = FFEnvelope_Helpers.CompensatedRampArrays(
            cfg, "Gain_Pulse", "ramp_initial_gain", "Gain_Expt",
            cfg["expt_samples_ramp"],
        )
    except Exception as exc:
        print(f"[demo_4] CompensatedRampArrays failed (expected if the "
              f"crosstalk matrix isn't loaded): {exc}")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    samples = np.arange(len(arrays[0]))
    for ch, arr in enumerate(arrays):
        ax.plot(samples, arr, label=f"FF ch {ch}")
    ax.set_xlabel("Sample (0.291 ns each)")
    ax.set_ylabel("DAC amplitude (compensated)")
    ax.set_title("Compensated FF ramp on Q1; off-channels carry crosstalk-correction")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    out = Path(__file__).with_suffix("").parent / "demo4_ff_ramp.png"
    fig.savefig(out)
    print(f"[demo_4] Saved {out.name}")


# ---------------------------------------------------------------------------
# Demo 5: a 5-line custom experiment skeleton
# ---------------------------------------------------------------------------

def demo_5_echo_skeleton() -> None:
    """Write out a minimal Hahn-echo experiment as a `.py` file you can
    drop into Desq via Load Exp. We don't run it here; we just print the
    file content so you can save it manually.
    """
    src = '''
"""Hahn-echo (T2E) experiment — minimal skeleton."""
import numpy as np
import matplotlib.pyplot as plt
import scipy.optimize
from qick.asm_v2 import QickSweep1D

from WorkingProjects.triangle_lattice_quench.Experiment import ExperimentClass
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Helpers.IQ_contrast import IQ_contrast


class EchoProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"], mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for ch, f in zip(cfg["ro_chs"], cfg["res_freqs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][0],
                                 freq=f, gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const",
                       mask=cfg["ro_chs"], length=cfg["res_length"])

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"],
                       length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name="pi2",
                       style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0], phase=0,
                       gain=cfg["qubit_gains"][0] / 2.0)
        self.add_pulse(ch=cfg["qubit_ch"], name="pi",
                       style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0], phase=0,
                       gain=cfg["qubit_gains"][0])
        # Inner sweep: half-delay tau (so total wait is 2*tau).
        self.add_loop("tau_loop", cfg["expts"])
        self.tau = QickSweep1D("tau_loop", start=0, end=cfg["stop_delay_us"] / 2)

    def _body(self, cfg):
        FF_pad = 10
        # Hold flux during the whole pulse train.
        total = self.qubit_length_us := cfg["sigma"] * 4
        self.FFPulses(self.FFPulse, 3 * total + FF_pad + cfg["stop_delay_us"])
        self.pulse(ch=cfg["qubit_ch"], name="pi2", t=FF_pad)
        self.delay(self.tau, tag="tau1")
        self.pulse(ch=cfg["qubit_ch"], name="pi", t="auto")
        self.delay(self.tau, tag="tau2")
        self.pulse(ch=cfg["qubit_ch"], name="pi2", t="auto")
        self.delay_auto()

        # Standard mux readout.
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, td in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=td)
        self.pulse(cfg["res_ch"], name="res_drive")
        self.wait_auto()
        self.delay_auto(10)
        # Compensation
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, 3 * total + FF_pad + cfg["stop_delay_us"])


class T2EchoMUX(ExperimentClass):
    def acquire(self, progress=False):
        prog = EchoProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                        final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get("rounds", 1), progress=progress)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = 2 * prog.get_time_param("tau2", "t", as_array=True)
        self.data = {"config": self.cfg,
                     "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq}}
        return self.data

    def display(self, data=None, plotDisp=False, ax=None, **kwargs):
        if data is None: data = self.data
        x_pts = data["data"]["x_pts"]
        c = IQ_contrast(data["data"]["avgi"], data["data"]["avgq"])
        if ax is None:
            fig, ax = plt.subplots(); own = True
        else:
            fig = ax.figure; own = False
        ax.plot(x_pts, c, "o-")
        ax.set_xlabel("Total wait (us)")
        ax.set_ylabel("IQ contrast")
        ax.set_title("Hahn echo")
        fig.savefig(self.iname[:-4] + ".png")
        if plotDisp and own:
            plt.show(block=False)

    def save_data(self, data=None):
        super().save_data(data=data["data"])
'''
    out = Path(__file__).parent / "demo5_t2echo_skeleton.py"
    out.write_text(src.lstrip(), encoding="utf-8")
    print(f"[demo_5] Wrote skeleton to {out.name}. "
          "Drop this into Desq via Load Exp to try it.")


# ---------------------------------------------------------------------------
# Demo 6: read a confusion matrix and apply correction
# ---------------------------------------------------------------------------

def demo_6_confusion() -> None:
    """Build a synthetic confusion matrix from typical contrast errors,
    apply the correction to a fake measured-population trace, and compare."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from WorkingProjects.triangle_lattice_quench.Helpers.rotate_SS_data import (
            correct_occ,
        )
    except Exception as exc:
        print(f"[demo_6] correct_occ unavailable: {exc}")
        return

    ne = 0.05  # P(measure |e> | prepare |g>)
    ng = 0.04  # P(measure |g> | prepare |e>)
    cm = np.array([[1 - ng,        ne],
                   [    ng,    1 - ne]])
    print(f"[demo_6] Confusion matrix:\n{cm}")
    # Simulated measured populations (a clean Rabi)
    t = np.linspace(0, 2 * np.pi, 50)
    p_excited_true = (1 - np.cos(t)) / 2.0
    measured = (1 - ng) * p_excited_true + ne * (1 - p_excited_true)
    corrected = correct_occ(measured, cm)
    fig, ax = plt.subplots()
    ax.plot(t, p_excited_true, "k-", label="true P(|e>)")
    ax.plot(t, measured,        "C1.", label="measured (with readout error)")
    ax.plot(t, corrected,       "C2x", label="corrected")
    ax.set_xlabel("phase")
    ax.set_ylabel("P(|e>)")
    ax.legend()
    out = Path(__file__).with_suffix("").parent / "demo6_confusion.png"
    fig.savefig(out)
    print(f"[demo_6] Saved {out.name}. corrected should overlay true.")


DEMOS = {
    "demo_1": demo_1_inspect_h5,
    "demo_2": demo_2_tproc_dump,
    "demo_3": demo_3_cfg_walkthrough,
    "demo_4": demo_4_ff_crosstalk,
    "demo_5": demo_5_echo_skeleton,
    "demo_6": demo_6_confusion,
}


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in DEMOS:
        DEMOS[argv[1]]()
        return 0
    if len(argv) > 1:
        print(f"Unknown demo {argv[1]!r}. Choose from {list(DEMOS)}.")
        return 1
    for name, fn in DEMOS.items():
        print(f"\n========== {name} ==========")
        try:
            fn()
        except Exception as exc:
            print(f"[{name}] failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
