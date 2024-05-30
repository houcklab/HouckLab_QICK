
from qick import *
# from qick import helpers
# import matplotlib.pyplot as plt
# import numpy as np
# from tqdm.notebook import tqdm
# import time

class mTransmission_GUI_test(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["x_pts_label"] = "trans freq (MHz)"
        self.cfg["start"] = self.freq2reg(self.cfg["read_freq_start"], gen_ch=self.cfg["res_ch"])
        # We are also given freq_stop and SpecNumPoints, use these to compute freq_step
        self.cfg["step"] = self.freq2reg(
            (self.cfg["read_freq_stop"] - self.cfg["read_freq_start"]) / (self.cfg["TransNumPoints"] - 1),
            gen_ch=self.cfg["res_ch"])
        self.cfg["expts"] = self.cfg["TransNumPoints"]
        # self.cfg["reps"] = self.cfg["averages"]

        self.q_rp = self.ch_page(self.cfg["res_ch"])  # get register page for res_ch
        self.q_freq = self.sreg(cfg["res_ch"], "freq")  # get freq register for res_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout

        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["start"], gen_ch=cfg["res_ch"])


        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=cfg["start"], phase=0,
                                 gain=cfg["read_pulse_gain"],
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
        self.mathi(self.q_rp, self.q_freq, self.q_freq, '+', self.cfg["step"])  # update freq of the Gaussian pi pulse
