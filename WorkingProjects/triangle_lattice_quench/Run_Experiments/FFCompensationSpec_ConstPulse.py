# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
import datetime
import time

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mFFSpecCalibration_MUX import \
    FFSpecCalibrationMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Debugging_Programs.mFFSpecCalibration_MUX_CONST_PULSE import \
    FFSpecCalCONST
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *



# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
import numpy as np

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 542,
                      'FF_Gains': [-21498, 0, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3892.8, 'sigma': 0.05, 'Gain': 3019},
          'Pulse_FF': [-21498, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.5, 'Gain': 885,
                      'FF_Gains': [0, -23200, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3893.7, 'sigma': 0.05, 'Gain': 2994},
          'Pulse_FF': [0, -23200, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.8, 'Gain': 1228,
                      'FF_Gains': [0, 0, -19298, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3881.1, 'sigma': 0.05, 'Gain': 7301},
          'Pulse_FF': [0, 0, -19298, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 885,
                      'FF_Gains': [0, 0, 0, -22048, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3913.2, 'sigma': 0.05, 'Gain': 4404},
          'Pulse_FF': [0, 0, 0, -22048, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7363.4, 'Gain': 1400,
                      'FF_Gains': [0, 0, 0, 0, -20560, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3871.5, 'sigma': 0.05, 'Gain': 4270},
          'Pulse_FF': [0, 0, 0, 0, -20560, 0, 0, 0]},
    '6': {'Readout': {'Frequency': 7441.6, 'Gain': 1400,
                      'FF_Gains': [0, 0, 0, 0, 0, -22448, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3875.9, 'sigma': 0.05, 'Gain': 4649},
          'Pulse_FF': [0, 0, 0, 0, 0, -22448, 0, 0]},
    '7': {'Readout': {'Frequency': 7253.7, 'Gain': 1228,
                      'FF_Gains': [0, 0, 0, 0, 0, 0, -20578, 0], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3812.5, 'sigma': 0.05, 'Gain': 3041},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, -20578, 0]},
    '8': {'Readout': {'Frequency': 7309.1, 'Gain': 1057,
                      'FF_Gains': [0, 0, 0, 0, 0, 0, 0, -19516], 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3858.1, 'sigma': 0.05, 'Gain': 4000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, -19516]},
}




'''Usage: jump from gain_expt to gain_BS. Pulse_FF is not used'''
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

for Q in [1,2,3,4,5,6,7,8]:

    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]
    exec(open("UPDATE_CONFIG.py").read())
    config['FF_Qubits'][str(Q)]['Gain_BS'] = config['FF_Qubits'][str(Q)]['Gain_Readout']

    idataArray = [None] * 8

    idataArray[Q-1] = Compensated_Pulse(config['FF_Qubits'][str(Q)]['Gain_BS'],
                                            config['FF_Qubits'][str(Q)]['Gain_Expt'], Q)
    center_freq = config['qubit_freqs'][0]
    SpecSpan = 125
    FFCal_params = {"SpecStart": center_freq-SpecSpan/2, "SpecEnd":center_freq+SpecSpan/2,
                    "SpecNumPoints": 126,
                    "Gauss_gain": min(32766, 9*Qubit_Parameters[str(Q)]['Qubit']['Gain']),

                    "sigma": 0.00465,
                    # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                    'delay_start': 20, 'delay_step': 6, 'delay_points': 10400,
                    'reps': 200, 'relax_delay':100
                    }

    FFSpecCalCONST(path="FFSpecCONST", cfg=config | FFCal_params,
                       soc=soc, soccfg=soccfg, outerFolder=outerFolder,
                         prefix=f'Q{Q}_CONST').acquire_display_save(plotDisp=True, block=False)

    print(f"Q{Q} finished at", datetime.datetime.fromtimestamp(time.time()).strftime('%A %B %d, %I:%M:%S %p'))
    #
    # Qubit_Readout = [Q]
    # Qubit_Pulse = [Q]
    # exec(open("UPDATE_CONFIG.py").read())
    #
    # idataArray = [None] * 8
    # idataArray[Q-1] = config['FF_Qubits'][str(Q)]['Gain_Pulse'] + sinusoid(1000 *(-1 if Q==4 or Q==5 else 1), 100)
    # config['FF_Qubits'][str(Q)]['Gain_Expt'] = config['FF_Qubits'][str(Q)]['Gain_Pulse']
    # config['FF_Qubits'][str(Q)]['Gain_BS'] = config['FF_Qubits'][str(Q)]['Gain_Pulse']
    #
    # center_freq = config['qubit_freqs'][0]
    # SpecSpan = 125
    # FFCal_params = {"SpecStart": center_freq - SpecSpan / 2, "SpecEnd": center_freq + SpecSpan / 2,
    #                 "SpecNumPoints": 126,
    #                 "Gauss_gain": min(32766, 10 * Qubit_Parameters[str(Q)]['Qubit']['Gain']),
    #
    #                 "sigma": 0.00465,
    #                 # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
    #                 'delay_start': 20, 'delay_step': 0.5, 'delay_points': 120,
    #                 'reps': 800, 'relax_delay': 200,
    #                 'IDataArray': idataArray,
    #                 }
    # #
    # FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
    #                      soc=soc, soccfg=soccfg, outerFolder=outerFolder,
    #                      prefix=f'Q{Q}_sinusoid').acquire()
    # print(f"Q{Q} sinusoid finished at", datetime.datetime.fromtimestamp(time.time()).strftime('%A %B %d, %I:%M:%S %p'))
    #
    # Qubit_Readout = [Q]
    # Qubit_Pulse = [Q]
    # exec(open("UPDATE_CONFIG.py").read())
    #
    # idataArray = [None] * 8
    # # idataArray[Q - 1] = config['FF_Qubits'][str(Q)]['Gain_Pulse'] + sinusoid(1000 * (-1 if Q == 4 else 1), 100)
    # config['FF_Qubits'][str(Q)]['Gain_Expt'] = config['FF_Qubits'][str(Q)]['Gain_Pulse']
    # config['FF_Qubits'][str(Q)]['Gain_BS'] = config['FF_Qubits'][str(Q)]['Gain_Pulse']
    #
    # center_freq = config['qubit_freqs'][0]
    # SpecSpan = 125
    # FFCal_params = {"SpecStart": center_freq - SpecSpan / 2, "SpecEnd": center_freq + SpecSpan / 2,
    #                 "SpecNumPoints": 101,
    #                 "Gauss_gain": min(32766, 9 * Qubit_Parameters[str(Q)]['Qubit']['Gain']),
    #
    #                 "sigma": 0.00465,
    #                 # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
    #                 'delay_start': 0, 'delay_step': 20, 'delay_points': 10,
    #                 'reps': 500, 'relax_delay': 100,
    #                 'IDataArray': idataArray,
    #                 }
    #
    # FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
    #                      soc=soc, soccfg=soccfg, outerFolder=outerFolder,
    #                      prefix=f'Q{Q}_flat').acquire()
    # print(f"Q{Q} flat finished at", datetime.datetime.fromtimestamp(time.time()).strftime('%A %B %d, %I:%M:%S %p'))

# for Q in [1,2,3,4,5,6,7,8]:



plt.show()