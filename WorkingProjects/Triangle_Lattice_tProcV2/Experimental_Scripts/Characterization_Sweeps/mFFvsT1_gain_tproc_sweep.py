import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1Program
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import \
    FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots

class T1_FFExpt_Program(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

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


        ### Start fast flux
        self.FFDefinitions(self)

        self.add_loop("delay_loop", self.cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])
        # add qubit pulse
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0])
        self.qubit_length_us = cfg["sigma"] * 4


    def _body(self, cfg):
        expt_length =  self.qubit_length_us + 1.05 + self.delay_loop
        self.FFPulses(self.FFPulse, expt_length)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.delay(self.qubit_length_us + 1.05)

        # Sweep this delay time
        self.delay(self.delay_loop, tag = 'swept_delay')

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, expt_length)

    def loop_pts(self):
        return (self.get_time_param("swept_delay", "t", as_array=True),)

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