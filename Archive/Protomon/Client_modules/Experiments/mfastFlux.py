from qick import *
# from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class LoopbackProgramFastFlux(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        # res_ch = cfg["res_ch"]
        # #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        # self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        # Qubit configuration
        ffChannel = cfg["ff_ch"]
        self.declare_gen(ch=ffChannel, nqz=cfg["ff_nqz"])

        # configure the readout lengths and downconversion frequencies
        # for ro_ch in cfg["ro_chs"]:
        #     self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])
        style = self.cfg["ff_pulse_style"]
        # freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
        #     0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        ff_freq = self.freq2reg(cfg["ff_freq"],
                                   gen_ch=ffChannel)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.ff_freq = ff_freq
        self.style = style

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if style in ["flat_top", "arb"]:
            sigma = cfg["sigma"]
            nsigma = 5
            samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
            idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
                                  si=sigma * samples_per_clock,
                                  length=sigma * samples_per_clock * nsigma,
                                  maxv=np.iinfo(np.int16).max - 1)
            self.add_pulse(ch=ffChannel, name="measure", idata=idata)
        if style == "const":
            self.set_pulse_registers(ch=ffChannel, style=style, freq=ff_freq, phase=0, gain=cfg["ff_gain"],
                                     length=cfg["ff_length"])

        elif style == "flat_top":
            self.set_pulse_registers(ch=ffChannel, style=style, freq=ff_freq, phase=0, gain=cfg["ff_gain"],
                                     waveform="measure", length=cfg["ff_length"])
        elif style == "arb":
            self.set_pulse_registers(ch=ffChannel, style=style, freq=ff_freq, phase=0, gain=cfg["ff_gain"],
                                     waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses

        # Play qubit pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.style, freq=self.ff_freq, phase=0,
                                 gain= self.cfg["ff_gain"],
                                 length=self.cfg["ff_length"])
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        # self.synci(1000) ### WAIT
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play readout pulse



        # self.synci(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels



# class SpecSlice(ExperimentClass):
#     """
#     Basic spec experiement that takes a single slice of data
#     """
#
#     def __init__(self, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
#         super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
#
#     def acquire(self, progress=False, debug=False):
#         for f in tqdm(fpts, position=0, disable=True):
#             self.cfg["qubit_freq"] = f
#             prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
#             results.append(prog.acquire(self.soc, load_pulses=True))
#         print(f'Time: {time.time() - start}')
#         results = np.transpose(results)
#         #
#         # prog = LoopbackProgram(self.soccfg, self.cfg)
#         # self.soc.reset_gens()  # clear any DC or periodic values on generators
#         # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
#         data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
#         self.data=data
#
#         #### find the frequency corresponding to the qubit dip
#         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
#         avgamp0 = np.abs(sig)
#         peak_loc = np.argmin(avgamp0)
#         self.qubitFreq = data['data']['fpts'][peak_loc]
#
#         return data
#
#     def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
#         if data is None:
#             data = self.data
#         plt.figure(figNum)
#         x_pts = data['data']['fpts'] /1e3 #### put into units of frequency GHz
#         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
#         avgamp0 = np.abs(sig)
#         # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
#         # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")
#         plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
#         plt.ylabel("a.u.")
#         plt.xlabel("Qubit Frequency (GHz)")
#         plt.title("Averages = " + str(self.cfg["reps"]))
#
#         plt.savefig(self.iname)
#
#         if plotDisp:
#             plt.show(block=False)
#             plt.pause(0.1)
#
#     def save_data(self, data=None):
#         print(f'Saving {self.fname}')
#         super().save_data(data=data['data'])
#
# # ====================================================== #
#
# # class Transmission(ExperimentClass):
# #     """
# #     Transmission Experiment basic
# #     """
# #
# #     def __init__(self, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
# #         super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
# #
# #     def acquire(self, progress=False, debug=False):
# #         expt_cfg = {
# #                 "center": self.cfg["pulse_freq"],
# #                 "span": self.cfg["TransSpan"],
# #                 "expts": self.cfg["TransNumPoitns"]
# #         }
# #         expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
# #         expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
# #         fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
# #         results = []
# #         start = time.time()
# #         for f in tqdm(fpts, position=0, disable=True):
# #             self.cfg["pulse_freq"] = f
# #             prog = LoopbackProgramTrans(self.soccfg, self.cfg)
# #             results.append(prog.acquire(self.soc, load_pulses=True))
# #         print(f'Time: {time.time() - start}')
# #         results = np.transpose(results)
# #         #
# #         # prog = LoopbackProgram(self.soccfg, self.cfg)
# #         # self.soc.reset_gens()  # clear any DC or periodic values on generators
# #         # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
# #         data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
# #         self.data=data
# #
# #         #### find the frequency corresponding to the peak
# #         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
# #         avgamp0 = np.abs(sig)
# #         peak_loc = np.argmin(avgamp0)
# #         self.peakFreq = data['data']['fpts'][peak_loc]
# #
# #         return data
# #
# #     def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
# #         if data is None:
# #             data = self.data
# #         plt.figure(figNum)
# #         x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
# #         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
# #         avgamp0 = np.abs(sig)
# #         # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
# #         # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")
# #         plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
# #         plt.ylabel("a.u.")
# #         plt.xlabel("Cavity Frequency (GHz)")
# #         plt.title("Averages = " + str(self.cfg["reps"]))
# #
# #         plt.savefig(self.iname)
# #
# #         if plotDisp:
# #             plt.show(block=False)
# #             plt.pause(0.1)
# #
# #
# #     def save_data(self, data=None):
# #         print(f'Saving {self.fname}')
# #         super().save_data(data=data['data'])
# #
# #
# #
# #
# #
