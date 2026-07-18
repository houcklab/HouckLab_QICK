"""
Single-shot discrimination primitives -- VERBATIM lift from the QUA repo's
LabCode/Helpers/ss_helpers.py (find_blob_mean/median, concatenate,
find_threshold with its exact 100-threshold sweep and F formula), so step 5's
threshold/fidelity numerics are identical to the OPX workflow.
"""

import numpy as np


def find_blob_mean(IQ_trace, axis=None):
    if axis:
        return np.mean(np.real(IQ_trace), axis) + 1j * np.mean(np.imag(IQ_trace), axis)
    else:
        return np.mean(np.real(IQ_trace)) + 1j * np.mean(np.imag(IQ_trace))

def find_blob_median(IQ_trace, axis=None):
    if axis:
        return np.median(np.real(IQ_trace), axis) + 1j * np.median(np.imag(IQ_trace), axis)
    else:
        return np.median(np.real(IQ_trace)) + 1j * np.median(np.imag(IQ_trace))

def concatenate(IQ_trace_1, IQ_trace_2):
    return np.concatenate((IQ_trace_1, IQ_trace_2))

def find_threshold(IQ_trace_g, IQ_trace_e):
    ground_projections = np.sort(np.real(IQ_trace_g))
    excited_projections = np.sort(np.real(IQ_trace_e))

    min_threshold = np.min(concatenate(ground_projections, excited_projections))
    max_threshold = np.max(concatenate(ground_projections, excited_projections))

    ground_mean = np.mean(ground_projections)
    excited_mean = np.mean(excited_projections)

    if ground_mean < excited_mean:
        left_blob = ground_projections
        right_blob = excited_projections
    else:
        left_blob = excited_projections
        right_blob = ground_projections

    num_thresholds = 100
    num_items = len(right_blob)

    F = np.zeros(num_thresholds)
    thresholds = np.linspace(min_threshold, max_threshold, num_thresholds)

    for i, t in enumerate(thresholds):

        F_left = len(right_blob)
        F_right = 0

        for b in left_blob:

            if t > b:
                F_left = F_left - 1
            else:
                break

        for b in right_blob:

            if t > b:
                F_right = F_right + 1
            else:
                break

        F[i] = 1 - F_left / (2*num_items) - F_right / (2*num_items)

    return thresholds, F
