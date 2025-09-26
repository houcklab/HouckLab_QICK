###
# This experiment runs mFFTransSlice in a loop with varying the ff value.
###

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from time import time

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFTransSlice import FFTransSlice_Experiment


class FFTransVsFlux_Experiment(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress: bool = False, plot_disp: bool = True, plot_save: bool = True, fig_num: int = None):
        """

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

        mosaic =[['amp']]
        fig, axs = plt.subplot_mosaic(mosaic, figsize=(14, 10), num=fig_num)

        # convenience handles we’ll re-use
        im_handles, cbar_handles = {}, {}

        self.__predeclare_arrays()

        # Time the experiments
        start_time = datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
        start = time()

        # Loop over different ff_gains
        for i, gain in enumerate(self.ff_gains):
            print('Gain:')
            print(gain)
            if i == 1:
                step = time()

            # Update ff_gain value in config; creates key on first iteration
            self.cfg["ff_gain"] = gain

            # Run single slice program, take data
            expt = FFTransSlice_Experiment(path="FFTransVsFlux_Slice", cfg=self.cfg, soc=self.soc, soccfg=self.soccfg,
                                              outerFolder = self.outerFolder, short_directory_names = True)
            dat = expt.acquire(progress = True)
            data = {'config': dat['config'],
                    'data': {'x_pts': dat['data']['fpts'], 'avgi': dat['data']['avgi'], 'avgq': dat['data']['avgq']}}

            # Store the data in the data dictionary (see note on references in __predeclare_arrays()
            self.Is[i, :] = data['data']['avgi']
            self.Qs[i, :] = data['data']['avgq']
            self.amps[i, :] = np.sqrt(np.square(self.Is[i, :]) + np.square(self.Qs[i, :]))  # - self.cfg["minADC"]
            self.phases[i,:] = np.angle(self.Is[i,:] + 1j*self.Qs[i,:])

            # --------   draw / update each panel   -----------------------------------
            def _imshow(key, mat, extent, cmap='viridis'):
                """Initialise or update a single imshow + colorbar."""
                if key not in im_handles:
                    im_handles[key] = axs[key].imshow(
                        np.transpose(mat), aspect='auto', origin='lower',
                        interpolation='none', extent=extent, cmap=cmap
                    )
                    cbar_handles[key] = fig.colorbar(im_handles[key], ax=axs[key], extend='both')
                else:
                    im_handles[key].set_data(np.transpose(mat))
                    im_handles[key].set_clim(vmin=np.nanmin(mat), vmax=np.nanmax(mat))
                    cbar_handles[key].remove()
                    cbar_handles[key] = fig.colorbar(im_handles[key], ax=axs[key], extend='both')

            extent = [self.ff_gains[0], self.ff_gains[-1],
                      self.trans_fpts[0], self.trans_fpts[-1]]

            _imshow('amp', self.amps, extent)

            # labels (set once)
            if i == 0:
                axs['amp'].set_title('Amplitude')

                for ax in axs.values():
                    ax.set_ylabel('Trans freq (MHz)')
                    ax.set_xlabel('FF end point [DAC units]')

            if plot_disp:
                plt.show(block=False)
                plt.pause(0.2)

            # # Create new plot the first time, change data in the future; matplotlib is too slow.
            # if i == 0:
            #     plot1 = axs['a'].imshow(np.transpose(self.amps), aspect = 'auto', origin = 'lower', interpolation = 'none',
            #                             extent = [self.delays[0] * 1000, self.delays[-1] * 1000,
            #                                       self.spec_fpts[0], self.spec_fpts[-1]])
            #     cbar0 = fig.colorbar(plot1, ax=axs['a'], extend='both')
            #     cbar0.set_label('ADC units', rotation=90)
            # else:
            #     plot1.set_data(np.transpose(self.amps))
            #     plot1.set_clim(vmin=np.nanmin(self.amps))
            #     plot1.set_clim(vmax=np.nanmax(self.amps))
            #     cbar0.remove()
            #     cbar0 = fig.colorbar(plot1, ax=axs['a'], extend='both')
            #     cbar0.set_label('ADC units', rotation=90)
            #
            # axs['a'].set_ylabel("Spec frequency (MHz)")
            # axs['a'].set_xlabel("post FF pulse delay (ns)")
            #
            # if plot_disp:
            #     plt.show(block=False)
            #     plt.pause(0.2)

            # Z_spec[:i + 1, :] = spec_normalize(I_spec[:i + 1, :], Q_spec[:i + 1, :])
            # # Z_spec[i, :] = avgamp0  # - self.cfg["minADC"]

        plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))
        plt.savefig(self.iname)

        return self.data

    def __predeclare_arrays(self):
        # Create the array of delays to loop over
        self.ff_gains = np.rint(np.linspace(self.cfg["ff_gain_start"], self.cfg["ff_gain_stop"], num = self.cfg["ff_gain_steps"])).astype(int)
        # Create array of transmission frequency points
        self.trans_fpts = np.linspace(start = self.cfg['start_freq'], stop = self.cfg['stop_freq'], num = self.cfg['num_freqs'])

        # Declare and instantiate some arrays and the data dictionary, to be filled with data
        # We've created two references to the same arrays: for example, self.Is and self.data['data']['spec_Imat'] are
        # pointers to the same location, and changing either will change both.
        self.Is = np.zeros((self.cfg["ff_gain_steps"], self.cfg["num_freqs"]))
        self.Qs = np.zeros((self.cfg["ff_gain_steps"], self.cfg["num_freqs"]))
        self.amps = np.full((self.cfg["ff_gain_steps"], self.cfg["num_freqs"]), np.nan)
        self.phases = np.full((self.cfg["ff_gain_steps"], self.cfg["num_freqs"]), np.nan)
        self.data = {
            'config': self.cfg,
            'data': {'trans_Imat': self.Is, 'trans_Qmat': self.Qs, 'trans_fpts': self.trans_fpts,
                     'ff_gains_vec': self.ff_gains
                     }
        }

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        #TODO broken by change of experiment
        return 1

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "const",     # --Fixed
        "read_length": 5,                # [us]
        "read_pulse_gain": 8000,         # [DAC units]
        "read_pulse_freq": 7392.25,      # [MHz]
        "ro_mode_periodic": False,       # Bool: if True, keeps readout tone on always

        # Fast flux pulse parameters
        "ff_length": 50,                 # [us] Total length of positive fast flux pulse
        "ff_pulse_style": "const",       # one of ["const", "flat_top", "arb"], currently only "const" is supported
        "ff_ch": 6,                      # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

        # ff_gain sweep parameters: DAC value of fast flux pulse endpoint
        "ff_gain_start": 0,              # [DAC] Initial value
        "ff_gain_stop": 2,               # [DAC] Final value
        "ff_gain_steps": 10,             # number of qubit_spec_delay points to take

        # New format parameters for transmission experiment
        "start_freq": 5000,              # [MHz] Start frequency of sweep
        "stop_freq": 6000,               # [MHz] Stop frequency of sweep
        "num_freqs": 101,                # Number of frequency points to use
        "init_time": 1,                  # [us] Thermalisation time after FF to new point before starting measurement
        "measure_at_0": False,           # [Bool] Do we go back to 0 DAC units on the FF to measure?
        "reversed_pulse": False,         # [Bool] Do we play a reversed pulse on the ff channel after measurement?

        "yokoVoltage": 0,                # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
    }