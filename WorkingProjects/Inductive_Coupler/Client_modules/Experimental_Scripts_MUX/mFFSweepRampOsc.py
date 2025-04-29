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
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAdiabaticRampOscillations import AdiabaticRampOscillations
from scipy.optimize import curve_fit

class FFSweepRampOscillations(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)


    def acquire(self, angle, threshold, progress=False, figNum=1):
        # Gets the keys 'swept_index', 'gain_start', 'gain_end', and 'num_points'

        gainVec = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'], self.cfg['num_points'])
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        excited_pop_matrix = np.full((len(gainVec), len(tpts)), np.nan)

        read_index = self.cfg['Read_Indeces'][0]

        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(10, 8), num=figNum)
        fig.suptitle(str(self.titlename), fontsize=16)
        X = tpts
        X_step = X[1] - X[0]
        Y = gainVec
        Y_step = Y[1] - Y[0]

        for j, gain in enumerate(gainVec):
            self.cfg['FF_Qubits'][str(self.cfg['swept_index'])]['Gain_Expt'] = gain
            adiabatic_ramp_osc = AdiabaticRampOscillations(path="AdiabaticRampSingleShot",
                                                                            outerFolder=self.outerFolder, cfg=self.cfg,
                                                                            soc=self.soc,
                                                                            soccfg=self.soccfg)
            data = adiabatic_ramp_osc.acquire(threshold=threshold, angle=angle)

            excited_pop = data['data']['Exp_values']

            excited_pop_matrix[j] = correct_occ(np.array(excited_pop), self.cfg['confusion_matrix'])

            if j == 0:
                ax_plot_1 = axs.imshow(
                    excited_pop_matrix,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none')
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('Excited Population', rotation=90)
            else:
                ax_plot_1.set_data(excited_pop_matrix)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('Excited Population', rotation=90)

            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")
            plt.savefig(self.iname)

            plt.show(block=False)
            plt.pause(0.1)

        fig.clf(True)
        # plt.close(fig)


        self.data = {
            'config': self.cfg,
            'data': {'Exp_values': [excited_pop_matrix for i in range(len(self.cfg["ro_chs"]))],
                     'threshold': threshold,
                     'angle': angle, 'wait_times': tpts,
                     'gainVec': gainVec,
                     }
        }

        return self.data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        percent_excited = data['data']['Exp_values']
        gainVec = data['data']['gainVec']

        X = x_pts
        Y = gainVec

        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]

        for i, read_index in enumerate(self.cfg['Read_Indeces']):
            while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
                figNum += 1

            fig, axs = plt.subplots(1, 1, figsize=(10, 8), num=figNum)
            fig.suptitle(str(self.titlename), fontsize=16)
            ax_plot_1 = axs.imshow(
                percent_excited[i],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
            cbar1.set_label('Excited Population', rotation=90)

            axs.set_ylabel("FF Gain (a.u.)")
            axs.set_xlabel("Wait time (2.32/16 ns )")
            axs.set_title("Oscillations")
            plt.title(self.titlename + ", Read: " + str(read_index))
            plt.savefig(self.iname[:-4] + "_Read_" + str(read_index) + '.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




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