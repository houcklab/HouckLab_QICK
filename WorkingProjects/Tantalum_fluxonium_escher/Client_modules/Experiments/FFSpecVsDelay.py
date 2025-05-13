###
# This experiment runs mFFSpecSlice in a loop with varying post_ff_delay.
# Lev May 13, 2025. Create file
###

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from time import time

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFSpecSlice import FFSpecSlice


class FFSpecVsDelay_Experiment(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress: bool = False, plot_disp: bool = True, plot_save: bool = True, fig_num: int = None):
        """
        Runs qubit spectroscopy with a fast flux pulse with post_ff_delay values changing in a for loop.
        Does not currently perform cavity transmission as presumably it's not that necessary. Will be updated if
        it looks like the readout is changing a lot. For now, readout should be tuned up AT THE POINT WE'RE MOVING TO.
        :param progress: bool: should the individual experiment files display a progress bar.
        :param plot_disp: bool: should we display the plots of the data during aqcuisition.
        :param plot_save: bool: should we save the plot of the data
        :param fig_num: int: fignum of figure to plot on
        :return: data: dict: dictionary of data obtained from the experiment.
        """

        # If no fig_num is given, use a brute-force way to create a new one. Else, assume we want to use the given value
        if fig_num is None:
            fig_num = 1
            while plt.fignum_exists(num = fig_num):
                fig_num += 1
        fig, axs = plt.subplot_mosaic([['a','a'],['b','c']], figsize = (8,10), num = fig_num)

        # Create the array of delays to loop over
        delays = np.linspace(self.cfg["post_ff_delay_start"], self.cfg["post_ff_delay_stop"], self.cfg["post_ff_delay_steps"])

        self.__predeclare_arrays(delays)

        # Time the experiments
        start_time = datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
        start = time()

        # Loop over different delay lengths
        for i, delay in enumerate(delays):
            if i == 1:
                step = time()

            # Update post_ff_delay value in config; creates key on first iteration (as it's not used in FFSpecVsDelay)
            self.cfg["post_ff_delay"] = delay

            # Run single slice program, take data
            prog = FFSpecSlice(self.soccfg, self.cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=self.progress)
            data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}

            self.data['data']['spec_Imat'][i, :] = data['data']['avgi'][0][0]
            self.data['data']['spec_Qmat'][i, :] = data['data']['avgq'][0][0]

            data_I = self.data['data']['spec_Imat'][i, :]
            data_Q =  self.data['data']['spec_Qmat'][i, :]

            # plot out the spec data
            sig = data_I + 1j * data_Q
            # avgamp0 = np.abs(sig)
            # Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]
            if i == 0:
                rangeQ = np.max(data_Q) - np.min(data_Q)
                rangeI = np.max(data_I) - np.min(data_I)
                if rangeQ > rangeI:
                    q_data = True
                    i_data = False
                    # Z_spec[i, :] = (data_I - np.max(data_I)) / (np.max(data_I) - np.min(data_I))#- self.cfg["minADC"]
                else:
                    q_data = False
                    i_data = True
                    # Z_spec[i, :] = (data_Q - np.max(data_Q)) / (np.max(data_Q) - np.min(data_Q))#- self.cfg["minADC"]

            # I_spec[i, :] = data_I
            #
            # Q_spec[i, :] = data_Q
            #
            # Z_spec[:i + 1, :] = spec_normalize(I_spec[:i + 1, :], Q_spec[:i + 1, :])
            # # Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]

        return self.data

    def __predeclare_arrays(self, delays):
        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        self.spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"], self.cfg["qubit_freq_expts"])
        #X_trans = (self.trans_fpts + self.cfg["cavity_LO"] / 1e6) / 1e3
        #X_trans_step = X_trans[1] - X_trans[0]
        #X_spec = self.spec_fpts / 1e3
        #X_spec_step = X_spec[1] - X_spec[0]
        # Y = voltVec
        # Y_step = Y[1] - Y[0]
        # Z_trans = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["TransNumPoints"]), np.nan)
        # Z_specamp = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        # Z_specphase = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        # Z_specI = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        # Z_specQ = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["SpecNumPoints"]), np.nan)
        #
        # ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.spec_Imat = np.zeros((self.cfg["post_ff_delay_steps"], self.cfg["qubit_freq_expts"]))
        self.spec_Qmat = np.zeros((self.cfg["post_ff_delay_steps"], self.cfg["qubit_freq_expts"]))
        self.data = {
            'config': self.cfg,
            'data': {'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                     'delays_vec': delays
                     }
        }

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        return (self.cfg["reps"] * self.cfg["post_ff_delay_steps"] * self.cfg["qubit_freq_expts"] *
                (self.cfg["relax_delay"] + self.cfg["ff_length"]) * 1e-6)  # [s]

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "const",     # --Fixed
        "read_length": 5,                # [us]
        "read_pulse_gain": 8000,         # [DAC units]
        "read_pulse_freq": 7392.25,      # [MHz]
        "ro_mode_periodic": False,       # Bool: if True, keeps readout tone on always

        # Qubit spec parameters
        "qubit_freq_start": 1001,        # [MHz]
        "qubit_freq_stop": 2000,         # [MHz]
        "qubit_pulse_style": "flat_top", # one of ["const", "flat_top", "arb"]
        "sigma": 0.050,                  # [us], used with "arb" and "flat_top"
        "qubit_length": 1,               # [us], used with "const"
        "flat_top_length": 0.300,        # [us], used with "flat_top"
        "qubit_gain": 25000,             # [DAC units]
        "qubit_ch": 1,                   # RFSOC output channel of qubit drive
        "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
        "qubit_mode_periodic": False,    # Bool: Applies only to "const" pulse style; if True, keeps qubit tone on always

        # Fast flux pulse parameters
        "ff_gain": 1,                    # [DAC units] Gain for fast flux pulse
        "ff_length": 50,                 # [us] Total length of positive fast flux pulse
        "ff_pulse_style": "const",       # one of ["const", "flat_top", "arb"], currently only "const" is supported
        "ff_ch": 6,                      # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

        # post_ff_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
        "post_ff_delay_start": 1,        # [us] Initial value
        "post_ff_delay_stop": 10,        # [us] Final value
        "post_ff_delay_steps": 10,       # number of post_ff_delay points to take

        "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "qubit_freq_expts": 2000,        # number of points of qubit frequency
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
    }