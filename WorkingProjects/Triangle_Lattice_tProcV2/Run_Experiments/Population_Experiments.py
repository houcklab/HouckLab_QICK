# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import FFvsRamsey
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mT1vsFF import FFvsT1
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX, ROTimingOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX

import numpy as np



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.1, 'Gain': 4500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4398.7, 'sigma': 0.03, 'Gain': 6000},
          'Pulse_FF': [21750, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.85, 'Gain': 5000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 4406.4, 'sigma': 0.03, 'Gain':4900},
          'Pulse_FF': [0, 23307, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.0, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.75, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 3468.35, 'sigma': 0.03, 'Gain': 9500},
          'Pulse_FF': [    0,     0, -20313,     0,     0,     0,     0,     0]},

    '4': {'Readout': {'Frequency': 7568.7, 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 4421.152, 'sigma': 0.03, 'Gain': 6750},
          'Pulse_FF': [    0,     0,     0, 22048,     0,     0,     0,     0]},
}

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0



Qubit_Readout = [3]
Qubit_Pulse   = [3]



RunT1_TLS = False
T1TLS_params = {"FF_gain_start": 21000, "FF_gain_stop": 23000, "FF_gain_steps": 11,
                "stop_delay_us": 250, "expts": 40, "reps": 150,
                'qubitIndex': Qubit_Pulse[0]}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 4, 'reps': 100,
                         'start': 1, 'step': 16, 'expts': 71,
                         'gainStart': -4400,
                         'gainStop': -3200, 'gainNumPoints': 11, 'relax_delay': 100}
Oscillation_Gain_QICK_sweep = True

Oscillation_Single = False # uses same dict as gain sweep

Calib_FF_vs_drive_delay = True
ff_drive_delay_dict = {'start':200, 'step':8, 'expts': 200, # delay of FF, units of samples
                       'qubit_delay_cycles': 80,
                       'reps': 4000,
                        'qubit_index': Qubit_Pulse[0],}


SingleShot_2Qubit = False
SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400}


SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
                'second_qubit_freq': 3809.3, 'second_qubit_gain': 1140}

# This ends the working section of the file.
#----------------------------------------
# Not used
FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0
exec(open("UPDATE_CONFIG.py").read())
#--------------------------------------------------
# This begins the booleans
soc.reset_gens()

exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if Oscillation_Gain:
    if not Oscillation_Gain_QICK_sweep:
        GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    else:
        # raise AssertionError('this sweep not working yet.')
        print("Testing arbitrary waveform sweep")
        # GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              # cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=False)
        GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if Oscillation_Single:
    QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
                          cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

# TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
#                           cfg=config | {'reps': 5,
#                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if RunT1_TLS:
    FFvsT1(path="FFvsT1", outerFolder=outerFolder,
                    cfg=config | T1TLS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)


if SingleShot_2Qubit:
    SingleShot_2QFFMUX(path="SingleShot_2Qubit", outerFolder=outerFolder,
                           cfg=config | SS_2Q_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

if Calib_FF_vs_drive_delay:
    CalibrateFFvsDriveTiming(path="FF_drive_timing", outerFolder=outerFolder,
                           cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)
# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)

