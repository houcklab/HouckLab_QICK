# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2EMUX import T2EMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeSNR_TWPAPumpParams import \
    SNROpt_wSingleShot
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import RamseyVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
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


fig1, axs1 = plt.subplots(2,4,figsize=(14,6),tight_layout=True)
fig1.suptitle("T1 measurements")
plt.show(block=False)
fig2, axs2 = plt.subplots(2,4,figsize=(14,6),tight_layout=True)
fig2.suptitle("T2 measurements")
plt.show(block=False)
iter_axs1 = iter(axs1.flatten())
iter_axs2 = iter(axs2.flatten())

for Q in [1,2,3,4,5,6,7,8]:
# for Q in [3]:
    Qubit_Readout = [Q]
    Qubit_Pulse =   [f"{Q}R"]
    # Qubit_Pulse = [Q]

    t = True
    f = False


    # These T1 and T2R experiments are done at FFPulses!
    RunT1 = True
    RunT2 = True

    T1_params = {"stop_delay_us": 100, "expts": 40, "reps": 150}

    T2R_params = {"stop_delay_us": 5, "expts": 150, "reps": 300,
                  "freq_shift": 0.0, "phase_shift_cycles": 4, "relax_delay":200}



    # This ends the working section of the file.
    #----------------------------------------
    # Not used
    # FF_gain1_BS = 0
    # FF_gain2_BS = 0
    # FF_gain3_BS = 0
    # FF_gain4_BS = 0
    # FF_gain5_BS = 0
    # FF_gain6_BS = 0
    # FF_gain7_BS = 0
    # FF_gain8_BS = 0
    exec(open("UPDATE_CONFIG.py").read())
    #--------------------------------------------------
    # This begins the booleans

    if RunT1:
        T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False, ax=next(iter_axs1))
    fig1.canvas.draw()
    fig1.canvas.flush_events()
    if RunT2:
        T2RMUX(path="T2R", cfg=config | T2R_params,
                  soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True, block=False, ax=next(iter_axs2))
    fig2.canvas.draw()
    fig2.canvas.flush_events()


plt.show()