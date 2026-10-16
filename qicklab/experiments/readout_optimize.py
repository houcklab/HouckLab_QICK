"""2-D single-shot fidelity / overlap maps for readout and qubit-pulse optimisation."""

import datetime
import time

import matplotlib.pyplot as plt
import numpy as np

from qicklab.analysis.readout import (
    calibrate_readout_from_labeled_shots,
    hist_process,
    labelled_overlap_error,
    readout_assignment_errors,
)
from qicklab.core.experiment import ExperimentClass
from qicklab.experiments.single_shot import SingleShotProgram

# Side of the NaN-aware box filter summarize_contrast_map() smooths the contrast map with.
SMOOTH_SIZE = 3


def contrast_point_stats(i_g, q_g, i_e, q_e, fid, threshold, angle):
    """(Pgg, Pee, fid_err) of one g/e single-shot pair at hist_process's (threshold, angle).

    Pgg = P(assigned g | prepared g) and Pee = P(assigned e | prepared e) are counted with
    ``readout_assignment_errors`` (rotate by ``angle``, excited := I' > ``threshold``), so
    Pgg + Pee - 1 is the contrast ``fid`` hist_process returned; a mismatch beyond float
    tolerance prints a warning. fid_err = sqrt(Pgg(1 - Pgg)/Ng + Pee(1 - Pee)/Ne), with the
    actual class sizes Ng, Ne, is the binomial standard error of the contrast at a fixed
    threshold. It ignores that the threshold was chosen on the same shots to maximise the
    contrast, which biases C upward by a further ~0.003-0.011 (under 0.5 fid_err) at 1000
    shots per class for well-separated clouds (C >~ 0.4), ~0.015 at C ~ 0.1-0.2, and ~0.04
    (about 2 fid_err) at zero true contrast, so off-resonant or low-gain points read
    C ~ 0.04 +/- 0.02 rather than 0. NaN for an empty class. See
    docs/experiments/readout_optimize.md#analysis.
    """
    p_e_given_g, p_g_given_e = readout_assignment_errors(i_g, q_g, i_e, q_e, angle, threshold)
    pgg, pee = 1.0 - p_e_given_g, 1.0 - p_g_given_e
    if np.isfinite(fid) and not abs(pgg + pee - 1.0 - fid) <= 1e-9:
        print(
            f"WARNING: Pgg + Pee - 1 = {pgg + pee - 1.0!r} differs from the contrast {fid!r} "
            "(threshold and rotation do not reproduce hist_process)."
        )
    n_g, n_e = np.size(i_g), np.size(i_e)
    if n_g == 0 or n_e == 0:
        return pgg, pee, np.nan
    return pgg, pee, float(np.sqrt(pgg * (1.0 - pgg) / n_g + pee * (1.0 - pee) / n_e))


def analog_snr(i_g, q_g, i_e, q_e):
    """snr_analog of calibrate_readout_from_labeled_shots (the number the parity readout gates
    use: moment separation / pooled moment std, prep errors included); NaN when it raises."""
    try:
        return calibrate_readout_from_labeled_shots(i_g, q_g, i_e, q_e)["snr_analog"]
    except ValueError:
        return np.nan


def _box_sum(a, size):
    """Sum of each size x size neighbourhood, edges extended by the nearest value."""
    r = size // 2
    padded = np.pad(a, r, mode="edge")
    out = np.zeros(a.shape, dtype=padded.dtype)
    for di in range(size):
        for dj in range(size):
            out = out + padded[di : di + a.shape[0], dj : dj + a.shape[1]]
    return out


def summarize_contrast_map(fid_mat, fid_err_mat, gain_pts, freq_pts, size=SMOOTH_SIZE):
    """Recommended grid point of a gain (rows) x frequency (columns) contrast map.

    The map is smoothed with a NaN-aware ``size`` x ``size`` box filter (mean of the finite
    neighbours, edges extended by the nearest value) to damp the winner's curse of picking the
    brightest raw pixel; no 2-D fit. The recommendation is the argmax of the smoothed map over
    the points that have a finite contrast. Returns a dict of h5-ready values:
    ``fid_smooth_mat``; ``best_gain``, ``best_freq`` (axis values there), ``best_fid`` and
    ``best_fid_err`` (raw contrast and its standard error there), ``best_fid_smooth`` (the
    smoothed maximum); ``tied_mask`` (points with fid_mat >= best_fid_smooth - best_fid_err,
    i.e. within one standard error of the smoothed maximum); ``median_fid_err``. Scalars are
    NaN and ``tied_mask`` all False when no point is finite. Works for single-row or
    single-column grids. See docs/experiments/readout_optimize.md#analysis.
    """
    fid = np.asarray(fid_mat, dtype=float)
    err = np.asarray(fid_err_mat, dtype=float)
    finite = np.isfinite(fid)
    total = _box_sum(np.where(finite, fid, 0.0), size)
    count = _box_sum(finite.astype(np.int64), size)
    smooth = np.full(fid.shape, np.nan)
    np.divide(total, count, out=smooth, where=count > 0)
    finite_err = err[np.isfinite(err)]
    out = {
        "fid_smooth_mat": smooth,
        "tied_mask": np.zeros(fid.shape, dtype=bool),
        "best_gain": np.nan,
        "best_freq": np.nan,
        "best_fid": np.nan,
        "best_fid_err": np.nan,
        "best_fid_smooth": np.nan,
        "median_fid_err": float(np.median(finite_err)) if finite_err.size else np.nan,
    }
    candidates = np.where(finite, smooth, np.nan)
    if not np.any(np.isfinite(candidates)):
        return out
    row, col = np.unravel_index(int(np.nanargmax(candidates)), fid.shape)
    best_smooth = float(smooth[row, col])
    best_err = float(err[row, col])
    out.update(
        tied_mask=finite & (fid >= best_smooth - best_err),
        best_gain=float(gain_pts[row]),
        best_freq=float(freq_pts[col]),
        best_fid=float(fid[row, col]),
        best_fid_err=best_err,
        best_fid_smooth=best_smooth,
    )
    return out


def contrast_optimum_edges(summary, gain_pts, freq_pts):
    """Axes ("gain", "frequency") on whose first or last point the recommendation lies.

    Only axes with at least 3 points count (on a shorter axis every point is an edge). A
    border point is smoothed over fewer distinct neighbours (edge replication) and so has
    more noise than an interior point: on a map that is flat within noise the smoothed argmax
    lands on the border far more often than the border's share of the grid (about 78% vs
    35% of points on a 7x21 map, 63% vs 18% on 21x21). See
    docs/experiments/readout_optimize.md#analysis.
    """
    edges = []
    if not np.isfinite(summary["best_fid_smooth"]):
        return edges
    for name, best, pts in (
        ("gain", summary["best_gain"], gain_pts),
        ("frequency", summary["best_freq"], freq_pts),
    ):
        pts = np.asarray(pts, dtype=float)
        if pts.size >= 3 and best in (float(pts[0]), float(pts[-1])):
            edges.append(name)
    return edges


def report_contrast_optimum(summary, what, gain_pts, freq_pts):
    """Print the summarize_contrast_map() recommendation for the ``what`` (readout/qubit) map,
    with a warning when it lies on the map border (contrast_optimum_edges)."""
    if not np.isfinite(summary["best_fid_smooth"]):
        print(f"No finite contrast in the {what} map: no recommendation.")
        return
    print(
        f"Recommended {what} point (argmax of the {SMOOTH_SIZE}x{SMOOTH_SIZE}-smoothed contrast; "
        f"NOT written back): gain {summary['best_gain']:.0f}, frequency "
        f"{summary['best_freq']:.4f} MHz: C = {summary['best_fid']:.3f} "
        f"+/- {summary['best_fid_err']:.3f} (smoothed {summary['best_fid_smooth']:.3f}); "
        f"{int(np.sum(summary['tied_mask']))} of {summary['tied_mask'].size} points are within "
        "one standard error of the smoothed maximum (tied_mask)."
    )
    edges = contrast_optimum_edges(summary, gain_pts, freq_pts)
    if edges:
        print(
            f"WARNING: the recommended {what} point is on the edge of the "
            f"{' and '.join(edges)} sweep. Border points are noisier after smoothing, so on a "
            "map that is flat within noise this is usually noise: trust it only if the contrast "
            "clearly rises toward that edge (then extend the sweep); otherwise read tied_mask."
        )


def fid_err_title(fid_err_mat):
    """Colorbar title of the fidelity panel: the median per-point standard error, in %."""
    err = np.asarray(fid_err_mat, dtype=float)
    err = err[np.isfinite(err)]
    return f"median 1 s.e. {np.median(err) * 100:.1f}%" if err.size else ""


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
        snr_mat = np.full((len(Y), len(X)), np.nan)
        fid_err_mat = np.full((len(Y), len(X)), np.nan)
        Pgg_mat = np.full((len(Y), len(X)), np.nan)
        Pee_mat = np.full((len(Y), len(X)), np.nan)
        threshold_mat = np.full((len(Y), len(X)), np.nan)
        angle_mat = np.full((len(Y), len(X)), np.nan)
        print(X)
        print(Y)
        self.data = {
            "config": self.cfg,
            "data": {
                "fid_mat": Z_fid,
                "overlap_mat": Z_overlap,
                "snr_mat": snr_mat,
                "trans_fpts": self.trans_fpts,
                "gain_pts": self.gain_pts,
                "fid_err_mat": fid_err_mat,
                "Pgg_mat": Pgg_mat,
                "Pee_mat": Pee_mat,
                "threshold_mat": threshold_mat,
                "angle_mat": angle_mat,
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
                pgg, pee, fid_err = contrast_point_stats(i_g, q_g, i_e, q_e, fid, threshold, angle)
                fid_err_mat[idf_cavgain, idx_trans] = fid_err
                Pgg_mat[idf_cavgain, idx_trans] = pgg
                Pee_mat[idf_cavgain, idx_trans] = pee
                threshold_mat[idf_cavgain, idx_trans] = threshold
                angle_mat[idf_cavgain, idx_trans] = angle

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
                cbar0.ax.set_title(fid_err_title(fid_err_mat), fontsize=8)

                axs[0].set_ylabel("Cavity Gain (a.u.)")
                axs[0].set_xlabel("Cavity Frequency (GHz)")
                axs[0].set_title("fidelity")

                # Overlap metric: labelled g/e fit for an arb/flat_top/const drive
                # (docs/experiments/readout_optimize.md#analysis).
                snr_mat[idf_cavgain, idx_trans] = analog_snr(i_g, q_g, i_e, q_e)
                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb", "const"]:
                    overlapErr = labelled_overlap_error(i_g, q_g, i_e, q_e)
                    Z_overlap[idf_cavgain, idx_trans] = overlapErr

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

        optimum = summarize_contrast_map(Z_fid, fid_err_mat, self.gain_pts, self.trans_fpts)
        self.data["data"].update(optimum)
        report_contrast_optimum(optimum, "readout", self.gain_pts, self.trans_fpts)

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
        snr_mat = np.full((n_rows, n_cols), np.nan)
        fid_err_mat = np.full((n_rows, n_cols), np.nan)
        Pgg_mat = np.full((n_rows, n_cols), np.nan)
        Pee_mat = np.full((n_rows, n_cols), np.nan)
        threshold_mat = np.full((n_rows, n_cols), np.nan)
        angle_mat = np.full((n_rows, n_cols), np.nan)
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
                "snr_mat": snr_mat,
                "qubit_fpts": self.qubit_fpts,
                "gain_pts": self.gain_pts,
                "g_ref_index": g_ref_index,
                "g_block_time": g_block_time,
                "g_drift_frac": g_drift_frac,
                "g_drift_sigma": g_drift_sigma,
                "fid_err_mat": fid_err_mat,
                "Pgg_mat": Pgg_mat,
                "Pee_mat": Pee_mat,
                "threshold_mat": threshold_mat,
                "angle_mat": angle_mat,
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
                if k == 0:
                    cbars[k].ax.set_title(fid_err_title(fid_err_mat), fontsize=8)
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
            pgg, pee, fid_err = contrast_point_stats(i_g, q_g, i_e, q_e, fid, threshold, angle)
            fid_err_mat[row, col] = fid_err
            Pgg_mat[row, col] = pgg
            Pee_mat[row, col] = pee
            threshold_mat[row, col] = threshold
            angle_mat[row, col] = angle
            print(
                "Fidelity: ",
                fid,
                "gain: ",
                int(self.gain_pts[row]),
                "frequency: ",
                self.qubit_fpts[col],
            )
            # Overlap metric: labelled g/e fit for an arb/flat_top/const drive
            # (docs/experiments/qubit_optimize.md).
            snr_mat[row, col] = analog_snr(i_g, q_g, i_e, q_e)
            if self.cfg["qubit_pulse_style"] in ["flat_top", "arb", "const"]:
                Z_overlap[row, col] = labelled_overlap_error(i_g, q_g, i_e, q_e)

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

        optimum = summarize_contrast_map(Z_fid, fid_err_mat, self.gain_pts, self.qubit_fpts)
        self.data["data"].update(optimum)
        report_contrast_optimum(optimum, "qubit", self.gain_pts, self.qubit_fpts)

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
