import numpy as np

from WorkingProjects.Triangle_Lattice.Basic_Experiments_Programs.SweepExperiment2D import SweepExperiment2D
from WorkingProjects.Triangle_Lattice.Basic_Experiments_Programs.NPartProgram import ThreePartProgramOneFF


class FFvsSpec(SweepExperiment2D):
    # {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
    #                      'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

    def init_sweep_vars(self):
        self.Program = ThreePartProgramOneFF
        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Expt")
        self.y_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'])
        self.x_key = 'wait_time'
        self.x_points = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.z_value = 'population' # contrast or population
        self.ylabel = 'FF gain (DAC units)'  # for plotting
        self.xlabel = 'Time (2.32 ns)'  # for plotting

        if np.array(self.cfg["IDataArray"]).any() != None:

            self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '1']['Gain_Pulse'], 1)
            self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '2']['Gain_Pulse'], 2)
            self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                                   '3']['Gain_Pulse'], 3)
            self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
                                                                               '4']['Gain_Pulse'], 4)


    def before_each_program(self):
        '''Run this on every iteration on the sweep. Use for setting waveforms, etc.'''
        if type(self.cfg["IDataArray"][0]) != type(None):
            self.cfg["IDataArray"][self.cfg["qubit_FF_index"] - 1] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'],
                                                                                self.cfg['FF_Qubits'][str(self.cfg["qubitIndex"])]['Gain_Pulse'],
                                                                                    self.cfg["qubitIndex"])
            
###################################################

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

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 2):
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
# Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
# Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
# Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_corrected_V3.p', 'rb'))
# Qubit2_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))
Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_PreFinal.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_PreFinal.p', 'rb'))
# Qubit1_[0] *= 1.
# Qubit1_[2] *= 1.
# Qubit1_[4] *= 1.2
#
# # print(Qubit4_)
# Qubit4_[0] *= 1.6
# Qubit4_[2] *= 1.6
# Qubit4_[4] *= 1.7

# print(Qubit4_)

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
Qubit2_[0] *= 0.75
Qubit2_[2] *= 0.75
Qubit2_[4] *= 1

Qubit2_[0] *= 1.3
Qubit2_[1] *= 1.2
Qubit2_[2] *= 1.2
Qubit2_[3] *= 1.2

Qubit4_[0] *= 1.3
Qubit4_[1] *= 1.2
Qubit4_[2] *= 1.2
Qubit4_[3] *= 1.2
# Qubit4_[0] *= 1.2



v_awg_Q1 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit1_)[1]
v_awg_Q2 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit2_)[1]
v_awg_Q4 = Compensated_AWG(int(600 * 16 * 3 * 2.2), Qubit4_)[1]



# v_awg_Q2 = Compensated_AWG_LongTimes(150 * 2 * 16 * 3, Qubit2_parameters_long)[1]

# print(v_awg_Q2)

Compensated_pulse_list = [v_awg_Q1, v_awg_Q2, v_awg_Q2, v_awg_Q4]

def Compensated_Pulse(final_gain, initial_gain, Qubit_number = 1, compensated = True):
    print(Qubit_number, final_gain, initial_gain)
    if not compensated:
        return(np.ones(16 * 2000) * final_gain)
    Pulse = Compensated_pulse_list[Qubit_number - 1]
    Comp_Difference = Pulse - 1
    Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
    Comp_Step_Gain[Comp_Step_Gain > 32000] = 32000
    Comp_Step_Gain[Comp_Step_Gain < -32000] = -32000

    return(Comp_Step_Gain)