import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

# 8Q Pi Flux parameters
Readout_FF = np.array([-1638, -14218, 18524, -4102, -16358, 15227, 3721, -19085])
# (4000.0, 3700.0, 4350.0, 3950.0, 3600.0, 4300.0, 4050.0, 3550.0)


# Expt_FF = np.array([-11175, -12314, -9138, -11986, -10533, -11127, -7795, -7165])
# (3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0)

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = np.array([-9260, -9812, -7228, -9688, -8477, -8869, -6010, -7171])

# manual
Expt_FF = np.array([-9360, -9712, -7228, -9888, -8477, -8869, -6010, -7171])

# From RampFFvsRamsey with ramp time = 2000
# Expt_FF = np.array([-9231, -9880, -7278, -9681, -8492, -9070, -6088, -7157])

# for beamsplitter points
# Expt_FF = np.array([-9260, -9807, -7227, -9681, -8026, -8875, -6010, -7160])

# Expt_FF = np.array([-9420, -9760, -7210, -10000, -8274, -9278, -6017, -6976])


_45 = 1800 # FF for 45 MHz
ordering =  [8, 5, 4, 1,  3,  2,  6,  7]
detunings = [3, 2, 1, 0, -1, -2, -3, -4]
pulse_1854 = np.array([x for _,x in sorted(zip(ordering,detunings))]) * _45
print("pulse_1854:", pulse_1854 / _45)

# (4100.0, 3600.0, 3600.0, 4280.0, 3850.0, 3550.0, 3600.0, 4150.0)
pulse_4815 = [2437, -19389, -14955, 10372, -6525, -21935, -13757, 4160]
# (4100.0, 3600.0, 3600.0, 4200.0, 3850.0, 3550.0, 3600.0, 4150.0)
# pulse_4815 = [2437, -19389, -14955, 6240, -6525, -21935, -13757, 4160]


resonance_frequency = 3800

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.4 - BaseConfig["res_LO"], 'Gain': 710,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3999.2, 'sigma': 0.07, 'Gain': 3400},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 1000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3699.5, 'sigma': 0.07, 'Gain': 3300},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7511.33 - BaseConfig["res_LO"], 'Gain': 970,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4362.0, 'sigma': 0.07, 'Gain': 4350},
          'Pulse_FF': Readout_FF},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"], 'Gain': 1229,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3948.9, 'sigma': 0.07, 'Gain': 2250},
          'Pulse_FF': Readout_FF + [0, 0, 0, 0, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7362.65 - BaseConfig['res_LO'], 'Gain': 971,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3612.0, 'sigma': 0.07, 'Gain': 2827},
          'Pulse_FF': Readout_FF },
    '6': {'Readout': {'Frequency': 7441.6 - BaseConfig['res_LO'], 'Gain': 1000,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4308.4, 'sigma': 0.07, 'Gain': 3250},
          'Pulse_FF': Readout_FF},
    '7': {'Readout': {'Frequency': 7254.1 - BaseConfig['res_LO'], 'Gain': 1000,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4052.17, 'sigma': 0.07, 'Gain': 3350},
          'Pulse_FF': Readout_FF},
    '8': {'Readout': {'Frequency': 7308.54 - BaseConfig['res_LO'], 'Gain': 1280,
                      'FF_Gains': Readout_FF, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          # 'Qubit': {'Frequency': 3537.05  + 40, 'sigma': 0.07, 'Gain': 3000},
          'Qubit': {'Frequency': 3601.1, 'sigma': 0.07, 'Gain': 2544},
          'Pulse_FF': Readout_FF + [0,0,0,0, 4000,0,0,4000]},

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
    '1_1854': {'Qubit': {'Frequency': 3801.93, 'sigma': 0.07, 'Gain': 1940},
                   'Pulse_FF': Expt_FF + pulse_1854},
    '8_1854': {'Qubit': {'Frequency': 3959, 'sigma': 0.07, 'Gain': 2260},
                 'Pulse_FF': Expt_FF + pulse_1854},
    '5_1854': {'Qubit': {'Frequency': 3901.1, 'sigma': 0.07, 'Gain': 2470},
                   'Pulse_FF': Expt_FF + pulse_1854},
    '4_1854': {'Qubit': {'Frequency': 3849.2, 'sigma': 0.07, 'Gain': 5395},
                   'Pulse_FF': Expt_FF + pulse_1854},


    # far away
    '1_4815': {'Qubit': {'Frequency': 4098.73, 'sigma': 0.07, 'Gain': 2562},
                   'Pulse_FF': pulse_4815},
    '4_4815': {'Qubit': {'Frequency': 4285, 'sigma': 0.07, 'Gain': 2950},
                   'Pulse_FF': pulse_4815},
    '5_4815': {'Qubit': {'Frequency': 3853.1, 'sigma': 0.07, 'Gain': 4800},
                   'Pulse_FF': pulse_4815},
    '8_4815': {'Qubit': {'Frequency': 4123.7, 'sigma': 0.07, 'Gain': 2800},
                 'Pulse_FF': pulse_4815},


    '1_4815_readout': {'Readout': {'Frequency': 7121.75 - BaseConfig["res_LO"], 'Gain': 714,
                                   "FF_Gains": pulse_4815, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4099.0, 'sigma': 0.07, 'Gain': 3100},
                       'Pulse_FF': pulse_4815},
    '4_4815_readout': {'Readout': {'Frequency': 7568.85 - BaseConfig["res_LO"], 'Gain': 1229,
                                   "FF_Gains": pulse_4815, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4203.1, 'sigma': 0.07, 'Gain': 3000},
                       'Pulse_FF': pulse_4815},
    '5_4815_readout': {'Readout': {'Frequency': 7363.37 - BaseConfig['res_LO'], 'Gain': 1229,
                                   'FF_Gains': pulse_4815, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
                       'Qubit': {'Frequency': 3855.36, 'sigma': 0.07, 'Gain': 5300},
                       'Pulse_FF': pulse_4815},
    '8_4815_readout': {'Readout': {'Frequency': 7309.3 - BaseConfig['res_LO'], 'Gain': 1229,
                                   'FF_Gains': pulse_4815, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4123.54, 'sigma': 0.07, 'Gain': 2070},
                       'Pulse_FF': pulse_4815},










    'no_ramp_4815': {'Ramp':{'Init_FF': None,
                    'Expt_FF': pulse_4815}},
    '12': {'Ramp':{'Init_FF': None,
                    'Expt_FF': Expt_FF + [0,0, 8000, -8000, -8000, 8000, 8000, -8000]}},
    '34': {'Ramp':{'Init_FF': Readout_FF,
                        'Expt_FF': Expt_FF + [-8000,-8000,0,0,-8000,-8000, -8000, -8000]}},
    '35': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000,8000,0,8000,0,8000, 8000, 8000]}},
    '46': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [-8000, -8000, -8000, 0, -8000, 0, -8000, -8000]}},

    '45': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [8000, 8000, 8000, 0, 0, 8000, 8000, 8000]}},

    '56': {'Ramp':{'Init_FF': Readout_FF,
                        'Expt_FF': Expt_FF + [-8000, -8000, 8000, -8000,0,0, -8000, -8000]}},

    '67': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [-8000,-8000,-8000,-8000,-8000, 0, 0, -8000]}},
    '78': {'Ramp': {'Init_FF': Readout_FF,
                    'Expt_FF': Expt_FF + [8000, 8000, 8000, 8000, 8000, 8000, 0, 0]}},

    '68': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000,-8000, 8000, 8000, 0, 8000, 0]}},
    '57': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000, 8000, 8000, 0, 8000, 0, 8000]}},

    '1234': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [0, 0, 0, 0, 8000, 8000, 8000, 8000]}},


    '362': {'Ramp':{'Init_FF': Expt_FF + [-4*_45, 0, 0, -5*_45, -3*_45, 0, 10000, 10000],
                       'Expt_FF': Expt_FF + [0,0,0,0,0,0, 10000, 10000]}},

    '6Q': {'Ramp':{'Init_FF': Expt_FF + [0, -3600, -1800, 0, 0, -5400, 10000, 10000],
                       'Expt_FF': Expt_FF + [0,0,0,0,0,0, 10000, 10000]}},

    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Expt_FF + [0, -3600, -1800, 0, 0, -5400, -7200, 0],
                       'Expt_FF': Expt_FF}},


    # beamsplitter definitions
    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS':{'BS_FF': [-18685, -19389, 14131, 11543, -12678, -13248, 4768, 2214]}},
    '1234_correlations_double': {'BS':{'BS_FF': [-18782, -19389, 14131, 11543, -12678, -13248, 4768, 2214]}},
    # '1234_correlations_2': {'BS':{'BS_FF': [-18440, -19389, 13904, 11543, -12400, -13248, 17110, 11182]}},


    # (3600.0, 3600.0, 4000.0, 4400.0, 4400.0, 3700.0, 3700.0, 4300.0)
    '1245_correlations': {'BS': {'BS_FF': [-18633, -19389, -41, 19544, 23097, -13444, -9686, 11182]}},
    # '1245_correlations_2': {'BS': {'BS_FF': [-18440, -19389, -41, 19742, 23097, -22139, -16113, 11182]}},

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
    # '5R': {'Qubit': {'Frequency': 3789.3, 'sigma': 0.07, 'Gain': 3876},
    #         'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, 0, +4000, +4000, +4000]},
    '6R': {'Readout': {'Frequency': 7441.1 - BaseConfig['res_LO'], 'Gain': 4000,
            'FF_Gains': Expt_FF + [+4000, +4000, +4000, +4000, +4000, 0, +4000, +4000], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
            'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, 0, +4000, +4000]},
    '7R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, +4000, 0, +4000]},
    '8R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [+4000, +4000, +4000, +4000, +4000, +4000, +4000, 0]},

   # Resonant points but with other FFs in opposite direction. Guess: [0,0,0,0]
    '1R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 1750},
           'Pulse_FF': Expt_FF + [0, -4000, -4000, -4000, -4000, -4000, -4000, -4000]},
    '2R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2000},
           'Pulse_FF': Expt_FF + [-4000, 0, -4000, -4000, -4000, -4000, -4000, -4000]},
    '3R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3150},
           'Pulse_FF': Expt_FF + [-4000, -4000, 0, -4000, -4000, -4000, -4000, -4000]},
    '4R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, 0, -4000, -4000, -4000, -4000]},
    '5R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
            'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, 0, -4000, -4000, -4000]},
    # '5R-': {'Qubit': {'Frequency': 3789.3, 'sigma': 0.07, 'Gain': 3876},
    #         'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, 0, -4000, -4000, -4000]},
    '6R-': {'Readout': {'Frequency': 7441.1 - BaseConfig['res_LO'], 'Gain': 4000,
            'FF_Gains': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, -4000, -4000], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
            'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, 0, -4000, -4000]},
    '7R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, -4000, 0, -4000]},
    '8R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + [-4000, -4000, -4000, -4000, -4000, -4000, -4000, 0]},

}

Ramp_state = '8Q_4815'
# Ramp_state = '12'

Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']


beamsplitter_point = '1234_correlations'
# beamsplitter_point = '1234_correlations_double'
# beamsplitter_point = '1245_correlations'
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

