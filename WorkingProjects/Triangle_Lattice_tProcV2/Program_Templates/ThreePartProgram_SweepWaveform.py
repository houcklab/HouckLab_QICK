from qick.asm_v2 import AsmV2, AsmInst

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
from math import ceil

class ThreePartProgram_SweepOneFF(FFAveragerProgramV2):
    def __init__(self, *args, **kwargs):

        cfg = kwargs['cfg']
        after_reps = kwargs.get("after_reps", AsmV2())
        reset_loop = AsmV2()
        # reset_loop.add_reg(name='cycle_counter')
        reset_loop.write_reg(dst='cycle_counter', src=2 + ceil(cfg["start"] / 16))
        # sample_counter: total samples Mod 16, but output (1...16) instead
        # reset_loop.add_reg(name='sample_counter')
        reset_loop.write_reg(dst='sample_counter', src=(cfg["start"] - 1) % 16 + 1)

        after_reps.extend_macros(reset_loop)
        kwargs["after_reps"] = after_reps

        super().__init__(*args, **kwargs)


    def _initialize(self, cfg):
        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)
        longest_length = self.cfg["start"] + self.cfg["expts"] * self.cfg["step"]
        # print(longest_length)
        FF.FFLoad16Waveforms(self, self.FFPulse, "FFExpt", longest_length)

        # Qubit (Equal sigma for all)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        for i in range(len(self.cfg["qubit_gains"])):
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i],
                           phase=90, gain=cfg["qubit_gains"][i])

        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        self.add_reg(name='cycle_counter')
        self.write_reg(dst='cycle_counter',  src= 2 + ceil(cfg["start"]/16))
        # sample_counter: total samples Mod 16, but output (1...16) instead
        self.add_reg(name='sample_counter')
        self.write_reg(dst='sample_counter', src=(cfg["start"]-1) % 16 + 1)


        self.add_reg(name='data_counter')
        self.write_reg(dst='data_counter', src=10)
        self.add_reg(name='temp')

        self.write_dmem(addr=7, src='sample_counter')
        IncrementLength = AsmV2()
        IncrementLength.inc_reg(dst='cycle_counter',  src=cfg["step"] // 16)
        IncrementLength.inc_reg(dst='sample_counter', src=cfg["step"]  % 16)

        ############# If sample_counter > 16:
        IncrementLength.cond_jump("finish_inc", "sample_counter", "S", "-", 17)
        IncrementLength.inc_reg(dst='cycle_counter', src= +1)
        IncrementLength.inc_reg(dst='sample_counter',src= -16)
        IncrementLength.label("finish_inc")
        ##############

        # IncrementLength.write_reg("temp", "w_length")
        # IncrementLength.inc_reg(addr='temp', src='sample_counter')
        IncrementLength.inc_reg(dst='data_counter', src=+1)
        IncrementLength.write_dmem("data_counter", "sample_counter")
        IncrementLength.nop()
        #############
        print(self.cfg["expts"])
        self.add_loop("expt_samples", self.cfg["expts"], exec_after=IncrementLength)

        # print("writing to data memory")
        # self.write_dmem(addr=1, src=137)
        # self.write_dmem(addr=2, src='w_length')
        # self.write_dmem(addr=3, src=137)
        # self.write_dmem(addr=4, src='w_env')
        # self.write_dmem(addr=5, src=137)
        # self.write_dmem(addr=6, src='cycle_counter')
        self.delay_auto(200)

    def _body(self, cfg):
        # 1: FFPulses
        # self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 1 + i*4*self.cfg["sigma"]
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)

        # 2: FFExpt
        # Play the correct pulse depending on sample counter, which has values from 1 to 16
        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(1,17):
            self.cond_jump( f"l{i}", "sample_counter", 'Z', '-', i)
        for i in range(1,17):
            self.label(f"l{i}")
            FF.FFPlayChangeLength(self, f"FFExpt_{i}", "cycle_counter", t_start=0)
            self.jump("finish")

        self.label("finish")
        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)


        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"], t_start=0)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"])
        self.delay(2*self.cfg["res_length"] + 10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        for i in range(1, 17):
            self.cond_jump(f"{i}_inv", "sample_counter", 'Z', '-', i)
        for i in range(1, 17):
            self.label(f"{i}_inv")
            FF.FFInvertWaveforms(self, f"FFExpt_{i}", t_start=0)
            self.jump("finish_inv")
        self.label("finish_inv")
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01, t_start=0)
        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 10.01)

    def loop_pts(self):
        return (self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts']) ,)




class ThreePartProgram_SweepTwoFF(ThreePartProgram_SweepOneFF):
    def _body(self, cfg):
        # 1: FFPulses
        self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        # 2: FFExpt
        assert 'expt_samples' not in self.cfg, "Use expt_samples1 and expt_samples2 instead."
        assert 'IDataArray'  not in self.cfg, "Use IDataArray1 and IDataArray2 instead."

        # print(self.cfg["IDataArray1"], self.cfg["IDataArray2"])
        concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_samples1"]], arr2])
                                    for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"],
                             self.FFPulse, IQPulseArray=concat_IQarray, waveform_label='FFExpts')
        self.delay_auto()


        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3) # Overshoot to freeze dynamics
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 4.65515/1e3*3)

        ###     If waveform memory becomes a problem, change this code to use the same waveform
        ###         but invert the gain on the generator channel.
        IQ_Array_Negative = [None if array is None else -1 * np.array(array) for array in concat_IQarray]
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples1"]+self.cfg["expt_samples2"], -1 * self.FFReadouts, IQPulseArray = IQ_Array_Negative,
                            waveform_label='FF2')
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.delay_auto()