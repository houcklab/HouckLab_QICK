'''File for streamlined calibration of delay timing'''
import time

from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import FF_gains

# from qubit_parameter_files.Qubit_Parameters_Master import *
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

#Unused
FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0



Readout_FF = FF_gains([+20000]*8)
Lower_SS = [-26873, -29001, -25000, -27160, -25200, -27670, -25722, -25000]
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.2, 'Gain': 1057,
                      'FF_Gains': [-19500, 20000, 20000, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3517.6, 'sigma': 0.03, 'Gain': 4511},
          'Pulse_FF': [-26873, 20000, 20000, 20000, 20000, 20000, 20000, 20000]},
    '2': {'Readout': {'Frequency': 7077.3, 'Gain': 1228,
                      'FF_Gains': [20000, -21500, 20000, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3508.6, 'sigma': 0.03, 'Gain': 5151},
          'Pulse_FF': [20000, -29001, 20000, 20000, 20000, 20000, 20000, 20000]},
    '3': {'Readout': {'Frequency': 7510.2, 'Gain': 1228,
                      'FF_Gains': [20000, 20000, -17500, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3468.1, 'sigma': 0.03, 'Gain': 12099},
          'Pulse_FF': [20000, 20000, -25000, 20000, 20000, 20000, 20000, 20000]},
    '4': {'Readout': {'Frequency': 7567.9, 'Gain': 1400,
                      'FF_Gains': [20000, 20000, 20000, -19600, 20000, 20000, 20000, 20000], 'Readout_Time': 2,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3510.9, 'sigma': 0.03, 'Gain': 6919},
          'Pulse_FF': [20000, 20000, 20000, -27160, 20000, 20000, 20000, 20000]},
    '5': {'Readout': {'Frequency': 7363.0, 'Gain': 1400,
                      'FF_Gains': [20000, 20000, 20000, 20000, -17700, 20000, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3505.2, 'sigma': 0.03, 'Gain': 9751},
          'Pulse_FF': [20000, 20000, 20000, 20000, -25200, 20000, 20000, 20000]},
    '6': {'Readout': {'Frequency': 7441.0, 'Gain': 1057,
                      'FF_Gains': [20000, 20000, 20000, 20000, 20000, -20170, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3507.1, 'sigma': 0.03, 'Gain': 8596},
          'Pulse_FF': [20000, 20000, 20000, 20000, 20000, -27670, 20000, 20000]},
    '7': {'Readout': {'Frequency': 7254.2, 'Gain': 1057,
                      'FF_Gains': [-20000, -20000, -20000, -20000, -20000, -20000, 17500, -20000], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4313.6, 'sigma': 0.03, 'Gain': 5105},
          'Pulse_FF': [-20000, -20000, -20000, -20000, -20000, -20000, 25722, -20000]},
    '8': {'Readout': {'Frequency': 7308.5, 'Gain': 1057,
                      'FF_Gains': [20000, 20000, 20000, 20000, 20000, 20000, 20000, -17500], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3506.9, 'sigma': 0.03, 'Gain': 11389},
          'Pulse_FF': [20000, 20000, 20000, 20000, 20000, 20000, 20000, -25000]},
    # '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1228,
    #                   'FF_Gains': [-20000, 20000, 20000, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3,
    #                   'ADC_Offset': 1},
    #       'Qubit': {'Frequency': 3517.6, 'sigma': 0.03, 'Gain': 5308 * 0.85},
    #       'Pulse_FF': [-26873, 20000, 20000, 20000, 20000, 20000, 20000, 20000]},
}

Qubit_Parameters = {
   '8': {'Readout': {'Frequency': 7309.25, 'Gain': 600,
                          'FF_Gains': [0, 0, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
              'Qubit': {'Frequency': 4404.2, 'sigma': 0.03, 'Gain': 7864*0.85},
              'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 19816]},
}

t = True
f = False

if __name__ == '__main__':
    for Q in [8]:
        Qubit_Readout = [Q]
        Qubit_Pulse = [Q]

        Calib_FF_vs_drive_delay = True
        ff_drive_delay_dict = {'start':300, 'step':8//2, 'expts': 175*2, # delay of FF, units of samples
                               'qubit_delay_cycles': 80,
                               'reps': 2*300, 'relax_delay':250,
                                'qubit_index': Qubit_Pulse[0],
                               'invert':False}

        exec(open("UPDATE_CONFIG.py").read())
        exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
        soc.reset_gens()

        start_time = time.time()
        if Calib_FF_vs_drive_delay:
            CalibrateFFvsDriveTiming(path="FF_drive_timing", outerFolder=outerFolder,
                                   cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)
        elapsed_minutes = (time.time() - start_time)/60
        print(f'{elapsed_minutes:.2f} minutes elapsed for Q{Q}.')
        # import matplotlib.pyplot as plt
        # while True:
        #     plt.pause(50)

    plt.show()

