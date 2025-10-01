from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsRamsey import FFvsRamsey
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsRamseyCompPulse import \
    CompFFvsRamsey
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFRampVsRamsey import \
    RampFFvsRamsey
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


from qubit_parameter_files.Qubit_Parameters_Master import *


for Q in [1,2,3,4,5,6,7,8]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [f'{Q}R']

    Run_FF_v_Ramsey = True
    Run_CompFF_v_Ramsey = False

    FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 1,
                                       "expts": 71, "reps": 200,
                                       "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                       "FF_gain_start": Expt_FF[int(str(Qubit_Readout[0])[0]) - 1] - 160,
                                       "FF_gain_stop": Expt_FF[int(str(Qubit_Readout[0])[0]) - 1] + 160,
                                       "FF_gain_steps": 8,
                                       "relax_delay": 100, 'populations': False,  # "qubit_drive_freq":3950.0
                                       }

    # PulseFF will become like FFExpts in this experiment. Ramp_initial_gains works as usual
    Run_RampFF_v_Ramsey = False
    FF_Ramp_params = {"ramp_duration": 1000,
                      "FFPrev": pulse_4815,
                      "FFInit": Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
                      }

    exec(open("UPDATE_CONFIG.py").read())
    if FF_sweep_Ramsey_relevant_params['populations']:
        exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

    if Run_FF_v_Ramsey:
        FFvsRamsey(path="FF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
    if Run_CompFF_v_Ramsey:
        print('running comp FF')
        CompFFvsRamsey(path="CompFF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
    if Run_RampFF_v_Ramsey:
        print('running ramp FF')
        RampFFvsRamsey(path="RampFF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params | FF_Ramp_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

plt.show()