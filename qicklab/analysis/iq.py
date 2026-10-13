import numpy as np

def rotate_data(data, theta):
    i = data[0]
    q = data[1]
    i_new = i * np.cos(theta) - q * np.sin(theta)
    q_new = i * np.sin(theta) + q * np.cos(theta)

    return((i_new, q_new))

def count_percentage(data, threshold):
    i = data[0][0]

    excited_population = sum(val > threshold for val in i)
    return(excited_population / len(i))

def average_data(data):
    i = data[0][0]
    return(np.mean(i))


def rotate_iq(avgi, avgq):
    sig = np.asarray(avgi) + 1j*np.asarray(avgq)
    theta = -np.angle(np.mean(sig))
    sig_rot = sig * np.exp(1j*theta)
    return sig_rot


def project_iq_signal(avgi, avgq, edge_frac=0.15):
    """Project complex IQ data onto its signal-bearing axis for peak finding.

    Two-tone spec frequently lands almost the entire qubit response in one
    quadrature, sitting on top of a large constant offset in the other. Taking
    |I + iQ| (or its square) then buries the feature: the magnitude is dominated
    by the big, noisy background quadrature, so peak-finding and Lorentzian fits
    lock onto background noise spikes instead of the qubit (see e.g. the
    2026-06-02 Q6 QubitSpecFF traces, where the real feature in I at ~3054 MHz
    was missed in favour of Q-noise spikes at 3038/3069 MHz).

    This removes the off-resonant background and rotates the deviation onto its
    principal axis, returning a real-valued trace in which the qubit feature
    appears as a positive peak rising from a ~0 baseline.

    Parameters
    ----------
    avgi, avgq : array_like
        Real and imaginary readout quadratures (1-D, same length).
    edge_frac : float
        Fraction of the sweep taken from each end as the off-resonant baseline
        anchor (see the baseline/orientation note below). 0.15 = outer 15% per
        side; pass 0 to fall back to the whole-trace median.

    Returns
    -------
    np.ndarray
        Real-valued, background-subtracted, principal-axis-projected trace,
        oriented so the qubit feature rises as a positive peak from a ~0
        baseline.
    """
    avgi = np.asarray(avgi, dtype=float)
    avgq = np.asarray(avgq, dtype=float)
    sig = avgi + 1j * avgq

    # Centre the cloud before estimating the axis. Any error in this offset lies
    # *along* the signal axis, so it biases the baseline but not the axis angle;
    # the baseline is re-estimated properly below.
    bg = np.median(sig.real) + 1j * np.median(sig.imag)
    dev = sig - bg

    # Principal axis of the deviation. sum(dev**2) has argument 2*theta, where
    # theta is the axis the signal varies along; half its angle recovers theta
    # (and resolves the 180-degree fold). Projecting onto exp(-i*theta) puts the
    # variation into the real part.
    if np.allclose(dev, 0):
        return np.zeros_like(avgi)
    ang = 0.5 * np.angle(np.sum(dev ** 2))
    proj = (dev * np.exp(-1j * ang)).real

    # Baseline and orientation.
    #
    # The old code used the whole-trace median as the baseline and flipped the
    # sign whenever abs(min) > abs(max). Both break as soon as the feature is
    # WIDE relative to the span: the median then sits *inside* the feature, the
    # trace splits into a roughly half-positive / half-negative excursion, and
    # the min-vs-max comparison becomes a coin flip decided by a single noisy
    # point. That inverted the broad ~3753 MHz response of the 2026-09-02 12:03
    # CSTQ03/Q2 spec into a dip and put both "peaks" on edge noise at 3764 MHz,
    # even though I and Q both showed the bump plainly.
    #
    # A spec span is centred on the expected line, so the outer edges are the
    # points most likely to be off-resonance whatever the linewidth. Anchor the
    # baseline there, then orient by TOTAL excursion mass (many points on the
    # feature side) rather than by the single most extreme sample.
    n = proj.size
    k = int(round(edge_frac * n))
    if k >= 3 and 2 * k < n:
        baseline = float(np.median(np.concatenate([proj[:k], proj[-k:]])))
    else:
        baseline = float(np.median(proj))
    proj = proj - baseline

    if -proj[proj < 0].sum() > proj[proj > 0].sum():
        proj = -proj
    return proj


def classify_and_average_iq(raw_i, raw_q, g_center, e_center, average_n_shots=25):
    """
    Projects IQ shots onto the calibrated ground/excited axis.

    Returns:
      binary_states: 0 or 1 per shot
      excited_avg: averaged excited population in groups of average_n_shots
      elapsed_idx_avg: group index for plotting
      scores: raw projection scores
      threshold_score: decision threshold
    """

    iq = np.column_stack([raw_i, raw_q])

    g_center = np.asarray(g_center, dtype=float)
    e_center = np.asarray(e_center, dtype=float)

    normal = e_center - g_center
    midpoint = 0.5 * (g_center + e_center)

    # Projection coordinate along g -> e axis
    scores = (iq - midpoint) @ normal

    # By construction, scores > 0 is closer to excited center
    binary_states = (scores > 0).astype(int)

    average_n_shots = max(1, int(average_n_shots))

    n_full = len(binary_states) // average_n_shots
    if n_full > 0:
        trimmed = binary_states[:n_full * average_n_shots]
        excited_avg = trimmed.reshape(n_full, average_n_shots).mean(axis=1)
        elapsed_idx_avg = np.arange(n_full)
    else:
        excited_avg = np.array([np.mean(binary_states)])
        elapsed_idx_avg = np.array([0])

    return {
        "binary_states": binary_states,
        "excited_avg": excited_avg,
        "elapsed_idx_avg": elapsed_idx_avg,
        "scores": scores,
        "normal": normal,
        "midpoint": midpoint,
    }


def project_iq_onto_separator(I, Q, separator):
    """
    Project (I, Q) sample arrays onto the ground -> excited axis defined by a
    single-shot calibration separator dict.

    Parameters
    ----------
    I, Q : array_like
        Sample arrays (1-D or any shape that ravels to 1-D). Must be same length.
    separator : dict
        Must contain keys "g_center" and "e_center", each a length-2 array-like
        (I, Q) coordinate. Keys "normal" and "midpoint" if present are ignored;
        they are recomputed from g_center and e_center.

    Returns
    -------
    scores : np.ndarray, shape (N,)
        Signed projection of each sample onto (e_center - g_center). Positive
        scores are closer to the excited centroid.
    binary_states : np.ndarray, shape (N,), dtype int
        1 where score > 0 (excited side), 0 otherwise.
    """
    g = np.asarray(separator["g_center"], dtype=float)
    e = np.asarray(separator["e_center"], dtype=float)
    if g.shape != (2,) or e.shape != (2,):
        raise ValueError(
            f"separator g_center and e_center must each be length-2, "
            f"got shapes {g.shape} and {e.shape}"
        )
    normal = e - g
    midpoint = 0.5 * (g + e)
    I_arr = np.ravel(np.asarray(I, dtype=float))
    Q_arr = np.ravel(np.asarray(Q, dtype=float))
    if I_arr.size != Q_arr.size:
        raise ValueError(
            f"I and Q must have the same length, got I.size={I_arr.size}, "
            f"Q.size={Q_arr.size}"
        )
    if I_arr.size == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=int)
    iq = np.column_stack([I_arr, Q_arr])
    scores = (iq - midpoint) @ normal
    binary_states = (scores > 0).astype(int)
    return scores, binary_states
