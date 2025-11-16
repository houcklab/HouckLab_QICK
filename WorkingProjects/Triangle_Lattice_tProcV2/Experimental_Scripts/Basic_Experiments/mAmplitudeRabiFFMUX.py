import numpy as np
from qick.asm_v2 import QickSweep1D
from scipy.optimize import curve_fit

from Archive.q4diamond.Client_modules.Running_Experiments_MUX.MUXSimpleExample import x_pts
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast, frequency_guess


class AmplitudeRabiFFProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])


        FF.FFDefinitions(self)

        self.add_loop("qubit_gain_loop", self.cfg["expts"])
        qubit_gain_sweep = QickSweep1D("qubit_gain_loop",
                                       start=0,
                                       end=cfg["max_gain"] / 32766.)


        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][-1],
                       phase=90, gain=qubit_gain_sweep)
        self.qubit_length_us = cfg["sigma"] * 4

        self.delay_auto(0.05)

    def _body(self, cfg):

        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t = 1)  # play probe pulse
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 1)


def fit_func_simple(gain, ampl, pi_gain):
    return ampl * np.cos(gain * np.pi / pi_gain)

def rabi_fit_func(gain, A, pi_gain, offset, phi):
    return offset + A * np.cos(np.pi * gain / pi_gain + phi)

class AmplitudeRabiFFMUX(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        # You would overwrite these in the config if you wanted to
        cfg_ARabi_defaults = {'start': 0, "expts": 31, "reps": 30, "rounds": 30,
                                "f_ge": self.cfg["qubit_freqs"][-1]}
        self.cfg = cfg_ARabi_defaults  | self.cfg
        self.cfg['step'] = int(self.cfg["max_gain"] / self.cfg['expts'])


        prog = AmplitudeRabiFFProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_pulse_param("qubit_drive", "gain", as_array=True) * 32766

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data


        # Attempt a fit
        self.analyze(data)

        return data

    def analyze(self, data=None, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']


        ### Attempt a simple fit
        contrast = IQ_contrast(avgi, avgq)
        try:
            gain_guess = 1 / frequency_guess(x_pts, contrast) / 2
            popt, _ = curve_fit(fit_func_simple, x_pts, contrast, p0=[np.max(contrast), gain_guess])
            self.ampl_fit_simple = popt[0]
            self.pi_gain_fit_simple = np.abs(popt[1])
        except:
            print("Simple Fitting failed")



        ### Attempting more complex fit
        # initial guesses
        pi_gain_guess = 1 / frequency_guess(x_pts, contrast) / 2  # your current guess
        A_guess = 0.5 * (np.max(contrast) - np.min(contrast))
        offset_guess = np.mean(contrast)
        phi_guess = 0.0

        # restrict fit to moderate gains (first ~1–1.5 oscillations) - not sure if needed
        mask = x_pts <= 2 * pi_gain_guess  # don't use crazy-high gains
        x_fit = x_pts[mask]
        y_fit = contrast[mask]

        try:
            # keep pi_gain near the FFT guess (e.g. within a factor of 2)
            lower = [0.0, 0.5 * pi_gain_guess, -np.inf, -np.pi]
            upper = [np.inf, 2.0 * pi_gain_guess, np.inf, np.pi]
            popt, _ = curve_fit(
                rabi_fit_func, x_fit, y_fit,
                p0=[A_guess, pi_gain_guess, offset_guess, phi_guess],
                bounds=(lower, upper),
            )

            A_fit, pi_gain_fit, offset_fit, phi_fit = popt
            self.ampl_fit_complex = A_fit
            self.pi_gain_fit_complex = np.abs(pi_gain_fit)


            # Compare both fits:
            resid = y_fit - rabi_fit_func(x_fit, *popt)
            R2 = 1 - np.var(resid) / np.var(y_fit)
            if R2 < 0.8:
                print("Complex rabi fit looks bad, falling back to simple.")
                if hasattr(self, 'ampl_fit_simple'):
                    self.ampl_fit = self.ampl_fit_simple
                    self.pi_gain_fit = self.pi_gain_fit_simple
            else:
                print("Complex rabi fit looks good.")
                self.ampl_fit = self.ampl_fit_complex
                self.pi_gain_fit = self.pi_gain_fit_complex

        except Exception as e:
            print("Complex Fitting failed:", e)
            # Resort to simple fit if succeeded
            if hasattr(self, 'ampl_fit_simple'):
                self.ampl_fit = self.ampl_fit_simple
                self.pi_gain_fit = self.pi_gain_fit_simple

        if hasattr(self, 'ampl_fit'):
            data['data']['ampl_fit'] = self.ampl_fit
            data['data']['pi_gain_fit'] = self.pi_gain_fit

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        if ax is None:
            plt.figure(figNum)
        else:
            plt.sca(ax)
        if 'ampl_fit' in data['data']:
            contrast = IQ_contrast(avgi, avgq)
            ampl = data['data']['ampl_fit']
            pi_gain = data['data']['pi_gain_fit']
            print(pi_gain)
            gains = np.linspace(x_pts[0], x_pts[-1], 61)
            plt.plot(x_pts, contrast, 'o-', color='seagreen', label='IQ contrast')
            plt.plot(x_pts, avgi - np.mean(avgi), 'o-', label="i", color='orange', alpha=0.5,zorder=0)
            plt.plot(x_pts, avgq - np.mean(avgq), 'o-', label="q", color='blue', alpha=0.5,zorder=0)

            # Plotting fits
            if hasattr(self, 'ampl_fit_simple') and self.ampl_fit_simple == self.ampl_fit:
                plt.plot(gains, fit_func_simple(gains, ampl, pi_gain), '--', color='black')
            elif hasattr(self, 'ampl_fit_complex') and self.ampl_fit_complex == self.ampl_fit:
                plt.plot(gains, rabi_fit_func(gains, ampl, pi_gain), '--', color='black')

            plt.axvline(pi_gain, color='black', label=f'[complex fit] gain = {int(np.round(pi_gain))}')
        else:
            plt.plot(x_pts, avgi, 'o-', label="i", color='orange')
            plt.plot(x_pts, avgq, 'o-', label="q", color='blue')
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        plt.show(block=block)
        plt.pause(0.1)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


