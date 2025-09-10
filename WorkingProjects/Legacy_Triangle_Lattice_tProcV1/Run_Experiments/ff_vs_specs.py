from WorkingProjects.Triangle_Lattice_tProcV1.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts.mChiShiftMUX import ChiShift
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts.mOptimizeReadoutandPulse_FFMUX import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
# from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
import numpy as np

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.79 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 10900,
                      "FF_Gains": [0, 0, 30000, -30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4300, 'sigma': 0.05, 'Gain': 7950},
          'Pulse_FF': [0, 0, 30000, -30000]},  # FOURTH index
    '2': {'Readout': {'Frequency': 7096.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4050,
                      "FF_Gains": [0, 0, 0, 30000], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4150, 'sigma': 0.05, 'Gain': 3250},
          'Pulse_FF': [0, 0, 0, 30000]},  # third index
}

Qubit_Readout = [1]
Qubit_Pulse = [1]

FF_gain1_init = 0  # 8000
FF_gain2_init = 0
FF_gain3_init = -30000
FF_gain4_init = 30000

FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 30000

Spec_relevant_params = {"qubit_gain": 300, "SpecSpan":500, "SpecNumPoints": 1001,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 950,
                        'reps': 400, 'rounds': 1, 'relax_delay':150}
FF_sweep_spec_relevant_params = {"qubit_FF_index": 4,
                            "FF_gain_start": -30000, "FF_gain_stop": 30000, "FF_gain_steps":31}
exec(open("UPDATE_CONFIG.py").read())
FFvsSpec(path="FF_vs_Spec", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
         prefix="Q1sweep", soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=False)

Qubit_Readout = [2]
Qubit_Pulse = [2]

exec(open("UPDATE_CONFIG.py").read())
Spec_relevant_params = {"qubit_gain": 300, "SpecSpan":850, "SpecNumPoints": 1701,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 950,
                        'reps': 400, 'rounds': 1, 'relax_delay':150}
FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
                            "FF_gain_start": -30000, "FF_gain_stop": 30000, "FF_gain_steps":31}

FFvsSpec(path="FF_vs_Spec", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
         prefix="Q2sweep", soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

