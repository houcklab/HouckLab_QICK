import numpy as np


def _rolling_median(x, w=5):
    x = np.asarray(x, dtype=float)
    n = x.size
    h = max(1, w // 2)
    return np.array([np.median(x[max(0, i - h):min(n, i + h + 1)]) for i in range(n)])


def glitched_rows(baseline, sigma=6.0):
    b = np.asarray(baseline)
    if np.iscomplexobj(b):
        trend = _rolling_median(b.real) + 1j * _rolling_median(b.imag)
    else:
        trend = _rolling_median(b)
    resid = np.abs(b - trend)
    mad = 1.4826 * np.median(np.abs(resid - np.median(resid))) + 1e-9
    return np.where(resid > float(sigma) * mad)[0]


def remeasure_glitched_rows(baseline_fn, reacquire, sigma=6.0, passes=2, label="", row_labels=None):
    for _ in range(int(passes)):
        bad = glitched_rows(baseline_fn(), sigma=sigma)
        if bad.size == 0:
            break
        for i in bad:
            reacquire(int(i))
        if label:
            if row_labels is not None:
                tag = ", ".join(str(row_labels[int(i)]) for i in bad)
            else:
                tag = ", ".join(str(int(i)) for i in bad)
            print(f"[{label}] re-measured glitched row(s): {tag}")
