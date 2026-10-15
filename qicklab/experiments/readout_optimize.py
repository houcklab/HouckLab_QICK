"""2-D single-shot fidelity / overlap maps for readout and qubit-pulse optimisation."""

import datetime
import time

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.readout import MixedShots, hist_process
from qicklab.core.experiment import ExperimentClass
from qicklab.experiments.single_shot import SingleShotProgram


class ReadOpt_wSingleShotFF(ExperimentClass):
    """Sweep readout gain x readout frequency; g/e single-shot fidelity and overlap
    error per point. See docs/experiments/readout_optimize.md."""

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
        calibrate=True,
        cavityAtten=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            prefix=prefix,
            outerFolder=outerFolder,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(
        self,
        progress=False,
        plotDisp=True,
        plotSave=True,
        calibrate=False,
        cavityAtten=None,
        figNum=1,
    ):
        expt_cfg = {
            "cav_gain_Start": self.cfg["cav_gain_Start"],
            "cav_gain_Stop": self.cfg["cav_gain_Stop"],
            "cav_gain_Points": self.cfg["cav_gain_Points"],
            "trans_freq_start": self.cfg["trans_freq_start"],
            "trans_freq_stop": self.cfg["trans_freq_stop"],
            "TransNumPoints": self.cfg["TransNumPoints"],
        }
        self.gain_pts = np.linspace(
            expt_cfg["cav_gain_Start"], expt_cfg["cav_gain_Stop"], expt_cfg["cav_gain_Points"]
        )
        self.trans_fpts = np.linspace(
            expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"]
        )
        print("Gain pts: ", self.gain_pts)
        print("Frequency pts: ", self.trans_fpts)

        X = self.trans_fpts
        print(X)
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)
        print(X)
        print(Y)
        self.data = {
            "config": self.cfg,
            "data": {
                "fid_mat": Z_fid,
                "overlap_mat": Z_overlap,
                "trans_fpts": self.trans_fpts,
                "gain_pts": self.gain_pts,
            },
        }

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(8, 10), num=figNum)
        plt.suptitle(self.titlename)

        startTime = datetime.datetime.now()
        print("starting date time: " + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        for idf_cavgain in range(len(self.gain_pts)):
            self.cfg["pulse_gains"] = [self.gain_pts[idf_cavgain] / 32000]
            self.cfg["pulse_gain"] = int(self.gain_pts[idf_cavgain])

            for idx_trans in range(len(self.trans_fpts)):
                self.cfg["pulse_freq"] = self.trans_fpts[idx_trans]
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()
                if plt.fignum_exists(10):
                    plt.close(10)

                fid, threshold, angle = hist_process(
                    data=[i_g, q_g, i_e, q_e],
                    plot=False,
                    ran=None,
                    figNum=10,
                    print_fidelities=False,
                    normalize="per_class",
                )
                print(
                    "Fidelity: ",
                    fid,
                    "Threshold: ",
                    threshold,
                    "Angle: ",
                    angle,
                    "Gain",
                    int(self.gain_pts[idf_cavgain]),
                    "Frequency: ",
                    self.cfg["pulse_freq"],
                )

                Z_fid[idf_cavgain, idx_trans] = fid
                self.data["data"]["fid_mat"][idf_cavgain, idx_trans] = fid

                if idf_cavgain == 0 and idx_trans == 0:
                    ax_plot_0 = axs[0].imshow(
                        Z_fid * 100,
                        aspect="auto",
                        extent=[
                            X[0] - X_step / 2,
                            X[-1] + X_step / 2,
                            Y[0] - Y_step / 2,
                            Y[-1] + Y_step / 2,
                        ],
                        origin="lower",
                        interpolation="none",
                    )
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend="both")
                    cbar0.set_label("fidelity (%)", rotation=90)
                else:
                    ax_plot_0.set_data(Z_fid * 100)
                    ax_plot_0.autoscale()
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend="both")
                    cbar0.set_label("fidelity (%)", rotation=90)

                axs[0].set_ylabel("Cavity Gain (a.u.)")
                axs[0].set_xlabel("Cavity Frequency (GHz)")
                axs[0].set_title("fidelity")

                # Overlap metric: g+e shots pooled for an arb/flat_top drive, e shots only
                # for a const drive (docs/experiments/readout_optimize.md).
                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                    mixed_i = np.concatenate((i_g, i_e))
                    mixed_q = np.concatenate((q_g, q_e))

                    mixed = MixedShots(mixed_i, mixed_q)

                    overlapErr = mixed.OverlapErr

                    Z_overlap[idf_cavgain, idx_trans] = overlapErr
                    self.data["data"]["overlap_mat"][idf_cavgain, idx_trans] = overlapErr

                elif self.cfg["qubit_pulse_style"] == "const":
                    mixed = MixedShots(i_e, q_e)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idf_cavgain, idx_trans] = overlapErr
                    self.data["data"]["overlap_mat"][idf_cavgain, idx_trans] = overlapErr

                if idf_cavgain == 0 and idx_trans == 0:
                    ax_plot_1 = axs[1].imshow(
                        Z_overlap,
                        aspect="auto",
                        extent=[
                            X[0] - X_step / 2,
                            X[-1] + X_step / 2,
                            Y[0] - Y_step / 2,
                            Y[-1] + Y_step / 2,
                        ],
                        origin="lower",
                        interpolation="none",
                    )
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend="both")
                    cbar1.set_label("overlap err (a.u.)", rotation=90)
                else:
                    ax_plot_1.set_data(Z_overlap)
                    ax_plot_1.autoscale()
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend="both")
                    cbar1.set_label("overlap err (a.u.)", rotation=90)

                axs[1].set_ylabel("Cavity Atten (dB")
                axs[1].set_xlabel("Cavity Frequency (GHz)")
                axs[1].set_title("overlap err")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)

                if idf_cavgain == 0 and idx_trans == 0:
                    t_delta = time.time() - start
                    timeEst = t_delta * expt_cfg["cav_gain_Points"] * expt_cfg["TransNumPoints"]
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print("Time for 1 sweep: " + str(round(t_delta / 60, 2)) + " min")
                    print("estimated total time: " + str(round(timeEst / 60, 2)) + " min")
                    print("estimated end: " + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print("actual end: " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)

        return self.data

    def _acquireSingleShotData(self):
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig, shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie, shots_qe = prog.acquire(self.soc, load_pulses=True)

        i_g = shots_ig[0][0]
        q_g = shots_qg[0][0]
        i_e = shots_ie[0][0]
        q_e = shots_qe[0][0]

        fid, threshold, angle = hist_process(
            data=[i_g, q_g, i_e, q_e],
            plot=False,
            ran=None,
            print_fidelities=False,
            normalize="per_class",
        )

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


# Drift of the |g> reference across one qubit-gain row, as a fraction of the row's g-e
# separation, above which QubitPulseOpt_wSingleShotFF.acquire() prints a warning ...
G_DRIFT_WARN_FRAC = 0.05
# ... provided the shift is also this many standard errors of a median difference, so a
# small g-e separation (frac = noise / small number) does not trigger it on noise alone.
G_DRIFT_WARN_NSE = 3.0


def g_reference_drift(g_start, g_end, e_ref):
    """Shift of the |g> cloud between two reference blocks, measured along the g->e axis.

    ``g_start``, ``g_end`` and ``e_ref`` are (I, Q) shot arrays. The axis is the median-to-median
    line from ``g_start`` to ``e_ref`` (the axis ``hist_process`` rotates onto). Returns
    ``(frac, n_sigma)``: the median of ``g_end`` minus the median of ``g_start``, projected on
    that axis, divided by the g-e median separation (``frac``) and by the spread of ``g_start``
    along the axis, 1.4826 x MAD (``n_sigma``). Positive means g moved toward e. NaN when the
    separation (or the spread) is zero. See docs/experiments/qubit_optimize.md.
    """
    gs = np.array([np.median(g_start[0]), np.median(g_start[1])])
    ge = np.array([np.median(g_end[0]), np.median(g_end[1])])
    e = np.array([np.median(e_ref[0]), np.median(e_ref[1])])
    sep = float(np.hypot(*(e - gs)))
    if not sep > 0:
        return np.nan, np.nan
    axis = (e - gs) / sep
    shift = float(np.dot(ge - gs, axis))
    proj = np.asarray(g_start[0]) * axis[0] + np.asarray(g_start[1]) * axis[1]
    spread = 1.4826 * float(np.median(np.abs(proj - np.median(proj))))
    return shift / sep, (shift / spread if spread > 0 else np.nan)


class QubitPulseOpt_wSingleShotFF(ExperimentClass):
    """Sweep qubit gain x qubit frequency; g/e single-shot fidelity and overlap error
    per point. The |g> reference plays no qubit pulse, so it is taken once per row boundary
    (rows + 1 blocks), not per point: each point is analysed against the nearer of the two g
    blocks that bracket its gain row, and the g drift across the row is recorded.
    See docs/experiments/qubit_optimize.md."""

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
        calibrate=True,
        cavityAtten=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            prefix=prefix,
            outerFolder=outerFolder,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(
        self,
        progress=False,
        plotDisp=True,
        plotSave=True,
        calibrate=False,
        cavityAtten=None,
        figNum=1,
        Qubit_Sweep_Index=0,
    ):
        expt_cfg = {
            "qubit_gain_Start": self.cfg["qubit_gain_Start"],
            "qubit_gain_Stop": self.cfg["qubit_gain_Stop"],
            "qubit_gain_Points": self.cfg["qubit_gain_Points"],
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "QubitNumPoints": self.cfg["QubitNumPoints"],
        }
        self.gain_pts = np.linspace(
            expt_cfg["qubit_gain_Start"], expt_cfg["qubit_gain_Stop"], expt_cfg["qubit_gain_Points"]
        )
        self.qubit_fpts = np.linspace(
            expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["QubitNumPoints"]
        )

        X = self.qubit_fpts
        X_step = X[1] - X[0]
        Y = self.gain_pts
        Y_step = Y[1] - Y[0]
        n_rows, n_cols = len(Y), len(X)
        Z_fid = np.full((n_rows, n_cols), np.nan)
        Z_overlap = np.full((n_rows, n_cols), np.nan)
        # g block b is taken before gain row b (b = n_rows: after the last row); row r is
        # bracketed by blocks r and r + 1.
        g_ref_index = np.full((n_rows, n_cols), -1)
        g_block_time = np.full(n_rows + 1, np.nan)
        g_drift_frac = np.full(n_rows, np.nan)
        g_drift_sigma = np.full(n_rows, np.nan)

        self.data = {
            "config": self.cfg,
            "data": {
                "fid_mat": Z_fid,
                "overlap_mat": Z_overlap,
                "qubit_fpts": self.qubit_fpts,
                "gain_pts": self.gain_pts,
                "g_ref_index": g_ref_index,
                "g_block_time": g_block_time,
                "g_drift_frac": g_drift_frac,
                "g_drift_sigma": g_drift_sigma,
            },
        }

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(8, 10), num=figNum)
        plt.suptitle(self.titlename)
        extent = [X[0] - X_step / 2, X[-1] + X_step / 2, Y[0] - Y_step / 2, Y[-1] + Y_step / 2]
        panels = (
            (Z_fid, 100, "fidelity (%)", "fidelity"),
            (Z_overlap, 1, "overlap err (a.u.)", "overlap err"),
        )
        images, cbars = [], []

        def redraw():
            for k, (Z, scale, label, title) in enumerate(panels):
                if k == len(images):
                    images.append(
                        axs[k].imshow(
                            Z * scale,
                            aspect="auto",
                            extent=extent,
                            origin="lower",
                            interpolation="none",
                        )
                    )
                    cbars.append(None)
                else:
                    images[k].set_data(Z * scale)
                    images[k].autoscale()
                    cbars[k].remove()
                cbars[k] = fig.colorbar(images[k], ax=axs[k], extend="both")
                cbars[k].set_label(label, rotation=90)
                axs[k].set_ylabel("Qubit Gain (a.u.)")
                axs[k].set_xlabel("Qubit Frequency (GHz)")
                axs[k].set_title(title)
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

        def analyse(row, col, g, e, block):
            i_g, q_g = g
            i_e, q_e = e
            if plt.fignum_exists(10):
                plt.close(10)
            fid, threshold, angle = hist_process(
                data=[i_g, q_g, i_e, q_e],
                plot=False,
                ran=None,
                figNum=10,
                normalize="per_class",
                print_fidelities=True,
            )
            self.fid, self.threshold, self.angle = fid, threshold, angle
            Z_fid[row, col] = fid
            g_ref_index[row, col] = block
            print(
                "Fidelity: ",
                fid,
                "gain: ",
                int(self.gain_pts[row]),
                "frequency: ",
                self.qubit_fpts[col],
            )
            # Overlap metric: g+e shots pooled for an arb/flat_top drive, e shots only
            # for a const drive (docs/experiments/qubit_optimize.md).
            if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                mixed = MixedShots(np.concatenate((i_g, i_e)), np.concatenate((q_g, q_e)))
                Z_overlap[row, col] = mixed.OverlapErr
            elif self.cfg["qubit_pulse_style"] == "const":
                Z_overlap[row, col] = MixedShots(i_e, q_e).OverlapErr

        startTime = datetime.datetime.now()
        print("starting date time: " + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        def take_g(block):
            g = self._acquire_shots(pulse=False)
            g_block_time[block] = (datetime.datetime.now() - startTime).total_seconds()
            return g

        g_next = take_g(0)
        t_g = time.time() - start
        # Points [0, split) are nearer in time to the row's opening g block, the rest to its
        # closing one; the latter are analysed once the closing block is in.
        split = (n_cols + 1) // 2

        for idf_qubitgain in range(n_rows):
            self.cfg["qubit_gain"] = int(self.gain_pts[idf_qubitgain])
            g_start = g_next
            e_shots = []
            for idx_qubit in range(n_cols):
                t_point = time.time()
                self.cfg["f_ge"] = self.qubit_fpts[idx_qubit]
                e_shots.append(self._acquire_shots(pulse=True))
                if idx_qubit < split:
                    analyse(idf_qubitgain, idx_qubit, g_start, e_shots[-1], idf_qubitgain)
                    redraw()

                if idf_qubitgain == 0 and idx_qubit == 0:
                    t_delta = time.time() - t_point
                    timeEst = t_g * (n_rows + 1) + t_delta * n_rows * n_cols
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print("Time for 1 sweep: " + str(round((t_g + t_delta) / 60, 2)) + " min")
                    print("estimated total time: " + str(round(timeEst / 60, 2)) + " min")
                    print("estimated end: " + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

            g_next = take_g(idf_qubitgain + 1)
            for idx_qubit in range(split, n_cols):
                analyse(idf_qubitgain, idx_qubit, g_next, e_shots[idx_qubit], idf_qubitgain + 1)
            if split < n_cols:
                redraw()

            row_fid = Z_fid[idf_qubitgain]
            if np.any(np.isfinite(row_fid)):
                best = int(np.nanargmax(row_fid))
                frac, n_sigma = g_reference_drift(g_start, g_next, e_shots[best])
                g_drift_frac[idf_qubitgain] = frac
                g_drift_sigma[idf_qubitgain] = n_sigma
                # standard error of a difference of two medians, in units of the g width
                se = 1.2533 * np.sqrt(1.0 / len(g_start[0]) + 1.0 / len(g_next[0]))
                if abs(frac) > G_DRIFT_WARN_FRAC and not abs(n_sigma) <= G_DRIFT_WARN_NSE * se:
                    print(
                        f"WARNING: |g> reference drifted {frac:+.3f} of the g-e separation "
                        f"({n_sigma:+.2f} sigma) across gain row {idf_qubitgain} "
                        f"(gain {int(self.gain_pts[idf_qubitgain])}); that row of the map may "
                        "be biased (docs/experiments/qubit_optimize.md)."
                    )

        print("actual end: " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)

        return self.data

    def _acquire_shots(self, pulse):
        """One SingleShotProgram run, (I, Q) shots of the first readout. pulse=False is the
        |g> reference. Leaves cfg["Pulse"] True, the value the saved cfg records."""
        self.cfg["Pulse"] = pulse
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)
        self.cfg["Pulse"] = True
        return shots_i[0][0], shots_q[0][0]

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
