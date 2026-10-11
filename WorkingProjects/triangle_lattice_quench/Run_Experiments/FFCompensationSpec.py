# os.add_dll_directory(os.getcwd() + '\\Equipment_Drivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
import datetime
import time

from triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mFFSpecCalibration import \
    FFSpecCalibration
from triangle_lattice_quench.MUXInitialize import BaseConfig


from triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import *
import numpy as np

from triangle_lattice_quench.build_config import QubitParams
from triangle_lattice_quench.socProxy import makeProxy

'''Usage: jump from FF_expt to FF_Pulses.'''

soc, soccfg = makeProxy()

for Q in [1]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    QP = QubitParams("Qubit_Parameters\\qubit_parameters.json")
    config = BaseConfig | QP.res_qubit_config("FF_Comp_Spec_midpoint", Qubit_Readout, Qubit_Pulse)
    config['FF_Expts'] = np.zeros_like(config['FF_Readouts'])
    idataArray = [None] * 8

    # idataArray[Q-1] = Compensated_Pulse(config['FF_BS'][int(Q) - 1],
    #                                         config['FF_Expt'][int(Q) - 1], Q)
    center_freq = config['qubit_freqs'][0] + 20
    SpecSpan = 125
    FFCal_params = {"SpecStart": center_freq-SpecSpan/2, "SpecEnd":center_freq+SpecSpan/2,
                    "SpecNumPoints": 126,
                    "Gauss_gain": min(32766, 9*config["qubit_gains"][0]*32766),

                    "sigma": [0.00465],
                    # Delays are in units of clock cycles! delay step must be an integer # one clock cycle is 2.3 ns
                    'delay_start': 15, 'delay_step': 0.5, 'delay_points': 200,
                    'reps': 400, 'relax_delay':200,
                    'IDataArray': idataArray,
                    }

    config['meta'] = {'group_name': 'uncompensated'}
    FFSpecCalibration(cfg=config | FFCal_params, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

    print(f"Q{Q} finished at", datetime.datetime.fromtimestamp(time.time()).strftime('%A %B %d, %I:%M:%S %p'))


plt.show()