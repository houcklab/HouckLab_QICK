import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1Program
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots

class T1_FFExpt_Program(T1Program):
    def _body(self, cfg):

        self.FFPulses(self.FFPulse, 2 + self.qubit_length_us, t_start=0)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)  # play probe pulse
        self.delay(self.qubit_length_us + 2)

        # Sweep this delay time
        # print(self.delay_loop+1.0)
        self.FFPulses(self.FFExpts, self.delay_loop+1.0, t_start=0)
        self.delay(self.delay_loop + 1.0, tag = 'swept_delay')

        self.FFPulses(self.FFReadouts, cfg["res_length"], t_start=0)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.delay_loop+1.0)


class FFvsT1(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.Program = T1_FFExpt_Program

        self.y_key = ("FF_Qubits", str(self.cfg["qubitIndex"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)


        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubitIndex"]}'  # for plotting
        self.xlabel = 'Time (us)'  # for plotting