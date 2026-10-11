from triangle_lattice_quench.build_config import QubitParams
from triangle_lattice_quench.socProxy import makeProxy
from triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from triangle_lattice_quench.MUXInitialize import BaseConfig

import matplotlib.pyplot as plt

soc, soccfg = makeProxy()


# for det,Q in itertools.product([+20000, -20000],[1,2,3,4,5,6,7,8]):
for Q in [2,4,6]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    QP = QubitParams("Qubit_Parameters\\qubit_parameters.json")
    config = BaseConfig | QP.res_qubit_config("Upper_sweetspot", Qubit_Readout, Qubit_Pulse)

    config['qubit_gains'][0] *= 0.80


    Calib_FF_vs_drive_delay = True

    # Usage: set both delay of FF (start,step,expts) and delay of qubit drive to large values,
    #        the experiment will sweep delay of FF. The x-axis will be (delay_of_FF) - (delay_of_qubit_drive),
    #        given in both samples and ns.
    ff_drive_delay_dict = {'start': 200, 'step': 8, 'expts': 200,  # delay of FF,          units of samples
                           'qubit_delay_cycles': 80,               # delay of qubit drive, units of master clock cycles = 16 samples
                           'reps': 2000,
                           'qubit_swept': Q}

    if Calib_FF_vs_drive_delay:
        CalibrateFFvsDriveTiming(cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)

plt.show()