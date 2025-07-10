from Compensated_Pulse_Josh import *
from RampHelpers import *

'''
Quickly generates IQDataArrays for each fast flux channel.

Usage:
    IQDataArray = StepPulseArrays(self.cfg, "Gain_Pulse", "Gain_Expt")
'''

def StepPulseArrays(cfg, initial_key, final_key) -> list:
    N = len(cfg['fast_flux_chs'])
    return [Compensated_Pulse(cfg['FF_Qubits'][str(Q)][final_key],
                      cfg['FF_Qubits'][str(Q)][initial_key], Q) for Q in range(1, N+1)]

def CubicRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    N = len(cfg['fast_flux_chs'])
    return [generate_cubic_ramp(cfg['FF_Qubits'][str(Q)][initial_key],
                              cfg['FF_Qubits'][str(Q)][final_key], ramp_duration, reverse=reverse) for Q in range(1, N + 1)]

