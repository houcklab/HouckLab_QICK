from qick.asm_v2 import AsmV2

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepWaveformAveragerProgram import \
    SweepWaveformAveragerProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *

from math import ceil

class ThreePartProgram_SweepOneFF(SweepWaveformAveragerProgram):
    def _body(self, cfg):
        # 1: FFPulses
        # self.delay_auto()
        FFDelayTime = 10
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01 + FFDelayTime)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 + FFDelayTime if i==0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        self.delay(len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01 + FFDelayTime)

        # 2: FFExpt
        self.FFLoad16Waveforms(self.FFExpts, self.FFPulse, cfg["IDataArray"])
        self.FFPulses_arb_length_and_delay(t_start = 0)

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
        self.FFInvert_arb_length_and_delay(t_start = 0)
        self.FFPulses(-1 * self.FFPulse, FFDelayTime+len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01,
                      t_start=0)
        self.delay(len(self.cfg["qubit_gains"]) * self.qubit_length_us + FFDelayTime+1.01)




class ThreePartProgram_SweepTwoFF(SweepWaveformAveragerProgram):
    def _body(self, cfg):
        # 1: FFPulses
        # self.delay_auto()
        FFDelayTime = 10
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01 + FFDelayTime)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = 1 + FFDelayTime if i == 0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time_)
        self.delay(len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01 + FFDelayTime)

        # 2: FFExpt
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples1"],
                             self.FFPulse, IQPulseArray=cfg["IDataArray1"], waveform_label='FFExpts1')
        self.delay_auto()
        self.FFLoad16Waveforms(self.FFBS, self.FFExpts, cfg["IDataArray2"])
        self.FFPulses_arb_length_and_delay(t_start=0)

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
        self.FFInvert_arb_length_and_delay(t_start=0)
        self.FFPulses(-1 * self.FFPulse, FFDelayTime + len(self.cfg["qubit_gains"]) * self.qubit_length_us + 1.01,
                      t_start=0)
        self.delay(len(self.cfg["qubit_gains"]) * self.qubit_length_us + FFDelayTime + 1.01)
        FF.FFInvertWaveforms(self, waveform_label='FFExpts1')
        self.delay(2+ceil(self.cfg["expt_samples1"]/16))