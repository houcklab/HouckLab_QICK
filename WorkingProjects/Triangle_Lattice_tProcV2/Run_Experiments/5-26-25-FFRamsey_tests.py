# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mFFSpecCalibration_MUX import FFSpecCalibrationMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mGainSweepQubitOscillations import GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mSingleQubitOscillations import QubitOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mChiShiftMUX import ChiShift
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mOptimizeReadoutAndPulse import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Jero import Compensated_Pulse
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.79 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 10900,
                      "FF_Gains": [0, 0, 30000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4300, 'sigma': 0.05, 'Gain': 7950},
          'Pulse_FF': [0, 0, 30000, -30000]},  # FOURTH index
    '2': {'Readout': {'Frequency': 7095.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 0, -18000, 30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4150, 'sigma': 0.05, 'Gain': 3250},
          'Pulse_FF': [0, 0, 0, 30000]},  # third index
}


# Qubit_Readout = [1]
# Qubit_Pulse = [1]
#
# FF_gain1_init = 0
# FF_gain2_init = 0
# FF_gain3_init = 20000
# FF_gain4_init = 30000
#
# FF_gain1_expt = 0
# FF_gain2_expt = 0
# FF_gain3_expt = 20000
# FF_gain4_expt = 0
# exec(open("UPDATE_CONFIG.py").read())
#
# CalibrationFF_params = {'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
#                         "start": 0, "step": 1, "expts": 20 * 16 * 1,
#                         "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
#                 'IDataArray': [None,
#                                None,
#                                None,
#                                # sinusoid(2000, 50, 256)
#                                None, #Compensated_Step(FF_gain4_expt, FF_gain4_init, 1)
#                                ]}

# FFSpecCalibrationMUX(path="FFSpecCalibration", cfg=config | FFCal_params,
#                    soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix='Q1_compensated').acquire_display_save(plotDisp=True)

Qubit_Readout = [2]
Qubit_Pulse = [2]

FF_gain1_init = 0  # 8000
FF_gain2_init = 0
FF_gain3_init = 0
FF_gain4_init = 30000

FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = -15000
FF_gain4_expt = 30000
exec(open("UPDATE_CONFIG.py").read())

RunCalibrationFF = True
RamseyCal_cfg = {'FFQubitIndex': 3,
                        "start": 0, "step": 1, "expts": 20 * 16 * 1,
                        "reps": 100, "rounds": 20, "relax_delay": 100, "YPulseAngle": 90,
                'IDataArray': [None,
                               None, #Compensated_Pulse(FF_gain2_expt, FF_gain2_init, 2),
                               None, #Compensated_Step(FF_gain3_expt, FF_gain3_init, 2),
                               None]}
if RunCalibrationFF:
    RamseyCal_cfg['FFlength'] = int(np.ceil(CalibrationFF_params['expts'] / 16)) * 16

    print(config["FF_Qubits"])
    config = config | RamseyCal_cfg | RamseyCal_cfg

    config['IDataArray'] = [None, None, None, None]
    # config['IDataArray'] = [-15000 * Compensated_AWG((20) * 16, Qubit1_parameters)[1], None, None, None]
    # config['IDataArray'][2] = None
    config['IDataArray'] = [None if Idata==None else Idata[:config['FFlength']] for Idata in config['IDataArray']]
    print("config['IDataArray']:", config['IDataArray'])

    # RAveragerProgram
    print('0 degrees: ')
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    soc.reset_gens()

    config["SecondPulseAngle"] = config["YPulseAngle"]
    print(f'{config["SecondPulseAngle"]} degrees: ')
    iRamsCal = RamseyFFCalR(path="RamseyFFCalR", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRamsCal = RamseyFFCalR.acquire(iRamsCal)
    RamseyFFCalR.display(iRamsCal, dRamsCal, plotDisp=False, figNum=2)
    RamseyFFCalR.save_data(iRamsCal, dRamsCal)