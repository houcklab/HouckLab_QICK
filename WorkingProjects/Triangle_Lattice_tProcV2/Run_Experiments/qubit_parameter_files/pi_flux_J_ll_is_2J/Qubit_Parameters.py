import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains, QubitParams
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1234_Readout import BS1234_Readout, Readout_1234_FF
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1254_Readout import BS1254_Readout, Readout_1254_FF
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1267_Readout import \
    BS1267_Readout
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_2356_Readout import BS2356_Readout, Readout_2356_FF
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_2345_Readout import BS2345_Readout, Readout_2345_FF
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_2378_Readout import \
    BS2378_Readout
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_3467_Readout import \
    BS3467_Readout
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_4578_Readout import \
    BS4578_Readout
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_4578_Readout_Josh import \
    BS4578_Readout_Josh

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([-9386, -10105, -7663, -10219, -8999, -9451, -6356, -9128])


# nosiy
# Expt_FF = FF_gains([-9886, -9605, -8163, -9719, -9499, -8951, -6856, -8628])


Expt_FF_SS = FF_gains([13494, 14223, 14061, 11965, 12183, 15452, 20913, 11826])

# manual
Expt_FF_SS = FF_gains([13594, 14423, 13961, 12065, 12183, 15352, 20713, 11926])
# Expt_FF = Expt_FF_SS


# Readout_1234_FF = FF_gains([-8464, -27262, 9303, -5379, -16232, 16903, 584, -12960])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)

Pulse_4815_FF = FF_gains([2203, -14469, -11500, 5860, -9207, -13800, -10102, 2901])
# (4100.0, 3700.0, 3700.0, 4200.0, 3800.0, 3700.0, 3700.0, 4125.0)

# (3960.0, 3527.2, 3496.5, 4120.0, 3850.0, 3534.5, 3460.3, 4010.0)
Pulse_4815_FF = FF_gains([-3456, -29001, -25392, 2152, -7038, -28060, -25722, -1281])

Pulse_4815_FF = FF_gains([-3456, -29001, -25392, 5500, -7038, -28060, -25722, -1281])



Pulse_4815_FFB = FF_gains([2203, -14469, -11500, 3883, 13298, -13800, -10102, 6879])
# (4100.0, 4220.0, 4220.0, 4160, 4320.0, 4220.0, 4220.0, 4220)

# Start of ramp, after pulse
# set to below ramp point at 4320
holes = ['Q2', 'Q3', 'Q6', 'Q7']
set_kwargs = {f'Q{i+1}': Expt_FF[i] for i in range(8)}
for hole in holes:
    set_kwargs[hole] -= 6000

Init_4815_FF = Expt_FF.set(**set_kwargs)

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

    # far away
    '1_4Q': {
        'Qubit': {'Frequency': 3956.1, 'sigma': 0.03, 'Gain': 5060},        'Pulse_FF': Pulse_4815_FF},
    '4_4Q': {
        'Qubit': {'Frequency': 4201.3, 'sigma': 0.03, 'Gain': 6159},
        'Pulse_FF': Pulse_4815_FF},
    '5_4Q': {
        'Qubit': {'Frequency': 3855.9, 'sigma': 0.03, 'Gain': 11757},
        'Pulse_FF': Pulse_4815_FF},
    '8_4Q': {
        'Qubit': {'Frequency': 4017.9, 'sigma': 0.03, 'Gain': 5301},
        'Pulse_FF': Pulse_4815_FF},

    '2_4Q': {'Qubit': {'Frequency': 3700, 'sigma': 0.03, 'Gain': 6505},
                   'Pulse_FF': Pulse_4815_FF.subsys(2)},
    '3_4Q': {'Qubit': {'Frequency': 3700, 'sigma': 0.03, 'Gain': 6530},
                   'Pulse_FF': Pulse_4815_FF.subsys(3)},
    '6_4Q': {'Qubit': {'Frequency': 3700, 'sigma': 0.03, 'Gain': 8800},
                   'Pulse_FF': Pulse_4815_FF.subsys(6)},
    '7_4Q': {'Qubit': {'Frequency': 3700, 'sigma': 0.03, 'Gain': 6698},
                 'Pulse_FF': Pulse_4815_FF.subsys(7)},

    '1_4815': {'Readout': {'Frequency': 7121.5, 'Gain': 885,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
               'Qubit': {'Frequency': 4097.9, 'sigma': 0.03, 'Gain': 7348},
               'Pulse_FF': Pulse_4815_FF},
    '4_4815': {'Readout': {'Frequency': 7568.6, 'Gain': 1400,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
               'Qubit': {'Frequency': 4207.8, 'sigma': 0.03, 'Gain': 6787},
               'Pulse_FF': Pulse_4815_FF},
    '8_4815': {'Readout': {'Frequency': 7309.1, 'Gain': 1400,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
               'Qubit': {'Frequency': 4129.3, 'sigma': 0.03, 'Gain': 6156},
               'Pulse_FF': Pulse_4815_FF},
    '5_4815': {'Readout': {'Frequency': 7368.6, 'Gain': 1057,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
               'Qubit': {'Frequency': 3802.1, 'sigma': 0.03, 'Gain': 9713},
               'Pulse_FF': Pulse_4815_FF},

    '1_4QB': {'Readout': {'Frequency': 7121.5, 'Gain': 885,
                          'FF_Gains': Pulse_4815_FFB, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4098.9, 'sigma': 0.03, 'Gain': 7000},
              'Pulse_FF': Pulse_4815_FFB},
    '4_4QB': {'Readout': {'Frequency': 7568.4, 'Gain': 1228,
                          'FF_Gains': Pulse_4815_FFB, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4160.6, 'sigma': 0.03, 'Gain': 7154},
              'Pulse_FF': Pulse_4815_FFB},
    '8_4QB': {'Readout': {'Frequency': 7309.5, 'Gain': 885,
                          'FF_Gains': Pulse_4815_FFB, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4223.9, 'sigma': 0.03, 'Gain': 5768},
              'Pulse_FF': Pulse_4815_FFB},
    '5_4QB': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Pulse_4815_FFB, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4332.0, 'sigma': 0.03, 'Gain': 9000},
              'Pulse_FF': Pulse_4815_FFB},

    '1_4Q_readout': {'Readout': {'Frequency': 7121.5, 'Gain': 885,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3941.0, 'sigma': 0.03, 'Gain': 5263},
                     'Pulse_FF': Readout_1234_FF},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.4, 'Gain': 1228,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4194.6, 'sigma': 0.03, 'Gain': 6248},
                     'Pulse_FF': Readout_1234_FF},
    '8_4Q_readout': {'Readout': {'Frequency': 7309.5, 'Gain': 885,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4005.0, 'sigma': 0.03, 'Gain': 5562},                     'Pulse_FF': Readout_1234_FF},
    '5_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
                     'Qubit': {'Frequency': 3829.0, 'sigma': 0.03, 'Gain': 12997},
                     'Pulse_FF': Readout_1234_FF},
    '6_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              # 'Qubit': {'Frequency': 3970.4, 'sigma': 0.03, 'Gain': 4833},
                'Qubit': {'Frequency': 3973.4, 'sigma': 0.03, 'Gain': 5833},
                'Pulse_FF': Readout_1254_FF},

    '2_4Q_readout': {'Readout': {'Frequency': 7077.8, 'Gain': 885,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4126.6, 'sigma': 0.03, 'Gain': 6114},
                     'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '3_4Q_readout': {'Readout': {'Frequency': 7511.4, 'Gain': 885,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4360.9, 'sigma': 0.03, 'Gain': 7768},
                     'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '7_4Q_readout': {'Readout': {'Frequency': 7253.8, 'Gain': 700,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
                     'Qubit': {'Frequency': 4058.8, 'sigma': 0.03, 'Gain': 9876},
                     'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
}

ramp_params = {
    'no_ramp_4815': {'Ramp':{'Init_FF': None,
                    'Expt_FF': Pulse_4815_FF}},
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

    '1234': {'Ramp': {'Init_FF': None,
                        'Expt_FF': Expt_FF + [0, 0, 0, 0, 8000, 8000, 8000, 8000]}},



    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},


    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS': {'BS_FF': [-18235, -19389, 13810, 11543, -12502, -13248, 6392, 2214]}},

    '1234_correlations_double': {'BS': {'BS_FF': [-18169, -19389, 13769, 11543, -12501, -13248, 6380, 2214]}},
    # '1234_correlations_double': {'BS': {'BS_FF': [-18169, -19389, 13769, 11543, 12501, 13248, 13769, 13769]}},

    # (4020.0, 4020.0, 4380.0, 4245.0, 4245.0, 4095.0, 4095.0, 4418.0)
    # '1254_correlations': {'BS':{'BS_FF': [-752, -908, 25392, 8588, 9011, 3333, 5709, 24395]}},


    '1254_correlations_45_res': {'BS': {'BS_FF': [6755, 7050, 25392,  -10244, -8995, 3382, 5657, 24395]}},






    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4200.0, 4200.0, 3522.7)
    '2345_correlations': {'BS': {'BS_FF': [-26873, 13378, 13421, -17245, -15217, 7885, 10782, -24395]}},

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 4000.0, 4000.0, 3522.7)
    # '2345_correlations': {'BS': {'BS_FF': [-26873, 12831, 13421, -17006, -15217, -1195, 1383, -24395]}},

    # (3535.3, 4300.0, 4300.0, 3650.0, 3650.0, 3950.0, 3950.0, 3522.7)
    # '2345_correlations': {'BS': {'BS_FF': [-26873, 12831, 13421, -17006, -15217, -3268, -590, -24395]}},

    # (4400.0, 4400.0, 3496.5, 4000.0, 4000.0, 3534.5, 3460.3, 3522.7)
    '1254_correlations': {'BS': {'BS_FF': [22293, 21904, -25392, -2668, -1488, -28060, -25722, -24395]}},


    '1267_correlations': {'BS': {'BS_FF': [22665, 21904, -25392, -28060, -25722, -2245, 500, -24395]}},

    # (3535.3, 4380.0, 4380.0, 3540.1, 4000.0, 4000.0, 3460.3, 3522.7)
    '2356_correlations': {'BS': {'BS_FF': [-26873, 20755, 21495, -27560, -1370, -1233, -25722, -24395]}},
    '2378_correlations': {'BS': {'BS_FF': [-26873, 20610, 21495, -27560, -25722, -24395, 10069, 5000]}},




    # (3535.3, 3527.2, 4380.0, 4380.0, 3534.4, 4000.0, 4000.0, 3522.7)
    '3467_correlations': {'BS': {'BS_FF': [-26873, -29001, 21495, 16460, -25700, -1123, 1383, -24395]}},

    # (3535.3, 4200.0, 4200.0, 3900.0, 3900.0, 4200.0, 3600.0, 3600.0)
    '4578_correlations_Josh': {'BS':{'BS_FF': [-26873, 7050, 7799, -6188, -5192, 8140, -13491, -16604]}},

    # (4415.2, 4424.4, 4389.6, 4000.0, 4000.0, 4392.0, 3600.0, 3600.0)
    '4578_correlations': {'BS': {'BS_FF': [26873, 29001, 25392, -2530, -1488, 28060, -13418, -16604]}},
}



readout_params = BS1234_Readout
# readout_params = BS2356_Readout
# readout_params = BS2378_Readout
# readout_params = BS3467_Readout
# readout_params = BS4578_Readout

Ramp_state = '8Q_4815'
# Ramp_state = '78'

beamsplitter_point = '1234_correlations_double'
# beamsplitter_point = '4578_correlations'

Qps = Qps | readout_params | drive_params | ramp_params
Qubit_Parameters = Qps.d

# print(Qubit_Parameters)





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

gains = [Readout_1254_FF, Init_FF, Ramp_FF, BS_FF, Readout_1254_FF]
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



