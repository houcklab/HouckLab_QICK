import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

# 8Q Pi Flux parameters
Readout_FF4 = np.array([-2099, 29032, 12849, -15783, 5558, 6197, 5563, 5170])
# (3700.0, 4350.0, 4100.0, 3519.3, 3900.0, 3900.0, 3900.0, 3900.0)

Readout_FF8 = np.array([9690, 10259, 8954, 9592, -1991, 31114, 13734, -14398])
# (4000.0, 4000.0, 4000.0, 4000.0, 3700.0, 4350.0, 4100.0, 3512.7)

Readout_1245 = np.array([-2099, 29032, 5000, -15783, 12000, 6197, 5563, 5170])

Readout = Readout_1245
# Readout = Readout_FF4

Expt_FF = np.array([60, 66, -110, 240, -461, 35, -240, -685])



# All at 4065.0
Pulse4_FF = Expt_FF + [-8000, 0, -8000, 2000, -8000, -4000, -2000, -8000]
# Q2 at 3800, Q4 at 3750, Q7 at 3700, Q6 at 3650, rest at 3550
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.3 - BaseConfig["res_LO"], 'Gain': 5300,
                      "FF_Gains": Readout, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3698.0, 'sigma': 0.07, 'Gain': 3000},
          'Pulse_FF': Readout},
    '2': {'Readout': {'Frequency': 7078.1 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": Readout, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4350.0, 'sigma': 0.07, 'Gain': 2250},
          'Pulse_FF': Readout},
    '3': {'Readout': {'Frequency': 7510.9 - BaseConfig["res_LO"], 'Gain': 2600,
                      "FF_Gains": Readout, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4104.7, 'sigma': 0.07, 'Gain': 6400},
          'Pulse_FF': Readout },
    '4': {'Readout': {'Frequency': 7567.7 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": Readout, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3584.4, 'sigma': 0.07, 'Gain': 4200},
          'Pulse_FF': Readout + [8000, 0, 0, +8000, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7363.4 - BaseConfig['res_LO'], 'Gain': 6500,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4073.1, 'sigma': 0.07, 'Gain': 4000},
          'Pulse_FF': Readout},
    '6': {'Readout': {'Frequency': 7442.0 - BaseConfig['res_LO'], 'Gain': 5300,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4360.1, 'sigma': 0.07, 'Gain': 2500},
          'Pulse_FF': Readout},
    '7': {'Readout': {'Frequency': 7254.0 - BaseConfig['res_LO'], 'Gain': 4000,
                      'FF_Gains': Readout, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4104.0, 'sigma': 0.07, 'Gain': 2502},
          'Pulse_FF': Readout },
    '8': {'Readout': {'Frequency': 7309.0 - BaseConfig['res_LO'], 'Gain': 5400,
                      'FF_Gains': Readout + [0, 0, 0, 0, +8000, 0, 0, +8000], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3514.7, 'sigma': 0.07, 'Gain': 5150},
          'Pulse_FF': Readout},

    # Resonant points. +- 4000 FF gain ~ 100 MHz
    '1H': {'Qubit': {'Frequency': 3826.4, 'sigma': 0.07, 'Gain': 2840},
           'Pulse_FF': Expt_FF + [3000, 0, 0, 0, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 3822.4, 'sigma': 0.07, 'Gain': 3000},
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

    '4HH': {'Qubit': {'Frequency': 3825.5, 'sigma': 0.07, 'Gain': 3500},
                   'Pulse_FF': Expt_FF + [-4000, 0, -4000, 3000, -4000, -4000, -4000, -4000]},
    '2HH': {'Qubit': {'Frequency': 3749.5, 'sigma': 0.07, 'Gain': 3000},
               'Pulse_FF': Expt_FF + [-4000, 0, -4000, 3000, -4000, -4000, -4000, -4000]},

    '7HH': {'Qubit': {'Frequency': 3830.7, 'sigma': 0.07, 'Gain': 3220},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, 3000, -4000]},
    '6HH': {'Qubit': {'Frequency': 3749.5, 'sigma': 0.07, 'Gain': 3060},
               'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, 3000, -4000]},


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



prepared_state = '4HH'
pulse_FF = Qubit_Parameters[prepared_state]['Pulse_FF'].copy()

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

# Q4-Q5 resonance
# pulse_FF[3:5] = Expt_FF[3:5]
# Expt_FF = pulse_FF
# pulse_FF[1] = -20000



FF_gain1_expt = Expt_FF[0] - 0 # resonance
FF_gain2_expt = Expt_FF[1] - 0 # resonance
FF_gain3_expt = Expt_FF[2] - 0 # resonance
FF_gain4_expt = Expt_FF[3] - 0 # resonance
FF_gain5_expt = Expt_FF[4] - 0 # resonance
FF_gain6_expt = Expt_FF[5] - 0 # resonance
FF_gain7_expt = Expt_FF[6] - 0 # resonance
FF_gain8_expt = Expt_FF[7] - 0 # resonance

FF_gain1_BS =  23000  # 4300.0
FF_gain2_BS =  23927  # 4300.0
FF_gain3_BS =  Expt_FF[2] + 10000
FF_gain4_BS =  -4428  # 3650.0
FF_gain5_BS =  -4972
FF_gain5_BS =  -4581
FF_gain6_BS =  Expt_FF[5] + 10000
FF_gain7_BS =  Expt_FF[6] + 10000
FF_gain8_BS =  Expt_FF[7] + 10000
