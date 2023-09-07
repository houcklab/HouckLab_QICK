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

class LoopbackProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        print(cfg["res_ch"], 2, cfg["mixer_freq"], cfg["pulse_freqs"], cfg["ro_chs"], cfg["pulse_gains"],
              cfg["readout_length"], cfg["length"], cfg["adc_trig_offset"])

        self.declare_gen(ch=cfg["res_ch"], nqz=2,
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            # freq = self.freq2reg(cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"],
            #                  ro_ch=cfg["ro_chs"][iCh])
            # print(freq)
            # self.declare_readout(ch=ch, freq=freq, length=cfg["readout_length"],
            #                      gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=cfg["ro_chs"])
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels


config = {"res_ch": 6,  # --Fixed
          "mixer_freq": 5000,  # MHz
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 10,  # --Fixed
          "pulse_style": "const",  # --Fixed

          "length": 2450,  # [Clock ticks]
          # Try varying length from 10-100 clock ticks

          "readout_length": 700,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks



          "adc_trig_offset": 175,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 1000
          # Try varying soft_avgs from 1 to 200 averages
          }

config['pulse_freqs'] = [7250.2 - config['mixer_freq'], 7117.9 - config['mixer_freq'], 7056.0 - config['mixer_freq']][:len(config['ro_chs'])]
config['pulse_freqs'] = [133.2, 7117.9 - config['mixer_freq'], 7056.0 - config['mixer_freq']][:len(config['ro_chs'])]

print(config['pulse_freqs'])
config["pulse_gains"]= [0.3] * len(config['pulse_freqs'])

# In this program the signal is up and downconverted digitally so you won't see any frequency
# components in the I/Q traces below. But since the signal gain depends on frequency,
# if you lower pulse_freq you will see an increased gain.


###################
# Try it yourself !
###################

frequency_ranges = config["mixer_freq"] + np.linspace(-0.0001, 0.0001, 100)
i_data = []
q_data = []
results = []
for f in frequency_ranges:
    config["mixer_freq"] = f
    prog = LoopbackProgram(soccfg, config)
    freq = prog.acquire(soc, load_pulses=True)
    results.append(freq)
    # print(freq, freq[0][1][0], freq[0][1][1])#, freq[0][0][0], freq[1][0][0])
    # i_data.append(freq[0][1][0])
    # q_data.append(freq[0][1][1])
results = np.transpose(results)

for i in range(len(results[0])):
    avgi = results[0][i][0]
    avgq = results[0][i][1]
    x_pts = frequency_ranges  #### put into units of frequency GHz
    sig = avgi + 1j * avgq
    avgamp0 = np.abs(sig)

    plt.plot(x_pts, avgi, '.-', color='Green', label="I")
    plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")
    plt.plot(x_pts, avgamp0, color='Magenta', label="Amp")
    plt.ylabel("a.u.")
    plt.xlabel("Cavity Frequency (GHz)")
    plt.legend()
    plt.show()

# plt.plot(frequency_ranges, i_data)
# plt.plot(frequency_ranges, q_data)
# plt.plot(frequency_ranges, np.abs(np.array(i_data) + 1j * np.array(q_data)))
#
# plt.show()

# prog = LoopbackProgram(soccfg, config)
# iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
# freq = prog.acquire(soc, load_pulses=True)
# print(freq)
#
# fig, axs = plt.subplots(2,1,figsize=(10,10))
#
# for ii, iq in enumerate(iq_list[:1]):
#     plot = axs[ii]
#     plot.plot(iq[0], label="I value, ADC %d"%(config['ro_chs'][ii]))
#     plot.plot(iq[1], label="Q value, ADC %d"%(config['ro_chs'][ii]))
#     plot.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d"%(config['ro_chs'][ii]))
#     plot.set_ylabel("a.u.")
#     plot.set_xlabel("Clock ticks")
#     plot.set_title("Averages = " + str(config["soft_avgs"]))
#     plot.legend()
# plt.show()


