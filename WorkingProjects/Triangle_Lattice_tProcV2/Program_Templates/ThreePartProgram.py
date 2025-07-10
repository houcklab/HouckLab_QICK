from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *

import scipy

class ThreePartProgramOneFF(FFAveragerProgramV2):
    def _initialize(self, cfg):
        # Qubit (Equal sigma for all)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit
        self.pulse_sigma = cfg["sigma"]
        self.pulse_qubit_length = cfg["sigma"] * 4
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])

        for i in range(len(self.cfg["qubit_gains"])):
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i],
                           phase=90, gain=cfg["qubit_gains"][i])
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        # 1: FFPulses
        self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        # 2: FFExpt
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_cycles"], self.FFPulse, IQPulseArray= self.cfg["IDataArray"],
                             waveform_label='FFExpts')
        self.delay_auto()


        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        self.trigger(ros=cfg["ro_chs"], pins=[0],
                     t=cfg["adc_trig_delay"])
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)

        ###     If waveform memory becomes a problem, change this code to use the same waveform
        ###         but invert the gain on the generator channel.
        IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in self.cfg["IDataArray"]]
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_cycles"], -1 * self.FFReadouts, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.delay_auto()

class ThreePartProgramTwoFF(ThreePartProgramOneFF):
    def _body(self, cfg):
        # 1: FFPulses
        self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        # 2: FFExpt
        assert 'expt_cycles' not in self.cfg, "Use expt_cycles1 and expt_cycles2 instead."
        assert 'IDataArray'  not in self.cfg, "Use IDataArray1 and IDataArray2 instead."

        # print(self.cfg["IDataArray1"], self.cfg["IDataArray2"])
        concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_cycles1"]], arr2])
                                    for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_cycles1"]+self.cfg["expt_cycles2"],
                             self.FFPulse, IQPulseArray=concat_IQarray, waveform_label='FFExpts')
        self.delay_auto()


        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        self.trigger(ros=cfg["ro_chs"], pins=[0],
                     t=cfg["adc_trig_delay"])
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)

        ###     If waveform memory becomes a problem, change this code to use the same waveform
        ###         but invert the gain on the generator channel.
        IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in concat_IQarray]
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_cycles1"]+self.cfg["expt_cycles2"], -1 * self.FFReadouts, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.delay_auto()

# class ThreePartProgramTwoFF(ThreePartProgramOneFF):
#     def body(self):
#         # 1: FFPulses
#         self.sync_all(gen_t0=self.gen_t0)
#         self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
#         for i in range(len(self.cfg["qubit_gains"])):
#             gain_ = self.cfg["qubit_gains"][i]
#             freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])
#             time_ = self.us2cycles(1) if i == 0 else 'auto'
#
#             self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
#                                  gain=gain_,
#                                  waveform="qubit", t=time_)
#         # 2: FFExpt
#         assert 'expt_cycles' not in self.cfg, "Use expt_cycles1 and expt_cycles2 instead."
#         assert 'IDataArray'  not in self.cfg, "Use IDataArray1 and IDataArray2 instead."
#
#         concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_cycles1"]], arr2])
#                             for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
#         # fig, ax = plt.subplots()
#         # for i, arr in enumerate(concat_IQarray):
#         #     ax.plot(arr,marker='o', label=i)
#         # ax.legend()
#         # plt.show(block=True)
#         self.FFPulses_direct(self.FFExpts, self.cfg["expt_cycles1"]+self.cfg["expt_cycles2"],
#                              self.FFPulse, IQPulseArray=concat_IQarray)
#         self.sync_all(gen_t0=self.gen_t0)
#
#
#         if 'ReadoutIQ' in self.cfg:
#             print("Using loaded FFReadouts envelope")
#             self.FFPulses_direct(self.FFReadouts, int(3.0 / 0.145e-3 // 16 * 16 + 16),
#                                  [g[-1] for g in concat_IQarray], IQPulseArray=self.cfg['ReadoutIQ'], waveform_label='FFRO')
#             # Not enough waveform memory for the entire 20 us res_length so compensate the first 3 us
#         self.FFPulses(self.FFReadouts, self.cfg["res_length"]-3.0)
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=self.cfg["ro_chs"], pins=[0],
#                      adc_trig_delay=self.us2cycles(self.cfg["adc_trig_delay"]),
#                      wait=True,
#                      syncdelay=self.us2cycles(10))
#
#         # End: invert FF pulses to ensure pulses integrate to 0
#         self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
#         # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)
#
#         ###     If waveform memory becomes a problem, change this code to use the same waveform
#         ###         but invert the gain on the generator channel.
#         IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in concat_IQarray]
#         self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_cycles1"]+self.cfg["expt_cycles2"], - 1 * self.FFReadouts,
#                              IQPulseArray=IQ_Array_Negative,
#                              waveform_label='FF2')
#         self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
#
#

