from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import \
    FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import *
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy

# import matplotlib; matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt

import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
import scipy
import functools
import operator
import itertools
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.SweepHelpers
from qick.asm_v2 import AveragerProgramV2


'''
To avoid repeating code, a single base class to sweep over an arbitrary number of config
keys an AveragerProgramV2 with an arbitrary number of QICK loops.
- 07/29/2025
'''

class SweepExperimentND(ExperimentClass):
    """
        Sweeps a config entry for an AveragerProgram. The user will define:
        init_sweep_vars(self): Run once at the beginning of the entire sweep
            set_up_instance(self): Run before each iteration, utilizing the updated sweep variable.

        analyze(self, data, **kwargs): (Optional). Run at the end of the entire sweep, use to fits, etc.

    """
    def init_sweep_vars(self):
        self.Program =  None   #  FFAveragerProgramV2
        self.keys =    tuple()   #  key, or a list of keys for nested dicts
        self.sweep_arrays = tuple()   # list of arrays, each containing the sweep values for each key

        self.z_value =  None   #  'contrast' or 'population'

        raise NotImplementedError("Please implement init_sweep_vars() to define sweep variables.")

    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        pass


    def _display_plot(self, data, fig_axs):
        pass
    
    def _update_fig(self, data, fig_axs):
        pass


    def __init__(self, path='', prefix='data', soc=None, soccfg=None, cfg=None, config_file=None,
                 liveplot_enabled=False, **kwargs):
        super().__init__(path=path, prefix=prefix, soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file,
                         liveplot_enabled=liveplot_enabled, **kwargs)
        self.keys = tuple()
        self.sweep_arrays = tuple()

        self.init_sweep_vars()
        if "x_key" in self.__dict__:
            self.keys = (self.x_key,) + self.keys
            self.sweep_arrays = (self.x_points,) + self.sweep_arrays
        if "y_key" in self.__dict__:
            self.keys = (self.y_key,) + self.keys
            self.sweep_arrays = (self.y_points,) + self.sweep_arrays

        '''Compile the program once to inspect the defined QICK loops'''
        for key, sweep in zip(self.keys, self.sweep_arrays):
            SweepHelpers.set_nested_item(self.cfg, key, sweep[0])
        self.set_up_instance()
        prog = self.Program(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        
        '''
        sweep_shape: shape of the outer python sweep, e.g. (50,) for a FF gain sweep with 50 points
        acquire_shape: shape of the sweeps from QICK-defined loops. e.g (71,) for a SpecSlice with 71 points.
        '''
        self.sweep_shape = tuple(len(sweep) for sweep in self.sweep_arrays)
        # AveragerProgramV2.loops = [("reps", self.reps, self.before_reps, self.after_reps), ("myloop1", num_steps, ...), ...]
        qick_loops = prog.loops[1:] if len(prog.loops) > 1 else tuple()
        self.loop_names =    tuple(loop[0] for loop in qick_loops)
        self.loop_shape = tuple(loop[1] for loop in qick_loops)
        '''I defined loop_pts in each program I wrote because i couldn't think of a better way to automatically
        get the looped values for plotting'''
        self.loop_values = prog.loop_pts()
        self.data_shape = self.sweep_shape + self.loop_shape
        
        

    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):
        while plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum += 1

        readout_list = self.cfg["Qubit_Readout_List"]

        '''Index by Z_mat[ro_index][*sweep_shape, *data_shape].
            e.g., 4 MUXed readouts on a FF gain vs SpecSlice. sweep_shape = (50,), acquire_shape = (71,).
            Z_mat will have shape (4)(50, 71).'''
        Z_mat = [np.full(self.data_shape, np.nan) for _ in readout_list]

        if self.z_value == 'population_shots':
            print('population shots true')
            Z_mat = [np.full(self.data_shape + (self.cfg['reps'] * self.cfg.get('rounds', 1),), np.nan, dtype=np.int64) for _ in readout_list]

        # raw i and q data
        I_mat = [np.full(self.data_shape, np.nan) for _ in readout_list]
        Q_mat = [np.full(self.data_shape, np.nan) for _ in readout_list]

        if self.z_value == "population_corrected" or self.z_value == "population" and "confusion_matrix" in self.cfg:
            Z_corrected = [np.full(self.data_shape, np.nan) for _ in readout_list]
        # Define data dictionary
        key_names = [SweepHelpers.key_savename(key) for key in self.keys]

        self.data = {
            'config': self.cfg,
            'data': {self.z_value: Z_mat,
                     "I": I_mat,
                     "Q": Q_mat,
                     'readout_list': readout_list,
                     # Outer python loops
                     **{key_name: value_array for key_name,value_array in zip(key_names, self.sweep_arrays)},
                     # On-board tprocV2 loops
                     **{key_name: value_array for key_name, value_array in zip(self.loop_names, self.loop_values)},

                     **{key : self.cfg[key] for key in ('angle', 'threshold', 'confusion_matrix') if key in self.cfg},
                     'Qubit_Readout_List': self.cfg["Qubit_Readout_List"]},

        }
        if self.z_value == "population_corrected" or self.z_value=="population" and "confusion_matrix" in self.cfg:
            self.data['data']['population'] = Z_mat
            self.data['data']['population_corrected'] = Z_corrected
            self.z_value = "population_corrected"

        self.last_saved_time = time.time()

        '''iterating through itertools.product is equivalent to a nested for loop such as
        for i, y_pt in enumerate(self.y_points):
            for j, x_pt in enumerate(self.x_points):'''
        
        '''e.g. index_iterator yields (0,0), (0,1), (0,2), ... (1,0), (1,1), ... (M-1, N-1)'''
        index_iterator = itertools.product(*(range(len(arr)) for arr in self.sweep_arrays))
        value_iterator = itertools.product(*self.sweep_arrays)

        first_iteration = True
        for sweep_indices, sweep_values in zip(index_iterator, value_iterator): 
            # Update config entries based on sweep
            for key, pt in zip(self.keys, sweep_values):
                SweepHelpers.set_nested_item(self.cfg, key, pt)

            # set up the AveragerProgram instance
            self.set_up_instance()

            if issubclass(self.Program, FFAveragerProgramV2):
                prog = self.Program(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"], initial_delay=10.0)
            else:
                raise TypeError("Please assign an AveragerProgramV2 object in self.Program.")

            # shape of iq_list: [num of ROs, 1 (num triggers?), SpecNumPoints, 2 (I or Q)],
            #              e.g. [1, 1, 71, 2] for SpecSlice
            if self.z_value == 'contrast':
                iq_list = prog.acquire(self.soc, load_pulses=True, soft_avgs=self.cfg.get('rounds', 1), progress=progress)
                avgi, avgq = [iq[-1, ..., 0] for iq in iq_list], [iq[-1, ..., 1] for iq in iq_list]
                
                for ro_index in range(len(readout_list)):
                    I_mat[ro_index][*sweep_indices, ...] = avgi[ro_index]
                    Q_mat[ro_index][*sweep_indices, ...] = avgq[ro_index]
                    slices = tuple(slice(j+1) for j in sweep_indices)

                    rotated_i = IQ_contrast(I_mat[ro_index][*slices], Q_mat[ro_index][*slices])

                    Z_mat[ro_index][*slices] = rotated_i
            elif self.z_value == 'population' or self.z_value == 'population_corrected':
                excited_populations = prog.acquire_populations(soc=self.soc, return_shots=False,
                                                            load_pulses=True, soft_avgs=self.cfg.get('rounds', 1), progress=progress)

                for ro_index in range(len(readout_list)):
                    Z_mat[ro_index][*sweep_indices, ...] = excited_populations[ro_index]
                    if self.cfg.get('confusion_matrix') is not None:
                        corrected_population = correct_occ(excited_populations[ro_index],
                                                           self.cfg['confusion_matrix'][ro_index])
                        Z_corrected[ro_index][*sweep_indices, ...] = corrected_population

            elif self.z_value == 'population_shots':


                excited_populations = prog.acquire_population_shots(soc=self.soc, return_shots=False,
                                                               load_pulses=True, soft_avgs=self.cfg.get('rounds', 1),
                                                               progress=progress)


                for ro_index in range(len(readout_list)):
                    Z_mat[ro_index][*sweep_indices, ...] = excited_populations[ro_index]
            else:
                raise ValueError("So far I only support 'contrast' or 'population' or 'population_shots'.")

            # print(prog)
            self.debug(prog)

            if (plotDisp or plotSave) and (len(self.sweep_shape) <= 1) or (sweep_indices[-1] == self.sweep_shape[-1] - 1):
                # Create figure
                # fig, ax = plt.subplots(figsize=(4,8))
                # concat_IQarray = [np.concatenate([arr1[:self.cfg["expt_samples1"]], arr2])
                #                   for arr1, arr2, in zip(self.cfg["IDataArray1"], self.cfg["IDataArray2"])]
                # for i in range(4):
                #     ax.plot(concat_IQarray[i])
                #     ax.set_xlim(0,500)
                # plt.show(block=True)

                if first_iteration:
                    fig, axs = self.display(self.data, figNum=figNum,
                                            plotDisp=plotDisp, block=False,plotSave=False)
                    first_iteration = False
                # Update figure
                else:
                    if self.z_value == "population_corrected":
                        self._update_fig(Z_corrected, fig, axs)
                    else:
                        self._update_fig(Z_mat, fig, axs)

                    fig.canvas.draw()
                    fig.canvas.flush_events()
                    # fig.show()
                    # plt.pause(0.01)

            if time.time() - self.last_saved_time > 5 * 60:  # Save data every 5 minutes
                ### print(self.data)
                self.last_saved_time = time.time()
                self.save_data(data=self.data)
                if plotSave:
                    plt.savefig(self.iname[:-4] + '.png')
        if plotSave:
            plt.savefig(self.iname[:-4] + '.png')

        if (plotDisp or plotSave):
            print("CLosing fig")
            # fig.clear(True)
            plt.close(fig)

        self.analyze(data=self.data)
        self.save_data(data=self.data)
        return self.data

    def analyze(self, data, **kwargs):
        return super().analyze(data, **kwargs)

    def debug(self, prog):
        pass

    def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, fig_axs=None):
        readout_list = data["data"]["Qubit_Readout_List"]

        # Create a new figure if you did not pass in your own fig and axs.
        if fig_axs is None:
            fig, axs = self._make_subplots(figNum, len(readout_list))
        else:
            fig, axs = fig_axs
        
        # Run the corresponding display code
        if plotDisp or plotSave:
            self._display_plot(data, fig_axs = (fig, axs))

        if plotSave:
            plt.savefig(self.iname[:-4] + '.png')
        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)

        return fig, axs


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    def _make_subplots(self, figNum, count):
        if plt.fignum_exists(num=figNum):  # if figure with number already exists
            figNum = None
        if count == 1:
            fig, ax = plt.subplots(1, 1, figsize=(10, 8), num=figNum)
            axs = [ax]
        elif count == 2:
            fig, axs = plt.subplots(1, 2, figsize=(14, 8), num=figNum, tight_layout=True)
        elif count in [3, 4]:
            fig, axs = plt.subplots(2, 2, figsize=(14, 8), num=figNum, tight_layout=True)
            axs = (axs[0][0], axs[0][1], axs[1][0], axs[1][1])
            if count == 3:
                axs[3].set_axis_off()
        else:
            raise Exception("I don't think we support MUX with N > 4 yet???")
        
        return fig, axs

