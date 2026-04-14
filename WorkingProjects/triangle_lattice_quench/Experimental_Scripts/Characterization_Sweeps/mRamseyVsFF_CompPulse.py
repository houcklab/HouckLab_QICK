
import matplotlib.pyplot as plt
import numpy as np
import scipy
from qick.asm_v2 import QickSweep1D, AsmV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import \
    RamseyVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepCyclesAveragerProgram import \
    SweepCyclesAveragerProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import \
    SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensated_Pulse
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast, omega_guess
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2

'''Same as T2R experiment except you use a compensated pulse for QubitPulse'''
class RamseyCompPulseProgram(SweepCyclesAveragerProgram):
    def _initialize(self, cfg):
        super()._initialize(cfg)
        # Qubit (Equal sigma for all)
        self.phase_loop = 180
        # add qubit pulse
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_1', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=0, gain=cfg["pi2_gain"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive_2', style="arb", envelope="qubit",
                       freq=cfg["qubit_drive_freq"],
                       phase=self.phase_loop, gain=cfg["pi2_gain"])
        self.qubit_length_us = cfg["sigma"] * 4
        self.qubit_length_cycles = self.us2cycles(self.qubit_length_us)  # in master clock units
        print('cycles:', self.qubit_length_cycles)

        self.add_reg(name='pulse_delay_counter')

    def _body(self, cfg):

        IDataArray = [Compensated_Pulse(fgain, 0, Qubit=j+1) for j, fgain in enumerate(self.FFPulse)]
        self.FFLoad1Waveform(self.FFPulse, [0]*len(self.FFPulse), IDataArray)


        # schedule second qubit drive to end right before the compensated pulse
        self.write_reg(dst='pulse_delay_counter', src='cycle_counter')
        self.inc_reg(dst='pulse_delay_counter', src= - self.qubit_length_cycles)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_1", t=0.100)  # pi/2
        self.FFPulses_arb_cycles_and_delay(t_start=0, delay_reg='pulse_delay_counter')
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_2", t=0.000,
                   tag='swept_delay')  # pi/2, with phase
        self.delay(self.qubit_length_us)


        self.FFPulses(self.FFReadouts, cfg["res_length"], t_start=0)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"] + 1)
        self.delay(self.cfg["res_length"] + 10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        self.FFInvert_arb_cycles_and_delay(t_start=0)

    def loop_pts(self):
        return (self.cfg['step'] * np.arange(self.cfg['expts']) ,)

class RamseyVsFFComp(RamseyVsFF):

    def init_sweep_vars(self):
        self.cfg.setdefault('qubit_drive_freq', self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift",0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

        qubit_cycles = self.soccfg.us2cycles(4*self.cfg['sigma'])
        self.cfg['start'] = 2*qubit_cycles + self.soccfg.us2cycles(0.100)
        self.cfg['step'] = self.soccfg.us2cycles(self.cfg['stop_delay_us'])//self.cfg['expts']
        print('step =', self.cfg['step'])
        assert self.cfg['step'] != 0

        print("Drive frequency at:", self.cfg['qubit_drive_freq'])
        if "phase_shift_cycles" in self.cfg:
            print("Caution: Adding additional cycles to RamseyVsFF. Did you intend to do this?")
        # else:
        #     self.cfg["phase_shift_cycles"] = 0

        self.Program = RamseyCompPulseProgram

        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)


        self.z_value = 'population' if self.cfg['populations'] else 'contrast' # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Delay (cycles = 4.65 ns)'  # for plotting
