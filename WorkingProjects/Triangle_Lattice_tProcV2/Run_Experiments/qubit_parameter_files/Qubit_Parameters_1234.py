import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

# 8Q Pi Flux parameters
Readout_FF4 = np.array([2437, 29001, -14955, -7886, 9742, 11696, 14450, 8551])
# (4100.0, 4419.1, 3600.0, 3850.0, 4250.0, 4250.0, 4250.0, 4250.0)


Readout_FF8 = np.array([9619, 10089, 10959, 8734, -4703, -14375, 25722, 2214])
# (4250.0, 4250.0, 4250.0, 4250.0, 3900.0, 3600.0, 4325.6, 4100.0)

Readout = Readout_FF4

Expt_FF = np.array([-11175, -12314, -9138, -11986, -10533, -11127, -7795, -9997])
# (3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0)

# pulse 145 within anharmonicity
pulse_145 = np.array([-9336, -29001, -25392, -7886, -12253, -28060, -25722, -24395])
# (3800.0, 3516.7, 3475.5, 3850.0, 3700.0, 3514.6, 3448.8, 3512.7)

# pulse 145 far away
# pulse_145 = np.array([2437, -29001, -25392, 8734, -4703, -28060, -25722, -24395])
# (4100.0, 3516.7, 3475.5, 4250.0, 3900.0, 3514.6, 3448.8, 3512.7)

# switch Q5 and Q6
pulse_146 = np.array([2000, -5000, -5000, 4000, -5000, -2000, -5000, -5000])



# All at 4065.0
Pulse4_FF = Expt_FF + [-8000, 0, -8000, 2000, -8000, -4000, -2000, -8000]
# Q2 at 3800, Q4 at 3750, Q7 at 3700, Q6 at 3650, rest at 3550
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.7 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": Readout_FF4, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4095.0, 'sigma': 0.07, 'Gain': 2460},
          'Pulse_FF': Readout_FF4},
    '2': {'Readout': {'Frequency': 7078.25 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": Readout_FF4, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4421.5, 'sigma': 0.07, 'Gain': 2250},
          'Pulse_FF': Readout_FF4},
    '3': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains": Readout_FF4, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3603.2, 'sigma': 0.07, 'Gain': 5780},
          'Pulse_FF': Readout_FF4 },
    '4': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7300,
                      "FF_Gains": Readout_FF4, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3846.6, 'sigma': 0.07, 'Gain': 4260},
          'Pulse_FF': Readout_FF4 + [0, 0, 0, 0, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7363.1 - BaseConfig['res_LO'], 'Gain': 3200,
                      'FF_Gains': Readout_FF8, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3904.7, 'sigma': 0.07, 'Gain': 2460},
          'Pulse_FF': Readout_FF8},
    '6': {'Readout': {'Frequency': 7440.9 - BaseConfig['res_LO'], 'Gain': 6500,
                      'FF_Gains': Readout_FF8, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3676.5, 'sigma': 0.07, 'Gain': 2300},
          'Pulse_FF': Readout_FF8},
    '7': {'Readout': {'Frequency': 7254.4 - BaseConfig['res_LO'], 'Gain': 6500,
                      'FF_Gains': Readout_FF8, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4328, 'sigma': 0.07, 'Gain': 3000},
          'Pulse_FF': Readout_FF8 },
    '8': {'Readout': {'Frequency': 7309.5 - BaseConfig['res_LO'], 'Gain': 6000,
                      'FF_Gains': Readout_FF8, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4092.5, 'sigma': 0.07, 'Gain': 2160},
          'Pulse_FF': Readout_FF8},

    # Resonant points. +- 4000 FF gain ~ 100 MHz
    '1H': {'Qubit': {'Frequency': 3827.5, 'sigma': 0.07, 'Gain': 2840},
           'Pulse_FF': Expt_FF + [3000, 0, 0, 0, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 3820.86, 'sigma': 0.07, 'Gain': 3000},
           'Pulse_FF': Expt_FF + [0, 3000, 0, 0, 0, 0, 0, 0]},
    '3H': {'Qubit': {'Frequency': 3834.1, 'sigma': 0.07, 'Gain': 6100},
           'Pulse_FF': Expt_FF + [0, 0, 3000, 0, 0, 0, 0, 0]},
    '4H': {'Qubit': {'Frequency': 3826.4, 'sigma': 0.07, 'Gain': 3700},
           'Pulse_FF': Expt_FF + [0, 0, 0, 3000, 0, 0, 0, 0]},
    '5H': {'Qubit': {'Frequency': 3828.7, 'sigma': 0.07, 'Gain': 6400},
               'Pulse_FF': Expt_FF + [0, 0, 0, 0, 3000, 0, 0, 0]},
    '6H': {'Qubit': {'Frequency': 3821.6, 'sigma': 0.07, 'Gain': 3060},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 3000, 0, 0]},
    '7H': {'Qubit': {'Frequency': 3830.7, 'sigma': 0.07, 'Gain': 3480},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 0, 3000, 0]},
    '8H': {'Qubit': {'Frequency': 3835.9, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 0, 0, 3000]},

    '4HH': {'Qubit': {'Frequency': 3826.5, 'sigma': 0.07, 'Gain': 4160},
                   'Pulse_FF': Expt_FF + [-4000, 0, -4000, 3000, -4000, -4000, -4000, -4000]},
    '2HH': {'Qubit': {'Frequency': 3749, 'sigma': 0.07, 'Gain': 2870},
               'Pulse_FF': Expt_FF + [-4000, 0, -4000, 3000, -4000, -4000, -4000, -4000]},

    '7HH': {'Qubit': {'Frequency': 3830.7, 'sigma': 0.07, 'Gain': 3220},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, 3000, -4000]},
    '6HH': {'Qubit': {'Frequency': 3749.5, 'sigma': 0.07, 'Gain': 3060},
               'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, 3000, -4000]},

    # within anharmonicity
    '1HHH_readout': {'Readout': {'Frequency': 7121.2 - BaseConfig["res_LO"], 'Gain': 5300,
                      "FF_Gains": pulse_145, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
             'Qubit': {'Frequency': 3792.5, 'sigma': 0.07, 'Gain': 1955},
             'Pulse_FF': pulse_145},
    '4HHH_readout': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 6000,
                         "FF_Gains": pulse_145, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
             'Qubit': {'Frequency': 3857.9, 'sigma': 0.07, 'Gain': 5300},
             'Pulse_FF': pulse_145},
    '5HHH_readout': {'Readout': {'Frequency': 7363.0 - BaseConfig['res_LO'], 'Gain': 7000,
                         'FF_Gains': pulse_145, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
             'Qubit': {'Frequency': 3704.1, 'sigma': 0.07, 'Gain': 6300},
             'Pulse_FF': pulse_145},
    '1HHH': {'Qubit': {'Frequency': 3792.5, 'sigma': 0.07, 'Gain': 1955},
             'Pulse_FF': pulse_145},
    '4HHH': {'Qubit': {'Frequency': 3857.9, 'sigma': 0.07, 'Gain': 5300},
             'Pulse_FF': pulse_145},
    '5HHH': {'Qubit': {'Frequency': 3706, 'sigma': 0.07, 'Gain': 6000},
             'Pulse_FF': pulse_145},

    # far away
    # '1HHH': {'Qubit': {'Frequency': 4093.5, 'sigma': 0.07, 'Gain': 2600},
    #        'Pulse_FF': pulse_145},
    # '4HHH': {'Readout': {'Frequency': 7568.8 - BaseConfig["res_LO"], 'Gain': 7000,
    #                   "FF_Gains": pulse_145, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
    #          'Qubit': {'Frequency': 4261, 'sigma': 0.07, 'Gain': 4500},
    #            'Pulse_FF': pulse_145},
    # '5HHH': {'Readout': {'Frequency': 7363.1 - BaseConfig['res_LO'], 'Gain': 7000,
    #          'FF_Gains': pulse_145, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
    #          'Qubit': {'Frequency': 3905, 'sigma': 0.07, 'Gain': 2550},
    #          'Pulse_FF': pulse_145},


    '4H4': {'Qubit': {'Frequency': 3799.7, 'sigma': 0.07, 'Gain': 2700},
                   'Pulse_FF': Pulse4_FF},
    '2H4': {'Qubit': {'Frequency': 3748.9, 'sigma': 0.07, 'Gain': 2600},
                   'Pulse_FF': Pulse4_FF},
    '7H4': {'Qubit': {'Frequency': 3698.2, 'sigma': 0.07, 'Gain': 3900},
           'Pulse_FF': Pulse4_FF},
    '6H4': {'Qubit': {'Frequency': 3663, 'sigma': 0.07, 'Gain': 3580},
               'Pulse_FF': Pulse4_FF},


    # Resonant points. Guess: [0,0,0,0]
    '1R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2300},
           'Pulse_FF': Expt_FF + [0, -4000, -4000, -4000, -4000, -4000, -4000, -4000]},
    '2R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [-4000, 0, -4000, -4000, -4000, -4000, -4000, -4000]},
    '3R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 4100},
           'Pulse_FF': Expt_FF + [-4000, -4000, 0, -4000, -4000, -4000, -4000, -4000]},
    '4R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 3200},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, 0, -4000, -4000, -4000, -4000]},
    '5R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2800},
            'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, 0, -4000, -4000, -4000]},
    '6R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 3500},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, -4000, -4000]},
    '7R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2300},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, -4000, 0, -4000]},
    '8R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, -4000, -4000, 0]},
}



prepared_state = '1H'
pulse_FF = Qubit_Parameters[prepared_state]['Pulse_FF'].copy()
print(f'pulse_FF = {pulse_FF}')

# no ramp
# Expt_FF = pulse_FF

# Q1
# pulse_FF[0] = Expt_FF[0]
# Expt_FF = pulse_FF

# Q1-Q2 resonance
# pulse_FF[0:2] = Expt_FF[0:2]
# # pulse_FF[1] += 400
# # pulse_FF[3] += 4000
# Expt_FF = pulse_FF

# Q1-Q4-Q5 resonance
# pulse_FF[0] = Expt_FF[0]
# pulse_FF[3] = Expt_FF[3]
# pulse_FF[4] = Expt_FF[4]
# Expt_FF = pulse_FF


# Q1-Q2-Q3 resonance
# pulse_FF[0:3] = Expt_FF[0:3]
# Expt_FF = pulse_FF

# Q3-Q4 resonance
# pulse_FF[2:4] = Expt_FF[2:4]
# pulse_FF[0] -= 10000
# Expt_FF = pulse_FF


# Q1-Q2-Q3-Q4 resonance
# pulse_FF[0:4] = Expt_FF[0:4]
# Expt_FF = pulse_FF

# Q1-Q2-Q3-Q4-Q5 resonance
# pulse_FF[0:5] = Expt_FF[0:5]
# Expt_FF = pulse_FF

# Q1-Q2-Q3-Q4-Q6 resonance
# pulse_FF[0:4] = Expt_FF[0:4]
# pulse_FF[5] = Expt_FF[5]
# Expt_FF = pulse_FF


# Q1-Q2-Q3-Q4-Q5-Q6 resonance
# pulse_FF[0:6] = Expt_FF[0:6]
# Expt_FF = pulse_FF

# only Q5
# pulse_FF -= 10000
# pulse_FF[4] = Expt_FF[4]
# Expt_FF = pulse_FF

print(f'Expt_FF = {pulse_FF}')


FF_gain1_expt = Expt_FF[0] - 8000 # resonance
FF_gain2_expt = Expt_FF[1] - 8000 # resonance
FF_gain3_expt = Expt_FF[2] - 8000 # resonance
FF_gain4_expt = Expt_FF[3] - 8000 # resonance
FF_gain5_expt = Expt_FF[4] - 8000 # resonance
FF_gain6_expt = Expt_FF[5] - 8000 # resonance
FF_gain7_expt = Expt_FF[6] - 8000 # resonance
FF_gain8_expt = Expt_FF[7] - 8000 # resonance

FF_gain1_BS =  22589  # 4400.0
FF_gain2_BS =  23000  # 4400.0
FF_gain3_BS = -12810  # 3650.0
FF_gain4_BS = -16374  # 3650.0

FF_gain5_BS =   7231  # 4200.0
FF_gain6_BS =   8739  # 4200.0
FF_gain7_BS = -25722  # 3448.8
FF_gain8_BS = -24395  # 3512.7

BS_FF = [FF_gain1_BS, FF_gain2_BS, FF_gain3_BS, FF_gain4_BS, FF_gain5_BS, FF_gain6_BS, FF_gain7_BS, FF_gain8_BS]


# pulse_qubits = [4, 1, 5]
# pulse_qubits = [1]
# ramp_initial_gains = Qubit_Parameters[prepared_state]['Pulse_FF'].copy()
# for qubit in pulse_qubits:
#     ramp_initial_gains[qubit-1] = Expt_FF[qubit-1]
#
# print(f'ramp_initial_gains = {ramp_initial_gains}')



if __name__ == '__main__':
    gains = np.array([pulse_145, Expt_FF, BS_FF, Readout_FF4])
    # gains = np.array([pulse_145, Readout_FF4])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()

