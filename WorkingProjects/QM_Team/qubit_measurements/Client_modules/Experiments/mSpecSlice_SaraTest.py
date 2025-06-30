from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0]) # conver f_res to dac register value

        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                 length=self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"]),mode="periodic")
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),mode="periodic")

        self.sync_all(self.us2cycles(1))

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index

# ====================================================== #

class SpecSlice(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"])/expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        #### find the frequency corresponding to the qubit dip
        sig = data['data']['avgi'] + 1j * data['data']['avgq']
        avgamp0 = np.abs(sig)

        peak_loc = np.argmax(np.abs(data['data']['avgq'])) # Maximum location
        print(np.max(np.abs(data['data']['avgq'])))
        self.qubitFreq = data['data']['x_pts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        # if data is None:
        #     data = self.data

        # while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
        #     figNum += 1
        # fig = plt.figure(figNum)
        #
        # x_pts = data['data']['x_pts'] /1e3 #### put into units of frequency GHz
        # sig = data['data']['avgi'][0][0] + 1j * data['data']['avgq'][0][0]
        # avgamp0 = np.abs(sig)
        # avgpphase0 = np.angle(sig, deg=True)
        # # plt.plot(x_pts, data['data']['avgi'][0][0],label="I")
        # plt.plot(x_pts, data['data']['avgq'][0][0],label="Q")
        # # plt.plot(x_pts, avgamp0, label="Amplitude")
        # # plt.plot(x_pts, avgpphase0, label= "Phase")
        # plt.ylabel("a.u.")
        # plt.xlabel("Qubit Frequency (GHz)")
        # plt.title("Averages = " + str(self.cfg["reps"]))
        # plt.legend()
        # plt.savefig(self.iname)

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        #avgphase = np.angle(sig, deg=True)
        avgphase = np.remainder(np.angle(sig, deg=True) + 360, 360)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Qubit Frequency (GHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Qubit Frequency (GHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, avgi[0][0], 'o-', label="I - Data")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Qubit Frequency (GHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, avgq[0][0], 'o-', label="Q - Data")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Qubit Frequency (GHz)")
        axs[3].legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
            # plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


