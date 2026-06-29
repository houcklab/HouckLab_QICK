from matplotlib import pyplot as plt
import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF import \
    RamseyVsFF
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF_CompPulse import \
    RamseyVsFFComp
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mRamseyVsFF_Ramp import \
    RamseyVsFF_Ramp
# from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import FFvsSpec

from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.build_config import build_config
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy

soc, soccfg = makeProxy()

Gain_list = []
for Q in [5]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [f'{Q}_3800+']
    config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse)

    Run_FF_v_Ramsey = True
    Run_CompFF_v_Ramsey = False

    FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 1,
                                       "expts": 71, "reps": 200,
                                       "qubit_FF_index": int(str(Qubit_Readout[0])[0]),
                                       "FF_gain_start": config["FF_Qubits"][str(Q)]["Gain_Expt"] - 200,
                                       "FF_gain_stop": config["FF_Qubits"][str(Q)]["Gain_Expt"] + 200,
                                       "FF_gain_steps":7,
                                       "relax_delay": 100, 'populations': False,  # "qubit_drive_freq":3950.0
                                       }

    # PulseFF will become like FFExpts in this experiment. Gain_RampInits works as usual
    Run_RampFF_v_Ramsey = False
    # FF_Ramp_params = {"ramp_duration": 1000,
    #                   "FFPrev": pulse_4815,
    #                   "FFInit": Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
    #                   }


    if FF_sweep_Ramsey_relevant_params['populations']:
        exec(open("Legacy_CALIBRATE_SINGLESHOT_READOUTS.py").read())

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