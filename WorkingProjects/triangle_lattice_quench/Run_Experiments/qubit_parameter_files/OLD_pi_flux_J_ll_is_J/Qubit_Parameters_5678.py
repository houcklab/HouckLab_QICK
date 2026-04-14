import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *



# 8Q Pi Flux parameters
Readout = np.array([27728, 29032, 27519, 26664, 1895, -17022, 18917, 5170])
# (4350.0, 4350.0, 4350.0, 4350.0, 3800.0, 3514.6, 4200.0, 3900.0)

Expt_FF = np.array([27728, 29032, 27519, 26664, -428, 35, -248, -701])

Qubit_Parameters = {
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 6400,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3804.7, 'sigma': 0.07, 'Gain': 3200},
          'Pulse_FF': Readout},
    '6': {'Readout': {'Frequency': 7440.6, 'Gain': 5300,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3576.1, 'sigma': 0.07, 'Gain': 3150},
          'Pulse_FF': Readout + [0, 0, 0, 0, 0, +8000, 0, 0]},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 7000,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4199.1, 'sigma': 0.07, 'Gain': 3100},
          'Pulse_FF': Readout },
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 4000,
                      'FF_Gains': Readout , 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3915.4, 'sigma': 0.07, 'Gain': 3590},
          'Pulse_FF': Readout},

    # Resonant points. +- 4000 FF gain ~ 100 MHz
    '6L': {'Qubit': {'Frequency': 3749.8, 'sigma': 0.07, 'Gain': 2375},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, +3000, 0, +3000, +3000]},
    '8L': {'Qubit': {'Frequency': 3670.5, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 0, 0, -3000]},

    '7HH': {'Qubit': {'Frequency': 3825.7, 'sigma': 0.07, 'Gain': 3276},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, -4000, 0, 3000, -4000]},
    '6HH': {'Qubit': {'Frequency': 3753.6, 'sigma': 0.07, 'Gain': 3233},
               'Pulse_FF': Expt_FF + [0, 0, 0, 0, -4000, 0, 3000, -4000]},



    # Resonant points. Guess: [0,0,0,0]
    '5R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 4000},
            'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, -4000, -4000, -4000]},
    '6R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 3500},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, -4000, 0, -4000, -4000]},
    '7R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2300},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, -4000, -4000, 0, -4000]},
    '8R': {'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, -4000, -4000, -4000, 0]},
}



# prepared_state = '4HH'
# pulse_FF = Qubit_Parameters[prepared_state]['Pulse_FF'].copy()

# Q1-Q2 resonance
# pulse_FF[0:2] = Expt_FF[0:2]
# Expt_FF = pulse_FF


# Q3-Q4 resonance
# pulse_FF[2:4] = Expt_FF[2:4]
# pulse_FF[1] = -10000
# Expt_FF = pulse_FF


# Q1-Q2-Q3-Q4 resonance
# pulse_FF[0:4] = Expt_FF[0:4]
# Expt_FF = pulse_FF

# Q5-Q6 resonance
FF_gain5_expt = Expt_FF[4] - 0 # resonance
FF_gain6_expt = Expt_FF[5] - 0 # resonance
FF_gain7_expt = Expt_FF[6] + 8000 # resonance
FF_gain8_expt = Expt_FF[7] + 8000 # resonance

# Q6-Q7 resonance
FF_gain5_expt = Expt_FF[4] - 10000 # resonance
FF_gain6_expt = Expt_FF[5] - 10000 # resonance
FF_gain7_expt = Expt_FF[6] + 0 # resonance
FF_gain8_expt = Expt_FF[7] + 0 # resonance

# 5,6,7,8 resonance
FF_gain5_expt = Expt_FF[4]
FF_gain6_expt = Expt_FF[5]
FF_gain7_expt = Expt_FF[6]
FF_gain8_expt = Expt_FF[7]

FF_gain5_BS =  -9702  # 3550.0
FF_gain6_BS = -10896  # 3550.0
FF_gain7_BS =   10195  # 4000.0
FF_gain8_BS =   8595  # 4000.0

# Qubits 1 to 4 kept at 4350 MHz
FF_gain1_expt = Expt_FF[0]
FF_gain2_expt = Expt_FF[1]
FF_gain3_expt = Expt_FF[2]
FF_gain4_expt = Expt_FF[3]
FF_gain1_BS =  Expt_FF[0]  # 4350.0
FF_gain2_BS =  Expt_FF[1]  # 4350.0
FF_gain3_BS =  Expt_FF[2]  # 4350.0
FF_gain4_BS =  Expt_FF[3]  # 4350.0

print("Using Qubit_Parameters_5678")