###
# This experiment runs mFFSpecSlice in a loop with varying qubit_spec_delay.
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
        Runs qubit spectroscopy with a fast flux pulse with qubit_spec_delay values changing in a for loop.
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

        mosaic = [['amp', 'phase'],
                  ['i', 'q']]
        fig, axs = plt.subplot_mosaic(mosaic, figsize=(14, 10), num=fig_num)

        # convenience handles we’ll re-use
        im_handles, cbar_handles = {}, {}

        self.__predeclare_arrays()

        # Time the experiments
        start_time = datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
        start = time()

        # Loop over different delay lengths
        for i, delay in enumerate(self.delays):
            if i == 1:
                step = time()

            # Update qubit_spec_delay value in config; creates key on first iteration (as it's not used in FFSpecVsDelay)
            self.cfg["qubit_spec_delay"] = delay

            # Run single slice program, take data
            prog = FFSpecSlice(self.soccfg, self.cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=self.progress)
            data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}

            # Store the data in the data dictionary (see note on references in __predeclare_arrays()
            self.Is[i, :] = data['data']['avgi'][0][0]
            self.Qs[i, :] = data['data']['avgq'][0][0]
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

            extent = [self.delays[0] * 1000, self.delays[-1] * 1000,
                      self.spec_fpts[0], self.spec_fpts[-1]]

            _imshow('amp', self.amps, extent)
            _imshow('phase', self.phases, extent,)
            _imshow('i', self.Is, extent)
            _imshow('q', self.Qs, extent)

            # labels (set once)
            if i == 0:
                axs['amp'].set_title('Amplitude')
                axs['phase'].set_title('Phase (rad)')
                axs['i'].set_title('I')
                axs['q'].set_title('Q')
                for ax in axs.values():
                    ax.set_ylabel('Spec freq (MHz)')
                    ax.set_xlabel('post-FF delay (ns)')

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
        self.delays = np.linspace(self.cfg["qubit_spec_delay_start"], self.cfg["qubit_spec_delay_stop"], self.cfg["qubit_spec_delay_steps"])
        # Create array of spectroscopy frequency points
        self.spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"], self.cfg["qubit_freq_expts"])

        # Declare and instantitate some arrays and the data dictionary, to be filled with data
        # We've created two references to the same arrays: for example, self.Is and self.data['data']['spec_Imat'] are
        # pointers to the same location, and changing either will change both.
        self.Is = np.zeros((self.cfg["qubit_spec_delay_steps"], self.cfg["qubit_freq_expts"]))
        self.Qs = np.zeros((self.cfg["qubit_spec_delay_steps"], self.cfg["qubit_freq_expts"]))
        self.amps = np.full((self.cfg["qubit_spec_delay_steps"], self.cfg["qubit_freq_expts"]), np.nan)
        self.phases = np.full((self.cfg["qubit_spec_delay_steps"], self.cfg["qubit_freq_expts"]), np.nan)
        self.data = {
            'config': self.cfg,
            'data': {'spec_Imat': self.Is, 'spec_Qmat': self.Qs, 'spec_fpts': self.spec_fpts,
                     'delays_vec': self.delays
                     }
        }

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        #TODO broken by change of experiment
        if self.cfg["qubit_pulse_style"] == "arb":
            qubit_pulse_length = self.cfg["sigma"] * 4  # [us]
        elif self.cfg["qubit_pulse_style"] == "flat_top":
            qubit_pulse_length = self.cfg["sigma"] * 4 + self.cfg["flat_top_length"]  # [us]
        elif self.cfg["qubit_pulse_style"] == "const":
            qubit_pulse_length = self.cfg["qubit_length"]  # [us]

        delays = np.linspace(self.cfg["qubit_spec_delay_start"], self.cfg["qubit_spec_delay_stop"], self.cfg["qubit_spec_delay_steps"])

        pulse_length = sum([np.max([self.cfg['ff_length'] + self.cfg['pre_ff_delay'], delay + qubit_pulse_length]) for delay in delays])
        return (self.cfg["reps"] * self.cfg["qubit_spec_delay_steps"] * self.cfg["qubit_freq_expts"] *
                (self.cfg['read_length'] + self.cfg["relax_delay"] + pulse_length) * 1e-6)  # [s]

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

        # qubit_spec_delay sweep parameters: delay after fast flux pulse (before qubit pulse)
        "qubit_spec_delay_start": 0,     # [us] Initial value
        "qubit_spec_delay_stop": 2,     # [us] Final value
        "qubit_spec_delay_steps": 10,    # number of qubit_spec_delay points to take

        "yokoVoltage": -0.115,           # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "qubit_freq_expts": 2000,        # number of points of qubit frequency
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
    }