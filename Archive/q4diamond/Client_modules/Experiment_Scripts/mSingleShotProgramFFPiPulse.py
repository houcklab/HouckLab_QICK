from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from q4diamond.Client_modules.Experiment import ExperimentClass
from q4diamond.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time

# class LoopbackProgramSingleShot(RAveragerProgram):
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#
#         #### first do nothing, then apply the pi pulse
#         cfg["start"]=0
#         cfg["step"]=cfg["qubit_gain"]
#         cfg["reps"]= cfg["shots"]
#         cfg["expts"]=2
#         # ##### reverse the experiment order
#         # cfg["start"]=cfg["qubit_gain"]
#         # cfg["step"]= -cfg["qubit_gain"]
#         # cfg["reps"]=cfg["shots"]
#         # cfg["expts"]=2
#
#         # self.cfg["rounds"] = 2
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
#         self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch
#
#         res_ch = cfg["res_ch"]
#         #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
#         self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
#
#         # Qubit configuration
#         qubit_ch = cfg["qubit_ch"]
#         self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
#
#         # configure the readout lengths and downconversion frequencies
#         for ro_ch in cfg["ro_chs"]:
#             # self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
#             #                      length=self.us2cycles(self.cfg["state_readout_length"]), gen_ch=cfg["res_ch"])
#             self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
#                                  length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])
#
#         read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
#         # convert frequency to dac frequency (ensuring it is an available adc frequency)
#         qubit_freq = self.freq2reg(cfg["qubit_freq"],
#                                    gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#         #FF Start
#         for FF_info in cfg["FF_list_readout"]:
#             self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])
#
#         self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
#         self.ff_style = self.cfg["ff_pulse_style"]
#
#         ### Finish FF
#         self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
#         self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
#
#         self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
#         self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
#         #FF End
#
#         # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
#         if cfg["qubit_pulse_style"] == "arb":
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
#                            sigma=self.us2cycles(self.cfg["sigma"]),
#                            length=self.us2cycles(self.cfg["sigma"]) * 4)
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
#                                      phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
#                                      waveform="qubit")
#             self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
#
#         elif cfg["qubit_pulse_style"] == "flat_top":
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
#                            sigma=self.us2cycles(self.cfg["sigma"]),
#                            length=self.us2cycles(self.cfg["sigma"]) * 4)
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
#                                      phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
#                                      waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
#             self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
#
#         else:
#             print("define pi or flat top pulse")
#
#         self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
#                                  length=self.us2cycles(self.cfg["readout_length"] + self.cfg["adc_trig_offset"]),
#                                  ) # mode="periodic")
#
#         self.synci(200)  # give processor some time to configure pulses
#
#     def body(self):
#         self.synci(200)  # give processor time to get ahead of the pulses
#         self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1_exp,
#                                  length=self.qubit_pulseLength + self.us2cycles(0.01))
#         self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2_exp,
#                                  length=self.qubit_pulseLength + self.us2cycles(0.01))
#
#         self.pulse(ch=self.FF_Channel1)
#         self.pulse(ch=self.FF_Channel2)
#
#         # self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
#         #                sigma=self.us2cycles(self.cfg["sigma"]),
#         #                length=self.us2cycles(self.cfg["sigma"]) * 4)
#         self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"],
#                                  freq=self.freq2reg(self.cfg["qubit_freq"], gen_ch=self.cfg["qubit_ch"]),
#                                  phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["start"],
#                                  waveform="qubit")
#         self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  #play probe pulse
#
#         self.sync_all() # align
#         print('GAIN :', self.cfg["start"])
#
#         self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1_readout,
#                                  length=self.us2cycles(self.cfg["length"]))
#         self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2_readout,
#                                  length=self.us2cycles(self.cfg["length"]))
#
#         self.pulse(ch=self.FF_Channel1)
#         self.pulse(ch=self.FF_Channel2)
#
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(self.cfg["relax_delay"]))
#     def update(self):
#         self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index
#         self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"]/2))  # update frequency list index
#
#     def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
#                 start_src="internal", progress=False, debug=False):
#
#         super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)
#
#         return self.collect_shots()
#
#     def collect_shots(self):
#         shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
#         shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
#
#         return shots_i0,shots_q0


class LoopbackProgramSingleShot(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### first do nothing, then apply the pi pulse
        cfg["start"]=0
        cfg["step"]=cfg["qubit_gain"]
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=2
        # ##### reverse the experiment order
        # cfg["start"]=cfg["qubit_gain"]
        # cfg["step"]= -cfg["qubit_gain"]
        # cfg["reps"]=cfg["shots"]
        # cfg["expts"]=2

        # self.cfg["rounds"] = 2

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_readout_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
                                 length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        #FF Start
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]

        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
        #FF End

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["readout_length"] + self.cfg["adc_trig_offset"]),
                                 ) # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1_exp,
                                 length=self.qubit_pulseLength + self.us2cycles(0.01))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2_exp,
                                 length=self.qubit_pulseLength + self.us2cycles(0.01))

        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        qubit_freq = self.freq2reg(self.cfg["qubit_freq_first"],
                                   gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain_first"],
                                 waveform="qubit")

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  #play probe pulse
        qubit_freq = self.freq2reg(self.cfg["qubit_freq"],
                                   gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["start"],
                                 waveform="qubit")

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))  #play probe pulse
        self.sync_all() # align

        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1_readout,
                                 length=self.us2cycles(self.cfg["length"]))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2_readout,
                                 length=self.us2cycles(self.cfg["length"]))

        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # wait = True
        # syncdelay=self.us2cycles(self.cfg["relax_delay"])
        # self.trigger([0], pins=None, adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))
        # self.pulse(ch=self.cfg["res_ch"])
        # self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"]) + self.us2cycles(self.cfg["readout_length"]))
        # # self.waiti(0, self.us2cycles(self.cfg["readout_length"]) + 100)
        # if wait:
        #     # tProc should wait for the readout to complete.
        #     # This prevents loop counters from getting incremented before the data is available.
        #     self.wait_all()
        # if syncdelay is not None:
        #     self.sync_all(syncdelay)
        #
        # # self.synci(self.us2cycles(self.cfg["relax_delay"]))



    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"]/2))  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['readout_length'], ro_ch = 0)

        return shots_i0,shots_q0



# ====================================================== #

class SingleShotProgramFFPiPulse(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
        shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)

        i_g = shots_i0[0]
        q_g = shots_q0[0]
        i_e = shots_i0[1]
        q_e = shots_q0[1]

        data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
        self.data = data

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=20) ### arbitrary ran, change later

        # stop = 100
        # plt.figure(101)
        # plt.plot(i_g[0:stop], q_g[0:stop], 'o')
        # plt.plot(i_e[0:stop], q_e[0:stop], 'o')
        # plt.show()


        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_g = data["data"]["i_g"]
        q_g = data["data"]["q_g"]
        i_e = data["data"]["i_e"]
        q_e = data["data"]["q_e"]

        #### plotting is handled by the helper histogram
        title = 'Read Length: ' + str(self.cfg["readout_length"]) + "us"
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=True, ran=ran, title = title)
        plt.suptitle(self.titlename)


        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        # else:
            # fig.clf(True)
            # plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


