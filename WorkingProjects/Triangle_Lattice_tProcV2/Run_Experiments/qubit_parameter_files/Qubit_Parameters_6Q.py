import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

# 8Q Pi Flux parameters
Readout_FF = np.array([-1638, -14218, 18524, -4102, -16892, 15227, 3721, -19085])
# (4000.0, 3700.0, 4350.0, 3950.0, 3600.0, 4300.0, 4050.0, 3550.0)


Expt_FF = np.array([-11175, -12314, -9138, -11986, -10533, -11127, -7795, -7165])
# (3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0)

# 3800
Expt_FF = np.array([-9236, -9840, -7214, -9696, -8462, -8874, -6015, -7188])
# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)

_45 = 1800 # FF for 45 MHz
pulse_362 = np.array([-4*_45, -2*_45, 0, -5*_45, -3*_45, -1*_45, 10000, 10000])

resonance_frequency = 3800

# All at 4065.0
Pulse4_FF = Expt_FF + [-8000, 0, -8000, 2000, -8000, -4000, -2000, -8000]
# Q2 at 3800, Q4 at 3750, Q7 at 3700, Q6 at 3650, rest at 3550
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.6 - BaseConfig["res_LO"], 'Gain': 707,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3998.8, 'sigma': 0.07, 'Gain': 3400},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 1000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3699.8, 'sigma': 0.07, 'Gain': 3365},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7511.58 - BaseConfig["res_LO"], 'Gain': 970,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4361.8, 'sigma': 0.07, 'Gain': 4400},
          'Pulse_FF': Readout_FF},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"], 'Gain': 1229,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3948.1, 'sigma': 0.07, 'Gain': 2380},
          'Pulse_FF': Readout_FF + [0, 0, 0, 0, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7362.87 - BaseConfig['res_LO'], 'Gain': 1229,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3601.7, 'sigma': 0.07, 'Gain': 2950},
          'Pulse_FF': Readout_FF },
    '6': {'Readout': {'Frequency': 7441.6 - BaseConfig['res_LO'], 'Gain': 1000,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4308.2, 'sigma': 0.07, 'Gain': 2827},
          'Pulse_FF': Readout_FF},
    '7': {'Readout': {'Frequency': 7254.1 - BaseConfig['res_LO'], 'Gain': 1000,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4052.17, 'sigma': 0.07, 'Gain': 3389},
          'Pulse_FF': Readout_FF},
    '8': {'Readout': {'Frequency': 7308.54 - BaseConfig['res_LO'], 'Gain': 1220,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3537.05, 'sigma': 0.07, 'Gain': 2780},
          'Pulse_FF': Readout_FF},

    # Resonant points. +- 4000 FF gain ~ 100 MHz
    '1H': {'Qubit': {'Frequency': 3878.3, 'sigma': 0.07, 'Gain': 3600},
           'Pulse_FF': Expt_FF + [3000, 0, 0, 0, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 3873.6, 'sigma': 0.07, 'Gain': 3780},
           'Pulse_FF': Expt_FF + [0, 3000, 0, 0, 0, 0, 0, 0]},
    '3H': {'Qubit': {'Frequency': 3885.5, 'sigma': 0.07, 'Gain': 3900},
           'Pulse_FF': Expt_FF + [0, 0, 3000, 0, 0, 0, 0, 0]},
    '4H': {'Qubit': {'Frequency': 3877.9, 'sigma': 0.07, 'Gain': 5000},
           'Pulse_FF': Expt_FF + [0, 0, 0, 3000, 0, 0, 0, 0]},
    '5H': {'Qubit': {'Frequency': 3882.3, 'sigma': 0.07, 'Gain': 2750},
               'Pulse_FF': Expt_FF + [0, 0, 0, 0, 3000, 0, 0, 0]},
    '6H': {'Qubit': {'Frequency': 3873.6, 'sigma': 0.07, 'Gain': 5000},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 3000, 0, 0]},
    '7H': {'Qubit': {'Frequency': 3881.2, 'sigma': 0.07, 'Gain': 2300},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 0, 3000, 0]},
    '8H': {'Qubit': {'Frequency': 3888.2, 'sigma': 0.07, 'Gain': 2600},
           'Pulse_FF': Expt_FF + [0, 0, 0, 0, 0, 0, 0, 3000]},

    '1L': {'Qubit': {'Frequency': 3798.7, 'sigma': 0.07, 'Gain': 1930},
               'Pulse_FF': Expt_FF + [0, 3000, 8000, 8000, 8000, 8000, 8000, 8000]},
    '3L': {'Qubit': {'Frequency': 3797.0, 'sigma': 0.07, 'Gain': 5180},
                   'Pulse_FF': Expt_FF + [8000, 8000, 0, 8000, 3000, 8000, 8000, 8000]},
    '4L': {'Qubit': {'Frequency': 3800.5, 'sigma': 0.07, 'Gain': 2500},
                   'Pulse_FF': Expt_FF + [8000, 8000, 8000, 0, 3000, 8000, 8000, 8000]},
    '7L': {'Qubit': {'Frequency': 3797.5, 'sigma': 0.07, 'Gain': 2828},
               'Pulse_FF': Expt_FF + [8000, 8000, 8000, 8000, 3000, 8000, 0, 8000]},
    '8L': {'Qubit': {'Frequency': 3798.4, 'sigma': 0.07, 'Gain': 2450},
                   'Pulse_FF': Expt_FF + [8000, 8000, 8000, 8000, 8000, 3000, 8000, 0]},
    # within anharmonicity
    '3_362': {'Qubit': {'Frequency': 3803.34, 'sigma': 0.07, 'Gain': 3510},
                   'Pulse_FF': Expt_FF + pulse_362},
    '6_362': {'Qubit': {'Frequency': 3759.2, 'sigma': 0.07, 'Gain': 3150},
                   'Pulse_FF': Expt_FF + pulse_362},
    '2_362': {'Qubit': {'Frequency': 3717.5, 'sigma': 0.07, 'Gain': 5450},
                   'Pulse_FF': Expt_FF + pulse_362},



    '12': {'Ramp':{'Init_FF': None,
                    'Expt_FF': Expt_FF + [0,0,8000,8000,8000,8000, 8000, 8000]}},
    '34': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [-8000,-8000,0,0,-8000,-8000, -8000, -8000]}},
    '35': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000,8000,0,8000,0,8000, 8000, 8000]}},
    '46': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [-8000, -8000, -8000, 0, -8000, 0, -8000, -8000]}},

    '45': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [8000, 8000, 8000, 0, 0, 8000, 8000, 8000]}},

    '56': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [-8000,-8000,-8000,-8000,0,0, -8000, -8000]}},

    '68': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000,-8000, 8000, 8000, 0, 8000, 0]}},
    '57': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000, 8000, 8000, 0, 8000, 0, 8000]}},

    '1234': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [0, 0, 0, 0, 8000, 8000, 8000, 8000]}},


    '362': {'Ramp':{'Init_FF': Expt_FF + [-4*_45, 0, 0, -5*_45, -3*_45, 0, 10000, 10000],
                       'Expt_FF': Expt_FF + [0,0,0,0,0,0, 10000, 10000]}},

    '6Q': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF + [0,0,0,0,0,0, 10000, 10000]}},

    '8Q': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    # beamsplitter definitions
    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS':{'BS_FF': [-18440, -19389, 13904, 11543, -12400, -13248, 5939, 2214]}},


    # (3600.0, 3600.0, 4000.0, 4400.0, 4400.0, 3700.0, 3700.0, 3700.0)
    '1245_correlations': {'BS': {'BS_FF': [-18440, -19389, -41, 19742, 23097, -13248, -9686, -11845]}},

    # (3600.0, 3600.0, 4380.0, 4435.8, 4404.2, 3600.0, 3600.0, 4418.0)
    '1267_correlations': {'BS': {'BS_FF': [-18440, -19389, 25392, 27560, 25700, -18375, -13757, 24395]}},


    # Resonant points. Guess: [0,0,0,0]
    '1R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 1750},
           'Pulse_FF': Expt_FF + [0, +4000, +4000, +4000, +4000, +4000, +4000, +4000]},
    '2R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2000},
           'Pulse_FF': Expt_FF + [+4000, 0, +4000, +4000, +4000, +4000, +4000, +4000]},
    '3R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3150},
           'Pulse_FF': Expt_FF + [+4000, +4000, 0, +4000, +4000, +4000, +4000, +4000]},
    '4R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, 0, +4000, +4000, +4000, +4000]},
    '5R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
            'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, 0, +4000, +4000, +4000]},
    '6R': {'Readout': {'Frequency': 7441.1 - BaseConfig['res_LO'], 'Gain': 4000,
            'FF_Gains': Expt_FF + [+4000, +4000, +4000, +4000, +4000, 0, +4000, +4000], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
            'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, 0, +4000, +4000]},
    '7R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, +4000, 0, +4000]},
    '8R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, +4000, +4000, 0]},



}

Ramp_state = '362'
Ramp_state = '6Q'
# Ramp_state = '45'
Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']

# beamsplitter_point = '1234_correlations'
beamsplitter_point = '1245_correlations'
BS_FF = Qubit_Parameters[beamsplitter_point]['BS']['BS_FF']


FF_gain1_expt = Ramp_FF[0] # resonance
FF_gain2_expt = Ramp_FF[1]  # resonance
FF_gain3_expt = Ramp_FF[2]  # resonance
FF_gain4_expt = Ramp_FF[3]  # resonance
FF_gain5_expt = Ramp_FF[4]  # resonance
FF_gain6_expt = Ramp_FF[5]  # resonance
FF_gain7_expt = Ramp_FF[6]  # resonance
FF_gain8_expt = Ramp_FF[7]  # resonance

FF_gain1_BS = BS_FF[0]
FF_gain2_BS = BS_FF[1]
FF_gain3_BS = BS_FF[2]
FF_gain4_BS = BS_FF[3]
FF_gain5_BS = BS_FF[4]
FF_gain6_BS = BS_FF[5]
FF_gain7_BS = BS_FF[6]
FF_gain8_BS = BS_FF[7]



if __name__ == '__main__':
    gains = np.array([Readout_FF, Expt_FF, BS_FF])
    # gains = np.array([pulse_145, Readout_FF4])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()

