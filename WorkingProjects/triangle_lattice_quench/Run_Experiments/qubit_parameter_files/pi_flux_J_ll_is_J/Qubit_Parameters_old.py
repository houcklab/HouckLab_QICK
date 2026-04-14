import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1234_Readout import BS1278_Readout, Readout_1278FF, BS1254_Readout, Readout_1254FF, BS1234_Readout, Readout_1234FF

# 8Q Pi Flux parameters



# Expt_FF = np.array([-11175, -12314, -9138, -11986, -10533, -11127, -7795, -7165])
# (3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0, 3750.0)

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = np.array([-9276, -9864, -7285, -9788, -8530, -8946, -6069, -7323])

# (4320.0, 4320.0, 4320.0, 4320.0, 4320.0, 4320.0, 4320.0, 4320.0))
Expt_FF_sweet_spot = np.array([13854, 14463, 14777, 12299, 12873, 16038, 21900, 13230])

# manual
Expt_FF_sweet_spot = np.array([13854, 14563, 14677, 12099, 12973, 16138, 22000, 13130])

# Expt_FF = Expt_FF_sweet_spot


# From RampFFvsRamsey with ramp time = 2000
# Expt_FF = np.array([-9231, -9880, -7278, -9681, -8492, -9070, -6088, -7157])

# From RampFFvsRamsey with ramp time = 1000
# Expt_FF = np.array([-9267, -9835, -7243, -9706, -8503, -8968, -6043, -7226])

# for beamsplitter points
# Expt_FF = np.array([-9260, -9712, -7228, -9688, -8477, -8869, -6010, -7171])


_45 = 1800 # FF for 45 MHz
ordering =  [8, 5, 4, 1,  3,  2,  6,  7]
detunings = [3, 2, 1, 0, -1, -2, -3, -4]
pulse_1854 = np.array([x for _,x in sorted(zip(ordering,detunings))]) * _45
print("pulse_1854:", pulse_1854 / _45)
print(Expt_FF + pulse_1854)
# (4100.0, 3600.0, 3600.0, 4280.0, 3850.0, 3550.0, 3600.0, 4150.0)
# pulse_4815 = [2437, -19389, -14955, 10372, -6525, -21935, -13757, 4160]
# (4100.0, 3600.0, 3600.0, 4200.0, 3800.0, 3550.0, 3600.0, 4150.0)
pulse_4815 = [2437, -19389, -14955, 6240, -8477, -21935, -13757, 4160]


resonance_frequency = 3800
# resonance_frequency = 4320


Drive_params = {
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
    '1_4815': {'Qubit': {'Frequency': 4099.5, 'sigma': 0.03, 'Gain': 6505},
                   'Pulse_FF': pulse_4815},
    '4_4815': {'Qubit': {'Frequency': 4203, 'sigma': 0.03, 'Gain': 6530},
                   'Pulse_FF': pulse_4815},
    '5_4815': {'Qubit': {'Frequency': 3801.8, 'sigma': 0.03, 'Gain': 8800},
                   'Pulse_FF': pulse_4815},
    '8_4815': {'Qubit': {'Frequency': 4126.6, 'sigma': 0.03, 'Gain': 6698},
                 'Pulse_FF': pulse_4815},


    '1_4815_readout': {'Readout': {'Frequency': 7121.75, 'Gain': 714,
                                   "FF_Gains": pulse_4815, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4099.0, 'sigma': 0.07, 'Gain': 2600},
                       'Pulse_FF': pulse_4815},
    '4_4815_readout': {'Readout': {'Frequency': 7568.85, 'Gain': 1229,
                                   "FF_Gains": pulse_4815, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4204.1, 'sigma': 0.07, 'Gain': 3000},
                       'Pulse_FF': pulse_4815},
    '5_4815_readout': {'Readout': {'Frequency': 7363.37, 'Gain': 1229,
                                   'FF_Gains': pulse_4815, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
                       'Qubit': {'Frequency': 3801.8, 'sigma': 0.07, 'Gain': 5300},
                       'Pulse_FF': pulse_4815},
    '8_4815_readout': {'Readout': {'Frequency': 7309.3, 'Gain': 1229,
                                   'FF_Gains': pulse_4815, 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
                       'Qubit': {'Frequency': 4126.6, 'sigma': 0.07, 'Gain': 3000},
                       'Pulse_FF': pulse_4815},
}




Ramp_params = {
    'no_ramp_4815': {'Ramp':{'Init_FF': None,
                    'Expt_FF': pulse_4815}},
    '12': {'Ramp':{'Init_FF': Expt_FF + [0,-5000, -12000, -12000, -12000, -12000, -12000, -12000],
                    'Expt_FF': Expt_FF + [0,0, -12000, -12000, -12000, -12000, -12000, -12000]}},
    '34': {'Ramp':{'Init_FF': Expt_FF + [-12000,-12000,0,-5000,-12000,-12000, -15000, -12000],
                        'Expt_FF': Expt_FF + [-12000,-12000,0,0,-12000,-12000, -15000, -12000]}},
    '35': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000,8000,0,8000,0,8000, 8000, 8000]}},
    '46': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [-8000, -8000, -8000, 0, -8000, 0, -8000, -8000]}},

    '45': {'Ramp': {'Init_FF': Expt_FF + [-12000, -12000, -12000, 0, -5000, -12000, -12000, -12000],
                    'Expt_FF': Expt_FF + [-12000, -12000, -12000, 0, 0, -12000, -12000, -12000]}},

    '56': {'Ramp':{'Init_FF': Expt_FF + [-12000, -12000, -12000, -12000,-5000,0, -12000, -12000],
                        'Expt_FF': Expt_FF + [-8000, -8000, -8000, -8000,0,0, -8000, -8000]}},

    '67': {'Ramp':{'Init_FF': Expt_FF + [-12000,-12000,-12000,-12000,-12000, 0, -5000, -12000],
                        'Expt_FF': Expt_FF + [-12000,-12000,-12000,-12000,-12000, 0, 0, -12000]}},
    '78': {'Ramp': {'Init_FF': Expt_FF + [-12000, -12000, -12000, -12000, -12000, -12000, 0, -5000],
                    'Expt_FF': Expt_FF + [-12000, -12000, -12000, -12000, -12000, -12000, 0, 0]}},

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
    '8Q_4815_holes_resonant': {'Ramp':
                {'Init_FF': [Expt_FF[0], -13763, -10472, Expt_FF[3], Expt_FF[4], -12794, -9303, Expt_FF[7]],
                 'Expt_FF': Expt_FF}},

    '8Q_4815_holes_resonant': {'Ramp':
                {'Init_FF': [Expt_FF[0], 8414, 9331, Expt_FF[3], Expt_FF[4], 9873, 12362, Expt_FF[7]],
                 'Expt_FF': Expt_FF}},



    # init 4245
    # (4245.0, 4245.0, 4245.0, 4245.0, 4245.0, 4245.0, 4245.0, 4245.0)
    # '8Q_4815_sweet_spot': {'Ramp':
    #             {'Init_FF': [Expt_FF_sweet_spot[0], 9802, 10677, Expt_FF_sweet_spot[3], Expt_FF_sweet_spot[4], 11380, 14078, Expt_FF_sweet_spot[7]],
    #              'Expt_FF': Expt_FF_sweet_spot}},



    # beamsplitter definitions
    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS':{'BS_FF': [-18610, -19389, 13973, 11543, -12553, -13248, 4781, 2214]}},

    '1234_correlations_double': {'BS':{'BS_FF': [-18686, -19389, 13667, 11543, -12325, -13248, 4424, 2214]}},

    # (3720.0, 3720.0, 3960.0, 3960.0, 3640.0, 3640.0, 3880.0, 3880.0)
    '1234_correlations_close': {'BS':{'BS_FF': [-12609, -13315, -1830, -3721, -14911, -16151, -4350, -5505]}},

    '1278_correlations_+-50':  {'BS':{'BS_FF': [-11136, -11797,  12621,  10312, -17836, -18869,  -3589,  -5243]}},

    '1278_correlations_+-50_12':  {'BS':{'BS_FF': [-11200, -11797,  25392, 27560, -25700, -28060, 25722, 24395]}},

    '1278_correlations_+-100_12':  {'BS':{'BS_FF': [-13114, -13797,  25392, 27560, -25700, -28060, 25722, 24395]}},

    # '1234_correlations_2': {'BS':{'BS_FF': [-18440, -19389, 13904, 11543, -12400, -13248, 17110, 11182]}},


    # (3600.0, 3600.0, 4000.0, 4400.0, 4400.0, 3700.0, 3700.0, 4300.0)
    '1245_correlations': {'BS': {'BS_FF': [-18685, -19389, -41, 19778, 23678, -13444, -9686, 11182]}},
    # (3600.0, 3600.0, 4000.0, 4050.0, 4050.0, 3700.0, 3700.0, 4300.0)
    '1245_correlations_2': {'BS': {'BS_FF': [-18386, -19389, -41, -221, 937, -13248, -9686, 11182]}},

    # (3600.0, 3600.0, 4380.0, 4435.8, 4404.2, 3600.0, 3600.0, 4418.0)
    '1267_correlations': {'BS': {'BS_FF': [-18685, -19389, 25392, 27560, 25700, -18375, -13757, 24395]}},

    # (4095.0, 4095.0, 4245.0, 4245.0, 4020.0, 4020.0, 4170.0, 4170.0)
    '1234_correlations_ss': {'BS':{'BS_FF': [2153, 2336, 10534, 8472, -103, 147, 9361, 5891]}},

    # (4020.0, 4020.0, 4380.0, 4245.0, 4245.0, 4095.0, 4095.0, 4418.0)
    '1254_correlations_ss': {'BS':{'BS_FF': [-919, -908, 25392, 8436, 9011, 3699, 5709, 24395]}},



}



ramsey_point_separation = 8000
ramsey_point_separation_list = -np.diag([ramsey_point_separation]*8) + ramsey_point_separation

Ramsey_params = {
    # Resonant points. Guess: [0,0,0,0]
    '1R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 1750},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[0]},
    '2R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2000},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[1]},
    '3R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3150},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[2]},
    '4R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[3]},
    '5R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
            'Pulse_FF': Expt_FF + ramsey_point_separation_list[4]},
    '6R': {'Readout': {'Frequency': 7441.1, 'Gain': 4000,
            'FF_Gains': Expt_FF + ramsey_point_separation_list[5], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
            'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[5]},
    '7R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[6]},
    '8R': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF + ramsey_point_separation_list[7]},

   # Resonant points but with other FFs in opposite direction. Guess: [0,0,0,0]
    '1R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 1750},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[0]},
    '2R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2000},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[1]},
    '3R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3150},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[2]},
    '4R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[3]},
    '5R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
            'Pulse_FF': Expt_FF - ramsey_point_separation_list[4]},
    '6R-': {'Readout': {'Frequency': 7441.1, 'Gain': 4000,
            'FF_Gains': Expt_FF - ramsey_point_separation_list[5]},
            'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2200},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[5]},
    '7R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 3100},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[6]},
    '8R-': {'Qubit': {'Frequency': resonance_frequency, 'sigma': 0.07, 'Gain': 2500},
           'Pulse_FF': Expt_FF - ramsey_point_separation_list[7]},

}

# pick readout point

readout_params = BS1234_Readout
# readout_params = BS1278_Readout

Qubit_Parameters = readout_params | Drive_params | Ramp_params | Ramsey_params

# Qubit_Parameters = BS1254_Readout | Drive_params | Ramp_params | Ramsey_params


Ramp_state = '8Q_4815'
Ramp_state = '8Q_4815_holes_resonant'
# Ramp_state = '8Q_4815_sweet_spot'
# Ramp_state = '67'

Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']


# beamsplitter_point = '1234_correlations_close'
# beamsplitter_point = '1234_correlations'
beamsplitter_point = '1278_correlations_+-100_12'
beamsplitter_point =  '1234_correlations_ss'
# beamsplitter_point =  '1254_correlations_ss'
# beamsplitter_point = '1245_correlations_2'
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
    gains = np.array([Readout_1234FF, Expt_FF, BS_FF])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()

