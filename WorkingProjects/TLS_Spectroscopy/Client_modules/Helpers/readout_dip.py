import numpy as np


def dip_metrics(freq_mhz, mag_db, edge_margin_mhz=1.0):
    f = np.asarray(freq_mhz, dtype=float)
    y = np.asarray(mag_db, dtype=float)
    good = np.isfinite(y)
    if good.sum() < 5:
        return dict(dip_mhz=np.nan, depth_db=np.nan, fwhm_mhz=np.nan,
                    baseline_db=np.nan, noise_db=np.nan, sigma=np.nan,
                    edge_flag=True)
    n = len(y)
    edge = max(3, n // 4)
    baseline = float(np.nanmedian(np.concatenate([y[:edge], y[-edge:]])))
    k = int(np.nanargmin(y))
    depth = baseline - y[k]

    dip = f[k]
    if 0 < k < n - 1 and np.all(np.isfinite(y[k - 1:k + 2])):
        y0, y1, y2 = y[k - 1], y[k], y[k + 1]
        den = y0 - 2.0 * y1 + y2
        if den != 0:
            delta = 0.5 * (y0 - y2) / den
            if abs(delta) <= 1.0:
                dip = f[k] + delta * (f[k + 1] - f[k])

    half = baseline - 0.5 * depth
    left = np.nan
    for i in range(k, 0, -1):
        if y[i - 1] >= half >= y[i]:
            span = y[i - 1] - y[i]
            frac = 0.0 if span == 0 else (y[i - 1] - half) / span
            left = f[i - 1] + frac * (f[i] - f[i - 1])
            break
    right = np.nan
    for i in range(k, n - 1):
        if y[i] <= half <= y[i + 1]:
            span = y[i + 1] - y[i]
            frac = 0.0 if span == 0 else (half - y[i]) / span
            right = f[i] + frac * (f[i + 1] - f[i])
            break
    fwhm = right - left if np.isfinite(left) and np.isfinite(right) else np.nan

    noise = float(np.std(np.diff(y[good])) / np.sqrt(2.0))
    sigma = depth / noise if noise > 0 else np.nan
    margin = min(abs(dip - f[0]), abs(dip - f[-1]))
    edge_flag = bool(margin < edge_margin_mhz) or not np.isfinite(fwhm)
    return dict(dip_mhz=float(dip), depth_db=float(depth), fwhm_mhz=float(fwhm),
                baseline_db=baseline, noise_db=noise, sigma=float(sigma),
                edge_flag=edge_flag)


def ladder_verdict(rows, expect_dip_mhz=None, shift_tol_mhz=0.05,
                   min_sigma=8.0):
    strong = [r for r in rows
              if np.isfinite(r["dip_mhz"]) and not r["edge_flag"]
              and np.isfinite(r["sigma"]) and r["sigma"] >= min_sigma]
    consensus = float(np.median([r["dip_mhz"] for r in strong])) if strong else np.nan
    typ_fwhm = float(np.nanmedian([r["fwhm_mhz"] for r in strong])) if strong else np.nan
    tol = max(1.0, 2.0 * typ_fwhm) if np.isfinite(typ_fwhm) else 1.0
    for r in rows:
        r["off_consensus_mhz"] = (r["dip_mhz"] - consensus
                                  if np.isfinite(consensus) else np.nan)
        r["stray_flag"] = bool(np.isfinite(r["off_consensus_mhz"])
                               and abs(r["off_consensus_mhz"]) > tol)
    agreeing = [r for r in strong if not r["stray_flag"]]
    scatter = (float(np.median(np.abs([r["off_consensus_mhz"] for r in agreeing])))
               if agreeing else np.nan)

    finite = [r for r in rows
              if np.isfinite(r["dip_mhz"]) and not r["edge_flag"] and not r["stray_flag"]]
    ref = finite[0]["dip_mhz"] if finite else np.nan
    for r in rows:
        r["shift_from_lowest_mhz"] = (r["dip_mhz"] - ref
                                      if np.isfinite(ref) else np.nan)
    linear = [r for r in rows
              if np.isfinite(r["shift_from_lowest_mhz"])
              and abs(r["shift_from_lowest_mhz"]) <= shift_tol_mhz
              and not r["edge_flag"] and not r["stray_flag"]]

    expect_offset = (consensus - float(expect_dip_mhz)
                     if expect_dip_mhz is not None and np.isfinite(consensus)
                     else np.nan)
    agrees = True
    if expect_dip_mhz is not None:
        budget = max(0.5, 2.0 * typ_fwhm) if np.isfinite(typ_fwhm) else 0.5
        agrees = bool(np.isfinite(expect_offset) and abs(expect_offset) <= budget)

    trustworthy = bool(
        len(agreeing) >= max(3, len(rows) // 3)
        and np.isfinite(scatter) and np.isfinite(typ_fwhm)
        and scatter <= typ_fwhm
        and agrees
    )
    usable = [r for r in linear if np.isfinite(r["sigma"])]
    best = max(usable, key=lambda r: r["sigma"]) if usable else None
    deepest = (max([r for r in linear if np.isfinite(r["depth_db"])],
                   key=lambda r: r["depth_db"], default=None))
    return dict(consensus_mhz=consensus, scatter_mhz=scatter, typ_fwhm_mhz=typ_fwhm,
                expect_offset_mhz=expect_offset, agrees_with_expected=agrees,
                trustworthy=trustworthy, n_agreeing=len(agreeing),
                linear_gain_max=max((r["gain"] for r in linear), default=np.nan),
                best=best, deepest=deepest)


def print_table(rows, verdict, shift_tol_mhz=0.05):
    print("")
    print(f"  {'gain':>8} {'dip MHz':>12} {'depth dB':>9} {'sigma':>7} "
          f"{'FWHM MHz':>9} {'shift MHz':>10}  flags")
    for r in rows:
        flags = " ".join(t for t, on in (("EDGE", r["edge_flag"]),
                                         ("STRAY", r.get("stray_flag", False))) if on)
        print(f"  {r['gain']:8d} {r['dip_mhz']:12.4f} {r['depth_db']:9.3f} "
              f"{r['sigma']:7.1f} {r['fwhm_mhz']:9.4f} "
              f"{r['shift_from_lowest_mhz']:10.4f}  {flags}")
    print("")
    if not verdict["trustworthy"]:
        print("  *** LADDER NOT TRUSTWORTHY ***")
        print("  The dip position does not agree across the gain ladder, or it")
        print("  disagrees with the expected position. Do NOT promote a read gain or")
        print("  frequency from this run; inspect the raw traces first.")
        if np.isfinite(verdict["consensus_mhz"]):
            print(f"  consensus {verdict['consensus_mhz']:.4f} MHz, "
                  f"scatter {verdict['scatter_mhz']:.4f} MHz, "
                  f"agreeing rows {verdict['n_agreeing']}")
        if not verdict["agrees_with_expected"]:
            print(f"  consensus is {verdict['expect_offset_mhz']:+.4f} MHz from the "
                  f"expected position")
        return
    print(f"  consensus dip across ladder : {verdict['consensus_mhz']:.4f} MHz "
          f"(scatter {verdict['scatter_mhz']:.4f} MHz, {verdict['n_agreeing']} rows)")
    print(f"  linear regime holds to gain <= {verdict['linear_gain_max']:.0f} "
          f"(|shift| <= {shift_tol_mhz:.3f} MHz)")
    if verdict["best"] is not None:
        b = verdict["best"]
        print(f"  best SNR inside linear regime : gain {b['gain']} at "
              f"{b['dip_mhz']:.4f} MHz ({b['sigma']:.1f} sigma, {b['depth_db']:.2f} dB)")
    if verdict["deepest"] is not None:
        d = verdict["deepest"]
        print(f"  deepest dip inside linear regime: gain {d['gain']} "
              f"({d['depth_db']:.2f} dB)")
    print("  these are transmission-contrast criteria, not state-discrimination")
    print("  fidelity; a readout optimum may sit higher in power than either.")
