'''
Scripts to calibrate the phase of the final measurement pi/2 pulse used in the Mott-quench protocol.
SweepPi2Phase: bare two-pi/2 phase sweep (pi/2 sanity / pulse-pair phase reference).
MottQuenchPi2Phase: full Mott-quench sequence at fixed expt_samples, sweeping the measurement pi/2 phase.
MottQuenchPi2Phase2D: maps the measurement pi/2 phase vs dynamics time, i.e. phi0(t).
'''
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mSweeppi2Phase import \
    SweepPi2Phase, MottQuenchPi2Phase, MottQuenchPi2Phase2D
import matplotlib.pyplot as plt
import numpy as np


from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
soc, soccfg = makeProxy()

Readout_Point = "readout_3800_new"
Qubit_Readout = [5,6]
Qubit_Pulse = [5,6]
Ramp_State = "56"
Dynamics_Point = "swap_5_6_2"


config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point, Readout_Point=Readout_Point)
config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg, Readout_Point=Readout_Point, shots=6000)

quench_base_dict = {'reps': 200, 'pi2_init_index': 0, 'swept_qubit': 1,
                    'second_pulse_at_dynamics': False}


run_sweep_pi2_phase = False
run_mott_quench_pi2_phase = False
run_mott_quench_pi2_phase_2d = True



sweep_pi2_phase_dict = {'phase_start': 0, 'phase_end': 360, 'phase_num_points': 41}

mott_quench_pi2_phase_dict = {'expt_samples': 110,
                              'phase_start': 0, 'phase_end': 360, 'phase_num_points': 41,
                              }

mott_quench_pi2_phase_2d_dict = {'samples_start': 0, 'samples_end': 200,
                                 'samples_num_points': 21,
                                 'phase_start': 0, 'phase_end': 360, 'phase_num_points': 11,
                                 }


# --------------------------------------------------


if run_sweep_pi2_phase:
    SweepPi2Phase(outerFolder=outerFolder, cfg=config | quench_base_dict | sweep_pi2_phase_dict,
                  soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if run_mott_quench_pi2_phase:
    MottQuenchPi2Phase(outerFolder=outerFolder, cfg=config | quench_base_dict | mott_quench_pi2_phase_dict,
                       soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if run_mott_quench_pi2_phase_2d:
    MottQuenchPi2Phase2D(outerFolder=outerFolder, cfg=config | quench_base_dict | mott_quench_pi2_phase_2d_dict,
                         soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)


print(config)
plt.show()
