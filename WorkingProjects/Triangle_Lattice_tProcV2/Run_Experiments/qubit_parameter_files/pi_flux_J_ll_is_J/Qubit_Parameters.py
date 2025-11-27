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
from .BS_Mux8_4578_Readout_Josh import BS4578_Readout_Josh

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([-9229, -9844, -7224, -9723, -8466, -8893, -6046, -7816])

#disordered
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


drive_params = {
    # Resonant points. +- 4000 FF gain ~ 100 MHz


    '1_4Q_readout': {'Readout': {'Frequency': 7121.5, 'Gain': 885,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3937.4, 'sigma': 0.03, 'Gain': 5156},
                     'Pulse_FF': Readout_1234_FF},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.4, 'Gain': 1228,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4186.8, 'sigma': 0.03, 'Gain': 6344},
                     'Pulse_FF': Readout_1234_FF},
    '8_4Q_readout': {'Readout': {'Frequency': 7309.5, 'Gain': 885,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4028.4, 'sigma': 0.03, 'Gain': 6877},
                     'Pulse_FF': Readout_1234_FF},
    '5_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3829.4, 'sigma': 0.03, 'Gain': 12660},
                     'Pulse_FF': Readout_1234_FF},
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
                 'Expt_FF':Expt_FF.add(Q2=125, Q4=125, Q6=125, Q8=125)},},
    '2345_dis': {'Ramp': {'Init_FF': Init_4815_FF,
                 'Expt_FF':Expt_FF.add(Q2=125, Q4=250, Q6=125)}},

    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},

    '8Q_4815_lowest_state': {'Ramp':{'Init_FF': Init_4815_FF_lowest,
                             'Expt_FF': Expt_FF}},


    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations_old': {'BS': {'BS_FF': [-18506, -19389, 13734, 11543, -12458, -13248, 5164, 2214]}},

    # (3600.0, 3600.0, 4200.0, 4200.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS': {'BS_FF': [-18526, -19389, 8323, 6543, -12467, -13248, 5141, 2214]},
                          't_offset': np.array([21, 24, 13, 24, 8, 8, 9, 0]) # default values
                                                -[2,2,2,2,2,0,0,0] # 56 offset correction
                                                -[1,1,1,1,1,1,1,0] # 78 offset correction
                                                -[1,0,1,0,0,0,1,0], # so that double jump gives 0 instead of 2pi},
                          },


    '1234_correlations_double': {'BS': {'BS_FF': [-18587, -19389, 13881, 11543, -12337, -13248, 6544, 2214]}},
    # '1234_correlations_double': {'BS': {'BS_FF': [-18169, -19389, 13769, 11543, 12501, 13248, 13769, 13769]}},
    '1234_intermediate': {'IJ':{'samples':[4, 0, 1, 0, 0, 0, 1, 0],
                                'gains':[-15530, None, -9058, None, None, None, -5000, None]}},
                                #'gains':[-14300, None, 1000, None, -20347, None, -2370, None]}},




    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4200.0, 4200.0, 3522.7)
    '2345_correlations': {'BS': {'BS_FF': [-26873, 13458, 13421, -17041, -15217, 8332, 10782, -24395]},
                          't_offset': np.array([22, 24, 13, 24, 8, 8, 9, 0])
                                                - [0,0,0,0,0,0,0,0] # correct 4-5
                                                + [1,1,0,0,0,0,0,0] # correct 2-3
                                      - [0, 1, 0, 0, 0, 1, 0, 0],  # so that double jump gives 0 instead of 2pi}
                          },

    '2345_correlations_double': {'BS': {'BS_FF': [-26873, 13458, 13421, -17064, -15217, 9000, 10782, -24395]}},

    '2345_intermediate': {'IJ':{'samples':[0, 1, 0, 0, 0, 2, 0, 0],
                                'gains':[None, -5220, None, None, None, -4130, None, None]}},

    '2345_correlations_67_check': {'BS': {'BS_FF': [-26873, 13399, 13421, -17240, -15217, 1757, 4782, -24395]}},

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4000.0, 4000.0, 3522.7)
    # '2345_correlations': {'BS': {'BS_FF': [-26873, 12831, 13421, -17006, -15217, -1195, 1383, -24395]}},

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 3950.0, 3950.0, 3522.7)
    # '2345_correlations': {'BS': {'BS_FF': [-26873, 12831, 13421, -17006, -15217, -3268, -590, -24395]}},

    # (4400.0, 4400.0, 3496.5, 4000.0, 4000.0, 3534.5, 3460.3, 3522.7)
    '1245_correlations': {'BS': {'BS_FF': [22268, 21904, -25392, -2473, -1488, -28060, -25722, -24395]},
                                 't_offset': np.array([22, 24, 13, 24, 8, 8, 9, 0])},

    # (4350.0, 4350.0, 3457.4, 3499.9, 3495.6, 4250.0, 4250.0, 3503.2)
    '1267_correlations': {'BS': {'BS_FF': [19890, 20033, -25392, -27560, -25700, 14165, 16575, -24395]}},


    # (3535.3, 4380.0, 4380.0, 3540.1, 4000.0, 4000.0, 3460.3, 3522.7)
    '2356_correlations': {'BS': {'BS_FF': [-26873, 17380, 21495, -27560, -1325, -1233, -25722, -24395]}},

    '2378_correlations': {'BS': {'BS_FF': [-26873, 17112, 21495, -27560, -25722, -24395, 10170, 5000]}},




    # (3535.3, 3527.2, 4380.0, 4380.0, 3534.4, 4000.0, 4000.0, 3522.7)
    '3467_correlations': {'BS': {'BS_FF': [-26873, -29001, 21187, 16460, -25700, -410, 1383, -24395]}},

    # (3535.3, 4200.0, 4200.0, 3900.0, 3900.0, 4200.0, 3600.0, 3600.0)
    '4578_correlations_Josh': {'BS':{'BS_FF': [-26873, 7050, 7799, -6188, -5192, 8140, -13491, -16604]}},

    # (4415.2, 4424.4, 4389.6, 4000.0, 4000.0, 4392.0, 3600.0, 3600.0)
    '4578_correlations': {'BS': {'BS_FF': [26873, 29001, 25392, -2609, -1488, 28060, -13600, -16604]}},

    'single_jump':{'IJ':{'samples':[None]*8,'gains':[None]*8}},

}



# readout_params = BS1234_Readout
# readout_params = BS2345_Readout
readout_params = BS1245_Readout
# readout_params = BS1267_Readout
# readout_params = BS2356_Readout
# readout_params = BS2378_Readout
# readout_params = BS3467_Readout
# readout_params = BS4578_Readout

# readout_params = BS2345_Readout


Ramp_state = '8Q_4815'
# Ramp_state = '8Q_4815_lowest_state'

# Ramp_state = '2345_dis'

# beamsplitter_point = '2345_correlations_double'
# beamsplitter_point = '1234_correlations_double'
# beamsplitter_point = '2356_correlations_double'
# beamsplitter_point = '4578_correlations'
# beamsplitter_point = '2345_correlations'
# beamsplitter_point = '2345_correlations'
# beamsplitter_point = '1254_correlations'
# beamsplitter_point = '1267_correlations'
# beamsplitter_point = '2356_correlations'
# beamsplitter_point = '2378_correlations'
# beamsplitter_point = '4578_correlations'
beamsplitter_point = '1245_correlations'

ijump_point = 'single_jump'

Qps = Qps | readout_params | drive_params | ramp_params
Qubit_Parameters = Qps.d

# print(Qubit_Parameters)





Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']

# Ramp_FF[5] = -9089

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



