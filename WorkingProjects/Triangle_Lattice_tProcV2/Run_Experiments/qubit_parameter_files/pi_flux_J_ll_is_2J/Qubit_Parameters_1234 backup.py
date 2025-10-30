import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains, QubitParams
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

# 8Q Pi Flux parameters

# (3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0, 3800.0)
Expt_FF = FF_gains([-9276, -9864, -7285, -9788, -8530, -8946, -6069, -7323])


Readout_1234_FF = FF_gains([-8464, -27262, 9303, -5379, -16232, 16903, 584, -12960])
# (3830.0, 3530.0, 4230.0, 3930.0, 3630.0, 4330.0, 3980.0, 3680.0)

Pulse_4815_FF = FF_gains([2203, -14469, -11500, 5860, -9207, -13800, -10102, 2901])
# (4100.0, 3700.0, 3700.0, 4200.0, 3800.0, 3700.0, 3700.0, 4125.0)

# Start of ramp, after pulse
Init_4815_FF = Expt_FF.set(Q2= Pulse_4815_FF,
                      Q3= Pulse_4815_FF,
                      Q6= Pulse_4815_FF,
                      Q7= Pulse_4815_FF,)

resonance = 3800

Qps = QubitParams()

Qps.add_pulse('1R', resonance, 1750, 0.07, ff_array = Expt_FF.subsys(1))
Qps.add_pulse('2R', resonance, 2000, 0.07, ff_array = Expt_FF.subsys(2))
Qps.add_pulse('3R', resonance, 3150, 0.07, ff_array = Expt_FF.subsys(3))
Qps.add_pulse('4R', resonance, 2500, 0.07, ff_array = Expt_FF.subsys(4))
Qps.add_pulse('5R', resonance, 3100, 0.07, ff_array = Expt_FF.subsys(5))
Qps.add_pulse('6R', resonance, 2200, 0.07, ff_array = Expt_FF.subsys(6))
Qps.add_pulse('7R', resonance, 3100, 0.07, ff_array = Expt_FF.subsys(7))
Qps.add_pulse('8R', resonance, 2500, 0.07, ff_array = Expt_FF.subsys(8))
Qps.add_pulse('1R-', resonance, 1750, 0.07, ff_array = Expt_FF.subsys(1, det=-4000))
Qps.add_pulse('2R-', resonance, 2000, 0.07, ff_array = Expt_FF.subsys(2, det=-4000))
Qps.add_pulse('3R-', resonance, 3150, 0.07, ff_array = Expt_FF.subsys(3, det=-4000))
Qps.add_pulse('4R-', resonance, 2500, 0.07, ff_array = Expt_FF.subsys(4, det=-4000))
Qps.add_pulse('5R-', resonance, 3100, 0.07, ff_array = Expt_FF.subsys(5, det=-4000))
Qps.add_pulse('6R-', resonance, 2200, 0.07, ff_array = Expt_FF.subsys(6, det=-4000))
Qps.add_pulse('7R-', resonance, 3100, 0.07, ff_array = Expt_FF.subsys(7, det=-4000))
Qps.add_pulse('8R-', resonance, 2500, 0.07, ff_array = Expt_FF.subsys(8, det=-4000))



BS1234_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 705,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3827.9, 'sigma': 0.03, 'Gain': 6151},
          'Pulse_FF': Readout_1234_FF},
    '2': {'Readout': {'Frequency': 7076.9, 'Gain': 1120,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3526.9, 'sigma': 0.03, 'Gain': 4031},
          'Pulse_FF': Readout_1234_FF},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 845,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4237.7, 'sigma': 0.03, 'Gain': 12500},
          'Pulse_FF': Readout_1234_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1229,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3922.2, 'sigma': 0.03, 'Gain': 6532},
          'Pulse_FF': Readout_1234_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1120,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3633.3, 'sigma': 0.03, 'Gain': 7508},
          'Pulse_FF': Readout_1234_FF},
    '6': {'Readout': {'Frequency': 7441.8, 'Gain': 1120,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4335.9, 'sigma': 0.03, 'Gain': 6165},
          'Pulse_FF': Readout_1234_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 845,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3983.0, 'sigma': 0.03, 'Gain': 7119},
          'Pulse_FF': Readout_1234_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1120,
                      'FF_Gains': Readout_1234_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3684.2, 'sigma': 0.03, 'Gain': 5559},
          'Pulse_FF': Readout_1234_FF},
}

Drive_params = {
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
          'Qubit': {'Frequency': 4099.9, 'sigma': 0.03, 'Gain': 7682},
          'Pulse_FF': Pulse_4815_FF},
    '4_4815': {'Readout': {'Frequency': 7568.6, 'Gain': 1400,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4202.8, 'sigma': 0.03, 'Gain': 6455},
          'Pulse_FF': Pulse_4815_FF},
    '8_4815': {'Readout': {'Frequency': 7309.1, 'Gain': 1400,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4126.3, 'sigma': 0.03, 'Gain': 6490},
          'Pulse_FF': Pulse_4815_FF},
    '5_4815': {'Readout': {'Frequency': 7362.6, 'Gain': 1057,
                      'FF_Gains': Pulse_4815_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3801.1, 'sigma': 0.03, 'Gain': 9380},
          'Pulse_FF': Pulse_4815_FF},
}



readout_params = BS1234_Readout


Qps = Qps | readout_params | Drive_params
Qubit_Parameters = Qps.d

# print(Qubit_Parameters)

Ramp_state = '8Q_4815'


Init_FF = Init_4815_FF
Ramp_FF = Expt_FF

print("Init_FF:", Init_FF)


BS_FF = Expt_FF

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

