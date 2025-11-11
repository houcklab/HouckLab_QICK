###
# This experiment runs mFFSpecSlice in a loop with varying qubit_spec_delay.
# Lev May 13, 2025. Create file
###

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from time import time

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSlice_wPulsePreDist import FFSpecSlice_wPPD


class FFSpecVsDelay_wPPD_Experiment(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress: bool = False, plot_disp: bool = True, plot_save: bool = True,
                fig_num: int = None, custom_delay_array=None, plot_debug = False):
        """
        Qubit spectroscopy vs post-FF delay.
        Handles non-uniform custom_delay_array by switching imshow (uniform) <-> pcolormesh (non-uniform)
        while keeping colorbars stable via update_normal().
        """
        import numpy as np
        import matplotlib.pyplot as plt
        from datetime import datetime
        from time import time

        # Figure selection
        if fig_num is None:
            fig_num = 1
            while plt.fignum_exists(num=fig_num):
                fig_num += 1

        mosaic = [['amp', 'phase'],
                  ['i', 'q']]
        fig, axs = plt.subplot_mosaic(mosaic, figsize=(14, 10), num=fig_num)

        # state
        artists, cbar_by_key = {}, {}

        # Predeclare arrays (sets self.delays, self.spec_fpts, and preallocs)
        self.__predeclare_arrays(delay_arr=custom_delay_array)

        # axis vectors in physical units
        delays_ns = np.asarray(self.delays, dtype=float) * 1000.0  # x
        freqs_mhz = np.asarray(self.spec_fpts, dtype=float)  # y

        # helpers -----------------------------------------------------------
        def _is_linear(x, rtol=1e-3, atol=1e-9):
            if len(x) < 3:
                return True
            d = np.diff(x)
            return np.allclose(d, d[0], rtol=rtol, atol=atol)

        def _centers_to_edges(c):
            c = np.asarray(c, float)
            if c.size == 1:
                w = 1.0
                return np.array([c[0] - 0.5 * w, c[0] + 0.5 * w])
            m = 0.5 * (c[1:] + c[:-1])
            left = c[0] - (m[0] - c[0])
            right = c[-1] + (c[-1] - m[-1])
            return np.concatenate(([left], m, [right]))

        def _ensure_colorbar(key, ax, mappable):
            """Create a colorbar once per panel; on updates, just rebind it to new mappable."""
            if key not in cbar_by_key or cbar_by_key[key] is None or getattr(cbar_by_key[key], "ax", None) is None:
                cbar_by_key[key] = fig.colorbar(mappable, ax=ax, extend='both')
            else:
                # keep same cbar, rebind to new mappable
                cbar_by_key[key].update_normal(mappable)

        def _set_titles_and_labels():
            axs['amp'].set_title('Amplitude')
            axs['phase'].set_title('Phase (rad)')
            axs['i'].set_title('I')
            axs['q'].set_title('Q')
            for ax in axs.values():
                ax.set_ylabel('Spec freq (MHz)')
                if self.cfg['spacing'] == 'log' and custom_delay_array is None:
                    ax.set_xlabel('log10(post-FF delay (ns))')
                else:
                    ax.set_xlabel('post-FF delay (ns)')

        def _draw_panel(key, Z, x_centers, y_centers, prefer_uniform=True):
            """
            Draw/update panel:
            - Use imshow when both axes are ~linear (fast).
            - Else use pcolormesh with proper bin edges.
            Keeps a single colorbar and updates it via update_normal().
            """
            ax = axs[key]
            Z = np.asarray(Z, float)

            if custom_delay_array is not None:
                use_uniform = False
            else:
                use_uniform = prefer_uniform

            # Remove any previous artist cleanly (but NOT the colorbar)
            if key in artists and artists[key] is not None:
                try:
                    artists[key].remove()
                except Exception:
                    pass
                artists[key] = None  # drop handle

            if use_uniform:
                if self.cfg['spacing'] == 'linear':
                    extent = [x_centers[0], x_centers[-1], y_centers[0], y_centers[-1]]
                elif self.cfg['spacing'] == 'log':
                    extent = [np.log10(x_centers[0] + 1e-12), np.log10(x_centers[-1]),
                              y_centers[0], y_centers[-1]]
                else:
                    raise ValueError(f"Unknown spacing {self.cfg['spacing']}")
                im = ax.imshow(Z.T, aspect='auto', origin='lower',
                               interpolation='none', extent=extent, cmap='viridis')
                artists[key] = im
                _ensure_colorbar(key, ax, im)
            else:
                Xe = _centers_to_edges(x_centers)
                Ye = _centers_to_edges(y_centers)
                # shading='auto' chooses 'flat' since we give edges; ensures shape compatibility
                qm = ax.pcolormesh(Xe, Ye, Z.T, shading='auto', cmap='viridis')
                artists[key] = qm
                _ensure_colorbar(key, ax, qm)

        # timing/info -------------------------------------------------------
        print()
        print('starting date time: ' + datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        start = time()

        # main loop ---------------------------------------------------------
        for i, delay in enumerate(self.delays):
            # update config
            self.cfg["qubit_spec_delay"] = delay

            # acquire
            prog = FFSpecSlice_wPPD(self.soccfg, self.cfg, plot_debug=plot_debug)
            x_pts, avgi, avgq = prog.acquire(
                self.soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=self.progress
            )
            # stash
            self.Is[i, :] = avgi[0][0]
            self.Qs[i, :] = avgq[0][0]
            self.amps[i, :] = np.hypot(self.Is[i, :], self.Qs[i, :])
            self.phases[i, :] = np.angle(self.Is[i, :] + 1j * self.Qs[i, :])

            # draw/update
            _draw_panel('amp', self.amps, delays_ns, freqs_mhz)
            _draw_panel('phase', self.phases, delays_ns, freqs_mhz)
            _draw_panel('i', self.Is, delays_ns, freqs_mhz)
            _draw_panel('q', self.Qs, delays_ns, freqs_mhz)

            if i == 0:
                _set_titles_and_labels()

            if plot_disp:
                plt.show(block=False)
                plt.pause(0.2)

        # finalize ----------------------------------------------------------
        plt.suptitle(
            self.fname + '\nYoko voltage %f V, FF amplitude %d DAC, FF ramp length %f ns.' %
            (self.cfg['yokoVoltage'], self.cfg['ff_gain'], self.cfg['ff_ramp_length'])
        )
        if plot_save:
            plt.savefig(self.iname)

        return self.data
    # def acquire(self, progress: bool = False, plot_disp: bool = True, plot_save: bool = True, fig_num: int = None, custom_delay_array = None):
    #     """
    #     Runs qubit spectroscopy with a fast flux pulse with qubit_spec_delay values changing in a for loop.
    #     Does not currently perform cavity transmission as presumably it's not that necessary. Will be updated if
    #     it looks like the readout is changing a lot. For now, readout should be tuned up AT THE POINT WE'RE MOVING TO.
    #     :param progress: bool: should the individual experiment files display a progress bar.
    #     :param plot_disp: bool: should we display the plots of the data during aqcuisition.
    #     :param plot_save: bool: should we save the plot of the data
    #     :param fig_num: int: fignum of figure to plot on
    #     :param custom_delay_array: np.array: if given, use this array of delays instead of the one in config
    #     :return: data: dict: dictionary of data obtained from the experiment.
    #     """
    #
    #     # If no fig_num is given, use a brute-force way to create a new one. Else, assume we want to use the given value
    #     if fig_num is None:
    #         fig_num = 1
    #         while plt.fignum_exists(num = fig_num):
    #             fig_num += 1
    #
    #     mosaic = [['amp', 'phase'],
    #               ['i', 'q']]
    #     fig, axs = plt.subplot_mosaic(mosaic, figsize=(14, 10), num=fig_num)
    #
    #     # convenience handles we’ll re-use
    #     im_handles, cbar_handles = {}, {}
    #
    #     self.__predeclare_arrays(delay_arr = custom_delay_array)
    #
    #     # Time the experiments
    #     start_time = datetime.now()
    #     print('') ### print empty row for spacing
    #     print('starting date time: ' + start_time.strftime("%Y/%m/%d %H:%M:%S"))
    #     start = time()
    #
    #     # Loop over different delay lengths
    #     for i, delay in enumerate(self.delays):
    #         if i == 1:
    #             step = time()
    #
    #         # Update qubit_spec_delay value in config; creates key on first iteration (as it's not used in FFSpecVsDelay)
    #         self.cfg["qubit_spec_delay"] = delay
    #
    #         # Run single slice program, take data
    #         prog = FFSpecSlice(self.soccfg, self.cfg)
    #         x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
    #                                          readouts_per_experiment=1, save_experiments=None,
    #                                          start_src="internal", progress=self.progress)
    #         data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
    #
    #         # Store the data in the data dictionary (see note on references in __predeclare_arrays()
    #         self.Is[i, :] = data['data']['avgi'][0][0]
    #         self.Qs[i, :] = data['data']['avgq'][0][0]
    #         self.amps[i, :] = np.sqrt(np.square(self.Is[i, :]) + np.square(self.Qs[i, :]))  # - self.cfg["minADC"]
    #         self.phases[i,:] = np.angle(self.Is[i,:] + 1j*self.Qs[i,:])
    #
    #         # --------   draw / update each panel   -----------------------------------
    #         def _imshow(key, mat, extent, cmap='viridis'):
    #             """Initialise or update a single imshow + colorbar."""
    #             if key not in im_handles:
    #                 im_handles[key] = axs[key].imshow(
    #                     np.transpose(mat), aspect='auto', origin='lower',
    #                     interpolation='none', extent=extent, cmap=cmap
    #                 )
    #                 cbar_handles[key] = fig.colorbar(im_handles[key], ax=axs[key], extend='both')
    #             else:
    #                 im_handles[key].set_data(np.transpose(mat))
    #                 im_handles[key].set_clim(vmin=np.nanmin(mat), vmax=np.nanmax(mat))
    #                 cbar_handles[key].remove()
    #                 cbar_handles[key] = fig.colorbar(im_handles[key], ax=axs[key], extend='both')
    #
    #         extent = [self.delays[0] * 1000, self.delays[-1] * 1000,
    #                   self.spec_fpts[0], self.spec_fpts[-1]]
    #
    #         _imshow('amp', self.amps, extent)
    #         _imshow('phase', self.phases, extent,)
    #         _imshow('i', self.Is, extent)
    #         _imshow('q', self.Qs, extent)
    #
    #         # labels (set once)
    #         if i == 0:
    #             axs['amp'].set_title('Amplitude')
    #             axs['phase'].set_title('Phase (rad)')
    #             axs['i'].set_title('I')
    #             axs['q'].set_title('Q')
    #             for ax in axs.values():
    #                 ax.set_ylabel('Spec freq (MHz)')
    #                 ax.set_xlabel('post-FF delay (ns)')
    #
    #         if plot_disp:
    #             plt.show(block=False)
    #             plt.pause(0.2)
    #
    #     plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))
    #     plt.savefig(self.iname)
    #
    #     return self.data

    def __predeclare_arrays(self, delay_arr = None):
        # Create the array of delays to loop over
        if delay_arr is not None:
            self.delays = delay_arr
        elif self.cfg.get("spacing", "linear") == "linear":
            self.delays = np.linspace(self.cfg["qubit_spec_delay_start"], self.cfg["qubit_spec_delay_stop"], self.cfg["qubit_spec_delay_steps"])
        elif self.cfg.get("spacing", "linear") == "log":
            self.delays = np.logspace(np.log10(self.cfg["qubit_spec_delay_start"] + 1e-12), np.log10(self.cfg["qubit_spec_delay_stop"] + 1e-12), self.cfg["qubit_spec_delay_steps"]) - 1e-12
        else:
            raise ValueError(f"Unknown spacing {self.cfg['spacing']}")
        # Create array of spectroscopy frequency points
        self.spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"], self.cfg["qubit_freq_expts"])

        # Declare and instantitate some arrays and the data dictionary, to be filled with data
        # We've created two references to the same arrays: for example, self.Is and self.data['data']['spec_Imat'] are
        # pointers to the same location, and changing either will change both.
        self.Is = np.zeros((self.delays.size, self.cfg["qubit_freq_expts"]))
        self.Qs = np.zeros((self.delays.size, self.cfg["qubit_freq_expts"]))
        self.amps = np.full((self.delays.size, self.cfg["qubit_freq_expts"]), np.nan)
        self.phases = np.full((self.delays.size, self.cfg["qubit_freq_expts"]), np.nan)
        self.data = {
            'config': self.cfg,
            'data': {'spec_Imat': self.Is, 'spec_Qmat': self.Qs, 'spec_fpts': self.spec_fpts,
                     'delays_vec': self.delays
                     }
        }

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        #TODO broken by change of experiment
        return (self.cfg["reps"] * self.cfg["qubit_spec_delay_steps"] * self.cfg["qubit_freq_expts"] *
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