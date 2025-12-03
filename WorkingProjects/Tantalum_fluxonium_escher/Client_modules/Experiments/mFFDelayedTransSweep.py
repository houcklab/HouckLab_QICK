from datetime import datetime, time

import numpy as np
from matplotlib import pyplot as plt

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass


class FFDelayedTransSlice_Experiment(ExperimentClass):
    """
    This class takes mFFDelayedTransSlice inside a loop that sweeps some parameter, as defined in the config dictionary.
    """

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "const",    # --Fixed
        "read_length": 5,               # [us]
        "read_pulse_gain": 8000,        # [DAC units]
        "ro_mode_periodic": False,      # Bool: if True, keeps readout tone on always

        # Fast flux pulse parameters
        "ff_gain": 1,                   # [DAC units] Gain for fast flux pulse
        "ff_ch": 6,                     # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                    # Nyquist zone to use for fast flux drive
        "ff_length": 99,                # [us] Total length of positive fast flux pulse
        "pre_ff_delay": 0.5,            # [us] Delay before ff pulse starts
        "post_ff_delay": 0.5,           # [us] Delay after ff pulse is over and before measurement

        # New format parameters for transmission experiment
        "start_freq": 5000,             # [MHz] Start frequency of sweep
        "stop_freq": 6000,              # [MHz] Stop frequency of sweep
        "num_freqs": 101,               # Number of frequency points to use

        "yokoVoltage": 0,               # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,              # [us] Delay after measurement before starting next measurement
        "reps": 1000,                   # Reps of measurements; init program is run only once
        "sets": 5,                      # Sets of whole measurement; used in GUI
        "reversed_pulse": False,        # [Bool] Whether to play a reversed pulse to compensate for reactive elements

        "sweep_param": "ff_gain",       # [str] Which parameter in above to sweep
        "sweep_start": -300,            # Start value of parameter in units np.linspace can work with
        "sweep_stop": 300,              # Stop value of parameter in units np.linspace can work with
        "sweep_steps": 10,              # [int] Number of points in the sweep
    }

    def __predeclare_arrays(self):
        # Create the array of delays to loop over
        self.sweep_pts = np.linspace(self.cfg["sweep_start"], self.cfg["sweep_stop"], self.cfg["sweep_steps"])
        # Create array of spectroscopy frequency points
        self.trans_fpts = np.linspace(self.cfg["start_freq"], self.cfg["stop_freq"], self.cfg["num_freqs"])

        # Declare and instantitate some arrays and the data dictionary, to be filled with data
        # We've created two references to the same arrays: for example, self.Is and self.data['data']['spec_Imat'] are
        # pointers to the same location, and changing either will change both.
        self.Is = np.zeros((self.cfg["sweep_steps"], self.cfg["num_freqs"]))
        self.Qs = np.zeros((self.cfg["sweep_steps"], self.cfg["num_freqs"]))
        self.amps = np.full((self.cfg["sweep_steps"], self.cfg["num_freqs"]), np.nan)
        self.phases = np.full((self.cfg["sweep_steps"], self.cfg["num_freqs"]), np.nan)
        self.data = {
            'config': self.cfg,
            'data': {'trans_Imat': self.Is, 'trans_Qmat': self.Qs, 'trans_fpts': self.trans_fpts,
                     'sweep_vec': self.sweep_pts
                     }
        }

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
            while plt.fignum_exists(num=fig_num):
                fig_num += 1

        mosaic = [['amp', 'phase'],
                  ['i', 'q']]
        fig, axs = plt.subplot_mosaic(mosaic, figsize=(14, 10), num=fig_num)

        # convenience handles we’ll re-use
        im_handles, cbar_handles = {}, {}

        self.__predeclare_arrays()

        # Time the experiments
        start_time = datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
        start = time()

        # Loop over different delay lengths
        for i, sweep_pt in enumerate(self.sweep_pts):
            if i == 1:
                step = time()

            # Update value of the swept param in config
            self.cfg[self.cfg["sweep_param"]] = sweep_pt

            # Run single slice program, take data
            prog = FFDelayedTransSlice_Experiment(self.soccfg, self.cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=self.progress)
            data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}

            # Store the data in the data dictionary (see note on references in __predeclare_arrays()
            self.Is[i, :] = data['data']['avgi'][0][0]
            self.Qs[i, :] = data['data']['avgq'][0][0]
            self.amps[i, :] = np.sqrt(np.square(self.Is[i, :]) + np.square(self.Qs[i, :]))  # - self.cfg["minADC"]
            self.phases[i, :] = np.angle(self.Is[i, :] + 1j * self.Qs[i, :])

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
            _imshow('phase', self.phases, extent, )
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

        plt.suptitle(
            self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))
        plt.savefig(self.iname)

        return self.data