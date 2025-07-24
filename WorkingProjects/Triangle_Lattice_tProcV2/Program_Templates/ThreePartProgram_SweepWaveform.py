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
        assert cfg["start"] >= 0, "Can't have a negative start time."
        assert cfg["step"] > 0, "Can't have a negative step"


        before_reps = kwargs.get("before_reps", AsmV2())
        # The "reps" loop is outermost, so this will reset the cycle and sample counter on each of these loops
        reset_loop = AsmV2()
        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        reset_loop.write_reg(dst='cycle_counter', src=2 + ceil(cfg["start"] / 16) - cfg["step"] // 16)
        # sample_counter: total samples Mod 16, but output (1...16) instead
        reset_loop.write_reg(dst='sample_counter', src=(cfg["start"] - 1) % 16 + 1 - cfg["step"]  % 16)

        before_reps.extend_macros(reset_loop)
        kwargs["before_reps"] = before_reps

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
        # sample_counter: total samples Mod 16, but output (1...16) instead
        self.add_reg(name='sample_counter')
        # Set in before_reps of the "reps" loop (see self.__init__ above)


        # Increment the cycle and sample counter. Carry the one if sample_counter > 16.
        IncrementLength = AsmV2()
        IncrementLength.inc_reg(dst='cycle_counter',  src=cfg["step"] // 16)
        IncrementLength.inc_reg(dst='sample_counter', src=cfg["step"]  % 16)
        ############# If sample_counter > 16:
        IncrementLength.cond_jump("finish_inc", "sample_counter", "S", "-", 17)
        IncrementLength.inc_reg(dst='cycle_counter', src= +1)
        IncrementLength.inc_reg(dst='sample_counter',src= -16)
        IncrementLength.label("finish_inc")
        IncrementLength.nop()
        ##############
        # # Write into data memory for debugging
        # self.add_reg(name='data_counter')
        # self.write_reg(dst='data_counter', src=0)
        # IncrementLength.write_reg("temp", "w_length")
        # IncrementLength.inc_reg(addr='temp', src='sample_counter')
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "cycle_counter")
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "sample_counter")
        #############
        # TODO <--- V2 has a bug in exec_after!!!! need to tell Sho. give him version number too --->
        self.add_loop("expt_samples", int(self.cfg["expts"]), exec_before=IncrementLength)

        self.delay_auto(200)

    def _body(self, cfg):
        # 1: FFPulses
        # self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 1 + i*4*self.cfg["sigma"]
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)

        # 2: FFExpt
        # Special case: 0 samples, so skip directly to readout (no FFExpt)
        # If cycle_counter < 3 (the minimum length for an arb waveform)
        self.cond_jump("start readout", "cycle_counter", 'S', '-', 3)
        # Else, choose the correct waveform depending on the amount of samples mod 16
        for i in range(1,17):
            self.cond_jump( f"l{i}", "sample_counter", 'Z', '-', i)
        for i in range(1,17):
            self.label(f"l{i}")
            FF.FFPlayChangeLength(self, f"FFExpt_{i}", "cycle_counter", t_start=0)
            self.jump("finish")
        self.label("finish")
        # Delay by cycle_counter cycles
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)



        self.label("start readout")
        # 3: FFReadouts
        self.FFPulses(self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(1)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"] + 1)
        self.delay(self.cfg["res_length"] + 10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        self.cond_jump("finish_inv", "cycle_counter", 'S', '-', 3)
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
        # self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i == 0 else 1 + i * 4 * self.cfg["sigma"]
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)

        # 2: FFExpt
        self.FFPulses_direct()

        # Special case: 0 samples, so skip directly to readout (no FFExpt)
        # If cycle_counter < 3 (the minimum length for an arb waveform)
        self.cond_jump("start readout", "cycle_counter", 'S', '-', 3)
        # Else, choose the correct waveform depending on the amount of samples mod 16
        for i in range(1, 17):
            self.cond_jump(f"l{i}", "sample_counter", 'Z', '-', i)
        for i in range(1, 17):
            self.label(f"l{i}")
            FF.FFPlayChangeLength(self, f"FFExpt_{i}", "cycle_counter", t_start=0)
            self.jump("finish")
        self.label("finish")
        # Delay by cycle_counter cycles
        self.asm_inst(inst={'CMD': 'TIME', 'C_OP': 'inc_ref', 'R1': self._get_reg("cycle_counter")}, addr_inc=1)

        self.label("start readout")
        # 3: FFReadouts
        self.FFPulses(self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(1)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"] + 1)
        self.delay(self.cfg["res_length"] + 10)  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        self.cond_jump("finish_inv", "cycle_counter", 'S', '-', 3)
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