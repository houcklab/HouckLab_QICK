import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV1.Basic_Experiments_Programs.SweepExperiment2D import SweepExperiment2D
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX




class ReadOpt_wSingleShotFFMUX(SweepExperiment2D):
    # SingleShot_ReadoutOptimize = False
    # SS_R_params = {"gain_start": 3000, "gain_stop": 20000, "gain_pts": 7, "span": 3, "trans_pts": 9, 'number_of_pulses': 1}
    #
    def init_sweep_vars(self):
        self.Program = SingleShotFFMUX

        self.y_key = ("res_gains", 0)
        self.y_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_stop'], self.cfg['gain_pts']) / 32000.
        self.y_plot_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_stop'], self.cfg['gain_pts'])

        self.x_key = "mixer_freq"
        self.x_points = np.linspace(self.cfg['mixer_freq'] - self.cfg['span'] / 2, self.cfg['mixer_freq'] + self.cfg['span'] / 2,
                                    self.cfg['trans_pts'])

        '''mixer_freq is swept, but plot total frequency'''
        self.x_plot_points = self.x_points + self.cfg['res_freqs'][0] + self.cfg['cavity_LO'] / 1e6

        self.z_value = 'fid'  # contrast or population
        self.ylabel = 'Cavity gain (DAC units)'  # for plotting
        self.xlabel = 'Readout frequency (MHz)'  # for plotting

class QubitPulseOpt_wSingleShotFFMUX(SweepExperiment2D):
    # SingleShot_QubitOptimize = False
    # SS_Q_params = {"Optimize_Index": 0, "q_gain_span": 5000, "q_gain_pts": 9, "q_freq_span": 5, "q_freq_pts": 9,
    #                'number_of_pulses': 1}
    def init_sweep_vars(self):
        self.Program = SingleShotFFMUX

        self.y_key = ("qubit_gains", 0)
        self.y_points = np.linspace(self.cfg['qubit_gains'][0] - self.cfg['q_gain_span'] / 2,
                                    self.cfg['qubit_gains'][0] + self.cfg['q_gain_span'] / 2,
                                    self.cfg['q_gain_pts'], dtype = int)

        self.x_key = ("qubit_freqs", 0)
        self.x_points = np.linspace(self.cfg['qubit_freqs'][0] - self.cfg['q_freq_span'] / 2,
                                    self.cfg['qubit_freqs'][0] + self.cfg['q_freq_span'] / 2,
                                    self.cfg['q_freq_pts'])



        self.z_value = 'fid'  # contrast or population
        self.ylabel = 'Qubit gain (DAC units)'  # for plotting
        self.xlabel = 'Drive frequency (MHz)'  # for plotting