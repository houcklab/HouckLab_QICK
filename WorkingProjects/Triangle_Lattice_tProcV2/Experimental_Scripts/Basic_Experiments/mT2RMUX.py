
import matplotlib.pyplot as plt
import numpy as np
import scipy
from qick.asm_v2 import QickSweep1D
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast, omega_guess
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2


class T2RProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        ### Start fast flux
        FF.FFDefinitions(self)

        self.add_loop("delay_loop", self.cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])
        if cfg["stop_delay_us"]/self.cfg["expts"] < 0.00465:
            print(f"T2RProgram: WARNING: step size ({cfg["stop_delay_us"]}/{cfg["expts"]})is less than one cycle (4.65 ns)!!!")

        if "phase_shift_cycles" in cfg and self.cfg["phase_shift_cycles"] != 0 :
            self.phase_loop = QickSweep1D("delay_loop", start=0, end=360*cfg["phase_shift_cycles"])
        else:
            self.phase_loop = 180
        # add qubit pulse
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_1', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=0, gain=cfg["pi2_gain"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_2', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=self.phase_loop, gain=cfg["pi2_gain"])
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        expt_length = self.qubit_length_us + 10.05 + self.delay_loop + self.qubit_length_us + 1
        self.FFPulses(self.FFPulse, expt_length)
        self.delay(10.0)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_1", t=0)  # pi/2
        self.delay(self.qubit_length_us)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_2", t=self.delay_loop, tag='swept_delay')  # pi/2, with phase
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, expt_length)

    def loop_pts(self):
        return (self.get_time_param("swept_delay", "t", as_array=True),)

class T2RMUX(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        self.cfg.setdefault('qubit_drive_freq',     self.cfg['qubit_freqs'][0] + self.cfg["freq_shift"])
        self.cfg.setdefault('pi_gain',  self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)


        prog = T2RProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                            final_delay=self.cfg["relax_delay"], initial_delay=10.0)

        iq_list = prog.acquire(self.soc, load_pulses=True,
                               soft_avgs=self.cfg.get('rounds', 1),
                               progress=progress)

        # shape of results: [num of ROs, 1 (num triggers), expts, 2 (I or Q)],
        #              e.g. [1, 1, 71, 2]
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_time_param("swept_delay", "t", as_array=True)

        data = {'config': self.cfg,
                'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'qfreq': self.cfg["qubit_freqs"][0], }}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
            figNum += 1
        # fig, (ax_i, ax_q) = plt.subplots(1, 2, figsize=(12.8, 4.8), num=figNum, tight_layout=True)
        #
        # ax_i.plot(x_pts, avgi, 'o-', label="i", color='orange')
        # ax_i.set_ylabel("a.u.")
        # ax_i.set_xlabel("Wait time (us)")
        # ax_i.legend()
        # ax_q.plot(x_pts, avgq, 'o-', label="q")
        # ax_q.set_ylabel("a.u.")
        # ax_q.set_xlabel("Wait time (us)")
        # ax_q.legend()

        fig, ax = plt.subplots(figsize=(7.2, 4.8))
        Contrast = IQ_contrast(avgi, avgq)
        ax.plot(x_pts, Contrast, 'o-', color='blue', label=f'qfreq = {self.cfg["qubit_drive_freq"]}')
        ax.set_ylabel("a.u.")
        ax.set_xlabel("Wait time (us)")

        def exp_fit(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0
        def fit(t, T2, A, y0, omega, phi):
            return A * np.exp(-t / T2) * np.cos(omega*t - phi) + y0

        p0_guess = [x_pts[-1] / 5, (np.max(Contrast) - np.min(Contrast))/2, Contrast[-1], omega_guess(x_pts, Contrast), 1e-2]
        try:
            (T2, A, y0, omega, phi), _ = scipy.optimize.curve_fit(fit, x_pts, Contrast, p0=p0_guess)
            ax.plot(x_pts, fit(x_pts, T2, A, y0, omega, phi), color='black')
            # ax.autoscale(False)
            ax.plot(x_pts, exp_fit(x_pts, T2, A, y0), color='black',ls='--', label=f'T2 = {T2:.3f} us')
            ax.plot(x_pts, exp_fit(x_pts, T2, -A, y0), color='black', ls='--')
            ax.legend(prop={'size': 14})
        except:
            print("No fit found.")

        plt.suptitle(self.titlename)
        plt.savefig(self.iname[:-4] + '.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

# from scipy import curve_fit
# def fit_T2