import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.TwoPartProgram import \
    TwoPartProgram
from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2



# TODO
class NGateProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        # print(cfg["res_freqs"])
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

        for i in range(len(self.cfg["qubit_gains"])):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            freq_ = cfg["qubit_freqs"][i]

            for j in range(self.cfg.get("number_of_pulses", 1)):
                gain_ = self.cfg["qubit_gains_matrix"][i, j]
                phase_ = self.cfg["qubit_phases_matrix"][i, j]

                self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_{i}_{j}', style="arb", envelope=f"qubit{i}",
                               freq=freq_,
                               phase=phase_,
                               gain=gain_)

        self.qubit_total_length_us = 4 * sum(cfg["sigma"])


    def _body(self, cfg):

        ############
        # print(cfg["readout_lengths"])
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.cfg['number_of_pulses'] * self.qubit_total_length_us + FF_Delay_time)

        for i in range(len(self.cfg["qubit_gains"])):
            for j in range(self.cfg.get("number_of_pulses", 1)):
                time_ = FF_Delay_time if i == 0 and j == 0 else 'auto'

                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_{i}_{j}', t=time_)

        self.delay_auto()

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        self.delay_auto()


class SweepXPhase(SweepExperiment1D_lines):
    '''
    This experiment performs two pi/2 pulses sequentially while sweeping the phase of the second pulse.
    '''
    def init_sweep_vars(self):

        self.Program = NGateProgram
        self.z_value = 'population_corrected'

        self.x_key = ('qubit_phases_matrix', self.cfg['swept_qubit']-1, 1)
        self.x_points = np.linspace(self.cfg['phase_start'], self.cfg['phase_end'],
                                    self.cfg['phase_num_points'])
        self.xlabel = 'pi pulse phase'

        number_of_qubits = len(self.cfg['qubit_gains'])
        number_of_pulses = 2
        self.cfg['number_of_pulses'] = number_of_pulses

        if 'qubit_gains_matrix' in self.cfg:
            qubit_gains_matrix =  self.cfg['qubit_gains_matrix']

            if isinstance(qubit_gains_matrix, np.ndarray):
                if len(qubit_gains_matrix.shape) == 2:
                    if qubit_gains_matrix.shape != (number_of_qubits, number_of_pulses):
                        # needs to have shape (number of qubits, number of pulses)
                        raise ValueError('qubit_gains_matrix must be a 2D array with shape (number of qubits, number of pulses)')
                    else:
                        if len(qubit_gains_matrix) == number_of_pulses:
                            qubit_gains_matrix = np.tile(qubit_gains_matrix, (number_of_qubits, 1))
                        elif len(qubit_gains_matrix) == len(self.cfg['qubit_pulse']):
                            qubit_gains_matrix = np.transpose(np.tile(qubit_gains_matrix, (number_of_pulses, 1)))
            elif isinstance(qubit_gains_matrix, (int, float)):
                qubit_gains_matrix = np.ones((number_of_qubits, 2)) * qubit_gains_matrix

            self.cfg['qubit_gains_matrix'] = qubit_gains_matrix

        else:
            self.cfg['qubit_gains_matrix'] = np.transpose(np.tile(self.cfg['qubit_gains'],(number_of_pulses,1)))

        self.cfg['qubit_phases_matrix'] = np.zeros((number_of_qubits, number_of_pulses))