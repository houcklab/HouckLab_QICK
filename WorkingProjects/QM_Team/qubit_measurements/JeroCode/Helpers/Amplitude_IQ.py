### function to turn I and Q into amplitude, getting best signal

import numpy as np

def Amplitude_IQ(I, Q, phase_num_points = 100):
    complex = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array([np.max(IQPhase.imag) - np.min(IQPhase.imag) for IQPhase in multiplied_phase])
    phase_index = np.argmin(Q_range)
    final_complex = complex * np.exp(1j * phase_values[phase_index])
    return(final_complex.real)