import time
import traceback

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram
from tqdm.notebook import tqdm

from qicklab.analysis.fitting import exp_decay_fit_fields, fit_exp_decay
from qicklab.analysis.iq import count_percentage, rotate_data
from qicklab.core.acquisition import acquire_with_retry
from qicklab.core.experiment import ExperimentClass
from qicklab.core.readout import cover_readout_window


def readout_assignment_errors(i_g, q_g, i_e, q_e, angle, threshold):
    """(P(e|g), P(g|e)) of single_shot calibration shots, counted exactly as T1_SS counts:
    rotate by ``angle`` (rotate_data) and call a shot excited when I' > threshold.

    These include the prep errors of the calibration (thermal |e> in the g shots, pi-pulse
    infidelity and decay during readout in the e shots), not only the readout overlap
    (docs/experiments/t1_single_shot.md#analysis). NaN for an empty set.
    """
    out = []
    for i, q, excited in ((i_g, q_g, False), (i_e, q_e, True)):
        i_rot, _ = rotate_data((np.ravel(i), np.ravel(q)), theta=angle)
        if i_rot.size == 0:
            out.append(float("nan"))
            continue
        frac_e = float(np.mean(i_rot > threshold))
        out.append(1.0 - frac_e if excited else frac_e)
    return tuple(out)


def readout_corrected_population(p, eps_g, eps_e):
    """Invert the 2x2 confusion matrix: (p - P(e|g)) / (1 - P(e|g) - P(g|e)), not clipped.

    All NaN when the errors are not finite or 1 - eps_g - eps_e <= 0 (the threshold does not
    separate g from e). Rescales the curve only: it cannot change a fitted T1. When the
    calibration played the same pi pulse (flattop_length None: T1_SS always plays the plain
    Gaussian) it maps t=0 to ~1 and the plateau to ~0 by construction; with a flat-top
    calibration pulse it does not (docs/experiments/t1_single_shot.md#analysis).
    """
    p = np.asarray(p, dtype=float)
    denom = 1.0 - eps_g - eps_e
    if not (np.isfinite(eps_g) and np.isfinite(eps_e) and denom > 0):
        return np.full(p.shape, np.nan)
    return (p - eps_g) / denom


def binomial_sigma(p, n, clip=False):
    """Standard error sqrt(p(1-p)/n) of a fraction of n shots. ``clip`` moves p to at least
    0.5/n from 0 and 1 first, so a fit weight is never infinite (docs: t1_single_shot.md)."""
    p = np.asarray(p, dtype=float)
    if clip:
        p = np.clip(p, 0.5 / n, 1.0 - 0.5 / n)
    return np.sqrt(p * (1.0 - p) / n)


def fit_t1ss_decay(x_pts, p, n):
    """T1 fit of a thresholded excited fraction ``p`` of ``n`` shots per point
    (docs: t1_single_shot.md#analysis). Pass 1 is the unweighted ``fit_exp_decay``; pass 2
    refits with the binomial sigma of pass 1's model curve (``binomial_sigma(yfit, n,
    clip=True)``). Weights from the model, not from the observed p: observed-p weights
    (Neyman chi-square) give the points that fluctuate low too much weight and pull T1 low by
    1-2 sigma when the plateau holds about one excited shot per point. Returns pass 2, or
    pass 1 when it has no finite model curve. Never raises (fit_exp_decay never does)."""
    first = fit_exp_decay(x_pts, p)
    yfit = np.asarray(first.get("yfit", np.nan), dtype=float)
    if yfit.shape != np.shape(p) or not np.all(np.isfinite(yfit)):
        return first
    return fit_exp_decay(x_pts, p, sigma=binomial_sigma(yfit, n, clip=True))


class T1SingleShotProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg["rounds"] = 1

        self.q_rp = self.ch_page(cfg["qubit_ch"])

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        cover_readout_window(self, cfg)
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        self.f_qubit01 = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_qubit01,
            phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
            # the pi gain the run writes (run_t1_ss: ctx.qubit_gain), not the regime-dependent
            # qubit_gain: docs/experiments/t1_single_shot.md#pulse-sequence
            gain=cfg["pi_gain"],
            waveform="qubit",
        )

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.pulse(ch=self.cfg["qubit_ch"])

        self.sync_all(self.us2cycles(self.cfg["variable_wait"]))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def acquire(
        self,
        soc,
        threshold=None,
        angle=None,
        load_pulses=True,
        readouts_per_experiment=1,
        save_experiments=None,
        start_src="internal",
        progress=False,
    ):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        ro_norm = self.readout_window_cycles[self.cfg["ro_chs"][0]]
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / ro_norm
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / ro_norm

        return shots_i0, shots_q0


class T1_SS(ExperimentClass):
    """Single-shot T1: one program per wait, shots thresholded with a single-shot angle and
    threshold into an excited fraction; display fits T1 (docs/experiments/t1_single_shot.md)."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(
        self, threshold=None, angle=None, excited_pulse=2, progress=False, readout_errors=None
    ):
        """``readout_errors`` = (P(e|g), P(g|e)) from the calibration (run_t1_ss), or None:
        adds the readout-corrected fraction next to the raw one."""
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg["Excited_PulseT1"] = excited_pulse

        results = []
        rotated_iq_array = []
        try:
            for t in tqdm(tpts, position=0, disable=True):
                self.cfg["variable_wait"] = t
                print(t)
                start = time.time()
                # fresh program per attempt on the stale-shot-counter race (docs/concepts/averaging.md)
                shots_i0, shots_q0 = acquire_with_retry(
                    lambda: T1SingleShotProgram(self.soccfg, self.cfg),
                    self.soc,
                    label=f"T1_SS wait {t}",
                    load_pulses=True,
                )
                print(time.time() - start)

                rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
                excited_percentage = count_percentage(rotated_iq, threshold=threshold)
                rotated_iq_array.append(rotated_iq)
                results.append(excited_percentage)
        except BaseException as err:
            # keep the completed wait points (docs/experiments/t1_single_shot.md#outputs)
            self._save_partial(results, rotated_iq_array, tpts, threshold, angle, err)
            raise

        results = np.transpose(results)

        self.data = {
            "config": self.cfg,
            "data": {
                "Exp_values": results,
                "Exp_err": binomial_sigma(results, self.cfg["reps"]),
                "RotatedIQ": rotated_iq_array,
                "threshold": threshold,
                "angle": angle,
                "wait_times": tpts,
            },
        }
        if readout_errors is not None:
            eps_g, eps_e = (float(v) for v in readout_errors)
            self.data["data"]["readout_P_e_given_g"] = eps_g
            self.data["data"]["readout_P_g_given_e"] = eps_e
            self.data["data"]["Exp_values_readout_corrected"] = readout_corrected_population(
                results, eps_g, eps_e
            )
        return self.data

    def _save_partial(self, results, rotated_iq_array, tpts, threshold, angle, err):
        """Save the wait points completed before `err`, marked with points_completed; never raises."""
        n_done = len(results)
        if n_done == 0:
            return
        try:
            print(
                f"[T1_SS] aborted after {n_done}/{len(tpts)} wait points ({err!r}); "
                "saving the completed points"
            )
            payload = {
                "Exp_values": np.transpose(results),
                "RotatedIQ": rotated_iq_array[:n_done],
                "threshold": threshold,
                "angle": angle,
                "wait_times": tpts[:n_done],
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            payload["points_completed"] = n_done
            self.cfg["points_completed"] = n_done
            self.cfg["aborted"] = repr(err)
            self.data = {"config": self.cfg, "data": payload}
            self.save_data(self.data)
            self.save_config()
        except Exception:
            traceback.print_exc()
            print("[T1_SS] partial save failed; re-raising the original error")

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data["data"]["wait_times"]
        expectation_values = data["data"]["Exp_values"]
        n_shots = self.cfg["reps"]
        exp_err = binomial_sigma(expectation_values, n_shots)

        # Binomial weights from the model curve (fit_t1ss_decay), clipped off 0 so a plateau
        # at 0 keeps a finite weight.
        # Guarded: a failed fit leaves self.fit = {'ok': False, 'error': ...} and the data plot.
        try:
            fit = fit_t1ss_decay(x_pts, expectation_values, n_shots)
        except Exception as e:
            traceback.print_exc()
            fit = {"ok": False, "error": repr(e)}
        self.fit = fit
        # Saved by save_data (finish() displays first): docs/experiments/t1_single_shot.md#outputs
        data["data"].update(exp_decay_fit_fields(fit, "t1ss"))
        yfit = np.asarray(fit.get("yfit", np.full(np.shape(x_pts), np.nan)), dtype=float)
        data["data"]["t1ss_fit_curve"] = yfit
        if not fit["ok"]:
            print(f"T1_SS fit not reliable: {fit['error']}")

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig = plt.figure(figNum)
        plt.errorbar(x_pts, expectation_values, yerr=exp_err, fmt="o", color="orange", label="data")
        if fit["ok"]:
            plt.plot(x_pts, yfit, "-", color="black", label="fit")
        elif np.all(np.isfinite(yfit)):
            plt.plot(x_pts, yfit, "--", color="gray", label="fit (not reliable)")
        plt.ylabel("Excited fraction (raw)")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(
            self.titlename
            + (
                "  ; T1 = "
                + str(round(fit["T"], 1))
                + r" $\pm$ "
                + str(round(fit["T_err"], 1))
                + "us"
                if fit["ok"]
                else "  ; T1 fit not reliable"
            )
        )
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
