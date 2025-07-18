

import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.ThreePartProgram import ThreePartProgramTwoFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import FFEnvelope_Helpers


class CurrentCorrelationMeasurement(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        self.cfg['expt_cycles1'] = self.cfg['ramp_time']
        self.cfg['expt_cycles2'] = self.cfg['beamsplitter_time']

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

        prog = ThreePartProgramTwoFF(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"])

        populations = prog.acquire_population_shots(soc=self.soc, load_pulses=True,
                                                soft_avgs=self.cfg.get('rounds', 1),
                                                progress=progress)

        data = {'config': self.cfg, 'data': {'populations': populations, 'angle': self.cfg['angle'],
                                             'threshold': self.cfg['threshold'],
                                             'confusion_matrix': self.cfg['confusion_matrix']}}
        self.data = data

        return self.data

    def display(self, data=None, plotDisp = False, figNum = 1, block=True, **kwargs):
        '''
        need to implement in the future
        '''
        pass



    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


