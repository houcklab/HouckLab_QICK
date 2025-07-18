from qick.asm_v2 import AsmV2, QickSweep1D

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
        samples_sweep = QickSweep1D("expt_samples",
                                       start=cfg["start"],
                                       end=cfg["start"] + cfg["step"]*cfg["expts"])
        ff_expts_length_us =
        for channel in self.FFChannels:
            for i in range(1,17):
                wname = f"FFExpt_{i}_{channel}"
                self.read_wmem(name=wname)
                self.write_reg(dst='w_length', src=(cfg["start"]-1) % 16 + 1)
                self.write_wmem(name=wname)

        IncrementSamples = AsmV2()
        for channel in self.FFChannels:
            for i in range(1,17):
                wname = f"FFExpt_{i}_{channel}"
                IncrementSamples.read_wmem(name=wname)
                IncrementSamples.inc_reg(dst='w_length', src= + 1)
                IncrementSamples.write_wmem(name=wname)
        IncrementSamples.label("finish")
        IncrementSamples.nop()
        #############
        self.add_loop("expt_samples", self.cfg["expts"], exec_after=IncrementSamples)

    def _body(self, cfg):
        # 1: FFPulses
        self.delay_auto()
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        # 2: FFExpt
        # Play the correct pulse depending on sample counter, which has values from 1 to 16
        for i in range(1,17):
            self.cond_jump( "1", "sample_counter", 'Z', '-', i)
        for i in range(1,17):
            self.label(f"{i}")
            FF.FFPlayWaveforms(self, "FFExpt_{i}")
            self.jump("finish")

        self.label("finish")

        self.delay(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01
                   + )


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
        for i in range(1, 17):
            self.cond_jump("1", "sample_counter", 'Z', '-', i)
        for i in range(1, 17):
            self.label(f"{i}")
            FF.FFInvertWaveforms(self, "FFExpt_{i}")
            self.jump("finish")
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.delay_auto()

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