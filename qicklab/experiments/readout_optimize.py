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


class QubitPulseOpt_wSingleShotFF(ExperimentClass):
    """Sweep qubit gain x qubit frequency; g/e single-shot fidelity and overlap error
    per point. See docs/experiments/qubit_optimize.md."""

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
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data = {
            "config": self.cfg,
            "data": {
                "fid_mat": Z_fid,
                "overlap_mat": Z_overlap,
                "qubit_fpts": self.qubit_fpts,
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

        for idf_qubitgain in range(len(self.gain_pts)):
            self.cfg["qubit_gain"] = int(self.gain_pts[idf_qubitgain])
            for idx_qubit in range(len(self.qubit_fpts)):
                self.cfg["f_ge"] = self.qubit_fpts[idx_qubit]
                i_g, q_g, i_e, q_e = self._acquireSingleShotData()
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

                Z_fid[idf_qubitgain, idx_qubit] = fid
                self.data["data"]["fid_mat"][idf_qubitgain, idx_qubit] = fid
                print(
                    "Fidelity: ",
                    fid,
                    "gain: ",
                    self.cfg["qubit_gain"],
                    "frequency: ",
                    self.cfg["f_ge"],
                )

                if idf_qubitgain == 0 and idx_qubit == 0:
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

                axs[0].set_ylabel("Qubit Gain (a.u.)")
                axs[0].set_xlabel("Qubit Frequency (GHz)")
                axs[0].set_title("fidelity")

                # Overlap metric: g+e shots pooled for an arb/flat_top drive, e shots only
                # for a const drive (docs/experiments/qubit_optimize.md).
                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                    mixed_i = np.concatenate((i_g, i_e))
                    mixed_q = np.concatenate((q_g, q_e))

                    mixed = MixedShots(mixed_i, mixed_q)

                    overlapErr = mixed.OverlapErr

                    Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
                    self.data["data"]["overlap_mat"][idf_qubitgain, idx_qubit] = overlapErr

                elif self.cfg["qubit_pulse_style"] == "const":
                    mixed = MixedShots(i_e, q_e)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idf_qubitgain, idx_qubit] = overlapErr
                    self.data["data"]["overlap_mat"][idf_qubitgain, idx_qubit] = overlapErr

                if idf_qubitgain == 0 and idx_qubit == 0:
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

                axs[1].set_ylabel("Qubit Gain (a.u.)")
                axs[1].set_xlabel("Qubit Frequency (GHz)")
                axs[1].set_title("overlap err")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)

                if idf_qubitgain == 0 and idx_qubit == 0:
                    t_delta = time.time() - start
                    timeEst = t_delta * expt_cfg["qubit_gain_Points"] * expt_cfg["QubitNumPoints"]
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
            normalize="per_class",
            print_fidelities=True,
        )

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
