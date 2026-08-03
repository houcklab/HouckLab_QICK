from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *
class CavitySpecFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])  # Readout
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                             ro_ch=cfg["ro_chs"][0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(200)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]))

    # ====================================================== #

class CavitySpecFF(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        fpts = np.linspace(self.cfg["pulse_freq"] - self.cfg["TransSpan"],
                           self.cfg["pulse_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["pulse_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=1,))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp=False, figNum=1, fit=True, **kwargs):
        if data is None:
            data = self.data

        avgi = np.asarray(data["data"]["results"][0][0][0], dtype=float)
        avgq = np.asarray(data["data"]["results"][0][0][1], dtype=float)
        fpts = np.asarray(data["data"]["fpts"], dtype=float)  # MHz IF-style axis

        x_pts = (fpts + self.cfg["cavity_LO"] / 1e6) / 1e3  # GHz absolute axis
        sig = avgi + 1j * avgq
        amp = np.abs(sig)
        y_db = 20 * np.log10(amp)

        raw_min_idx = np.argmin(y_db)
        raw_min_freq_mhz = float(fpts[raw_min_idx])
        raw_min_freq_ghz = float(x_pts[raw_min_idx])
        raw_min_val_db = float(y_db[raw_min_idx])

        fit_result = None

        if fit:
            try:
                # Better automatic starting point from the actual trace
                span_mhz = float(np.max(fpts) - np.min(fpts))
                y_edge = 0.5 * (np.median(y_db[:max(3, len(y_db) // 10)]) +
                                np.median(y_db[-max(3, len(y_db) // 10):]))
                depth_db = float(y_edge - raw_min_val_db)

                center_guess = raw_min_freq_mhz
                Qtot_guess = max(abs(center_guess) / max(span_mhz / 10, 1e-6), 1e3)
                Qext_guess = Qtot_guess * 1.5

                startpoint = [
                    center_guess,  # f0 [MHz]
                    Qtot_guess,  # Qtot
                    Qext_guess,  # Qext
                    0.0,  # asym
                    0.0  # offset
                ]

                fit_result = fit_hanger_transmission(
                    freq=fpts,
                    amp_db=y_db,
                    startpoint=startpoint
                )

                popt = fit_result["popt"]
                perr = fit_result["perr"]

                f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit = popt
                df0_fit, dQtot_fit, dQext_fit, dasym_fit, doffset_fit = perr
                Qint_fit = fit_result["Qint"]
                kappa_mhz = (f0_fit / Qext_fit) / 1e6

                x_fit_dense = np.linspace(np.min(fpts), np.max(fpts), 4000)
                y_fit_dense = fit_result["model"](x_fit_dense, *popt)
                fit_min_idx = np.argmin(y_fit_dense)
                fit_min_freq_mhz = float(x_fit_dense[fit_min_idx])
                fit_min_freq_ghz = float((fit_min_freq_mhz + self.cfg["cavity_LO"] / 1e6) / 1e3)
                fit_min_val_db = float(y_fit_dense[fit_min_idx])

                self.cfg["pulse_freq"] = fit_min_freq_mhz
                self.peakFreq_min = fit_min_freq_mhz

                data["data"]["hanger_fit_popt"] = np.asarray(popt)
                data["data"]["hanger_fit_perr"] = np.asarray(perr)
                data["data"]["hanger_fit_f0_mhz"] = np.asarray(f0_fit)
                data["data"]["hanger_fit_min_freq_mhz"] = np.asarray(fit_min_freq_mhz)
                data["data"]["hanger_raw_min_freq_mhz"] = np.asarray(raw_min_freq_mhz)
                data["data"]["hanger_fit_Qtot"] = np.asarray(Qtot_fit)
                data["data"]["hanger_fit_Qext"] = np.asarray(Qext_fit)
                data["data"]["hanger_fit_Qint"] = np.asarray(Qint_fit)
                data["data"]["hanger_fit_kappa_mhz"] = np.asarray(kappa_mhz)

                print("Hanger resonator fit:")
                print(
                    f"  raw minimum      = {raw_min_freq_mhz:.6f} MHz / {raw_min_freq_ghz:.9f} GHz, {raw_min_val_db:.3f} dB")
                print(f"  fit f0 parameter = {f0_fit:.6f} ± {df0_fit:.6f} MHz")
                print(
                    f"  fit minimum      = {fit_min_freq_mhz:.6f} MHz / {fit_min_freq_ghz:.9f} GHz, {fit_min_val_db:.3f} dB")
                print(f"  Qtot             = {Qtot_fit:.6e} ± {dQtot_fit:.6e}")
                print(f"  Qext             = {Qext_fit:.6e} ± {dQext_fit:.6e}")
                print(f"  Qint             = {Qint_fit:.6e}")
                print(f"  kappa            = {kappa_mhz:.6f} MHz")
                print(f"  asym             = {asym_fit:.6e} ± {dasym_fit:.6e}")
                print(f"  offset           = {offset_fit:.6e} ± {doffset_fit:.6e}")

            except Exception as err:
                print(f"Hanger fit failed: {err}")
                fit_result = None

        self.data = data

        # I/Q/Amp plot
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, ".-", color="Green", label="I")
        plt.plot(x_pts, avgq, ".-", color="Blue", label="Q")
        plt.plot(x_pts, amp, color="Magenta", label="Amp")
        plt.axvline(
            raw_min_freq_ghz,
            linestyle=":",
            color="blue",
            label=f"Raw min = {raw_min_freq_ghz:.9f} GHz"
        )
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.iname)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # Hanger fit plot
        if fit_result is not None:
            popt = fit_result["popt"]

            x_fit = np.linspace(np.min(fpts), np.max(fpts), 4000)
            y_fit = fit_result["model"](x_fit, *popt)

            x_plot = (fpts + self.cfg["cavity_LO"] / 1e6) / 1e3
            x_fit_plot = (x_fit + self.cfg["cavity_LO"] / 1e6) / 1e3

            fit_min_idx = np.argmin(y_fit)
            fit_min_freq_mhz = float(x_fit[fit_min_idx])
            fit_min_freq_ghz = float(x_fit_plot[fit_min_idx])
            fit_min_val_db = float(y_fit[fit_min_idx])

            fig = plt.figure(figNum + 1)
            plt.plot(
                x_plot,
                y_db,
                "o",
                label=f"Data | raw min = {raw_min_freq_ghz:.9f} GHz, {raw_min_val_db:.2f} dB"
            )
            plt.plot(
                x_fit_plot,
                y_fit,
                "-",
                linewidth=2,
                label=f"Fit | fit min = {fit_min_freq_ghz:.9f} GHz, {fit_min_val_db:.2f} dB"
            )
            plt.axvline(
                raw_min_freq_ghz,
                linestyle=":",
                color="blue",
                linewidth=2,
                label=f"Raw minimum = {raw_min_freq_ghz:.9f} GHz"
            )
            plt.axvline(
                fit_min_freq_ghz,
                linestyle=":",
                color="red",
                linewidth=2,
                label=f"Fit minimum = {fit_min_freq_ghz:.9f} GHz"
            )
            plt.xlabel("Cavity Frequency (GHz)")
            plt.ylabel("Transmission (dB)")
            plt.title("Transmission sweep with hanger fit")
            plt.legend()
            plt.tight_layout()
            plt.savefig(self.iname[:-4] + "_hanger_fit.png")

            if plotDisp:
                plt.show(block=True)
                plt.pause(0.1)
            else:
                fig.clf(True)
                plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





