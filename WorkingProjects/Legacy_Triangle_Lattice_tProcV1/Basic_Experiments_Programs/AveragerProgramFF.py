from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.FF_utils as FF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.rotate_SS_data import *
from qick import AveragerProgram, RAveragerProgram
import scipy
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.IQ_contrast import *

class AveragerProgramFF(AveragerProgram):
    '''Averager Program but adds FF and acquire helpers'''

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
        FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
                          waveform_label = waveform_label )

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    ##########

    def acquire_shots(self, *args, **kwargs):
        self.acquire(*args, **kwargs)

        all_i = []
        all_q = []

        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q

    def acquire_populations(self, angle=None, threshold=None, return_shots = False, *args, **kwargs):
        shots_i0, shots_q0 = self.acquire_shots(*args, **kwargs)

        rotated_iq_array = [[] for ro_ind in range(len(self.di_buf))]
        excited_percentages = [[] for ro_ind in range(len(self.di_buf))]

        if angle is None: angle = self.cfg['angle']
        if threshold is None: threshold = self.cfg['threshold']
        for ro_ind in range(len(self.di_buf)):
            rotated_iq = rotate_data((shots_i0[ro_ind], shots_q0[ro_ind]), theta=angle[ro_ind])
            excited_percentage = count_percentage(rotated_iq, threshold=threshold[ro_ind])


            rotated_iq_array[ro_ind] = rotated_iq
            excited_percentages[ro_ind] = excited_percentage

        if return_shots:
            return excited_percentages, (shots_i0, shots_q0)  ###, rotated_iq_array
        else:
            return excited_percentages
    
class RAveragerProgramFF(RAveragerProgram):
    '''Averager Program but adds FF and acquire helpers'''

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_hires(self, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
        FF.FFPulses_hires(self, list_of_gains, length_us, t_start = t_start, IQPulseArray=IQPulseArray,
                          waveform_label = waveform_label )

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    ##########
    def acquire_IQ_contrast(self, *args, **kwargs):
        expt_pts, avgi, avgq = self.acquire(*args, **kwargs)
        rotated_i_list = []
        for ro_ind in range(len(self.di_buf)): # For each ro_ch
            angle = IQ_angle(avgi[ro_ind], avgq[ro_ind])
            rotated_i, rotated_q = rotate(angle, avgi[ro_ind], avgq[ro_ind])

            rotated_i_list.append(rotated_i - np.mean(rotated_i))
        
        return rotated_i_list, avgi, avgq

    def acquire_shots(self, *args, **kwargs):
        self.acquire(*args, **kwargs)

        all_i = []
        all_q = []

        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((self.cfg["expts"], self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            shots_q0=self.dq_buf[i].reshape((self.cfg["expts"], self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = i)
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q

    def acquire_populations(self, angle=None, threshold=None, return_shots=False, *args, **kwargs):
        shots_i0, shots_q0 = self.acquire_shots(*args, **kwargs)
        rotated_iq_array =    [[] for ro_ind in range(len(self.di_buf))]
        excited_percentages = [[] for ro_ind in range(len(self.di_buf))]

        if angle is None: angle = self.cfg['angle']
        if threshold is None: threshold = self.cfg['threshold']
        for ro_ind in range(len(self.di_buf)):
            rotated_iq = rotate_data((shots_i0[ro_ind], shots_q0[ro_ind]), theta=angle[ro_ind])
            rotated_iq_array[ro_ind] = rotated_iq

            excited_percentage = np.sum(rotated_iq[0] > threshold[ro_ind], axis=1) / rotated_iq[0].shape[1]
            if self.cfg.get('confusion_matrix') is not None:
                excited_percentage = correct_occ(excited_percentage, self.cfg['confusion_matrix'][ro_ind])

            excited_percentages[ro_ind] = excited_percentage

        if return_shots:
            return excited_percentages, shots_i0, shots_q0 ###, rotated_iq_array
        else:
            return excited_percentages
        