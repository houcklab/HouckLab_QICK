import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains, QubitParams
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


from .BS_Mux8_1234_Readout import BS1234_Readout, Readout_1234_FF, Readout_4Q
from .BS_Mux8_1245_Readout import BS1245_Readout, Readout_1245_FF
from .BS_Mux8_1267_Readout import BS1267_Readout
from .BS_Mux8_2356_Readout import BS2356_Readout, Readout_2356_FF
from .BS_Mux8_2345_Readout import BS2345_Readout, Readout_2345_FF
from .BS_Mux8_2378_Readout import BS2378_Readout
from .BS_Mux8_3467_Readout import BS3467_Readout
from .BS_Mux8_4578_Readout import BS4578_Readout

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([-9619, -10378, -7896, -10562, -9180, -9710, -6376, -9148])

# disordered
# Expt_FF = Expt_FF.add(Q2=125, Q4=125, Q6=125, Q8=125)
# disordered
# Expt_FF = FF_gains([-8332, -9820, -6088, -8973, -7072, -8393, -5027, -8877])

# manual
# Expt_FF = FF_gains([-8743, -9251, -6203, -8739, -7319, -7785, -5443, -8311])

# Expt_FF = FF_gains([-8743, -9251, -6303, -8639, -7419, -7885, -5443, -8311])

# for measuring rung coupling
# Expt_FF = FF_gains([-8743, -9474, -6144, -8506, -7411, -7689, -5644, -8428])

# for measuring leg coupling
# Expt_FF = FF_gains([-8743, -9474, -6144, -8506, -7411, -7740, -5397, -8231])


# Start of ramp, after pulse
# set to below ramp point at 3850
holes = ['Q2', 'Q3', 'Q6', 'Q7']
set_kwargs = {f'Q{i+1}': Expt_FF[i] for i in range(8)}
for hole in holes:
    set_kwargs[hole] -= 6000

Init_4815_FF = Expt_FF.set(**set_kwargs)

# define ramp with 4 particles starting from below holes
# this prepares the lowest 4 particle state in the single occupation band
# this is the same as the ground state of the Hamiltonian with the opposite sign interactions
# since we simply transform H --> -H
holes = ['Q2', 'Q3', 'Q6', 'Q7']
set_kwargs = {f'Q{i+1}': Expt_FF[i] for i in range(8)}
for hole in holes:
    set_kwargs[hole] += 5000

Init_4815_FF_lowest = Expt_FF.set(**set_kwargs)

# Init_4815_FF = Expt_FF.set(Q2= 8099,
#                       Q3= 8789,
#                       Q6= 9251,
#                       Q7= 11999,)

# Init_4815_FF = Expt_FF - np.array([0, 5000, 5000, 0, 0, 5000, 5000, 0])

resonance = 3800
# resonance = 4320

Qps = QubitParams()

ramsey_detuning = 6000

Qps.add_pulse('1R', resonance, 4032, 0.03, ff_array = Expt_FF.subsys(1, det=ramsey_detuning))
Qps.add_pulse('2R', resonance, 4032, 0.03, ff_array = Expt_FF.subsys(2, det=ramsey_detuning))
Qps.add_pulse('3R', resonance, 13000,0.03, ff_array = Expt_FF.subsys(3, det=ramsey_detuning))
Qps.add_pulse('4R', resonance, 4329, 0.03, ff_array = Expt_FF.subsys(4, det=ramsey_detuning))
Qps.add_pulse('5R', resonance, 7690, 0.03, ff_array = Expt_FF.subsys(5, det=ramsey_detuning))
Qps.add_pulse('6R', resonance, 4179, 0.03, ff_array = Expt_FF.subsys(6, det=ramsey_detuning))
Qps.add_pulse('7R', resonance, 6549, 0.03, ff_array = Expt_FF.subsys(7, det=ramsey_detuning))
Qps.add_pulse('8R', resonance, 4822, 0.03, ff_array = Expt_FF.subsys(8, det=ramsey_detuning))
Qps.add_pulse('1R-', resonance, 4032, 0.03, ff_array = Expt_FF.subsys(1, det=-ramsey_detuning))
Qps.add_pulse('2R-', resonance, 4032, 0.03, ff_array = Expt_FF.subsys(2, det=-ramsey_detuning))
Qps.add_pulse('3R-', resonance, 1300, 0.03, ff_array = Expt_FF.subsys(3, det=-ramsey_detuning))
Qps.add_pulse('4R-', resonance, 4329, 0.03, ff_array = Expt_FF.subsys(4, det=-ramsey_detuning))
Qps.add_pulse('5R-', resonance, 7690, 0.03, ff_array = Expt_FF.subsys(5, det=-ramsey_detuning))
Qps.add_pulse('6R-', resonance, 4179, 0.03, ff_array = Expt_FF.subsys(6, det=-ramsey_detuning))
Qps.add_pulse('7R-', resonance, 6549, 0.03, ff_array = Expt_FF.subsys(7, det=-ramsey_detuning))
Qps.add_pulse('8R-', resonance, 4822, 0.03, ff_array = Expt_FF.subsys(8, det=-ramsey_detuning))

# The purpose of these is to scan for the coupler at low frequencies
scan_center = 3500
Qps.add_pulse('1C', scan_center, 4032, 0.03, ff_array = Expt_FF.subsys(1, det=ramsey_detuning))
Qps.add_pulse('2C', scan_center, 4032, 0.03, ff_array = Expt_FF.subsys(2, det=ramsey_detuning))
Qps.add_pulse('3C', scan_center, 13000,0.03, ff_array = Expt_FF.subsys(3, det=ramsey_detuning))
Qps.add_pulse('4C', scan_center, 4329, 0.03, ff_array = Expt_FF.subsys(4, det=ramsey_detuning))
Qps.add_pulse('5C', scan_center, 7690, 0.03, ff_array = Expt_FF.subsys(5, det=ramsey_detuning))
Qps.add_pulse('6C', scan_center, 4179, 0.03, ff_array = Expt_FF.subsys(6, det=ramsey_detuning))
Qps.add_pulse('7C', scan_center, 6549, 0.03, ff_array = Expt_FF.subsys(7, det=ramsey_detuning))
Qps.add_pulse('8C', scan_center, 4822, 0.03, ff_array = Expt_FF.subsys(8, det=ramsey_detuning))

drive_params = {
    # Resonant points. +- 4000 FF gain ~ 100 MHz


    '1_4Q_readout': {'Readout': {'Frequency': 7121.5, 'Gain': 885,
                          'FF_Gains': Readout_4Q, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3934.3, 'sigma': 0.03, 'Gain': 3249},
                     'Pulse_FF': Readout_4Q},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.4, 'Gain': 1228,
                          'FF_Gains': Readout_4Q, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4188.1, 'sigma': 0.03, 'Gain': 4000},
                     'Pulse_FF': Readout_4Q},
    '8_4Q_readout': {'Readout': {'Frequency': 7309.5, 'Gain': 885,
                          'FF_Gains': Readout_4Q, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3993.3, 'sigma': 0.03, 'Gain': 4186},
                     'Pulse_FF': Readout_4Q},
    '5_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_4Q, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3830.5, 'sigma': 0.03, 'Gain': 8384},
                     'Pulse_FF': Readout_4Q},
}

ramp_params = {
    '12': {'Ramp':{'Init_FF': Expt_FF + [0,-5000, -12000, -12000, -12000, -12000, -12000, -12000],
                    'Expt_FF': Expt_FF + [0,0, -12000, -12000, -12000, -12000, -12000, -12000]}},

    '23': {'Ramp':{'Init_FF': Expt_FF + [-12000, 0,-5000, -12000, -12000, -12000, -12000, -12000],
                    'Expt_FF': Expt_FF + [-12000, 0,0, -12000, -12000, -12000, -12000, -12000]}},

    '34': {'Ramp':{'Init_FF': Expt_FF + [-12000,-12000,0,-5000,-12000,-12000, -15000, -12000],
                        'Expt_FF': Expt_FF + [-12000,-12000,0,0,-12000,-12000, -15000, -12000]}},
    '35': {'Ramp':{'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000,8000,0,8000,0,8000, 8000, 8000]}},
    '46': {'Ramp': {'Init_FF': None,
                    'Expt_FF': Expt_FF + [-8000, -8000, -8000, 0, -8000, 0, -8000, -8000]}},

    '45': {'Ramp': {'Init_FF': Expt_FF + [-12000, -12000, -12000, 0, -5000, -12000, -12000, -12000],
                    'Expt_FF': Expt_FF + [-12000, -12000, -12000, 0, 0, -12000, -12000, -12000]}},

    '56': {'Ramp':{'Init_FF': Expt_FF + [-12000, -12000, -12000, -12000,0,-5000, -12000, -12000],
                        'Expt_FF': Expt_FF + [-8000, -8000, -8000, -8000,0,0, -8000, -8000]}},

    '67': {'Ramp':{'Init_FF': Expt_FF + [-12000,-12000,-12000,-12000,-12000, 0, -5000, -12000],
                        'Expt_FF': Expt_FF + [-12000,-12000,-12000,-12000,-12000, 0, 0, -12000]}},
    '78': {'Ramp': {'Init_FF': Expt_FF + [-12000, -12000, -12000, -12000, -12000, -12000, 0, -5000],
                    'Expt_FF': Expt_FF + [-12000, -12000, -12000, -12000, -12000, -12000, 0, 0]}},



    '68': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000,-8000, 8000, 8000, 0, 8000, 0]}},
    '57': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [8000, 8000, 8000, 8000, 0, 8000, 0, 8000]}},
    # disordered states for larger base contrast
    '12_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(1,2,det=-12000).add(Q2=-5000),
                       'Expt_FF': Expt_FF.subsys(1,2,det=-12000).add(Q2=-125)}},
    '23_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(2,3,det=-12000).add(Q3=-5000),
                       'Expt_FF': Expt_FF.subsys(2,3,det=-12000).add(Q3=-125)}},
    '34_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(3,4,det=-12000).add(Q4=-5000),
                       'Expt_FF': Expt_FF.subsys(3,4,det=-12000).add(Q4=-150)}},
    '45_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(4,5,det=-12000).add(Q5=-5000),
                       'Expt_FF': Expt_FF.subsys(4,5,det=-12000).add(Q5=-125)}},
    '56_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(5,6,det=-12000).add(Q6=-5000),
                       'Expt_FF': Expt_FF.subsys(5,6,det=-12000).add(Q6=-125)}},
    '67_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(6,7,det=-12000).add(Q7=-5000),
                       'Expt_FF': Expt_FF.subsys(6,7,det=-12000).add(Q7=-125)}},
    '78_dis': {'Ramp':{'Init_FF': Expt_FF.subsys(7,8,det=-12000).add(Q8=-5000),
                       'Expt_FF': Expt_FF.subsys(7,8,det=-12000).add(Q8=-125)}},

    '1234': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [0, 0, 0, 0, 8000, 8000, 8000, 8000]}},
    '1234_dis': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=200, Q4=-200, Q6=200, Q8=200)},},
    '2345_dis': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=-200, Q4=-200, Q6=200, Q8=200)}},

    '2345_dis10': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=400, Q4=400, Q6=400, Q8=400)}},

    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},

    '8Q_4815_lowest_state': {'Ramp':{'Init_FF': Init_4815_FF_lowest,
                             'Expt_FF': Expt_FF}},
}

bs_params = {
    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations_old': {'BS': {'BS_FF': [-18506, -19389, 13734, 11543, -12458, -13248, 5164, 2214]}},

    '1234_correlations_34check': {'BS': {'BS_FF': [-18506, -19389, -345, -2185, -15458, -13248, 5164, 2214]}},

    # (3600.0, 3600.0, 4200.0, 4200.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS': {'BS_FF': [-19883, -21113,   6886,   5105, -7300, -8000,   15750,   9000]},
                          't_offset': np.array([22, 24, 13, 24, 13, 14, 14, 6]),

                          'ij_samples':[0, 0, 0, 4, 0, 0, 4, 0],
                          'ij_gains':[None, None, None, 4000, None, None, 17497, None],
                          'pad_bs': [0, 0, 4, 0, 0, 0, 0, 4],
                          'exact_t_bs': [71, 71, 71, 71, 51, 51, 63, 63]
                          },

    # (3600.0, 3600.0, 4200.0, 4200.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_bonds': {'BS': {'BS_FF': [-19883, -21113,   6886,   5105, -7300, -8000,   15750,   9000]},
                          't_offset': np.array([22, 24, 13, 24, 13, 14, 14, 6]),
                          'ij_samples':   [0, 2, 1, 0, 0, 3, 2, 0],
                          'ij_gains': [None, -4500, -15850, None, None, 6200, -2500, None],
                          'pad_bs' : [2, 0, 0, 1, 3, 0, 0, 2],
                          'exact_t_bs': [78, 78, 70, 70, 50, 50, 70, 70], # correct for additions to ij_samples
                          },

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4200.0, 4200.0, 3522.7)
    '2345_correlations': {'BS': {'BS_FF': [-26873, 13413, 13421, -12082, -10450, 7460, 10676, -24395]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples':[0, 2, 0, 0, 0, 0, 1, 0],
                          'ij_gains':[None, 1000, None, None, None, None, 3600, None],
                          'pad_bs' : [0, 0, 2, 0, 0, 1, 0, 0],
                          'exact_t_bs': [65, 58, 58, 55, 55, 65, 65, 65],
                          },

    '2345_correlations_67_check': {'BS': {'BS_FF': [-26873, 13447, 13421, -17693, -15217, 2373, 4782, -24395]}},

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4200.0, 4200.0, 3522.7)
    '2345_bonds': {'BS': {'BS_FF': [-26873, 13540, 13207, -12000, -10500, 7700, 10657, -24395]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples':        [0, 0, 2, 2, 0, 2, 0, 0],
                          'ij_gains': [None, None, 1100, 6400, None, -5400, None, None],
                          'pad_bs' :  np.array([0, 2, 0, 0, 2, 0, 2, 0]), # correct for additions to ij_samples
                          'exact_t_bs': [65, 58, 58, 55, 55, 65, 65, 65],
                          },
    # old: (4400.0, 4400.0, 3496.5, 4000.0, 4000.0, 3534.5, 3460.3, 3522.7)
    # new: [3947.7, 3950. , 4250. , 3598.9, 3600. , 4250. , 4250. , 4250. ]
    '1245_correlations': {'BS': {'BS_FF': [-3415, -3800, 10959, -15798, -14047, 11696, 14450, 8551]},
                                 #[22268, 21904, -25392, -2473, -1488, -28060, -25722, -24395]},
                                 't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4])},

    # (4350.0, 4350.0, 3457.4, 3499.9, 3495.6, 4250.0, 4250.0, 3503.2)
    '1267_correlations': {'BS': {'BS_FF':#[-9757, -10312, 25392, -26783, -23537, -8126, -5572, -22064]},
                                     [ 12402,  13035, -25392, -21560, -22700,  10491,  13904, -22395]},
         't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                'ij_samples': [0, 3, 0, 0, 0, 0, 3, 0],
                'ij_gains': [None, 8859, None, None, None, -2500, 8000, None],
                'pad_bs':   [3, 0, 3, 3, 3, 3, 0, 3],
                'exact_t_bs': [65,65,66,66,66,66,66,66]
                          },

    '1267_correlations_alt': {'BS': {'BS_FF':[-9400, -10312, 25392, -21783, -21537, -5248, -2150, -21064]},
             't_offset': np.array([23, 25, 14, 25, 12, 14, 12, 4]),
                    # 'ij_samples': [0, 3, 0, 0, 0, 3, 0, 0],
                    # 'ij_gains': [None, 9859, None, None, None, 6000, None, None],
                    # 'pad_bs':   [3, 0, 3, 3, 3, 0, 3, 3],
                    'exact_t_bs': [65,65,66,66,66,66,66,66]
                              },

    # (3535.3, 4380.0, 4380.0, 3540.1, 4000.0, 4000.0, 3460.3, 3522.7)
    '2356_correlations_test': {'BS': {'BS_FF': [-26873,  20709,  21173, -27560,  -1922,  -1862, -25722, -24395]},
                          't_offset': np.array([22, 24, 13, 24, 11, 12, 12, 4]),
                          'ij_samples':        [0,   0,  0,  0,   0,  0,  0, 0],
                          'ij_gains':[None, 0, 0, None, -2693, None, None, None],
                          # 'pad_bs':            [3, 3, 0, 3, 0, 0, 3, 3]
                          },
    # Q2 and Q3 at 4200, Q5 and Q6 at 3800 (no jump)
    '2356_correlations': {'BS': {'BS_FF': [-22873,  9920,  10000, -27560,  -9381, -9719, -22722, -24395]},
                              't_offset': np.array([22, 24, 13, 24, 11, 12, 12, 4]),
                              'ij_samples':        [0,   0,  0,  0,   0,  0,  0, 0],
                              # 'ij_gains':[None, 0, 0, None, -2693, None, None, None],
                              # 'pad_bs':            [3, 3, 0, 3, 0, 0, 3, 3]
                             'exact_t_bs':[83, 64, 64, 83, 83, 83, 83, 83]
                              },

    # (3535.3, 4380.0, 4380.0, 3540.1, 3540, 3540.0, 4175, 4175)
    '2378_correlations': {'BS': {'BS_FF': [-21873,  20658,  20898, -19560, -21700, -19060,   9626,   4854]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4])
                                              -[0, 0, 0, 0, 0, 0, 1, 0],
                            'ij_samples': [0, 2, 0, 0, 0, 0, 4, 0],
                            'ij_gains': [None, 7714, None, None, None, None, 5887, None],
                            'pad_bs': [3, 0, 2, 3, 3, 3, 3, 0],
                            'exact_t_bs':[65, 61, 61, 65, 65, 65, 65, 65]
                        },

    # (3535.3, 3527.2, 4380.0, 4380.0, 3534.4, 4000.0, 4000.0, 3522.7)
    '3467_correlations': {'BS': {'BS_FF': [-26873, -29001,  19558,  15644, -25700,  -1393,   1283, -24395]},
                         't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples': [0, 0, 0, 3, 0, 0, 3, 0],
                          'ij_gains': [None, None, None, 19000, None, None, -8500, None],
                          'pad_bs': [3, 3, 3, 0, 3, 3, 0, 3],
                          'exact_t_bs':[69, 69, 63, 63, 69, 69, 69, 69]
                          },


    # (3535.3, 4400.0, 4400.0, 3900.0, 3900.0, 4400.0, 3600.0, 3600.0)
    '4578_correlations': {'BS':{'BS_FF': [-26873,  29001,  25392,  -6800,  -5386,  28060, -13638, -16896]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples': [0, 0, 0, 3, 0, 0, 0, 3],
                          'ij_gains': [None, None, None, -8500, None, None, None, -14400],
                          'pad_bs': [3, 3, 3, 0, 3, 3, 3, 0],
                          'exact_t_bs':[73, 73, 64, 64, 73, 73, 73, 73]
                          },
}





# readout_params = BS1234_Readout
# readout_params = BS2345_Readout
# readout_params = BS1245_Readout
# readout_params = BS1267_Readout
# readout_params = BS2356_Readout
# readout_params = BS2378_Readout
# readout_params = BS3467_Readout
# readout_params = BS4578_Readout

readout_params = BS2345_Readout


Ramp_state = '8Q_4815'
# Ramp_state = '8Q_4815_lowest_state'

# Ramp_state = '2345_dis'
# Ramp_state ='23'

# beamsplitter_point = '4578_correlations'
# beamsplitter_point = '2345_correlations'
# beamsplitter_point = '2345_correlations'
# beamsplitter_point = '1267_correlations'
# beamsplitter_point = '2356_correlations'
# beamsplitter_point = '2378_correlations'
# beamsplitter_point = '4578_correlations'
beamsplitter_point = '2345_correlations'

Qps = Qps | readout_params | drive_params | ramp_params | bs_params
Qubit_Parameters = Qps.d




Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']


BS_FF = Qubit_Parameters[beamsplitter_point]['BS']['BS_FF']
# BS_FF = Readout_1234_FF


print(f'Init_FF: {Init_FF}')
print(f'Ramp_FF: {Ramp_FF}')
print(f'BS_FF: {BS_FF}')

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

Readout_FF = readout_params['1']['Readout']['FF_Gains']
gains = [Readout_FF, Init_FF, Ramp_FF, BS_FF, Readout_FF]
labels = ['pulse', 'init', 'ramp', 'beamsplitter', 'readout']
for label, gain in zip(labels, gains):
    print(label, gain[3])


if __name__ == '__main__':
    gains = np.array([Readout_1234_FF, Expt_FF, BS_FF])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()



