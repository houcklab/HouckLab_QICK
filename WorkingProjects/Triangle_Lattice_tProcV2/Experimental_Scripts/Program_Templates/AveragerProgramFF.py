from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
import scipy

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import *
from qick.asm_v2 import AveragerProgramV2


class FFAveragerProgramV2(AveragerProgramV2):
    '''Averager Program but adds FF and acquire helpers'''

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)


    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    def loop_pts(self):
        '''This is purely for easy plotting purposes'''
        return []

    ##########
    def acquire(self, *args, **kwargs):
        return super().acquire(*args, **kwargs)

    def acquire_shots(self, *args, **kwargs):
        super().acquire(*args, **kwargs)

        all_i = []
        all_q = []

        d_buf = self.get_raw()  # [(*self.loop_dims, nreads, 2) for ro in ros]
        # Note: MUXed readouts have a default (-0.5, -0.5) IQ offset that I subtract out

        # print(np.array(d_buf).shape)

        for i in range(len(d_buf)):
            shots_i0 = +0.5 + d_buf[i][..., -1, 0] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
            shots_q0 = +0.5 + d_buf[i][..., -1, 1] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i, all_q

    def acquire_populations(self, angle=None, threshold=None, return_shots = False, *args, **kwargs):
        shots_i0, shots_q0 = self.acquire_shots(*args, **kwargs)

        rotated_iq_array = [[] for ro_ind in range(len(shots_i0))]
        excited_percentages = [[] for ro_ind in range(len(shots_i0))]

        if angle is None: angle = self.cfg['angle']
        if threshold is None: threshold = self.cfg['threshold']
        for ro_ind in range(len(shots_i0)):
            rotated_iq = rotate_data((shots_i0[ro_ind], shots_q0[ro_ind]), theta=angle[ro_ind])
            excited_percentage = count_percentage(rotated_iq, threshold=threshold[ro_ind])


            rotated_iq_array[ro_ind] = rotated_iq
            excited_percentages[ro_ind] = excited_percentage

        if return_shots:
            return excited_percentages, (shots_i0, shots_q0)  ###, rotated_iq_array
        else:
            return excited_percentages

    def acquire_population_shots(self, angle=None, threshold=None, return_shots = False, *args, **kwargs):
        '''
        Acquires single shot population data without averaging over all shots
        '''

        shots_i0, shots_q0 = self.acquire_shots(*args, **kwargs)

        excited_percentages = [[] for ro_ind in range(len(shots_i0))]

        if angle is None: angle = self.cfg['angle']
        if threshold is None: threshold = self.cfg['threshold']
        for ro_ind in range(len(shots_i0)):
            rotated_iq = rotate_data((shots_i0[ro_ind], shots_q0[ro_ind]), theta=angle[ro_ind])
            excited_percentage = rotated_iq[0] > threshold[ro_ind]
            # Move "reps" axis to be last
            excited_percentage = np.moveaxis(excited_percentage, 0, -1)
            excited_percentages[ro_ind] = excited_percentage


        if return_shots:
            return excited_percentages, (shots_i0, shots_q0)  ###, rotated_iq_array
        else:
            return excited_percentages