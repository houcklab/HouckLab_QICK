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
Expt_FF = FF_gains([-8401, -8973, -5676, -8041, -6931, -7152, -5236, -8095])

# for measuring rung coupling
# Expt_FF = FF_gains([-8743, -9474, -6144, -8506, -7411, -7689, -5644, -8428])

# for measuring leg coupling
# Expt_FF = FF_gains([-8405, -8973, -5677, -8042, -6933, -6550, -5242, -8127])


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


    '1_4Q_readout': {'Readout': {'Frequency': 7121.0, 'Gain': 666,
                  'FF_Gains': Readout_4Q, 'Readout_Time': 3.3, 'ADC_Offset': 0.7},
                'Qubit': {'Frequency': 3700.8, 'sigma': 0.015, 'Gain': 11300},
                'Pulse_FF': Readout_4Q},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.1, 'Gain': 1000,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.3, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 3895.0, 'sigma': 0.015, 'Gain': 12000},
          'Pulse_FF': Readout_4Q},
    '8_4Q_readout': {'Readout': {'Frequency': 7308.6, 'Gain': 1000,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.8, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 3580.1, 'sigma': 0.015, 'Gain': 9000},
          'Pulse_FF': Readout_4Q},
    '5_4Q_readout': {'Readout': {'Frequency': 7362.85, 'Gain': 1033,
                      'FF_Gains': Readout_4Q, 'Readout_Time': 2.8, 'ADC_Offset': 0.7},
          'Qubit': {'Frequency': 3762.1, 'sigma': 0.015, 'Gain': 7567},
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

    '1234_dis10': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=400, Q4=-400, Q6=400, Q8=400)},},
    '2345_dis10': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=-400, Q4=-400, Q6=400, Q8=400)}},

    '2345_dis10_lowest': {'Ramp': {'Init_FF': Init_4815_FF_lowest,
                 'Expt_FF':Expt_FF.add(Q2=-400, Q4=-400, Q6=400, Q8=400)}},

    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},

    '8Q_4815_lowest': {'Ramp':{'Init_FF': Init_4815_FF_lowest,
                             'Expt_FF': Expt_FF}},

    '1234_dis10_lowest': {'Ramp': {'Init_FF': Init_4815_FF_lowest,
                     'Expt_FF':Expt_FF.add(Q2=400, Q4=-400, Q6=-400, Q8=400)},},
}


# For this coupling point, should modify high beamsplitters to not be so high
bs_params = {
    # (3600.0, 3600.0, 4200.0, 4200.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS': {'BS_FF': [-17527, -18538,  13655,  10982, -11095, -11914,   8420,   3859]},
                          't_offset': np.array([22, 24, 13, 24, 13, 14, 14, 6]),

                          'ij_samples':[0, 1, 0, 2, 0, 0, 0, 2],
                          'ij_gains':[None, -12000, None, 7000, None, None, None, 1400],
                          'pad_bs': [1, 0, 2, 0, 0, 0, 2, 0],
                          'exact_t_bs': [84, 84, 87, 87, 60, 60, 65, 65]
                          },

    # (3600.0, 3600.0, 4200.0, 4200.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_bonds': {'BS': {'BS_FF': [-20977, -21888,   7140,   4827, -13470, -14280,   2877,   -780]},
                          't_offset': np.array([22, 24, 13, 24, 13, 14, 14, 6]),
                          'ij_samples':[2, 0, 0, 2, 2, 0, 0, 2],
                          'ij_gains': [-4000, None, None, -16000, 7800, None, None, -18250],
                          'pad_bs' : [0, 2, 2, 0, 0, 2, 2, 2],
                          # 'exact_t_bs': [78, 78, 70, 70, 50, 50, 70, 70], # correct for additions to ij_samples
                          },

    # [3947.7, 3950. , 4250. , 3598.9, 3600. , 4250. , 4250. , 4250. ]
    '1245_correlations': {'BS': {'BS_FF': [ -5141,  -5730,  10392, -17216, -15458,  10060,  10722,  7395]},
                                 #[22268, 21904, -25392, -2473, -1488, -28060, -25722, -24395]},
                                 't_offset': np.array([20, 24, 13, 24, 10, 12, 12, 4]),
                                 # 'exact_t_bs': [76,76,76,75,75,76,76,76]},
                                 'exact_t_bs': [58,58,82,82,82,82,82,82]},

    # (4350.0, 4350.0, 3457.4, 3499.9, 3495.6, 4250.0, 4250.0, 3503.2)
    '1267_correlations': {'BS': {'BS_FF':[  -138,   -516, -25392, -27560, -25700,   7170,   7835, -24395]},
         't_offset': np.array([20, 23, 12, 23, 10, 12, 12, 4]),
                'ij_samples': [1, 0, 0, 0, 0, 0, 1, 0],
                'ij_gains': [-346, None, None, None, None, None, 1200, None],
                'pad_bs':   [0, 1, 0, 0, 0, 1, 0, 0],
                'exact_t_bs': [67,67,67,67,67,67,67,67]
                          },


    '2345_correlations': {'BS': {'BS_FF': [-26873,   -636,   2124, -14730, -13096,   7274,   7908, -24395]},
                          't_offset': np.array([22, 24, 12, 23, 10, 12, 12, 4]),
                          'ij_samples':[0, 0, 1, 1, 0, 0, 1, 0],
                          'ij_gains':[None, None, -1300, -11200, None, None, 1900, None],
                          'pad_bs' : [0, 1, 0, 0, 1, 1, 0, 0],
                          'exact_t_bs': [64, 64, 64, 79, 79, 65, 65, 65],
                          },

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4200.0, 4200.0, 3522.7)
    '2345_bonds': {'BS': {'BS_FF': [-26873,   -598,   2124, -14710, -13115,   7285,   7835, -24395]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples':        [0, 3, 0, 0, 2, 0, 2, 0],
                          'ij_gains': [None, -15400, None, None, -6750, None, -11450, None],
                          'pad_bs' :  np.array([3, 0, 3, 2, 0, 2, 0, 2]), # correct for additions to ij_samples
                          'exact_t_bs': [65, 58, 58, 55, 55, 65, 65, 65],
                          },

    # Q2 and Q3 at 4200, Q5 and Q6 at 3800 (no jump)
    '2356_correlations': {'BS': {'BS_FF': [-26873,   3880,   7140, -27560,  -7100,  -7498, -25722, -24395]},
                              't_offset': np.array([22, 24, 13, 24, 11, 12, 12, 4]),
                              'ij_samples':        [0,   1,  0,  0,   0,  0,  0, 0],
                              'ij_gains':[None, -2000, None, None, None, None, None, None],
                              'pad_bs':            [0, 0, 1, 0, 0, 0, 0, 0],
                             'exact_t_bs':[59, 59, 59, 73, 73, 73, 73, 73]
                              },

    # (3535.3, 4380.0, 4380.0, 3540.1, 3540, 3540.0, 4175, 4175)
    '2378_correlations': {'BS': {'BS_FF': [-26873,   3871,   7140, -27560, -25700, -28060,  -5670,  -8434]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                            'ij_samples': [0, 1, 0, 0, 0, 0, 0, 0],
                            'ij_gains': [None, -2000, None, None, None, None, None, None],
                            'pad_bs': [0, 0, 1, 0, 0, 0, 0, 0],
                            'exact_t_bs':[61, 61, 61, 61, 62, 62, 62, 62]
                        },

    # (3535.3, 3527.2, 4380.0, 4380.0, 3534.4, 4000.0, 4000.0, 3522.7)
    '3467_correlations': {'BS': {'BS_FF': [-26873, -29001,   6891,   4540, -25700,  -7010,  -5206, -24395]},
                         't_offset': np.array([21, 23, 12, 23, 10, 12, 12, 4]),
                          'ij_samples': [0, 0, 0, 1, 0, 0, 0, 0],
                          'ij_gains': [None, None, None, -6000, None, None, None, None],
                          'pad_bs': [0, 0, 1, 0, 0, 0, 0, 0],
                          'exact_t_bs':[54, 54, 54, 54, 66, 66, 66, 66]
                          },


    # (3535.3, 4400.0, 4400.0, 3900.0, 3900.0, 4400.0, 3600.0, 3600.0)
    '4578_correlations': {'BS':{'BS_FF': [-26873,   4316,   7140,  -8077,  -6966,   6944, -14960, -18165]},
                          't_offset': np.array([21, 23, 12, 23, 10, 12, 11, 4]),
                          'ij_samples': [0, 0, 0, 0, 0, 0, 1, 0],
                          'ij_gains': [None, None, None, None, None, None, -10000, None],
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

beamsplitter_point = '1234_bonds'

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



