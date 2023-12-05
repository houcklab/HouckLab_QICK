from q4diamond.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
import os
import platform
from qick import *
# from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime


class ResSweepProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=2, ro_ch=cfg["ro_chs"][0], mixer_freq=0.0)

        self.declare_readout(ch=cfg["ro_chs"][0], freq=[cfg["pulse_freq"]], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        # play for ring_time
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], gain=cfg["pulse_gain"],
                                 freq=[cfg["pulse_freq"]], phase=0)
        self.synci(200)  # give processor some time to configure pulses
        self.pulse(ch=self.cfg["res_ch"], t=0)

        #reconfigure pulses for readout_length
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["readout_length"]+cfg["adc_trig_offset"],
                                 gain=[cfg["pulse_gain"]], freq=[cfg["pulse_freq"]], phase=0)

        #sync everything
        self.sync_all()


    def body(self):
        #play pulses. Trigger for a small wait time for the pulse to sync up a bit
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg['adc_trig_offset'])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # sync everything
        self.wait_all()
        self.sync_all()

class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        # self.declare_gen(ch=res_ch, nqz=2, mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=res_ch, nqz=2, ro_ch=cfg["ro_chs"][0])


        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])

        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        phase = self.deg2reg(cfg["res_phase"], gen_ch=res_ch)
        print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))

        self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=phase, gain=cfg["pulse_gain"],
                                     length=cfg["length"], mode='periodic')

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200) # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"],t=0)
        #
        # # control should wait until the readout is over
        # self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"])+self.us2cycles(self.cfg["readout_length"]))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=self.ro_chs,
        #              pins=[0],
        #              adc_trig_offset=self.cfg["adc_trig_offset"],
        #              wait=True,
        #              syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        # self.declare_gen(ch=res_ch, nqz=2, mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=res_ch, nqz=2, ro_ch=cfg["ro_chs"][0])

        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])

        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=cfg["length"], mode='periodic')

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200) # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"],t=0)
        self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"])+self.us2cycles(self.cfg["readout_length"]))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

config = {"res_ch": 1,  # --Fixed
          "mixer_freq": 6000,  # MHz
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 10,  # --Fixed
          "res_phase": 0,  # --Fixed
          "pulse_style": "const",  # --Fixed

          "length": 50,  # [Clock ticks]

          "readout_length": 200,  # [Clock ticks]

          "pulse_gain": 500,  # [DAC units]

          "pulse_freq": 500,  # [MHz]

          "adc_trig_offset": 100,  # [Clock ticks]

          "soft_avgs": 100
          }

prog = LoopbackProgram(soccfg, config)
soc.reset_gens()  # clear any DC or periodic values on generators
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)

# prog = ResSweepProgram(soccfg, config)
# soc.reset_gens()  # clear any DC or periodic values on generators
# iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)