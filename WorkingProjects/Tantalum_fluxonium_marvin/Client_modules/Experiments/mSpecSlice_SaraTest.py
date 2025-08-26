import datetime

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time


class LoopbackProgramSpecSlice(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)
        self.delay = None

    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

        #### define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
            self.qubit_pulseLength_us = self.cfg["sigma"] * 4
        elif self.cfg["qubit_pulse_style"] == "const":
            if self.cfg["mode_periodic"] == True:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                         mode="periodic")
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                         gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=0, gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))
            self.qubit_pulseLength_us = self.cfg["sigma"] * 4 + self.cfg["flat_top_length"]

        # Adding the resonator pulse
        if self.cfg['ro_periodic'] == True:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]), mode="periodic")
        elif self.cfg['ro_periodic'] == False:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(0.05))

        # Defining a delay between the qubit tone and the readout tone
        if "delay_btwn_pulses" in self.cfg:
            self.delay = self.cfg["delay_btwn_pulses"]  # in us

            # Check if delay is a float and is positive
            if self.delay < 0:
                # Throw an error
                raise ValueError("Delay_btwn_pulses must be a number greater than zero")
        else:
            self.delay = 0.05  # in us

    def body(self):

        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(self.delay))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index


# ====================================================== #

class SpecSlice(ExperimentClass):
    """
    Basic spec experiment that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        # Decreasing the denominator in the line below so that the last point is at qubit_freq_stop
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / (expt_cfg["SpecNumPoints"]-1)
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]

        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)

        # Timer
        startTime = datetime.datetime.now()
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        # Estimate runtime
        estimated_runtime = datetime.timedelta(seconds=1e-6 * (self.cfg['expts'] * self.cfg['reps'] *
                                                               (prog.qubit_pulseLength + self.cfg['read_length'] +
                                                                self.cfg[  # removed _us
                                                                    'relax_delay'])))
        print('estimated runtime: ' + str(estimated_runtime))
        print('estimated end time:' + (datetime.datetime.now() + estimated_runtime).strftime("%Y/%m/%d %H:%M:%S"))

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        #### find the frequency corresponding to the qubit dip
        sig = data['data']['avgi'][0][0] + 1j * data['data']['avgq'][0][0]
        avgamp0 = np.abs(sig)

        peak_loc = np.argmax(np.abs(data['data']['avgq']))  # Maximum location
        # print(np.max(np.abs(data['data']['avgq'])))
        self.qubitFreq = data['data']['x_pts'][peak_loc]

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)
        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
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

        # ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I - Data")
        ax2 = axs[2].plot(x_pts, avgi[0][0], 'o-', label="I - Data")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Qubit Frequency (GHz)")
        axs[2].legend()

        # ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q - Data")
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
