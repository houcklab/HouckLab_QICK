import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains, QubitParams
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1234_Readout import BS1234_Readout, Readout_1234_FF
from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.pi_flux_J_ll_is_2J.BS_Mux8_1254_Readout import BS1254_Readout, Readout_1254_FF

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([-9393, -10106, -7679, -10215, -8995, -9453, -6350, -8690])

# manual
Expt_FF = FF_gains([-9293, -10106, -7779, -10215, -8995, -9553, -6450, -8500])

Expt_FF_SS = FF_gains([13494, 14223, 14061, 11965, 12183, 15452, 20913, 11826])

# manual
Expt_FF_SS = FF_gains([13594, 14423, 13961, 12065, 12183, 15352, 20713, 11926])
# Expt_FF = Expt_FF_SS


# Readout_1234_FF = FF_gains([-8464, -27262, 9303, -5379, -16232, 16903, 584, -12960])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)

Pulse_4815_FF = FF_gains([2203, -14469, -11500, 5860, -9207, -13800, -10102, 2901])
# (4100.0, 3700.0, 3700.0, 4200.0, 3800.0, 3700.0, 3700.0, 4125.0)

Pulse_4815_FFB = FF_gains([2203, -14469, -11500, 3883, 13298, -13800, -10102, 6879])
# (4100.0, 4220.0, 4220.0, 4160, 4320.0, 4220.0, 4220.0, 4220)

# Start of ramp, after pulse
# set to 100 MHz below ramp point at 4320
holes = ['Q2', 'Q3', 'Q6', 'Q7']
holes = ['Q2', 'Q3', 'Q5', 'Q7']
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



# BS1234_Readout = {
#     '1': {'Readout': {'Frequency': 7121.1, 'Gain': 705,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3827.9, 'sigma': 0.03, 'Gain': 6151},
#           'Pulse_FF': Readout_1234_FF},
#     '2': {'Readout': {'Frequency': 7076.9, 'Gain': 1120,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3526.9, 'sigma': 0.03, 'Gain': 4031},
#           'Pulse_FF': Readout_1234_FF},
#     '3': {'Readout': {'Frequency': 7511.1, 'Gain': 845,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4237.7, 'sigma': 0.03, 'Gain': 12500},
#           'Pulse_FF': Readout_1234_FF},
#     '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1229,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3922.2, 'sigma': 0.03, 'Gain': 6532},
#           'Pulse_FF': Readout_1234_FF},
#     '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1120,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3633.3, 'sigma': 0.03, 'Gain': 7508},
#           'Pulse_FF': Readout_1234_FF},
#     '6': {'Readout': {'Frequency': 7441.8, 'Gain': 1120,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 4335.9, 'sigma': 0.03, 'Gain': 6165},
#           'Pulse_FF': Readout_1234_FF},
#     '7': {'Readout': {'Frequency': 7253.8, 'Gain': 845,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3983.0, 'sigma': 0.03, 'Gain': 7119},
#           'Pulse_FF': Readout_1234_FF},
#     '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1120,
#                       'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
#           'Qubit': {'Frequency': 3684.2, 'sigma': 0.03, 'Gain': 5559},
#           'Pulse_FF': Readout_1234_FF},
# }

drive_params = {
    # Resonant points. +- 4000 FF gain ~ 100 MHz

    # far away
    '1_4Q': {'Qubit': {'Frequency': 4099.5, 'sigma': 0.03, 'Gain': 6505},
                   'Pulse_FF': Pulse_4815_FF},
    '4_4Q': {'Qubit': {'Frequency': 4203, 'sigma': 0.03, 'Gain': 6530},
                   'Pulse_FF': Pulse_4815_FF},
    '5_4Q': {'Qubit': {'Frequency': 3801.8, 'sigma': 0.03, 'Gain': 8800},
                   'Pulse_FF': Pulse_4815_FF},
    '8_4Q': {'Qubit': {'Frequency': 4126.6, 'sigma': 0.03, 'Gain': 6698},
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
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4277.4, 'sigma': 0.03, 'Gain': 7955},
              'Pulse_FF': Readout_1254_FF},
    '4_4Q_readout': {'Readout': {'Frequency': 7568.4, 'Gain': 1228,
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 3867.9, 'sigma': 0.03, 'Gain': 10251},
              'Pulse_FF': Readout_1254_FF},
    '8_4Q_readout': {'Readout': {'Frequency': 7309.5, 'Gain': 885,
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4209.7, 'sigma': 0.03, 'Gain': 6006},
              'Pulse_FF': Readout_1254_FF},
    '5_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 3815.0, 'sigma': 0.03, 'Gain': 8833},
              'Pulse_FF': Readout_1254_FF},
    '6_4Q_readout': {'Readout': {'Frequency': 7364.1, 'Gain': 1400,
                          'FF_Gains': Readout_1254_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 3972.4, 'sigma': 0.03, 'Gain': 5500},
              'Pulse_FF': Readout_1254_FF},
}

ramp_params = {
    'no_ramp_4815': {'Ramp':{'Init_FF': None,
                    'Expt_FF': Pulse_4815_FF}},
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



    '8Q_1854': {'Ramp':{'Init_FF': None,
                       'Expt_FF': Expt_FF}},

    '8Q_4815': {'Ramp':{'Init_FF': Init_4815_FF,
                       'Expt_FF': Expt_FF}},


    # (3600.0, 3600.0, 4300.0, 4300.0, 3700.0, 3700.0, 4100.0, 4100.0)
    '1234_correlations': {'BS':{'BS_FF': [-18632, -19389, 13456, 11543, -12943, -13248, 5866, 2214]}},


    # (4020.0, 4020.0, 4380.0, 4245.0, 4245.0, 4095.0, 4095.0, 4418.0)
    # '1254_correlations': {'BS':{'BS_FF': [-752, -908, 25392, 8588, 9011, 3333, 5709, 24395]}},

    # (4200.0, 4200.0, 4389.6, 3900.0, 3900.0, 4100.0, 4100.0, 4423.3)
    '1254_correlations': {'BS':{'BS_FF': [6755, 7050, 25392, -6200, -5192, 3382, 5657, 24395]}},





}



# readout_params = BS1234_Readout
readout_params = BS1254_Readout


Qps = Qps | readout_params | drive_params | ramp_params
Qubit_Parameters = Qps.d

# print(Qubit_Parameters)

Ramp_state = '8Q_4815'
# Ramp_state = '12'

# beamsplitter_point = '1234_correlations'
beamsplitter_point = '1254_correlations'

Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']


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
    gains = np.array([Readout_1234_FF, Expt_FF, BS_FF])
    for i in range(gains.shape[1]):
        plt.plot(gains[:,i], label=f'Q{i+1}')
    plt.xlabel('experimental section index')
    plt.ylabel('gain')
    plt.legend()
    plt.show()

