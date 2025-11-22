import scipy.optimize
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF


class T1Program(FFAveragerProgramV2):
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

        self.add_loop("delay_loop", self.cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])
        # add qubit pulse
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0])
        self.qubit_length_us = cfg["sigma"] * 4


    def _body(self, cfg):
        expt_length =  self.qubit_length_us + 1.05 + self.delay_loop
        self.FFPulses(self.FFPulse, expt_length)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.delay(self.qubit_length_us + 1.05)

        # Sweep this delay time
        self.delay(self.delay_loop, tag = 'swept_delay')

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

class T1MUX(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        prog = T1Program(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                            final_delay=self.cfg["relax_delay"], initial_delay=10.0)

        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)

        # shape of results: [num of ROs, 1 (num triggers), expts, 2 (I or Q)],
        #              e.g. [1, 1, 71, 2]
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_time_param("swept_delay", "t", as_array=True)


        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'qfreq': self.cfg["qubit_freqs"][0],}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        # fig, (ax_i, ax_q) = plt.subplots(1, 2, figsize=(12.8, 4.8), num=figNum, tight_layout=True)
        #
        # ax_i.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        # ax_i.set_ylabel("a.u.")
        # ax_i.set_xlabel("Wait time (us)")
        # ax_i.legend()
        # ax_q.plot(x_pts, avgq, 'o-', label="q")
        # ax_q.set_ylabel("a.u.")
        # ax_q.set_xlabel("Wait time (us)")
        # ax_q.legend()

        if ax is None:
            fig, ax = plt.subplots(figsize=(7.2, 4.8), num=figNum)
            ax.set_title("Read:" + str(self.cfg["Qubit_Readout_List"]))
            plt.suptitle(self.titlename)
        else:
            fig = ax.get_figure()
            ax.set_title(self.titlename + " Read:" + str(self.cfg["Qubit_Readout_List"]))

        Contrast = IQ_contrast(avgi, avgq)

        ax.set_ylabel("a.u.")
        ax.set_xlabel("Wait time (us)")

        def fit(t, T1, A, y0):
            return A*np.exp(-t/T1) + y0
        p0_guess = [x_pts[-1]/5, np.max(Contrast) - np.min(Contrast), Contrast[-1]]
        try:
            (T1, A, y0), _ = scipy.optimize.curve_fit(fit, x_pts, Contrast, p0=p0_guess)
            sign = np.sign(A) # Force plot to go down
            ax.plot(x_pts, sign *  Contrast, 'o-', color='blue', label=f'qfreq = {self.cfg["qubit_freqs"][0]}')
            # ax.autoscale(False)
            ax.plot(x_pts, sign *  fit(x_pts, T1, A, y0), color='black', ls='--', label=f'T1 = {T1:.2f} us')
            ax.legend(prop={'size': 14})
            self.T1 = T1
        except:
            ax.plot(x_pts, Contrast, 'o-', color='blue')
            print("No fit found.")

        plt.savefig(self.iname[:-4] + '.png')

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.01)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

