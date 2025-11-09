"""
==========================
ChevronTesterExperiment.py
==========================
A Tester experiment for generating synthetic 2D chevron data to exercise GUI plotting
and fitting pipelines without any RFSoC connection.

Important: Set the TESTING variable in Desq.py to True.
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from Pyro4 import Proxy
from qick import QickConfig

from PyQt5.QtCore import pyqtSignal

from MasterProject.Client_modules.Desq_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from MasterProject.Client_modules.Desq_GUI.CoreLib.VoltageInterface import VoltageInterface


class ChevronTesterProgram():
    def __init__(self, soccfg, cfg):
        self.soccfg = soccfg
        self.cfg = cfg

    def initialize(self):
        print("ChevronTester initialized config: " + str(self.cfg))

    def body(self):
        print("ChevronTester measuring")
        time.sleep(0.1)

    def update(self):
        print("ChevronTester updating")


class ChevronTesterExperiment(ExperimentClassPlus):
    """
    Synthetic 2D chevron generator for testing GUI and fitting code.
    """

    # Signal sent with intermediate data dict as rows stream in
    intermediateData = pyqtSignal(object)

    # Template config (all values are arbitrary defaults; tune as needed)
    # times are arbitrary "us" units, gains are arbitrary "arb." units
    config_template = {
        "n_gains": 60,
        "n_times": 200,
        "gain_start": -10.0,
        "gain_stop": 10.0,
        "time_start": 0.0,
        "time_stop": 2.0,
        "noise_sigma": 0.03,      # Gaussian noise level
        "sleep_time": 0.0,        # delay between streaming rows (s)
        # randomization ranges for the underlying ground-truth model
        "rand_seed": None,        # or an int for reproducible tests
        "g_min": 0.25,
        "g_max": 0.6,
        "b_scale_min": 0.002,      # b will be scaled by 1/(gain_span^2)
        "b_scale_max": 0.06,
        "tau_scale_min": 0.3,     # tau in [tau_scale_min, tau_scale_max] * (time_stop - time_start)
        "tau_scale_max": 1.2,
        "A_min": 0.4,
        "A_max": 0.9,
    }

    # Hardware Requirement
    hardware_requirement = [Proxy, QickConfig, VoltageInterface]

    def __init__(self, path="", outerFolder="", prefix="data", hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress, is_tester=True)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.voltage_interface = hardware
        self.stop_flag = False

        # build axes and randomize ground-truth params now
        self._init_axes_and_params()

    # ------------------------
    # helpers
    # ------------------------

    def _init_axes_and_params(self):
        c = self.cfg

        self.gains = np.linspace(c["gain_start"], c["gain_stop"], int(c["n_gains"]))
        self.times = np.linspace(c["time_start"], c["time_stop"], int(c["n_times"]))

        # Randomize ground-truth chevron parameters
        rng = np.random.default_rng(c.get("rand_seed", None))
        gain_span = max(1e-9, c["gain_stop"] - c["gain_start"])

        d0 = rng.uniform(c["gain_start"] + 0.15 * gain_span,
                         c["gain_stop"] - 0.15 * gain_span)
        g = rng.uniform(c["g_min"], c["g_max"])
        # b controls the opening; scale w.r.t. span to keep shapes consistent across ranges
        b = rng.uniform(c["b_scale_min"], c["b_scale_max"])
        tau = rng.uniform(c["tau_scale_min"], c["tau_scale_max"]) * (self.times[-1] - self.times[0])
        A = rng.uniform(c["A_min"], c["A_max"])
        y0 = rng.uniform(0.05, 0.95 - 0.6 * A)
        phi0 = rng.uniform(-0.2 * np.pi, 0.2 * np.pi)

        # per-row small random jitters
        self._amp_jitter = rng.normal(0.0, 0.05, size=self.gains.shape)
        self._phase_jitter = rng.normal(0.0, 0.15, size=self.gains.shape)

        self.truth_params = {
            "d0": float(d0),
            "g": float(g),
            "b": float(max(0.0, b)),
            "tau": float(max(1e-6, tau)),
            "A": float(A),
            "y0": float(y0),
            "phi0": float(phi0),
        }

        print(self.truth_params["b"])

    @staticmethod
    def _freq(d, d0, b, g):
        # safe against tiny negatives from FP
        rad = b * (d - d0) ** 2 + g ** 2
        return 2.0 * np.sqrt(np.maximum(rad, 0.0))

    # ------------------------
    # core experiment API
    # ------------------------

    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1,
                smart_normalize=True):
        """
        Streams a synthetic 2D chevron row-by-row and emits intermediateData as it fills.
        The final self.data has:
            data['data']['chevron_Z']: (n_gains x n_times) matrix
            data['data']['times']: 1D time axis
            data['data']['gains']: 1D gain axis
            data['data']['truth_params']: dict of randomized ground truth
        """

        c = self.cfg
        n_gains = int(c["n_gains"])
        n_times = int(c["n_times"])
        noise_sigma = float(c["noise_sigma"])

        # fresh matrix
        Z = np.full((n_gains, n_times), np.nan, dtype=float)

        # base data dict for streaming
        self.data = {
            "config": self.cfg,
            "data": {
                "chevron_Z": Z,
                "times": self.times,
                "gains": self.gains,
                "truth_params": self.truth_params,
            }
        }

        # stream rows
        for i, d in enumerate(self.gains):
            if self.stop_flag:
                break

            # fake "hardware" delay between rows
            if i != 0 and c.get("sleep_time", 0.0) > 0:
                time.sleep(c["sleep_time"])

            # print setting voltages similar to TesterExperiment
            if "DACs" in c:
                for ch in c["DACs"]:
                    print(f"Setting channel {ch} to {d:.4f} (arb.)")

            # generate one chevron row
            f = self._freq(d, self.truth_params["d0"], self.truth_params["b"], self.truth_params["g"])
            A_i = np.clip(self.truth_params["A"] * (1.0 + self._amp_jitter[i]), 0.05, 1.2)
            phi = self.truth_params["phi0"] + self._phase_jitter[i]
            tau = self.truth_params["tau"]
            y0 = self.truth_params["y0"]

            row = y0 + A_i * np.exp(-self.times / tau) * np.cos(2.0 * np.pi * f * self.times + phi)

            if noise_sigma > 0:
                row = row + np.random.normal(0.0, noise_sigma, size=row.shape)

            row = np.clip(row, 0.0, 1.0)
            Z[i, :] = row

            # emit partial update until the final row
            if i != n_gains - 1:
                self.intermediateData.emit(self.data)

        # final data dict
        return self.data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        """
        Display the chevron as a single heatmap, matching TesterExperiment style.
        """

        # default to the experiment's own data
        if data is None:
            data = self.data

        gains = data["data"]["gains"]
        times = data["data"]["times"]
        Z = data["data"]["chevron_Z"]

        # choose an unused figure number like TesterExperiment
        while plt.fignum_exists(num=figNum):
            figNum += 1

        # single-axes layout
        fig, ax = plt.subplots(figsize=(8, 6), num=figNum)
        plt.suptitle("Chevron Tester: Synthetic 2D Chevron")
        ax.set_title("Chevron Heatmap")

        # extent setup for imshow
        t_step = times[1] - times[0] if len(times) > 1 else 1.0
        g_step = gains[1] - gains[0] if len(gains) > 1 else 1.0
        extent = [
            times[0] - t_step / 2.0,
            times[-1] + t_step / 2.0,
            gains[0] - g_step / 2.0,
            gains[-1] + g_step / 2.0,
        ]

        # draw the heatmap
        im = ax.imshow(
            Z,
            aspect="auto",
            extent=extent,
            origin="lower",
            interpolation="none",
        )

        cbar = fig.colorbar(im, ax=ax, extend="both")
        cbar.set_label("a.u.", rotation=90)

        ax.set_ylabel("Gain/Detuning (arb.)")
        ax.set_xlabel("Time (arb.)")

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)

        plt.close(fig)

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        # nothing custom to add

    @classmethod
    def estimate_runtime(self, cfg):
        # quick guess: proportionate to n_gains with small constant
        n_gains = int(cfg.get("n_gains", 60))
        return max(3, int(0.05 * n_gains))
