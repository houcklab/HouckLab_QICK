"""Verbatim logic from the existing triangle_lattice_quench code, for equivalence tests only.

Each function is the original code with its cfg/self lookups turned into arguments.
Sources (agentic_measurement @ 059437a3):

    ProgramBuilder.drive_schedule      Experimental_Scripts/Program_Templates/ProgramBuilder.py
    ProgramBuilder combined IQ array   ProgramBuilder._initialize, "Create combined_IQArray"
    BSClean beamsplitter arrays        Experimental_Scripts/mBSDoubleJump_CleanTiming.py, BSClean.set_up_instance
    MottQuench quench arrays           Experimental_Scripts/quench_experiments/mMottQuench.py, MottQuenchBase.set_up_instance
    Compensate / apply_IIR             Helpers/Compensated_Pulse_Josh.py
    rotate_data / count_percentage /   Helpers/rotate_SS_data.py
    correct_occ
    IQ_angle / rotate / IQ_contrast    Helpers/IQ_contrast.py
"""
import math

import numpy as np
from scipy.signal import lfilter


# ---------------------------------------------------------------- ProgramBuilder
def pb_drive_schedule(segments, cycle_us, drive_offset_cycles=0):
    out, cumulative = [], 16 * max(0, int(drive_offset_cycles))
    for si, seg in enumerate(segments):
        seg_start_us = cycle_us * ((cumulative + 15) // 16)
        cursor = seg_start_us
        for di, drv in enumerate(seg["drives"]):
            t = cursor if drv["relative_t"] == "auto" else seg_start_us + drv["relative_t"]
            cursor = max(cursor, t + drv["len_us"])
            out.append((si, di, t))
        cumulative += seg["length"]
    return out


def pb_combined_iq(segment_gains, segment_lengths, t_offset, ff_readouts, compensate=None,
                   base_pad=32):
    """ProgramBuilder._initialize for constant segments. ``compensate(arr, offset, qubit)``
    is called exactly as ProgramBuilder calls Compensate (absolute array, init offset)."""
    init_ffs = np.asarray(segment_gains[0], float)
    L_body = int(sum(segment_lengths))
    out = []
    for j in range(len(init_ffs)):
        combined = [np.full(int(t_offset[j]), init_ffs[j])]
        for gains, seg_len in zip(segment_gains, segment_lengths):
            combined.append(np.full(int(seg_len), gains[j]))
        combined.append(np.full((np.max(t_offset) - int(t_offset[j])) + base_pad, ff_readouts[j]))
        arr = np.concatenate(combined)
        out.append(compensate(arr, init_ffs[j], j + 1) if compensate else arr)
    return out, np.max(t_offset) + L_body + base_pad


# ---------------------------------------------------------------- BSClean
def bsclean_arrays(t_offset, intermediate_jump_gains, intermediate_jump_samples, bs_samples_cfg,
                   expt_samples2, ff_bs, gain_expt, gain_readout):
    t_offset = np.array(t_offset, dtype=int)
    t_offset -= np.min(t_offset)
    inter_gains = list(intermediate_jump_gains)
    inter_samples = list(intermediate_jump_samples)
    for j, g in enumerate(inter_gains):              # BSClean.init_sweep_vars
        if g is None:
            inter_gains[j] = ff_bs[j]
            inter_samples[j] = 0
    bs_samples = np.asarray(bs_samples_cfg) + expt_samples2
    RO_PAD = 0 * 20 * 16
    max_array_2_length = np.max(t_offset + inter_samples + bs_samples)
    out = []
    for j in range(len(gain_expt)):
        padded = max_array_2_length - t_offset[j] - inter_samples[j] - bs_samples[j] + RO_PAD
        arr = np.repeat([gain_expt[j], inter_gains[j], ff_bs[j], gain_readout[j]],
                        [t_offset[j], inter_samples[j], bs_samples[j], padded])
        out.append(arr.astype(float))
    return out


# ---------------------------------------------------------------- MottQuench
def mott_quench_arrays(t_offset, expt_samples, gain_pulse, gain_expt, gain_readout):
    t_offset = np.array(t_offset, dtype=int)
    t_offset -= np.min(t_offset)
    ff_ro_pad = 16 + math.ceil(np.max(t_offset) / 16) * 16
    out = []
    for j in range(len(t_offset)):
        arr = np.concatenate([np.full(t_offset[j], gain_pulse[j]),
                              np.full(expt_samples, gain_expt[j]),
                              np.full(ff_ro_pad, gain_readout[j])])
        out.append(arr.astype(float))
    return out


# ---------------------------------------------------------------- Compensate
def apply_IIR(ab, waveform):
    a, b = ab
    return np.real(lfilter(b, a, waveform))


def Compensate(waveform, offset, Qubit, files_by_qubit, fudge_scaling):
    for iir_file in files_by_qubit[Qubit]:
        ab = np.loadtxt(iir_file, dtype=np.complex128)
        waveform = apply_IIR(ab, waveform)
    waveform = waveform * fudge_scaling[Qubit - 1]
    return waveform + offset


# ---------------------------------------------------------------- rotate_SS_data
def rotate_data(data, theta):
    i = data[0]
    q = data[1]
    i_new = i * np.cos(theta) - q * np.sin(theta)
    q_new = i * np.sin(theta) + q * np.cos(theta)

    return (i_new, q_new)


def count_percentage(data, threshold):
    i = data[0]

    excited_population = sum(val > threshold for val in i)
    return excited_population / len(i)


def correct_occ(pop_data, confusion_matrix):
    vec = np.vstack([1.-pop_data, pop_data])
    return (np.linalg.inv(confusion_matrix)[1,:]  @  vec).flatten()


# ---------------------------------------------------------------- Helpers/IQ_contrast.py (verbatim)
def IQ_angle(Imat, Qmat):
    import scipy.optimize
    def newQvariance(theta):
        newQ = np.sin(theta)*Imat + np.cos(theta)*Qmat
        return np.max(newQ) - np.min(newQ)
    angle = scipy.optimize.minimize(newQvariance, (np.pi/4,)).x
    return angle


def rotate(theta, Imat, Qmat):
    return np.cos(theta)*Imat - np.sin(theta)*Qmat, np.sin(theta)*Imat + np.cos(theta)*Qmat # newI, newQ


def IQ_contrast(Imat, Qmat):
    theta = IQ_angle(Imat, Qmat)
    rotated_I, rotated_Q = rotate(theta, Imat, Qmat)
    return rotated_I - np.mean(rotated_I)
