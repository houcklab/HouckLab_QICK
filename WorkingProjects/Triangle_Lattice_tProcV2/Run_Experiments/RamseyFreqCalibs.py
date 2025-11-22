from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import \
    RamseyVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF_CompPulse import \
    RamseyVsFFComp
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF_Ramp import \
    RamseyVsFF_Ramp
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


from qubit_parameter_files.Qubit_Parameters_Master import *

Gain_list = []
for Q in [2]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [f'{Q}R']
    # Expt_FF = Pulse_4815_FF

    Run_FF_v_Ramsey = True
    Run_CompFF_v_Ramsey = False

    FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 1,
                                       "expts": 71, "reps": 200,
                                       "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                       "FF_gain_start": Expt_FF[int(str(Qubit_Readout[0])[0]) - 1] - 200,
                                       "FF_gain_stop": Expt_FF[int(str(Qubit_Readout[0])[0]) - 1] + 200,
                                       "FF_gain_steps":11,
                                       "relax_delay": 100, 'populations': False,  # "qubit_drive_freq":3950.0
                                       }

    # PulseFF will become like FFExpts in this experiment. Ramp_initial_gains works as usual
    Run_RampFF_v_Ramsey = False
    # FF_Ramp_params = {"ramp_duration": 1000,
    #                   "FFPrev": pulse_4815,
    #                   "FFInit": Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
    #                   }

    exec(open("UPDATE_CONFIG.py").read())
    if FF_sweep_Ramsey_relevant_params['populations']:
        exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

    if Run_FF_v_Ramsey:
        data = RamseyVsFF(path="FF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
        Gain_list.append(data['data'].get('center_gain'))
    if Run_CompFF_v_Ramsey:
        print('running comp FF')
        RamseyVsFFComp(path="CompFF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)
    if Run_RampFF_v_Ramsey:
        print('running ramp FF')
        RamseyVsFF_Ramp(path="RampFF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params | FF_Ramp_params,
                   soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=False)

print([int(np.round(g)) if g is not None else g for g in Gain_list])
plt.show()