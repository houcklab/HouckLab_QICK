from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Coupling_strength_fit import fit_chevron, freqfit
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FFEnvelope_Helpers import StepPulseArrays
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram_SweepWaveform import ThreePartProgram_SweepOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import soc

class GainSweepOscillationsR(SweepExperiment2D_plots):
    # {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
    #                      'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

    def init_sweep_vars(self):
        self.Program = ThreePartProgram_SweepOneFF
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int)
        self.x_name = 'expt_samples'
        # self.x_points = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.z_value = 'population' # contrast or population
        self.ylabel = f'FF gain index {self.cfg["qubit_FF_index"]} (DAC units)'  # for plotting
        self.xlabel = 'Samples (0.291 ns)'  # for plotting


        self.cfg["IDataArray"] = StepPulseArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt')


    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        # print(self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Expt'])
        soc.reset_gens()
        if type(self.cfg["IDataArray"][0]) != type(None):
            self.cfg["IDataArray"][self.cfg["qubit_FF_index"] - 1] = \
                Compensated_Pulse(self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Expt'],
                                  self.cfg['FF_Qubits'][str(self.cfg["qubit_FF_index"])]['Gain_Pulse'],
                                    int(self.cfg["qubit_FF_index"]))
        # soc.load_mem(list(range(10+2*self.cfg['expts'])), 'dmem')
    def debug(self, prog):

        # print(soc.read_mem(10+2*self.cfg['expts'], 'dmem'))
        # print(prog)
        pass

    def analyze(self, data):
        data_dict = data['data']
        Z, time = data_dict['population_corrected'], data_dict['expt_samples']
        gains = data_dict.get('Gain_Expt', data_dict.get('Gain_BS'))
        self.freq_param_list = [None]*len(Z)
        self.fit_freqs = [None] * len(Z)
        self.fit_gains = [None] * len(Z)
        time = time * 0.291e-3 # Convert to us
        
        for ro_ind in range(len(Z)):
            try:
                pop_matrix = Z[ro_ind]
                freq_param, fit_freqs, fit_gains = fit_chevron(gains, time, pop_matrix, return_fit_points=True)
                self.freq_param_list[ro_ind] = freq_param
                self.fit_freqs[ro_ind] = np.array(fit_freqs)
                self.fit_gains[ro_ind] = np.array(fit_gains)
            except RuntimeError:
                pass

        data_dict['freq_param_list'] = self.freq_param_list
        data_dict['fit_freqs'] = self.fit_freqs
        data_dict['fit_gains'] = self.fit_gains

    def _display_plot(self, data=None, fig_axs=None):
        fig, axs = super()._display_plot(data, fig_axs)

        if 'freq_param_list' in self.__dict__:
            gains = data['data'].get('Gain_Expt', data['data'].get('Gain_BS'))
            gain_step = gains[1] - gains[0]
            gain_linspace = np.linspace(gains[0]-gain_step/2, gains[-1]+gain_step/2, 80)
            for ro_ind in range(len(axs)):
                # Plot the first cycle
                freq_param = self.freq_param_list[ro_ind]
                if freq_param is not None:
                    axs[ro_ind].scatter(1/self.fit_freqs[ro_ind] / 0.291e-3, self.fit_gains[ro_ind], color='r', marker='o', s=150)
                    axs[ro_ind].plot(1/freqfit(gain_linspace, *freq_param) / 0.291e-3, gain_linspace,
                                     color='r', ls=':', zorder=1, lw=5, label = f'g = {freq_param[2]:.2f} MHz')
                    fig.canvas.draw()
                    axs[ro_ind].autoscale(False)
                    axs[ro_ind].axhline(freq_param[0], color='r', label=f'FF Gain = {freq_param[0]:.1f}', zorder=1, lw=5)
                    axs[ro_ind].legend(prop={'size': 14})



