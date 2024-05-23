
from qick import *
# from qick import helpers
# import matplotlib.pyplot as plt
# import numpy as np
# from tqdm.notebook import tqdm
# import time

class mTransmission_GUI_test(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        #cfg = self.cfg
        res_ch = self.cfg["res_ch"]

        #### set the start, step, and other parameters
        self.cfg["x_pts_label"] = "trans freq (MHz)"
        self.cfg["start"] = self.cfg["trans_freq_start"]
        self.cfg["step"] = (self.cfg["trans_freq_stop"] - self.cfg["trans_freq_start"]) / (self.cfg["TransNumPoints"] - 1)
        self.cfg["expts"] = self.cfg["TransNumPoints"]

        ### define the start and setp for the program
        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=self.cfg["res_ch"], ro_ch=self.cfg["ro_chs"][0])
        self.f_step = self.freq2reg(self.cfg["step"], gen_ch=self.cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["res_ch"])  # get register page for res_ch
        self.q_freq = self.sreg(self.cfg["res_ch"], "freq")  # get freq register for res_ch

        self.declare_gen(ch=res_ch, nqz=self.cfg["nqz"], mixer_freq=self.cfg["mixer_freq"], ro_ch=self.cfg["ro_chs"][0])

        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["start"], gen_ch=self.cfg["res_ch"])


        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_start, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):

        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.f_step)  # update freq of the Gaussian pi pulse


