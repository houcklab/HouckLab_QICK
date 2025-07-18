
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment1D_lines import SweepExperiment1D_lines
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment1D_plots import SweepExperiment1D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
import pickle
# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *


class RampCurrentCalibrationOffset(SweepExperiment2D_plots):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.y_key = ("t_offset", self.cfg["swept_index"])
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.x_key = 'expt_cycles2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Offset time (4.65/16 ns)'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_cycles1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse','Gain_Expt',self.cfg['ramp_time'])
        self.original_IDataArray2 = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''


        # offset all channels from the one with the least offset defined by t_offset (units of 1/16 clock cycles
        # t_offset can be passed as a list to define each channel's relative offset

        t_offset = np.array(self.cfg['t_offset'], dtype=int)

        if isinstance(t_offset, (list, np.ndarray, tuple)):
            pass
        elif isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        else:
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(self.cfg['t_offset'])

        self.cfg["IDataArray2"] = [None] * len(self.cfg['fast_flux_chs'])
        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.concatenate([
                self.cfg["IDataArray1"][i][self.cfg['expt_cycles1']:self.cfg['expt_cycles1'] + t_offset[i]],
                self.original_IDataArray2[i]])


class RampCurrentCalibrationGain(RampCurrentCalibrationOffset):
    '''Same set_up_instance as above'''
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.y_key = ('FF_Qubits', str(self.cfg['swept_index']+1), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'],
                                    dtype=int)
        self.x_key = 'expt_cycles2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'],
                                    dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'FF gain (Index {self.cfg["swept_index"]})'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_cycles1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('\nstarting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])
        self.original_IDataArray2 = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')


class RampCurrentCalibration1D(SweepExperiment1D_plots):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF

        self.x_key = 'expt_cycles2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Population'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting
        print(self.x_points)

        self.cfg['expt_cycles1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])

        # ramp_wait = 3000
        # for ch in range(len(self.cfg['fast_flux_chs'])):
        #     self.cfg["IDataArray1"][ch] = np.concatenate([
        #         self.cfg["IDataArray1"][ch], np.full(ramp_wait, self.cfg['FF_Qubits'][str(ch + 1)]['Gain_Expt'])])
        # self.cfg['expt_cycles1'] = self.cfg['ramp_time'] + ramp_wait


        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

        # offset all channels from the one with the least offset defined by t_offset (units of 1/16 clock cycles
        # t_offset can be passed as a list to define each channel's relative offset

        t_offset = np.array(self.cfg['t_offset'], dtype=int)

        if isinstance(t_offset, (list, np.ndarray, tuple)):
            pass
        elif isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        else:
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(self.cfg['t_offset'])

        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel

            self.cfg["IDataArray2"][i] = np.concatenate([
                self.cfg["IDataArray1"][i][self.cfg['expt_cycles1']:self.cfg['expt_cycles1'] + t_offset[i]],
                self.cfg["IDataArray2"][i]])


class RampCurrentCalibration1DShots(SweepExperiment1D_plots):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF

        self.x_key = 'expt_cycles2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population_shots'  # contrast or population
        self.ylabel = f'Population'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting
        print(self.x_points)

        self.cfg['expt_cycles1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])

        # ramp_wait = 3000
        # for ch in range(len(self.cfg['fast_flux_chs'])):
        #     self.cfg["IDataArray1"][ch] = np.concatenate([
        #         self.cfg["IDataArray1"][ch], np.full(ramp_wait, self.cfg['FF_Qubits'][str(ch + 1)]['Gain_Expt'])])
        # self.cfg['expt_cycles1'] = self.cfg['ramp_time'] + ramp_wait

        self.cfg["IDataArray2"] = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

        # offset all channels from the one with the least offset defined by t_offset (units of 1/16 clock cycles
        # t_offset can be passed as a list to define each channel's relative offset

        t_offset = np.array(self.cfg['t_offset'], dtype=int)

        if isinstance(t_offset, (list, np.ndarray, tuple)):
            pass
        elif isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        else:
            raise TypeError('t_offset must be an int or array like of ints')

        t_offset -= np.min(self.cfg['t_offset'])

        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel

            self.cfg["IDataArray2"][i] = np.concatenate([
                self.cfg["IDataArray1"][i][self.cfg['expt_cycles1']:self.cfg['expt_cycles1'] + t_offset[i]],
                self.cfg["IDataArray2"][i]])
