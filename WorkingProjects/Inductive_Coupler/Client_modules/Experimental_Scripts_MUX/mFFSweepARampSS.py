from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.AdiabaticRamps import generate_ramp
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.rotate_SS_data import *
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAdiabaticRampSingleShot import AdiabaticRampSingleShot
from scipy.optimize import curve_fit

class FFSweepAdiabaticRampSingleShot(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, progress=False):
        # Gets the keys 'swept_index', 'gain_start', 'gain_end', and 'num_points'
        self.data = {}
        gainVec = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'], self.cfg['num_points'])
        excited_pop_vecs = [np.zeros_like(gainVec) for _ in range(len(self.cfg['Read_Indeces']))]


        for j, gain in enumerate(gainVec):
            self.cfg['FF_Qubits'][str(self.cfg['swept_index'])]['Gain_Ramp'] = gain
            adiabatic_ramp_single_shot_experiment = AdiabaticRampSingleShot(path="AdiabaticRampSingleShot",
                                                                            outerFolder=self.outerFolder, cfg=self.cfg,
                                                                            soc=self.soc,
                                                                            soccfg=self.soccfg)
            data = adiabatic_ramp_single_shot_experiment.acquire()
            for read_index, angle, threshold, confusion_mat, i in \
                    zip(self.cfg['Read_Indeces'], self.cfg['angle'], self.cfg['threshold'],
                        self.cfg['confusion_matrix'], range(len(self.cfg['Read_Indeces']))):

                i_g = data['data']['i_g' + str(read_index)]
                q_g = data['data']['q_g' + str(read_index)]
                i_e = data['data']['i_e' + str(read_index)]
                q_e = data['data']['q_e' + str(read_index)]

                e_data = rotate_data((i_e, q_e), angle)[0]
                print(j, 'threshold', threshold)
                # print(e_data)
                excited_pop = np.sum(e_data > threshold) / len(e_data)

                excited_pop_vecs[i][j] = correct_occ(excited_pop, confusion_mat)


        self.data['gainVec'] = gainVec
        self.data['excited_pop_vecs'] = excited_pop_vecs

        return self.data



    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data


        plt.suptitle(self.titlename )
        #
        def lin_func(gain, g0, m):
            return m*(gain - g0) + self.cfg['fit_point']

        for i in range(len(self.cfg['Read_Indeces'])):
            try:
                (g0, m), _ = curve_fit(lin_func, data['gainVec'], data['excited_pop_vecs'][i], [np.median(data['gainVec']), 1e-3])
                print(m)

                plt.axvline(g0, ls='dotted', color='black', label=f'Read: {self.cfg["Read_Indeces"][i]}, gain = {g0}')
                plt.plot(data['gainVec'], lin_func(data['gainVec'], g0, m), ls='dashed',
                         color=['red','magenta','violet','crimson'][i], )
            except Exception:
                print("Couldn't fit data.")

            plt.plot(data['gainVec'], data['excited_pop_vecs'][i], marker='o', color=['red','magenta','violet','crimson'][i],
                     label=f'Read: {self.cfg["Read_Indeces"][i]}')

        plt.axhline(self.cfg['fit_point'], ls='dotted', color='black')

        plt.xlabel(f"Ramp {self.cfg['swept_index']} FF Gain")
        plt.ylabel("Excited population")
        plt.legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        # else:
            # fig.clf(True)
            # plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data)




import pickle
def QuadExponentialFit(t, A1, T1, A2, T2, A3, T3, A4, T4):
    return(A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2) + A3 * np.exp(-t / T3) + A4 * np.exp(-t / T4))

def Compensated_AWG(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = QuadExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3], Fit_Parameters[4], Fit_Parameters[5],
                                   Fit_Parameters[6], Fit_Parameters[7])
    analytic_n[analytic_n < -0.8] = -0.8
    v_awg = ideal_AWG / (1 + analytic_n)
    v_awg[v_awg > maximum] = maximum
    return(time, v_awg)

def DoubleExponentialFit(t, A1, T1, A2, T2):
    return (A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2))

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = DoubleExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3])
    print('analytic_n Before correction', analytic_n[:30])
    analytic_n[analytic_n < -0.7] = -0.7
    print('analytic_n After correction', analytic_n[:30])

    v_awg = ideal_AWG / (1 + analytic_n)
    print('v_awg Before correction', v_awg[:30])

    v_awg[v_awg > maximum] = maximum
    print('v_awg After correction', v_awg[:30])

    return(time, v_awg)

# Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
# Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
# Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
#
# v_awg_Q1 = Compensated_AWG(600 * 16 * 3, Qubit1_)[1]
# v_awg_Q2 = Compensated_AWG(600 * 16 * 3, Qubit2_)[1]
# v_awg_Q4 = Compensated_AWG(600 * 16 * 3, Qubit4_)[1]

v_awg_Q1 = np.ones(600 * 16 * 3)
v_awg_Q2 = np.ones(600 * 16 * 3)
v_awg_Q4 = np.ones(600 * 16 * 3)

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    return(Comp_Step_Gain)