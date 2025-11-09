"""
==============================
MultiPlotTesterExperiment.py
==============================
Produces three simple Matplotlib windows:
  1) Line plot
  2) Chevron-style heatmap (image)
  3) Singleshot-style histogram

Designed to work with ExperimentClassPlus.go(...).
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtCore import pyqtSignal

from MasterProject.Client_modules.Desq_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus


class MultiPlotTesterExperiment(ExperimentClassPlus):
    """Minimal multi-figure tester with Chevron-like API."""
    intermediateData = pyqtSignal(object)

    # Basic defaults (caller can pass cfg or JSON; ExperimentClassPlus expects one)
    config_template = {
        # Line plot
        "t_start": 0.0,
        "t_stop":  2.0,
        "t_points": 800,
        "line_noise_sigma": 0.02,

        # Heatmap (chevron-like)
        "n_gains": 60,
        "n_times": 200,
        "gain_start": -8.0,
        "gain_stop":   8.0,
        "time_start":  0.0,
        "time_stop":   2.0,
        "image_noise_sigma": 0.03,

        # Histogram
        "n_shots": 1500,
        "class0_mean": 0.0,
        "class0_std": 0.18,
        "class1_mean": 1.0,
        "class1_std": 0.20,
        "class1_prob": 0.5,

        # Optional delay
        "sleep_time": 0.0
    }

    def __init__(self, path="", outerFolder="", prefix="data", hardware=None,
                 cfg=None, config_file=None, progress=None):
        # IMPORTANT: is_tester=True so ExperimentClassPlus skips hardware validation
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         hardware=hardware, cfg=cfg, config_file=config_file,
                         progress=progress, is_tester=True)
        self.stop_flag = False
        self._rng = np.random.default_rng(None)
        self.data = None

    # ---------- helpers ----------

    @staticmethod
    def _freq_chevron(d, d0, b, g):
        # 2 * sqrt( b*(d-d0)^2 + g^2 ), clamp FP noise
        rad = b * (d - d0) ** 2 + g ** 2
        return 2.0 * np.sqrt(np.maximum(rad, 0.0))

    def _make_heatmap(self, c):
        gains = np.linspace(c["gain_start"], c["gain_stop"], int(c["n_gains"]))
        times = np.linspace(c["time_start"], c["time_stop"], int(c["n_times"]))
        Z = np.empty((gains.size, times.size), dtype=float)

        rng = self._rng
        span = max(1e-9, c["gain_stop"] - c["gain_start"])
        d0  = rng.uniform(c["gain_start"] + 0.15*span, c["gain_stop"] - 0.15*span)
        g   = rng.uniform(0.3, 0.6)
        b   = rng.uniform(0.01, 0.05)
        tau = rng.uniform(0.4, 1.0) * (times[-1] - times[0])
        A   = rng.uniform(0.5, 0.9)
        y0  = rng.uniform(0.05, 0.25)
        phi0 = rng.uniform(-0.2*np.pi, 0.2*np.pi)

        amp_jitter   = rng.normal(0.0, 0.05, size=gains.shape)
        phase_jitter = rng.normal(0.0, 0.15, size=gains.shape)

        for i, d in enumerate(gains):
            if self.stop_flag:
                break
            f   = self._freq_chevron(d, d0, b, g)
            Ai  = np.clip(A*(1.0 + amp_jitter[i]), 0.05, 1.2)
            phi = phi0 + phase_jitter[i]
            row = y0 + Ai * np.exp(-times/max(1e-6, tau)) * np.cos(2*np.pi*f*times + phi)
            if c["image_noise_sigma"] > 0:
                row += rng.normal(0.0, c["image_noise_sigma"], size=row.shape)
            Z[i, :] = np.clip(row, 0.0, 1.0)

            # If you want to stream partial rows to the GUI:
            # if i != len(gains) - 1:
            #     self.intermediateData.emit({"data": {"image_Z": Z, "gains": gains, "times": times}})

        return gains, times, Z

    # ---------- core API ----------

    def acquire(self, progress=False, plotDisp=True, figNum=1, **kwargs):
        """Generate simple line, image, and histogram data."""
        c = self.cfg
        rng = self._rng

        # Line data
        t = np.linspace(c["t_start"], c["t_stop"], int(c["t_points"]))
        s = np.sin(2*np.pi*1.3*t) + rng.normal(0, c["line_noise_sigma"], size=t.size)

        # Image (heatmap)
        gains, times, Z = self._make_heatmap(c)

        # Histogram (two-class mixture)
        n = int(c["n_shots"])
        k = rng.binomial(n, c["class1_prob"])
        shots0 = rng.normal(c["class0_mean"], c["class0_std"], size=n-k)
        shots1 = rng.normal(c["class1_mean"], c["class1_std"], size=k)
        shots  = np.concatenate([shots0, shots1])

        if c.get("sleep_time", 0) > 0:
            time.sleep(c["sleep_time"])

        self.data = {
            "config": c,
            "data": {
                "t": t, "s": s,
                "gains": gains, "times": times, "image_Z": Z,
                "shots": shots, "n0": n-k, "n1": k,
            }
        }
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, **kwargs):
        """
        Open three windows: 1) line, 2) heatmap, 3) histogram.
        Matches ExperimentClassPlus.go(display=True) expectations.
        """
        if data is None:
            data = self.data

        t   = data["data"]["t"]
        s   = data["data"]["s"]
        Z   = data["data"]["image_Z"]
        gains = data["data"]["gains"]
        times = data["data"]["times"]
        shots = data["data"]["shots"]
        n0, n1 = data["data"]["n0"], data["data"]["n1"]

        def next_fig(n):
            while plt.fignum_exists(num=n):
                n += 1
            return n

        # 1) Line plot
        figNum = next_fig(figNum)
        fig1, ax1 = plt.subplots(num=figNum, figsize=(7, 4))
        ax1.plot(t, s, lw=1.2)
        ax1.set_title("Line Plot")
        ax1.set_xlabel("Time (arb.)")
        ax1.set_ylabel("Amplitude (arb.)")
        fig1.tight_layout()
        if plotDisp:
            plt.show(block=False);

        # 2) Heatmap (chevron-like)
        figNum = next_fig(figNum + 1)
        fig2, ax2 = plt.subplots(num=figNum, figsize=(7, 5))
        t_step = times[1] - times[0] if len(times) > 1 else 1.0
        g_step = gains[1] - gains[0] if len(gains) > 1 else 1.0
        extent = [times[0] - t_step/2, times[-1] + t_step/2,
                  gains[0] - g_step/2, gains[-1] + g_step/2]
        im = ax2.imshow(Z, aspect="auto", extent=extent, origin="lower", interpolation="none")
        cbar = fig2.colorbar(im, ax=ax2, extend="both")
        cbar.set_label("a.u.", rotation=90)
        ax2.set_title("Heatmap")
        ax2.set_xlabel("Time (arb.)")
        ax2.set_ylabel("Gain/Detuning (arb.)")
        fig2.tight_layout()
        if plotDisp:
            plt.show(block=False);

        # 3) Histogram
        figNum = next_fig(figNum + 1)
        fig3, ax3 = plt.subplots(num=figNum, figsize=(7, 4))
        ax3.hist(shots, bins=60, alpha=0.9, density=True)
        ax3.set_title(f"Singleshot Histogram (n0={n0}, n1={n1})")
        ax3.set_xlabel("Readout value (arb.)")
        ax3.set_ylabel("Probability density")
        fig3.tight_layout()
        if plotDisp:
            plt.show(block=False); plt.pause(0.05)

        # Leave windows open; your plt.show interceptor/GUI can manage/close them.

    @classmethod
    def export_data(cls, data_file, data, config):
        # Use the base-class HDF5 exporter
        super().export_data(data_file, data, config)

    @classmethod
    def estimate_runtime(cls, cfg):
        # trivial estimate: tied to heatmap rows
        return max(1, int(0.03 * int(cfg.get("n_gains", 60))))
