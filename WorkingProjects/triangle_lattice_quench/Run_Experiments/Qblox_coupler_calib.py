# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.Readout_Crosstalk_Population import \
    ReadoutCrosstalkPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2EMUX import T2EMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mChiShift import ChiShift
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeSNR_TWPAPumpParams import \
    SNROpt_wSingleShot
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import RamseyVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsGain import SpecVsGain
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mTransmissionVsPower_MUX import \
    TransmissionVsPower
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Second_Excited_State_Experiments.mSpecSliceMulti import \
    QubitSpecSlice2nd
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mT1vsFF import T1vsFF

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from qubit_parameter_files.Qubit_Parameters_Master import *

voltage_arrs = []
# voltage_arrs.append(np.array([-0.5012, -0.8405, -0.4166, -0.82  , -0.3967, -0.7136, -0.4481,
       # -0.5398, -0.1534, -0.2156, -0.2286, -0.2122, -0.2113, -0.0392]))
# voltage_arrs.append
voltages = np.array([-0.4742, -0.8758, -0.4238, -0.8392, -0.4304, -0.7192, -0.512 ,
       -0.4966, -1.6512, -1.7301, -1.6729, -1.7928, -1.6343, -1.5154])

from WorkingProjects.Triangle_Lattice_tProcV2.Flux_Files.QbloxVoltageSet_function import spi_rack, set_voltages

for Q in [1,2,3,4,5,6]:
    # voltages = voltage_arrs[Q-1]
    set_voltages(voltages)
    # spi_rack.close()
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    Run2ToneSpec = False
    Spec_relevant_params = {
                          "qubit_gain": 500, "SpecSpan": 200, "SpecNumPoints": 141,
                          #   "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                          #    "qubit_gain": 100, "SpecSpan": 150, "SpecNumPoints": 4*71,
                          #   "qubit_gain": 199, "SpecSpan": 50, "SpecNumPoints": 71,
                            # "qubit_gain": 10, "SpecSpan": 10, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.03, "Gauss_gain": Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Gain'],
                            'reps': 2*155, 'rounds': 1}


    Run_Spec_v_Qblox = True
    center_voltage = voltages[Q+8-1]
    Spec_v_Qblox_params = {"Qblox_start": center_voltage-1.6, "Qblox_stop": center_voltage+1.6, "Qblox_steps": 51, "DAC": Q+8}


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


    if Run2ToneSpec:
        QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                            soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)


    if Run_Spec_v_Qblox:
        SpecVsQblox(path="SpecVsQblox", cfg=config | Spec_relevant_params | Spec_v_Qblox_params,
                                 soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)


    # import matplotlib.pyplot as plt
    # while True:
    #     plt.pause(50)
print(config)
set_voltages(voltages)
plt.show()