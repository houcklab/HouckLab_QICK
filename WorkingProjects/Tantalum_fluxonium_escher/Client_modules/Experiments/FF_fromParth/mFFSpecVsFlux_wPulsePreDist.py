###
# This experiment runs mFFSpecSlice in a loop with varying dac value for ff.
# Parth Sept 13, 2025. Create file
###

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from time import time

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSlice_wPulsePreDist import FFSpecSlice_wPPD


class FFSpecVsFlux_wPulsePreDist(ExperimentClass):
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
        # start_time = datetime.now()
        # print('') ### print empty row for spacing
        # print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
        # start = time()

        # Loop over different delay lengths
        for i, dac_val in enumerate(self.dac_vecs):
            # if i == 1:
                # step = time()

            # Update the FF DAC Val
            self.cfg['ff_gain'] = int(dac_val)
            print(int(dac_val))

            self.soc.reset_gens()
            # Run single slice program, take data
            prog = FFSpecSlice_wPPD(self.soccfg, self.cfg)
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

            extent = [self.dac_vecs[0] , self.dac_vecs[-1] ,
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
                    ax.set_xlabel('Gain DAC Values')

            if plot_disp:
                plt.show(block=False)
                plt.pause(0.2)


        plt.suptitle(self.fname + '\nYoko voltage %f V' % (self.cfg['yokoVoltage']))
        plt.savefig(self.iname)

        return self.data

    def __predeclare_arrays(self):
        # Create the array of delays to loop over
        self.dac_vecs = np.linspace(self.cfg["ff_gain_start"], self.cfg["ff_gain_stop"], self.cfg["ff_gain_num_points"])
        # Create array of spectroscopy frequency points
        self.spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"], self.cfg["qubit_freq_expts"])

        # Declare and instantitate some arrays and the data dictionary, to be filled with data
        # We've created two references to the same arrays: for example, self.Is and self.data['data']['spec_Imat'] are
        # pointers to the same location, and changing either will change both.
        self.Is = np.zeros((self.cfg["ff_gain_num_points"], self.cfg["qubit_freq_expts"]))
        self.Qs = np.zeros((self.cfg["ff_gain_num_points"], self.cfg["qubit_freq_expts"]))
        self.amps = np.full((self.cfg["ff_gain_num_points"], self.cfg["qubit_freq_expts"]), np.nan)
        self.phases = np.full((self.cfg["ff_gain_num_points"], self.cfg["qubit_freq_expts"]), np.nan)
        self.data = {
            'config': self.cfg,
            'data': {'spec_Imat': self.Is, 'spec_Qmat': self.Qs, 'spec_fpts': self.spec_fpts,
                     'dac_vecs': self.dac_vecs
                     }
        }

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        #TODO broken by change of experiment
        return (self.cfg["reps"] * self.cfg["ff_gain_num_points"] * self.cfg["qubit_freq_expts"] *
                (self.cfg["relax_delay"] + self.cfg["ff_length"] + self.cfg['read_length']) * 1e-6)  # [s]

    # Template config dictionary, used in GUI for initial values
    UpdateConfig = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 20,  # [us]
        "read_pulse_gain": 5000,  # [DAC units]
        "read_pulse_freq": 6671.71,  # [MHz]
        "ro_mode_periodic": False,  # currently unused

        # Qubit spec parameters
        "qubit_freq_start": 400,  # [MHz]
        "qubit_freq_stop": 600,  # [MHz]
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.02,  # [us], used with "arb" and "flat_top"
        "qubit_length": 0.5,  # [us], used with "const"
        "flat_top_length": 0.050,  # [us], used with "flat_top"
        "qubit_gain": 1000,  # [DAC units]
        "qubit_ch": 1,  # RFSOC output channel of qubit drive
        "qubit_nqz": 1,  # Nyquist zone to use for qubit drive
        "qubit_mode_periodic": False,  # Currently unused, applies to "const" drive
        "qubit_spec_delay": 0.5,

        # Fast flux pulse parameters
        "ff_gain": 500,  # [DAC units] Gain for fast flux pulse
        "ff_length": 3,  # [us] Total length of positive fast flux pulse
        "pre_ff_delay": 0.05,  # [us] Delay before the fast flux pulse, Ideally has to be zero, just setting it to a minimal valye for now
        "ff_pulse_style": "const",
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        "yokoVoltage": -0.115,  # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 15,  # [us]
        "qubit_freq_expts": 301,  # number of points
        "reps": 8000,
        "use_switch": False,

        # Sweep through the dac values for ff
        "ff_gain_start": 0,
        "ff_gain_stop": -1000,
        "ff_gain_num_points": 5,
    }