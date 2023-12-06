import pickle
import numpy as np
import matplotlib.pyplot as plt

def QuadExponentialFit(t, A1, T1, A2, T2, A3, T3, A4, T4):
    return(A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2) + A3 * np.exp(-t / T3) + A4 * np.exp(-t / T4))

def DoubleExponentialFit(t, A1, T1, A2, T2):
    return (A1 * np.exp(-t / T1) + A2 * np.exp(-t / T2))

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

def Compensated_AWG_LongTimes(Num_Points, Fit_Parameters, maximum = 1.5):
    step = 0.00232515 / 16
    time = np.arange(0,Num_Points)*step
    ideal_AWG = np.ones(Num_Points)
    analytic_n = DoubleExponentialFit(time, Fit_Parameters[0], Fit_Parameters[1], Fit_Parameters[2],
                                   Fit_Parameters[3])
    analytic_n[analytic_n < -0.8] = -0.8
    v_awg = ideal_AWG / (1 + analytic_n)
    v_awg[v_awg > maximum] = maximum
    return(time, v_awg)


# Qubit1_Long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_Fit_LongTimes_Corrected_1.p', 'rb'))
# Qubit2_Long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))
# Qubit4_Long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_Fit_LongTimes_Corrected_3.p', 'rb'))

# Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
# Qubit1_2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final2.p', 'rb'))
#
# Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
# Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))


Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_PreFinal.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_PreFinal.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_PreFinal.p', 'rb'))
# Qubit2_[0] *= 0.85
# Qubit2_[2] *= 0.85
# Qubit2_[4] *= 1
# Qubit1_[0] *= 2.35  #First one
# Qubit1_[2] *= 2.35  #First one
# Qubit1_[0] *= 1.   #Second one
# Qubit1_[2] *= 1.   #Second one
# Qubit1_[4] *= 1.2  #Second one
#
# print(Qubit4_)
# Qubit4_[0] *= 4.7  #First One
# Qubit4_[2] *= 4.7 #FIrst one

# Qubit4_[0] *= 1.6  #Second one
# Qubit4_[2] *= 1.6  #Second one
# Qubit4_[4] *= 1.7  #Second one
# pickle.dump(Qubit2_, open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'wb'))

# pickle.dump(Qubit1_, open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'wb'))
# pickle.dump(Qubit4_, open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'wb'))

Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))




# # Qubit1_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp.p', 'rb'))
# Qubit1_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Corrected.p', 'rb'))
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_corrected_V2.p', 'rb'))
# Qubit2_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))
# Qubit4_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_Fit_LongTimes_Corrected_3.p', 'rb'))
#
# Qubit1_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_Fit_LongTimes.p', 'rb'))
# # Qubit1_parameters_long = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Corrected_LongTime_3.p', 'rb'))
#
# Qubit1_parameters_long2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_Fit_LongTimes_Corrected_1.p', 'rb'))


# Qubit4_parameters_long2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_Fit_LongTimes_Corrected_2.p', 'rb'))

NumPoints = 30000
# time, v_awg_Q1L = Compensated_AWG_LongTimes(NumPoints, Qubit4_Long)

time, v_awg_Q1 = Compensated_AWG(NumPoints, Qubit1_)
# time, v_awg_Q12 = Compensated_AWG(NumPoints, Qubit1_2)

time, v_awg_Q2 = Compensated_AWG(NumPoints, Qubit2_)
time, v_awg_Q4 = Compensated_AWG(NumPoints, Qubit4_)

# time, v_awg_Q4 = Compensated_AWG_LongTimes(NumPoints, Qubit4_parameters_long)
# time, v_awg_Q42 = Compensated_AWG_LongTimes(NumPoints, Qubit4_parameters_long2)
# time, v_awg_Q43 = Compensated_AWG_LongTimes(NumPoints, Qubit4_parameters_long3)


# timeL, v_awg_Q2L = Compensated_AWG_LongTimes(NumPoints, Qubit2_parameters_long)
# print(v_awg_Q2[:20])

# plt.plot(time, v_awg_Q1, '.-', color = 'blue')
# plt.plot(time, v_awg_Q12, '.-', color = 'red')

# plt.plot(time, v_awg_Q2, '.-', color = 'red')
# plt.plot(time, v_awg_Q4, '.-', color = 'green')

# plt.show()
# plt.plot(time, v_awg_Q43, '.-', color = 'green')

#
# # print(v_awg_Q2[-1])
# # plt.plot(time[100:], v_awg_Q2[100:], '.-', color = 'red')
# # plt.plot(time[100:], v_awg_Q2L[100:], '.-', color = 'blue')
#
# plt.show()

# plt.plot(time, v_awg_Q1, '.-', color = 'blue')
# Qubit1_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp.p', 'rb'))
# time, v_awg_Q1 = Compensated_AWG(NumPoints, Qubit1_parameters)
# plt.plot(time, v_awg_Q1, '.-', color = 'red')

# plt.plot(time, v_awg_Q2, '.-', color = 'red')
# Qubit2_parameters = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp.p', 'rb'))
# time, v_awg_Q1 = Compensated_AWG(NumPoints, Qubit2_parameters)
# plt.plot(time, v_awg_Q1, '.-', color = 'blue')
# plt.plot(time, v_awg_Q4, '.-', color = 'green')
# plt.xlim(0, 0.2)
# plt.show()





#
#
# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/v_awg_V2.p', 'rb'))
#
# # Compensated_Step_Pulse
# Compensated_Step_Pulse[700:] = 1
# Compensated_Step_Pulse[0] = 2
# Comp_Step = np.concatenate([Compensated_Step_Pulse, np.ones(len(Compensated_Step_Pulse) % 16 + 16 * 500)])
#
# Comp_Difference = Comp_Step - 1
# initial_gain = 8000
# final_gain = -900
# Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
#
# Compensated_Step_Pulse = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
# print()
# # Compensated_Step_Pulse
# Compensated_Step_Pulse[700:] = 1
# Compensated_Step_Pulse[0] = 1.5
# Comp_Step = np.concatenate([Compensated_Step_Pulse, np.ones(len(Compensated_Step_Pulse) % 16 + 16 * 500)])
#
# Comp_Difference = Comp_Step - 1
# initial_gain = 8000
# final_gain = -900
# Comp_Step_Gain = Comp_Difference * (final_gain - initial_gain) + np.ones(len(Comp_Difference)) * final_gain
#
#
# Compensated_Step_Pulse2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V2.p', 'rb'))
#
# # Compensated_Step_Pulse
# Compensated_Step_Pulse2[3000:] = 1
# Compensated_Step_Pulse2[:6] = 1.5
# Comp_Step2 = np.concatenate([Compensated_Step_Pulse2, np.ones(len(Compensated_Step_Pulse2) % 16 + 16 * 500)])
#
# Comp_Difference2 = Comp_Step2 - 1
# initial_gain = 7000
# final_gain = 0
# Comp_Step_Gain2 = Comp_Difference2 * (final_gain - initial_gain) + np.ones(len(Comp_Difference2)) * final_gain
#
# Compensated_Step_Pulse3 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
#
# # Compensated_Step_Pulse
# Compensated_Step_Pulse3[3000:] = 1
# Compensated_Step_Pulse3[:4] = 1.5
# Comp_Step3 = np.concatenate([Compensated_Step_Pulse3, np.ones(len(Compensated_Step_Pulse3) % 16 + 16 * 500)])
#
# Comp_Difference3 = Comp_Step3 - 1
# initial_gain = 7000
# final_gain = 0
# Comp_Step_Gain3 = Comp_Difference3 * (final_gain - initial_gain) + np.ones(len(Comp_Difference3)) * final_gain
#
# Pulse_Q1 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q1_awg_V1.p', 'rb'))
# Pulse_Q2 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q2_awg_V3.p', 'rb'))
# Pulse_Q4 = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Q4_awg_V1.p', 'rb'))
#
#
#
# # print(Pulse_Q1[:10])
# # print(Pulse_Q2[:10])
# # print(Pulse_Q4[:10])
# #
# # print(len(Pulse_Q1))
# # print(len(Pulse_Q2))
# # print(len(Pulse_Q4))
# #
# # Pulse_Q1 -= 0.01
# # Pulse_Q2 -= 0.02
# # Pulse_Q4 -= 0.013
#
# # plt.plot(Pulse_Q1, label = 'Q1')
# # plt.plot(Pulse_Q2, label = 'Q2')
# # plt.plot(Pulse_Q4, label = 'Q4')
# # plt.hlines(1, 0, 2000)
#
# # plt.xlim(0, 2000)
# # plt.ylim(0.9, 1.1)
# # plt.legend()
# # plt.show()
#
