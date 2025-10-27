from qick import *
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.rotate_SS_data import *
import time
import WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.FF_utils as FF
import pickle
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experiment_Scripts.mRabiOscillations import WalkFFProg

import numpy as np

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Basic_Experiments_Programs.SweepExperiment2D import SweepExperiment2D
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Basic_Experiments_Programs.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Basic_Experiments_Programs.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.Compensated_Pulse_Jero import *


class CurrentCalibrationOffset(SweepExperiment2D):
    # current_calibration_offset_dict = {'reps': 1000, 't_evolve': 0, 'relax_delay': 150, "plotDisp": True,
    #                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
    #                                    'offsetStart': 300, 'offsetStop': 400, 'offsetNumPoints': 2}
    def init_sweep_vars(self):
        self.Program = ThreePartProgramTwoFF
        self.y_key = "t_offset"
        self.y_points = np.linspace(self.cfg['offsetStart'], self.cfg['offsetStop'], self.cfg['offsetNumPoints'], dtype=int)
        self.x_key = 'expt_cycles2'
        self.x_points = np.linspace(self.cfg['timeStart'], self.cfg['timeStop'], self.cfg['timeNumPoints'], dtype=int)
        self.z_value = 'population'  # contrast or population
        self.ylabel = f'Offset time (2.32/16 ns)'  # for plotting
        self.xlabel = 'Wait time (2.32/16 ns)'  # for plotting

        self.cfg['expt_cycles1'] = self.cfg['t_evolve']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = [None]*4
        self.cfg["IDataArray2"] = [None]*4
        self.cfg["IDataArray1"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['1']['Gain_Pulse'], 1)
        self.cfg["IDataArray1"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['2']['Gain_Pulse'], 2)
        self.cfg["IDataArray1"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['3']['Gain_Pulse'], 3)
        self.cfg["IDataArray1"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['4']['Gain_Pulse'], 4)


    def set_up_instance(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''


        self.cfg["IDataArray2"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_BS'],
                                                       self.cfg["IDataArray1"][0][self.cfg['expt_cycles1']], 1)
        self.cfg["IDataArray2"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_BS'],
                                                       self.cfg["IDataArray1"][1][self.cfg['expt_cycles1']], 2)
        self.cfg["IDataArray2"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_BS'],
                                                       self.cfg["IDataArray1"][2][self.cfg['expt_cycles1']], 3)
        self.cfg["IDataArray2"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_BS'],
                                                       self.cfg["IDataArray1"][3][self.cfg['expt_cycles1']], 4)

        # offset one channel from the other by t_offset (units of 1/16 clock cycles
        channel_1 = self.cfg['qubit_BS_indices'][0]
        channel_2 = self.cfg['qubit_BS_indices'][1]
        # these are 0-indexed
        # print(self.cfg['qubit_BS_indices'])
        # second channel is offset later by t_offset relative to channel 1
        if self.cfg['t_offset'] > 0:
            later_channel = channel_2
        else:
            later_channel = channel_1

        # pad at beginning to delay this channel
        self.cfg["IDataArray2"][later_channel] = np.concatenate([
            self.cfg["IDataArray1"][later_channel][self.cfg['expt_cycles1']:self.cfg['expt_cycles1']+np.abs(self.cfg['t_offset'])],
            self.cfg["IDataArray2"][later_channel]])


        # plt.show()

class CurrentCalibrationGain(CurrentCalibrationOffset):
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
        self.xlabel = 'Wait time (2.32/16 ns)'  # for plotting

        self.cfg['expt_cycles1'] = self.cfg['t_evolve']

        startTime = datetime.datetime.now()
        print('\nstarting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        self.cfg["IDataArray1"] = [None] * 4
        self.cfg["IDataArray2"] = [None] * 4
        self.cfg["IDataArray1"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['1']['Gain_Pulse'], 1)
        self.cfg["IDataArray1"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['2']['Gain_Pulse'], 2)
        self.cfg["IDataArray1"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['3']['Gain_Pulse'], 3)
        self.cfg["IDataArray1"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'],
                                                       self.cfg['FF_Qubits']['4']['Gain_Pulse'], 4)


