from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time


class LoopbackProgramQubit_Pulse_Test(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters

        # Frequency of putative ef pulse, in MHz
        self.cfg["start"] = 5000
        self.cfg["step"] = 1
        # How many frequency steps to do
        self.cfg["expts"] = 1

        # Number of averages at each step
        # self.cfg["reps"] = self.cfg["AmpRabi_reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.r_freq = self.sreg(self.cfg["qubit_ch"], "freq") # frequency register on qubit channel
        # To see list of all registers: self.pulse_registers

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # Define qubit pulse: gaussian
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_ge_freq, phase=0,
                                 gain=cfg["qubit_ge_gain"],
                                 length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                 mode="periodic")


        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"])  # play ge pi pulse

        self.sync_all(self.us2cycles(0.05)) # align channels and wait /

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.freq2reg(self.cfg["step"], gen_ch = self.cfg["qubit_ch"])) # update frequency of the ef spectroscopy probe




# ====================================================== #

class Qubit_Pulse_Test(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramQubit_Pulse_Test(self.soccfg, self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        max_indx = np.argmax(avgsig)
        print(x_pts[max_indx])
        avgphase = np.remainder(np.angle(sig,deg=True)+360,360)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="Phase")
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("e-f spec frequency (MHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("e-f spec frequency (MHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("e-f spec frequency (MHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("e-f spec frequency (MHz)")
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


