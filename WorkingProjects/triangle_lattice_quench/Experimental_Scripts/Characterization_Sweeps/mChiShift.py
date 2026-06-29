
# from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import numpy as np
from WorkingProjects.triangle_lattice_quench.Experiment import ExperimentClass
# from tqdm.notebook import tqdm
import time
import traceback
from tqdm import tqdm
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFProg

class CavitySpecExciteProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg['res_ch'], ro_ch=cfg['ro_chs'][0], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg['res_freqs'],
                         mux_gains=cfg['res_gains'],
                         mux_phases=[0]*len(cfg['res_freqs']))
        for ch, f in zip(cfg['ro_chs'], cfg['res_freqs']):
            self.declare_readout(ch=ch, length=cfg['readout_length'], freq=f, phase=0, gen_ch=cfg['res_ch'])

        self.add_pulse(ch=cfg['res_ch'], name="res_pulse",
                       style="const",
                       length=cfg["res_length"],
                       mask=cfg["ro_chs"])

        for i in range(len(self.cfg["qubit_gains"])):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=90, gain=cfg["qubit_gains"][i])
        self.qubit_total_length_us = 4 * sum(cfg["sigma"])

        FF.FFDefinitions(self)

    def _body(self, cfg):
        FF_Delay_time = 1
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + FF_Delay_time)
        for i in range(len(self.cfg["qubit_gains"])):
            if i == 0:
                time = FF_Delay_time
            else:
                time = 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time)

        self.delay_auto()
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        # self.delay(0.1)  # delay trigger and pulse to 0.5 us after beginning of FF pulses
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(self.cfg["res_ch"], name='res_pulse')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

    # ====================================================== #

class ChiShift(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, use_lorentzian=False):
        cfg = self.cfg
        fpts = np.linspace(cfg["res_freqs"][0] - cfg["TransSpan"],
                           cfg["res_freqs"][0] + cfg["TransSpan"],
                           cfg["TransNumPoints"])
        results_g = []
        start = time.time()
        if cfg.get('cav_gain') is not None:
            cfg['res_gains'][0] = cfg['cav_gain'] / 32766
        for f in tqdm(fpts, position=0, disable=False):
            cfg["res_freqs"][0] = f
            prog = CavitySpecFFProg(self.soccfg, reps=self.cfg['reps'],cfg=self.cfg, final_delay=self.cfg['cav_relax_delay'])
            results_g.append(prog.acquire(self.soc, rounds=self.cfg.get('rounds',1), load_envelopes=True, progress=progress))
        print(f'Time: {time.time() - start}')
        results_g = np.array(results_g)

        results_e = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=False):
            cfg["res_freqs"][0] = f
            prog = CavitySpecExciteProg(self.soccfg, reps=self.cfg['reps'], cfg=self.cfg,
                                    final_delay=self.cfg['cav_relax_delay'])
            results_e.append(prog.acquire(self.soc, rounds=self.cfg.get('rounds', 1), load_envelopes=True, progress=progress))
        print(f'Time: {time.time() - start}')
        results_e = np.array(results_e)


        # shape of results: (fpts, ROs, 1 [loops], I/Q)
        # print(results.shape)
        data={'config': self.cfg, 'data': {'results_g': results_g, 'results_e':results_e, 'fpts':fpts}}
        self.data=data

        # Fit the data
        self.analyze(data=data, use_lorentzian=use_lorentzian)

        return data

    def analyze(self, data=None, use_lorentzian=False, **kwargs):
        if not data:
            data = self.data

        # Lorentzian Fitting Method (noise resistant)
        # Inverted Lorentzian for transmission dip
        def inv_lorentzian(f, f0, gamma, A, offset):
            return -A / (1 + ((f - f0) / gamma) ** 2) + offset

        # Sloped background
        def inv_lorentzian_bg(f, f0, gamma, A, m, b):
            return -A / (1 + ((f - f0) / gamma) ** 2) + (m * f + b)

        # S21 of hanger measurement, see Lev Krayzman thesis eq. 2.26
        def S21_hanger_magnitude(f, f0, Ql, Qc, phi, A, m, b):
            return A* np.abs(1- Ql/np.abs(Qc)*np.exp(1j*phi) / (1+2j*Ql*(f/f0 - 1))) + m*f + b

        # self.peakFreq_argmin      = [None] * 2
        # self.lorentz_fit          = [None] * 2
        # self.peakFreq_lorentz_min = [None] * 2
        # self.linewidth            = [None] * 2
        # self.freq_uncertainty     = [None] * 2
        # self.perror               = [None] * 2
        # self.peakFreq_min         = [None] * 2
        self.lorentz_fit = [None] * 2
        self.popt = [None] * 2

        for index, key in enumerate(['results_g', 'results_e']):
            # Finding frequency by simple argmin, argmax
            sig = data['data'][key][:, 0, 0, 0] + 1j * data['data'][key][:, 0, 0, 1]
            avgamp0 = np.abs(sig)
            # self.peakFreq_argmin[index] = data['data']['fpts'][np.argmin(avgamp0)]

            try:
                fpts = data['data']['fpts']
                # Initial guess
                # f0_guess = fpts[np.argmin(avgamp0)]
                # gamma_guess = (fpts[-1] - fpts[0]) / 10  # Linewidth guess
                # A_guess = np.max(avgamp0) - np.min(avgamp0)
                # offset_guess = np.mean(avgamp0)

                # popt, pcov = curve_fit(
                    # inv_lorentzian_bg, fpts, avgamp0,
                    # p0=[f0_guess, gamma_guess, A_guess, 0.0, offset_guess]
                # )
                # lorentz_fit = inv_lorentzian_bg(fpts, *popt)

                # f, f0, Ql, Qc, phi, A, m, b
                f0_guess = data['data']['fpts'][np.argmin(avgamp0)]
                popt, pcov = curve_fit(
                    S21_hanger_magnitude, fpts, avgamp0,
                    p0=[f0_guess, f0_guess+self.cfg['res_LO'], f0_guess+self.cfg['res_LO'], 0.0, np.max(avgamp0)-np.min(avgamp0),0.0, np.max(avgamp0)],
                )


                self.lorentz_fit[index]          = S21_hanger_magnitude(fpts, *popt)
                self.popt[index]                 = popt
                # self.peakFreq_lorentz_min[index] = popt[0] # min frequency
                # self.linewidth[index]            = popt[1]  # cavity linewidth
                # self.freq_uncertainty[index]     = np.sqrt(pcov[0, 0])  # Uncertainty
                # self.perror[index]               = np.sqrt(np.diag(pcov))

                # print(f"Lorentzian fit found with uncertainty: {self.freq_uncertainty[index]} (threshold < {0.2 * self.linewidth[index]}).")

                # Determining which one to use vased on uncertainty
                # self.peakFreq_min[index] = self.peakFreq_lorentz_min[index] if use_lorentzian and self.freq_uncertainty[index] < 0.2 * self.linewidth[index] \
                #                     else self.peakFreq_argmin[index]

            except Exception as e:
                # If fit failed then default back
                print("Lorentzian fit failed.")
                traceback.print_exc()
                # self.lorentz_fit[index] = None
                # self.peakFreq_min[index] = self.peakFreq_argmin[index] # Use naive fit

    def display(self, data=None, plotDisp = True, figNum = 1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data
        # for i in range(len(data['data']['results'][0])):
        avgi = data['data']['results_g'][:,0,0,0]
        avgq = data['data']['results_g'][:,0,0,1]
        sig = avgi + 1j * avgq

        avgamp_g = np.abs(sig)

        avgi = data['data']['results_e'][:, 0, 0, 0]
        avgq = data['data']['results_e'][:, 0, 0, 1]
        sig = avgi + 1j * avgq

        avgamp_e = np.abs(sig)


        x_pts = (data['data']['fpts'] + self.cfg["res_LO"]) / 1e3  #### put into units of frequency GHz


        if ax is None:
            plt.figure()
        else:
            plt.sca(ax)
        # plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
        # plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.plot(x_pts, avgamp_g, '.-',  color = 'red', label="Ground state")
        plt.plot(x_pts, avgamp_e, '.-', color = 'Blue', label="Excited state")

        colors = ['red', 'blue']
        for j in range(len(self.lorentz_fit)):
            if self.lorentz_fit[j] is None:
                continue
            f0, Ql, Qc, phi, A, m, b = self.popt[j]
            print(f0, Qc, f0/np.abs(Qc))
            kappa = f0/np.abs(Qc)
            # print(kappa)
            plt.plot(x_pts, self.lorentz_fit[j], '--', color=colors[j], linewidth=2,
                     label=f"Fit:min={f0 + self.cfg["res_LO"]:.2f} MHz, κ={kappa:.3f} MHz")
            # plt.axvline(freq_min, color='black', linestyle='--', label=f"{chosen_text}Lorentz Min: {1e3 * freq_min:.2f} MHz")


        if self.lorentz_fit[0] is not None and self.lorentz_fit[1] is not None:
            min1 = self.popt[0][0]
            min2 = self.popt[1][0]
            center = (np.mean([min1, min2]) + self.cfg["res_LO"])
            chi = np.abs(min2 - min1)
            plt.axvline(center/1e3, color='black', linestyle='--',
                        label=f"Midpoint={center:.2f} MHz, chi={chi:.3f} MHz")
        # if hasattr(self, 'peakFreq_argmin'):
        #     freq_argmin = (self.peakFreq_argmin + self.cfg["res_LO"]) / 1e3
        #     chosen_text = "[Used] " if self.peakFreq_min == self.peakFreq_argmin else ""
        #     plt.axvline(freq_argmin, color='gray', linestyle=':', label=f"{chosen_text}Argmin: {1e3 * freq_argmin:.2f} MHz")

        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(f"{self.titlename} | Read:{self.cfg['Qubit_Readout_List']}")
        plt.legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)
        # plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
