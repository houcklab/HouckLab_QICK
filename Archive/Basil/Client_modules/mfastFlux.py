from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

class LoopbackProgramFastFlux(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # cfg = self.cfg
        #
        # self.declare_gen(ch=ffChannel, nqz=cfg["ff_nqz"])
        # style = self.cfg["ff_pulse_style"]
        #
        # ff_freq = self.freq2reg(cfg["ff_freq"],
        #                            gen_ch=ffChannel)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        # self.ff_freq = ff_freq
        # self.style = style

        self.FFDefinitions()

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        #self.sync_all(200)  # give processor time to get ahead of the pulses
        # print(self.us2cycles(1, self.FF_Channel1),self.us2cycles(5, self.FF_Channel1),
        #       self.us2cycles(10, self.FF_Channel1), self.us2cycles(100, self.FF_Channel1) )

        self.FFPulses(self.FFReadouts, self.cfg["ff_length"], idata_pulse = False)

        # self.FFPulses_old(self.FFReadouts, self.us2cycles(self.cfg["ff_length"]))
        print(self.cfg["relax_delay"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

    # def FFDefinitions(self):
    #     ### Start fast flux
    #     for FF_info in self.cfg["FF_list_readout"]:
    #         self.declare_gen(ch=FF_info[0], nqz=self.cfg["ff_nqz"])
    #
    #     self.ff_feqreq = self.freq2reg(self.cfg["ff_fr"], gen_ch=self.cfg["ff_ch"])
    #     self.ff_style = self.cfg["ff_pulse_style"]
    #
    #     ### Finish FF
    #     self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
    #     self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
    #     self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]
    #
    #     self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3])
    #     self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])

    def FFDefinitions(self):
        ### Start fast flux
        for FF_info in self.cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=self.cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(self.cfg["ff_freq"], gen_ch=self.cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]


        self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3])
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])

    def FFPulses(self, list_of_gains, length_us, t_start = None, idata_pulse = False):
        for i, gain in enumerate(list_of_gains):
            ### Sara edited to correctly convert to cycles using the correct gen_ch
            length = self.us2cycles(length_us, gen_ch=self.FFChannels[i])
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
            if idata_pulse:
                gencfg = self.soccfg['gens'][self.FFChannels[i]]
                idata = np.ones(length * 16)
                idata = idata * gencfg['maxv'] * gencfg['maxv_scale']
                print(idata[:3])

                qdata = np.zeros(length * 16)
                self.add_pulse(ch=self.FFChannels[i], name="FF",
                               idata=idata, qdata=qdata)
                sigma = 2#self.us2cycles(0.0023, gen_ch=self.FFChannels[i])
                total_length = 4#self.us2cycles(0.0023 * 2, gen_ch=self.FFChannels[i])

                self.add_gauss(ch=self.FFChannels[i], name="qubit", sigma=sigma, length=total_length)

                self.set_pulse_registers(ch=self.FFChannels[i], freq=0,style='arb',
                                         phase=0, gain=int(gain),
                                         waveform="qubit",outsel="input")
        if t_start == None:
            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)
            self.pulse(ch=self.FF_Channel3)
        else:
            self.pulse(ch=self.FF_Channel1, t = t_start)
            self.pulse(ch=self.FF_Channel2, t = t_start)
            self.pulse(ch=self.FF_Channel3, t = t_start)

    def FFPulses_Optimized(self, list_of_gains, length_us, t_start=None, idata_pulse=False, IQPulseArray = [None, None, None]):
        for i, gain in enumerate(list_of_gains):
            ### Sara edited to correctly convert to cycles using the correct gen_ch
            length = self.us2cycles(length_us, gen_ch=self.FFChannels[i])
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
            if idata_pulse and type(IQPulseArray[i]) != type(None):
                gencfg = self.soccfg['gens'][self.FFChannels[i]]
                if length > len(IQPulseArray[i]):
                    additional_array = np.ones(length - len(IQPulseArray[i]))
                else:
                    additional_array = np.array([])
                # print(np.array(IQPulseArray[i][:length]), additional_array)
                idata = np.concatenate([np.array(IQPulseArray[i][:length]), additional_array])  #ensures
                # print(idata)
                idata = idata.repeat(16)
                idata = (idata * gencfg['maxv'] * gencfg['maxv_scale']) // 1
                print(idata[:20], len(idata))

                qdata = np.zeros(length * 16)
                self.add_pulse(ch=self.FFChannels[i], name="FF",
                               idata=idata, qdata=qdata)
                self.set_pulse_registers(ch=self.FFChannels[i], freq=0, style='arb',
                                         phase=0, gain=int(gain * 2 * 1),
                                         waveform="FF")
        if t_start == None:
            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)
            self.pulse(ch=self.FF_Channel3)
        else:
            self.pulse(ch=self.FF_Channel1, t=t_start)
            self.pulse(ch=self.FF_Channel2, t=t_start)
            self.pulse(ch=self.FF_Channel3, t=t_start)

