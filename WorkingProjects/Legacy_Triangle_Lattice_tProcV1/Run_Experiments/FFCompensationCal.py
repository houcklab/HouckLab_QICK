# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mGainSweepQubitOscillations import GainSweepOscillations
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleQubitOscillations import QubitOscillations
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.MUXInitialize import *

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mChiShiftMUX import ChiShift
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mOptimizeReadoutAndPulse import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Helpers.Compensated_Pulse_Jero import *
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6979.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 12500,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4475, 'sigma': 0.10, 'Gain': 1237},
          'Pulse_FF': [0, 0, 20000, 0]},  # FOURTH index
    '2': {'Readout': {'Frequency': 7095.687 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 0, 2000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4500.6, 'sigma': 0.05, 'Gain': 3360},
          'Pulse_FF': [0, 0, 0, -30000]}, # third index
    }


Qubit_Readout = [1]
Qubit_Pulse = [1]

FF_gain1_init = 0
FF_gain2_init = 0
FF_gain3_init = 20000
FF_gain4_init = 30000

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 20000
FF_gain4_expt = 0
exec(open("UPDATE_CONFIG.py").read())

FFCal_params = {"SpecStart":4360, "SpecEnd":4530, "SpecNumPoints": 171,
                "Gauss_gain": 32000, "sigma": 0.005,
                # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                'delay_start': 0, 'delay_step': 1, 'delay_points': 150,
                'reps': 20, 'rounds': 20,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               None,  #Compensated_Pulse(FF_gain3_expt, FF_gain3_init, 3),
                               Compensated_Pulse(FF_gain4_expt, FF_gain4_init, 2)], 'relax_delay':200}

FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix='Q1_compensated_index2').acquire_display_save(plotDisp=False)

Qubit_Readout = [2]
Qubit_Pulse = [2]
FF_gain1_init = 0  # 8000
FF_gain2_init = 0
FF_gain3_init = -30000
FF_gain4_init = 30000

FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 30000
exec(open("UPDATE_CONFIG.py").read())

FFCal_params = {"SpecStart":4550, "SpecEnd":4720, "SpecNumPoints": 171,
                "Gauss_gain": 32000, "sigma": 0.005,
                # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                'delay_start': 0, 'delay_step': 1, 'delay_points': 150,
                'reps': 20, 'rounds': 20,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               Compensated_Pulse(FF_gain3_expt, FF_gain3_init, 3),
                               None], 'relax_delay':200}
# FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
#                    soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix='Q2_compensated').acquire_display_save(plotDisp=False)


