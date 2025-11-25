
from scipy.optimize import curve_fit

from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast

class QubitSpecSliceFFProg(FFAveragerProgramV2):
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


        ### Start fast flux
        FF.FFDefinitions(self)

        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        qubit_freq_sweep = QickSweep1D("qubit_freq_loop",
                                    start=cfg["qubit_freqs"][0] - cfg["SpecSpan"],
                                    end=cfg["qubit_freqs"][0] + cfg["SpecSpan"])
        # add qubit pulse
        # print(cfg["qubit_gain"])
        if cfg['Gauss']:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                           freq=qubit_freq_sweep,
                           phase=90, gain=cfg["Gauss_gain"] / 32766.)
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="const", freq=qubit_freq_sweep,
                           phase=0, gain=cfg["qubit_gain"] / 32766., length=cfg["qubit_length"])
            self.qubit_length_us = cfg["qubit_length"]

        # print(self.FFPulse)


    def _body(self, cfg):
        # print(self.FFPulse)
        FF_pulse_delay = 1
        self.FFPulses(self.FFPulse, self.qubit_length_us + FF_pulse_delay + 0.05)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t = FF_pulse_delay)  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1.05)

    def loop_pts(self):
        return (self.get_pulse_param("qubit_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0),)
# ====================================================== #

class QubitSpecSliceFFMUX(ExperimentClass):
    """
    Basic spec experiment that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, use_lorentzian=False):
        cfg = self.cfg

        self.cfg.setdefault("qubit_length", 100) ### length of CW drive in us

        prog = QubitSpecSliceFFProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)
        # print(np.array(iq_list).shape)

        # shape of results: [num of ROs, 1 (num triggers?), SpecNumPoints, 2 (I or Q)],
        #              e.g. [1, 1, 71, 2]
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_pulse_param("qubit_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0)

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        # Fit to find frequency
        self.analyze(data=data, use_lorentzian=use_lorentzian)

        return data

    def analyze(self, data=None, use_lorentzian=False, **kwargs):
        # Find the frequency corresponding to the qubit dip via argmax
        if not data:
            data = self.data

        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        x_pts = data['data']['x_pts']

        # sig = avgi + 1j * avgq
        sig = IQ_contrast(avgi, avgq)
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq_argmax = x_pts[peak_loc]

        # Find frequency using lorentzian fitting
        # Fit to Lorentzian (standard for qubit spectroscopy)
        def lorentzian_spec(f, f0, gamma, A, offset):
            return A / (1 + ((f - f0) / gamma) ** 2) + offset

        try:
            # Perform fit around the argmax window
            # Local window
            N = max(10, len(x_pts) // 20)
            i_min = max(0, peak_loc - N)
            i_max = min(len(x_pts), peak_loc + N)
            x_fit = x_pts[i_min:i_max]
            y_fit = avgamp0[i_min:i_max]

            # Guesses
            f0_guess = x_pts[peak_loc]
            gamma_guess = (x_fit[-1] - x_fit[0]) / 6
            A_guess = np.max(y_fit) - np.min(y_fit)
            offset_guess = np.min(y_fit)

            span = x_fit[-1] - x_fit[0]
            popt, pcov = curve_fit(
                lorentzian_spec,
                x_fit,
                y_fit,
                p0=[f0_guess, gamma_guess, A_guess, offset_guess],
                bounds=([x_fit[0], 0.0, 0.0, -np.inf],
                        [x_fit[-1], span, np.inf, np.inf]),
            )

            self.lorentz_fit = lorentzian_spec(x_pts, *popt)
            self.qubitFreq_lorentz = popt[0]
            self.qubit_linewidth = popt[1]
            self.freq_uncertainty = np.sqrt(pcov[0, 0])

            print(f"Lorentzian fit found with uncertainty: {self.freq_uncertainty} (threshold < {0.2 * self.qubit_linewidth}).")

            self.qubitFreq = self.qubitFreq_lorentz if use_lorentzian and self.freq_uncertainty < 0.2 * self.qubit_linewidth \
                else self.qubitFreq_argmax
        except:
            # Fallback to argmax if fit fails
            self.lorentz_fit = None
            self.qubitFreq = self.qubitFreq_argmax

    def display(self, data=None, plotDisp = False, figNum = 1, block=True,ax=None, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)

        if ax is None:
            plt.figure()
        else:
            plt.sca(ax)
        plt.plot(x_pts, avgi, '.-', color = 'Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")

        if hasattr(self, 'qubitFreq_lorentz') and hasattr(self, 'lorentz_fit') and self.lorentz_fit is not None:
            plt.plot(x_pts, self.lorentz_fit, '-', linewidth=2)
            chosen_text = "[Used] " if self.qubitFreq == self.qubitFreq_lorentz else ""
            plt.axvline(self.qubitFreq_lorentz, color='black', linestyle='--', label=f"{chosen_text}Lorentz Max: {self.qubitFreq_lorentz:.2f} MHz")
        if hasattr(self, 'qubitFreq_argmax'):
            chosen_text = "[Used] " if self.qubitFreq == self.qubitFreq_argmax else ""
            plt.axvline(self.qubitFreq_argmax, color='gray', linestyle=':', label=f"{chosen_text}Argmax: {self.qubitFreq_argmax:.2f} MHz")

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname[:-4] + '_IQ.png')
        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)
        # plt.close(figNum)



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


