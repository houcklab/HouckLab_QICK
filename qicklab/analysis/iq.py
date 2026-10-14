"""IQ rotations and projections; conventions in docs/concepts/iq_conventions.md."""

import numpy as np


def rotate_data(data, theta):
    """Rotate (I, Q) = data[:2] by theta."""
    i = data[0]
    q = data[1]
    i_new = i * np.cos(theta) - q * np.sin(theta)
    q_new = i * np.sin(theta) + q * np.cos(theta)

    return (i_new, q_new)


def count_percentage(data, threshold):
    """Fraction of data[0][0] above threshold."""
    i = data[0][0]

    excited_population = sum(val > threshold for val in i)
    return excited_population / len(i)


def rotate_iq(avgi, avgq):
    """Rotate I + iQ so its mean lies on +I (aligns the centroid, not the oscillation axis)."""
    sig = np.asarray(avgi) + 1j * np.asarray(avgq)
    theta = -np.angle(np.mean(sig))
    sig_rot = sig * np.exp(1j * theta)
    return sig_rot


def project_iq_signal(avgi, avgq, edge_frac=0.15):
    """Background-subtracted principal-axis projection of a spec trace: the qubit feature becomes a
    positive peak on a ~0 baseline taken from the outer ``edge_frac`` of each side (0 = whole-trace
    median). Why not |I + iQ|, and the evidence: docs/concepts/iq_conventions.md section 2."""
    avgi = np.asarray(avgi, dtype=float)
    avgq = np.asarray(avgq, dtype=float)
    sig = avgi + 1j * avgq

    # An error in this offset lies along the signal axis: it biases the baseline, not the angle.
    bg = np.median(sig.real) + 1j * np.median(sig.imag)
    dev = sig - bg

    # arg(sum(dev**2)) = 2*theta; halving it resolves the 180-degree fold.
    if np.allclose(dev, 0):
        return np.zeros_like(avgi)
    ang = 0.5 * np.angle(np.sum(dev**2))
    proj = (dev * np.exp(-1j * ang)).real

    # Edge baseline and orientation by total excursion mass (not the single extreme point):
    # robust when the feature is wide relative to the span.
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
    """Classify shots by the g/e perpendicular bisector (score > 0 -> e) and average the binary
    states in blocks of ``average_n_shots``. Returns binary_states, excited_avg, elapsed_idx_avg,
    scores, normal, midpoint."""
    iq = np.column_stack([raw_i, raw_q])

    g_center = np.asarray(g_center, dtype=float)
    e_center = np.asarray(e_center, dtype=float)

    normal = e_center - g_center
    midpoint = 0.5 * (g_center + e_center)

    scores = (iq - midpoint) @ normal

    binary_states = (scores > 0).astype(int)

    average_n_shots = max(1, int(average_n_shots))

    n_full = len(binary_states) // average_n_shots
    if n_full > 0:
        trimmed = binary_states[: n_full * average_n_shots]
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
    """Scores of (I, Q) along e_center - g_center about their midpoint (separator dict keys
    "g_center", "e_center"; "normal"/"midpoint" are recomputed) and binary states (score > 0).
    See docs/concepts/iq_conventions.md section 5."""
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
            f"I and Q must have the same length, got I.size={I_arr.size}, Q.size={Q_arr.size}"
        )
    if I_arr.size == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=int)
    iq = np.column_stack([I_arr, Q_arr])
    scores = (iq - midpoint) @ normal
    binary_states = (scores > 0).astype(int)
    return scores, binary_states


def min_q_range_phase(I, Q, n):
    """Phase in [0, pi] (n grid points) that minimises the peak-to-peak of Q after
    multiplying I + iQ by exp(i*phase), i.e. puts the contrast in I.
    See docs/concepts/iq_conventions.md section 3."""
    complex = I + 1j * Q
    phase_values = np.linspace(0, np.pi, n)
    multiplied_phase = [complex * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array(
        [np.max(IQPhase.imag) - np.min(IQPhase.imag) for IQPhase in multiplied_phase]
    )
    phase_index = np.argmin(Q_range)
    return phase_values[phase_index]


def kmeans_split(iq, min_blob_snr=None):
    """Split (N, 2) IQ points into two KMeans blobs along the centroid axis; state 1 = minority.

    Below `min_blob_snr` every shot is 0 (docs/architecture.md#analysis-conventions).
    Returns (states, c0, c1, normal, midpoint, scores, blob_snr); blob_snr None without the gate.
    """
    from sklearn.cluster import KMeans  # third-party; kept local so `iq` stays import-light

    kmeans = KMeans(n_clusters=2, random_state=0, n_init=20)
    labels = kmeans.fit_predict(iq)
    centers = kmeans.cluster_centers_

    c0 = centers[0]
    c1 = centers[1]
    normal = c1 - c0
    midpoint = 0.5 * (c0 + c1)
    scores = (iq - midpoint) @ normal
    states = (scores > 0).astype(int)

    blob_snr = None
    if min_blob_snr is not None:
        sep = float(np.linalg.norm(normal))
        within = float(
            np.sqrt(
                np.mean(
                    [
                        np.mean(np.sum((iq[labels == k] - centers[k]) ** 2, axis=1))
                        for k in (0, 1)
                        if np.any(labels == k)
                    ]
                )
            )
        )
        blob_snr = sep / within if within > 0 else np.inf
        if not blob_snr >= min_blob_snr:
            return np.zeros(len(iq), dtype=int), c0, c1, normal, midpoint, scores, blob_snr

    n0 = np.sum(states == 0)
    n1 = np.sum(states == 1)
    if n1 > n0:
        states = 1 - states
        c0, c1 = c1, c0
        normal = c1 - c0
        midpoint = 0.5 * (c0 + c1)
        scores = (iq - midpoint) @ normal
    return states, c0, c1, normal, midpoint, scores, blob_snr
