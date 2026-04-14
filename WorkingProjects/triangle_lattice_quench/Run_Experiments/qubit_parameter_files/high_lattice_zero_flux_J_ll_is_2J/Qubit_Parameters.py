import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains, QubitParams
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


from .BS_Mux8_1234_Readout import BS1234_Readout, Readout_1234_FF
from .BS_Mux8_1245_Readout import BS1245_Readout, Readout_1245_FF
from .BS_Mux8_1267_Readout import BS1267_Readout
from .BS_Mux8_2356_Readout import BS2356_Readout, Readout_2356_FF
from .BS_Mux8_2345_Readout import BS2345_Readout, Readout_2345_FF
from .BS_Mux8_2378_Readout import BS2378_Readout
from .BS_Mux8_3467_Readout import BS3467_Readout
from .BS_Mux8_4578_Readout import BS4578_Readout

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([13726, 14558, 16621, 13851, -10953, 17963, 21803, 11552])

# for measuring rung coupling
# Expt_FF = FF_gains([-8743, -9474, -6144, -8506, -7411, -7689, -5644, -8428])

# for measuring leg coupling
# Expt_FF = FF_gains([-8405, -8973, -5677, -8042, -6933, -6550, -5242, -8127])

ff_4150={f'Q{i+1}':FF for i, FF in enumerate([5752, 6120, 8238, 5998, -18501, 8446, 9679, 5227])}
# Start of ramp, after pulse
# set to below ramp point at 3850
holes = ['Q2', 'Q3', 'Q6', 'Q7']
set_kwargs = {f'Q{i+1}': Expt_FF[i] for i in range(8)}
for hole in holes:
    set_kwargs[hole] = ff_4150[hole] #-= 12000

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

# resonance = 3800
resonance = 4295

Qps = QubitParams()

ramsey_detuning = -8000

Qps.add_pulse('1R', resonance, 3823, 0.03, ff_array = Expt_FF.subsys(1, det=ramsey_detuning))
Qps.add_pulse('2R', resonance, 2336, 0.03, ff_array = Expt_FF.subsys(2, det=ramsey_detuning))
Qps.add_pulse('3R', resonance, 4507,0.03, ff_array = Expt_FF.subsys(3, det=ramsey_detuning))
Qps.add_pulse('4R', resonance, 2526, 0.03, ff_array = Expt_FF.subsys(4, det=ramsey_detuning))
Qps.add_pulse('5R', resonance, 2470, 0.03, ff_array = Expt_FF.subsys(5, det=ramsey_detuning))
Qps.add_pulse('6R', resonance, 3110, 0.03, ff_array = Expt_FF.subsys(6, det=ramsey_detuning))
Qps.add_pulse('7R', resonance, 2524, 0.03, ff_array = Expt_FF.subsys(7, det=ramsey_detuning))
Qps.add_pulse('8R', resonance, 4765, 0.03, ff_array = Expt_FF.subsys(8, det=ramsey_detuning))
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

Qps.add_pulse('5AC', 4150, 7690, 0.03, ff_array = FF_gains([-4000]*8).set(Q5=Expt_FF))
Readout_4Q = [1453, -3601, -1229, 5079, -9634, -2100, -146, 8141]
# (4190.0, 4000.0, 4000.0, 4240.0, 4329.1, 4000.0, 4000.0, 4280.0)
drive_params = {
    '1_4Q_readout': {'Readout': {'Frequency': 7121.0, 'Gain': 666,
                  'FF_Gains': Readout_4Q, 'Readout_Time': 3.3, 'ADC_Offset': 0.7},
                'Qubit': {'Frequency': 4058.4, 'sigma': 0.02, 'Gain': 6500},
                'Pulse_FF': Readout_4Q},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.1, 'Gain': 1000,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.3, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 4136.8, 'sigma': 0.02, 'Gain': 6792},
          'Pulse_FF': Readout_4Q},
    '8_4Q_readout': {'Readout': {'Frequency': 7308.6, 'Gain': 1000,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.8, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 4232.1, 'sigma': 0.02, 'Gain': 5900},
          'Pulse_FF': Readout_4Q},
    '5_4Q_readout': {'Readout': {'Frequency': 7362.85, 'Gain': 1033,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.8, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 4304.7, 'sigma': 0.02, 'Gain': 4658},
          'Pulse_FF': Readout_4Q},
}

q2_det = -12000
ramp_params = {
    '12': {'Ramp':{'Init_FF': Expt_FF + [0,-5000, q2_det, q2_det, q2_det, q2_det, q2_det, q2_det],
                    'Expt_FF': Expt_FF + [0,0, q2_det, q2_det, q2_det, q2_det, q2_det, q2_det]}},

    '23': {'Ramp':{'Init_FF': Expt_FF + [q2_det, 0,-5000, q2_det, q2_det, q2_det, q2_det, q2_det],
                    'Expt_FF': Expt_FF + [q2_det, 0,0, q2_det, q2_det, q2_det, q2_det, q2_det]}},

    '34': {'Ramp':{'Init_FF': Expt_FF + [q2_det,q2_det,0,-5000,q2_det,q2_det, q2_det, q2_det],
                        'Expt_FF': Expt_FF + [q2_det,q2_det,0,0,q2_det,q2_det, q2_det, q2_det]}},
    '35': {'Ramp':{'Init_FF': Expt_FF + [q2_det,q2_det,0,q2_det,-5000, q2_det, q2_det, q2_det],
                        'Expt_FF': Expt_FF + [q2_det,q2_det,0,q2_det,0,q2_det, q2_det, q2_det]}},
    '46': {'Ramp': {'Init_FF': Expt_FF + [q2_det,q2_det,q2_det,0, q2_det, -5000, q2_det, q2_det],
                    'Expt_FF': Expt_FF + [q2_det, q2_det, q2_det, 0, q2_det, 0, q2_det, q2_det]}},

    '45': {'Ramp': {'Init_FF': Expt_FF + [q2_det, q2_det, q2_det, 0, -5000, q2_det, q2_det, q2_det],
                    'Expt_FF': Expt_FF + [q2_det, q2_det, q2_det, 0, 0, q2_det, q2_det, q2_det]}},

    '56': {'Ramp':{'Init_FF': Expt_FF + [q2_det, q2_det, q2_det, q2_det,0,-5000, q2_det, q2_det],
                        'Expt_FF': Expt_FF + [q2_det, q2_det, q2_det, q2_det,0,0, q2_det, q2_det]}},

    '67': {'Ramp':{'Init_FF': Expt_FF + [q2_det,q2_det,q2_det,q2_det,q2_det, 0, -5000, q2_det],
                        'Expt_FF': Expt_FF + [q2_det,q2_det,q2_det,q2_det,q2_det, 0, 0, q2_det]}},
    '78': {'Ramp': {'Init_FF': Expt_FF + [q2_det, q2_det, q2_det, q2_det, q2_det, q2_det, 0, -5000],
                    'Expt_FF': Expt_FF + [q2_det, q2_det, q2_det, q2_det, q2_det, q2_det, 0, 0]}},



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

    '1234_dis10': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=400, Q4=-400, Q6=400, Q8=400)},},
    '2345_dis10': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=-800, Q4=-800, Q6=-800, Q8=-800)}},

    '2345_dis10_lowest': {'Ramp': {'Init_FF': Init_4815_FF_lowest,
                 'Expt_FF':Expt_FF.add(Q2=-400, Q4=-400, Q6=-400, Q8=-400)}},

    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},

    '8Q_4815_lowest': {'Ramp':{'Init_FF': Init_4815_FF_lowest,
                             'Expt_FF': Expt_FF}},

    '1234_dis10_lowest': {'Ramp': {'Init_FF': Init_4815_FF_lowest,
                     'Expt_FF':Expt_FF.add(Q2=400, Q4=-400, Q6=-400, Q8=400)},},
}


bs_params = {
    '1234_correlations': {'BS': {'BS_FF': [ -4750,  -5138, -16164, -20574,  -7500,  22806,   3319,   -705]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),

                          'ij_samples':[0, 1, 1, 0, 0, 0, 1, 0],
                          'ij_gains':[ 4703,  -1500,  -2300, -2652, -8723, 20700, 3000,  5664],
                          'pad_bs': [1, 0, 0, 1, 0, 0, 0, 1],
                          'exact_t_bs': [84, 84, 87, 87, 60, 60, 65, 65]
                          },

    '1234_bonds': {'BS': {'BS_FF': [ -4795,  -5050, -16164, -20504,  -7459,  22990,   3328,   -705]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                          'ij_samples':[2, 0, 2, 0, 0, 2, 0, 2],
                          'ij_gains': [12633, 15452, 8700, 15271, -9948, -9980, 24700, 19000],
                          'pad_bs' : [0, 2, 0, 2, 2, 0, 2, 0],
                          },

    '1245_correlations': {'BS': {'BS_FF': [-21108, -22074,   -618,  16628,  -7497, -28060, -25722, -24395]},
                                 't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                                 'ij_samples':[0, 1, 0, 0, 0, 0, 0, 0],
                                 'ij_gains':[-3398, -7500,  8883, 15479, -8723, -4119,  -511, -6181],
                                 'pad_bs':   [1, 0, 0, 0, 0, 0, 0, 0],
                                 'exact_t_bs': [58,58,82,82,82,82,82,82]},


    '1267_correlations': {'BS': {'BS_FF':[-12849, -13620,  25392,  27560,      0, -16644, -13249,  24395]},
         't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                'ij_samples': [0, 1, 0, 0, 0, 0, 1, 0],
                'ij_gains': [  700,   -5000, 21888, 21415, -4974,  -9000,  0, 18214],
                'pad_bs':   [1, 0, 0, 0, 0, 1, 0, 0],
                'exact_t_bs': [67,67,67,67,67,67,67,67]
                          },


    '2345_correlations': {'BS': {'BS_FF': [-26873,  -5153,  -2519,  16699,  -7497, -11657,  -9187,  24395]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                          'ij_samples':[0, 0, 1, 0, 0, 0, 1, 0],
                          'ij_gains':[-6299,  8900,  800, 15479, -8723,  -379,  1000, 18214],
                          'pad_bs' :   [0, 1, 0, 0, 0, 1, 0, 0],
                          'exact_t_bs': [64, 64, 64, 79, 79, 65, 65, 65],
                          },


    '2345_bonds': {'BS': {'BS_FF': [-26873,  -5208,  -2734,  16100,  -8410, -11740,  -9187,  24395]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                          'ij_samples':        [0, 2, 0, 2, 0, 0, 2, 0],
                          'ij_gains': [14276, 13500, 18385, -8600, -9948, 19823, 16600, 12034],
                          'pad_bs' :  [2, 0, 2, 0, 2, 2, 0, 2],
                          # 'exact_t_bs': [65, 58, 58, 55, 55, 65, 65, 65],
                          },


    '2356_correlations': {'BS': {'BS_FF': [ 26873, -22210, -16339,  -3838,  -7497,  22745, -25722, -24395]},
                              't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                              'ij_samples':        [0, 0, 1, 0, 0, 0, 0, 0],
                              'ij_gains':[20574, -3311,  -1500,  5716, -8723, 20700,  -511, -6181],
                              'pad_bs':            [0, 1, 0, 0, 0, 0, 0, 0],
                             'exact_t_bs':[59, 59, 59, 73, 73, 73, 73, 73]
                              },


    '2378_correlations': {'BS': {'BS_FF': [ 26873,  -9357,  -6205,  27560,      0,  28060,  -8303, -11351]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                            'ij_samples': [0, 0, 1, 0, 0, 0, 1, 0],
                            'ij_gains': [20574,  3084,  6750, 21415, -4974, 23941,  -1480,   341],
                            'pad_bs': [0, 1, 0, 0, 0, 0, 0, 1],
                            'exact_t_bs':[61, 61, 61, 61, 62, 62, 62, 62]
                        },


    '3467_correlations': {'BS': {'BS_FF': [ 26873,  29001, -16157, -20612,      0,  -1094,    370,  24395]},
                         't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                          'ij_samples': [0, 0, 1, 0, 0, 0, 1, 0],
                          'ij_gains': [20574, 22226,  -1600, -2652, -4974,  16000, 8000, 18214],
                          'pad_bs':     [0, 0, 0, 1, 0, 1, 0, 0],
                          'exact_t_bs':[54, 54, 54, 54, 66, 66, 66, 66]
                          },



    '4578_correlations': {'BS':{'BS_FF': [-26873, -29001,  -1576,  16706,  -7497,  -2529, -15050, -18332]},
                          't_offset': np.array([16, 18,  6, 18,  5,  7,  7,  0]),
                          'ij_samples': [0, 0, 0, 0, 0, 0, 1, 0],
                          'ij_gains': [-6299, -6775,  8404, 15479, -8723,  8647,  -7400, -3149],
                          'pad_bs': [0, 0, 0, 0, 0, 0, 0, 1],
                          'exact_t_bs':[80, 80, 80, 80, 73, 73, 73, 73]
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

readout_params = BS1234_Readout


Ramp_state = '8Q_4815'
# Ramp_state = '8Q_4815_lowest_state'

# Ramp_state = '2345_dis'
# Ramp_state ='23'

beamsplitter_point = '1234_correlations'

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
# for label, gain in zip(labels, gains):
#     print(label, gain[3])


if __name__ == '__main__':
    gains = np.array([Readout_1234_FF, Expt_FF, BS_FF])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()



