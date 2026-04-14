from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_plots import SweepExperiment1D_plots
import datetime
# from WorkingProjects.Triangle_Lattice_tProcV2.Experiment_Scripts.mRabiOscillations import WalkFFProg

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *


class RampCurrentCalibrationOffset(SweepExperiment2D_plots):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.y_key = ("t_offset", self.cfg["swept_index"])
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.x_key = 'expt_samples2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Offset time (4.65/16 ns)'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse','Gain_Expt',self.cfg['ramp_time'])
        self.cfg["IDataArray2"] = []
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

        t_offset -= np.min(t_offset)

        self.cfg["IDataArray2"] = [None] * len(self.cfg['fast_flux_chs'])
        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.original_IDataArray2[i], (t_offset[i], 0), mode='constant',
                                                constant_values=self.cfg["IDataArray1"][i][-1])

        # print(f't_offset: {t_offset}')
        # print(f'IDataArray1: {self.cfg["IDataArray1"][0]}')
        # print(f'padded IDataArray2: {self.cfg["IDataArray2"][0]}')


class RampCurrentCalibrationOffset_Multiple(SweepExperiment2D_plots):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF

        self.cfg['t_offset_current'] = 0
        self.y_key = "t_offset_current"
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.x_key = 'expt_samples2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Offset time (4.65/16 ns)'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse','Gain_Expt',self.cfg['ramp_time'])
        self.cfg["IDataArray2"] = []
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

        current_offset = self.cfg['t_offset_current']
        current_offset_relative = current_offset - t_offset[self.cfg['swept_index'][0]]

        for index in self.cfg["swept_index"]:
            t_offset[index] += current_offset_relative

        print(f't_offset: {t_offset}')

        t_offset -= np.min(t_offset)

        self.cfg["IDataArray2"] = [None] * len(self.cfg['fast_flux_chs'])
        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.original_IDataArray2[i], (t_offset[i], 0), mode='constant',
                                                constant_values=self.cfg["IDataArray1"][i][-1])

        # print(f't_offset: {t_offset}')
        # print(f'IDataArray1: {self.cfg["IDataArray1"][0]}')
        # print(f'padded IDataArray2: {self.cfg["IDataArray2"][0]}')


class RampCurrentCalibrationGain(SweepExperiment2D_plots):
    '''Same set_up_instance as above'''
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.y_key = ('FF_Qubits', str(self.cfg['swept_index']+1), 'Gain_BS')
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'],
                                    dtype=int)
        self.x_key = 'expt_samples2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'],
                                    dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'FF gain (Index {self.cfg["swept_index"]})'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('\nstarting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])
        self.original_IDataArray2 = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')

    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''


        self.original_IDataArray2 = FFEnvelope_Helpers.StepPulseArrays(self.cfg, 'Gain_Expt', 'Gain_BS')


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

        t_offset -= np.min(t_offset)

        self.cfg["IDataArray2"] = [None] * len(self.cfg['fast_flux_chs'])
        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.original_IDataArray2[i], (t_offset[i], 0), mode='constant',
                                                constant_values=self.cfg["IDataArray1"][i][-1])

        # print(f't_offset: {t_offset}')
        # print(f'IDataArray1: {self.cfg["IDataArray1"][0]}')
        # print(f'padded IDataArray2: {self.cfg["IDataArray2"][0]}')

class RampCurrentCalibration1D(SweepExperiment1D_plots):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF

        self.x_key = 'expt_samples2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Population'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting
        print(self.x_points)

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        # self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
        #                                                              self.cfg['ramp_time'])

        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'ramp_initial_gain','Gain_Expt',self.cfg['ramp_time'])


        # ramp_wait = 3000
        # for ch in range(len(self.cfg['fast_flux_chs'])):
        #     self.cfg["IDataArray1"][ch] = np.concatenate([
        #         self.cfg["IDataArray1"][ch], np.full(ramp_wait, self.cfg['FF_Qubits'][str(ch + 1)]['Gain_Expt'])])
        # self.cfg['expt_samples1'] = self.cfg['ramp_time'] + ramp_wait


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

        t_offset -= np.min(t_offset)

        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.cfg["IDataArray2"][i], (t_offset[i], 0), mode='constant', constant_values=self.cfg["IDataArray1"][i][-1])

        # fig, ax = plt.subplots()
        # for i in range(4):
        #     print(i)
        #     ax.plot(np.concatenate([self.cfg["IDataArray1"][i], self.cfg["IDataArray2"][i]]), label=f'Q{i + 1}')
        # ax.axvline(self.cfg['ramp_time'], linestyle='--', color='black', label='ramp time')
        # ax.legend()
        # plt.show()

class RampCurrentCalibration1DShots(SweepExperiment1D_plots):
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF

        self.x_key = 'expt_samples2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population_shots'  # contrast or population
        self.ylabel = f'Population'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting
        print(self.x_points)

        self.cfg['expt_samples1'] = self.cfg['ramp_time']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])

        # ramp_wait = 3000
        # for ch in range(len(self.cfg['fast_flux_chs'])):
        #     self.cfg["IDataArray1"][ch] = np.concatenate([
        #         self.cfg["IDataArray1"][ch], np.full(ramp_wait, self.cfg['FF_Qubits'][str(ch + 1)]['Gain_Expt'])])
        # self.cfg['expt_samples1'] = self.cfg['ramp_time'] + ramp_wait

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

        t_offset -= np.min(t_offset)

        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.cfg["IDataArray2"][i], (t_offset[i], 0), mode='constant',
                                                constant_values=self.cfg["IDataArray1"][i][-1])


class RampCurrentCalibrationTime(SweepExperiment1D_plots):
    '''
    Sweeps time variable through ramp and through beamsplitter interaction. Used to check populations during
    both portions of the experiment.
    '''


    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF


        self.x_key = 'expt_samples_total'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Population'  # for plotting
        self.xlabel = 'Wait time (4.65/16 ns)'  # for plotting
        print(self.x_points)

        self.cfg['expt_samples1'] = 0
        self.cfg['expt_samples2'] = 0
        self.cfg['expt_samples_total'] = 0


        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        self.cfg["IDataArray1"] = FFEnvelope_Helpers.CubicRampArrays(self.cfg, 'Gain_Pulse', 'Gain_Expt',
                                                                     self.cfg['ramp_time'])

        # ramp_wait = 3000
        # for ch in range(len(self.cfg['fast_flux_chs'])):
        #     self.cfg["IDataArray1"][ch] = np.concatenate([
        #         self.cfg["IDataArray1"][ch], np.full(ramp_wait, self.cfg['FF_Qubits'][str(ch + 1)]['Gain_Expt'])])
        # self.cfg['expt_samples1'] = self.cfg['ramp_time'] + ramp_wait


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

        t_offset -= np.min(t_offset)

        for i in range(len(self.cfg["IDataArray2"])):
            # pad at beginning to delay this channel
            self.cfg["IDataArray2"][i] = np.pad(self.cfg["IDataArray2"][i], (t_offset[i], 0), mode='constant', constant_values=self.cfg["IDataArray1"][i][-1])

        # fig, ax = plt.subplots()
        # for i in range(4):
        #     print(i)
        #     ax.plot(np.concatenate([self.cfg["IDataArray1"][i], self.cfg["IDataArray2"][i]]), label=f'Q{i+1}')
        # ax.axvline(self.cfg['ramp_time'])
        # ax.legend()
        # plt.show()

    def set_up_instance(self):

        # truncate IDataArrays based on expt_samples

        print('before')
        print(f'expt_samples1: {self.cfg["expt_samples1"]}')
        print(f'expt_samples2: {self.cfg["expt_samples2"]}')
        print(f'expt_samples_total: {self.cfg["expt_samples_total"]}')

        if self.cfg['expt_samples_total'] <= self.cfg['ramp_time']:
            # stop experiment during ramp IDataArray1
            self.cfg['expt_samples1'] =  self.cfg['expt_samples_total']
            self.cfg['expt_samples2'] = 0

        else:
            # stop experiment during beamsplitter interaction in IDataArray2
            self.cfg['expt_samples2'] = self.cfg['expt_samples_total'] - self.cfg['expt_samples1']


        print('after')
        print(f'expt_samples1: {self.cfg["expt_samples1"]}')
        print(f'expt_samples2: {self.cfg["expt_samples2"]}')
        print(f'expt_samples_total: {self.cfg["expt_samples_total"]}')