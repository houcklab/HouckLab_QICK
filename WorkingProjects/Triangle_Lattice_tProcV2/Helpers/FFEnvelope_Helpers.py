from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import *

'''
Quickly generates IQDataArrays for each fast flux channel.

Usage:
    IQDataArray = StepPulseArrays(self.cfg, "Gain_Pulse", "Gain_Expt")
'''



def StepPulseArrays(cfg, initial_key, final_key) -> list:
    '''Output: list of IQArrays'''
    N = len(cfg['fast_flux_chs'])
    return [Compensated_Pulse(cfg['FF_Qubits'][str(Q)][final_key],
                      cfg['FF_Qubits'][str(Q)][initial_key], Q) for Q in range(1, N+1)]

def CubicRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Output: list of IQArrays'''
    N = len(cfg['fast_flux_chs'])

    print(f'initial gains: {list([int(cfg["FF_Qubits"][str(Q)][initial_key]) for Q in range(1, N+1)])}')
    print(f'final gains: {list([int(cfg["FF_Qubits"][str(Q)][final_key]) for Q in range(1, N+1)])}')

    return [generate_cubic_ramp(cfg['FF_Qubits'][str(Q)][initial_key],
                              cfg['FF_Qubits'][str(Q)][final_key], ramp_duration, reverse=reverse) for Q in range(1, N + 1)]

def LinearRampArrays(cfg, initial_key, final_key, ramp_duration, reverse=False) -> list:
    '''Output: list of IQArrays'''
    N = len(cfg['fast_flux_chs'])
    return [generate_linear_ramp(cfg['FF_Qubits'][str(Q)][initial_key],
                                cfg['FF_Qubits'][str(Q)][final_key], ramp_duration, reverse=reverse) for Q in
            range(1, N + 1)]

