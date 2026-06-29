'''
Scripts to run MottQuenchBasic: a naive implementation of the Mott qsf protocol,
a pi/2 pulse on the center qubit and pi on the rest, evolution, then separation and pi/2 pulses
on all qubits. Doesn't account for phase evolution, so meant to be a foundation for tests
of these concepts.
'''
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mMottQuench import MottQuenchDynamics
import matplotlib.pyplot as plt
import numpy as np


from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
soc, soccfg = makeProxy()

Readout_Point = "readout_3800_new"
Qubit_Readout = [3,4,5,6,7,8]
Qubit_Pulse = [3,4,5,6,7,8]
Ramp_State = "6Q_Pulse_init"
Dynamics_Point = "Q1_quench"


config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point)
config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg, Readout_Point=Readout_Point, shots=6000)


quench_base_dict = {'reps':500, 'pi2_init_index': 3}
# quench_base_dict =  {'quench_gain': 0.55, 'quench_freq': 3792.5, 'quench_phase': 0,
#                          'reps': 500,
#                          'expt_samples_ramp': 0,
#                          'expt_samples_quench': 110,
#                          'expt_samples_dynamics': 0,
#                          'init_pulse': False,
#                      }



run_mott_quench_dynamics = True

for pi2_phase in [0, 90]:
    quench_dynamics_dict = {'samples_start': 0, 'samples_end': 8000,
                            'samples_num_points': 401,
                            'measurement_pi2_phase': pi2_phase,
                            }

    # This ends the translation of the Qubit_Parameters dict
    # --------------------------------------------------


    if run_mott_quench_dynamics:
        MottQuenchDynamics(outerFolder=outerFolder, cfg=config | quench_base_dict | quench_dynamics_dict,
                        soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)



print(config)
plt.show()
