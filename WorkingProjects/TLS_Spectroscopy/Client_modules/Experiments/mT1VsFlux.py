import csv
import os
import time
import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    acquire_with_retry, order_rng, resolve_rounds, split_reps, suppress_stdout,
    visit_order)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots


NOTEBOOK_FIT_PARAM_ORDER = ("f_max_GHz", "E_C_GHz", "d", "V_period_V", "V_sweet_V")


def _coerce_notebook_fit_params(notebook_fit_params):
    if notebook_fit_params is None:
        raise ValueError("notebook_fit_params is required.")
    if isinstance(notebook_fit_params, dict):
        vals = [notebook_fit_params.get(k) for k in NOTEBOOK_FIT_PARAM_ORDER]
    else:
        vals = list(notebook_fit_params)
    if len(vals) != 5 or any(v is None for v in vals):
        raise ValueError(f"notebook_fit_params must supply exactly the 5 values "
                         f"{NOTEBOOK_FIT_PARAM_ORDER}.")
    f_max, e_c, d, period, sweet = [float(v) for v in vals]
    if not all(np.isfinite([f_max, e_c, d, period, sweet])):
        raise ValueError("notebook_fit_params values must be finite.")
    if e_c <= 0:
        raise ValueError("E_C must be positive.")
    if period == 0:
        raise ValueError("V_period must be nonzero.")
    if f_max + e_c <= 0:
        raise ValueError("f_max + E_C must be positive.")
    ejmax = (f_max + e_c) ** 2 / (8.0 * e_c)
    notebook = dict(zip(NOTEBOOK_FIT_PARAM_ORDER, [f_max, e_c, d, period, sweet]))
    canonical = {"EJmax": ejmax, "Ec": e_c, "period_volts": period,
                 "phase_offset_volts": sweet, "d": d}
    return notebook, canonical


def _predict_qubit_frequency_hz_from_flux_fit(dc_values, flux_fit_params):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.flux_fit import (
        flux_tunable_transmon_frequency,
    )
    p = flux_fit_params
    f_ghz = flux_tunable_transmon_frequency(np.asarray(dc_values, dtype=float),
                                            p["EJmax"], p["Ec"], p["period_volts"],
                                            p["phase_offset_volts"], p["d"])
    return np.asarray(f_ghz, dtype=float) * 1e9


def _compute_3pt_t1(P0, P1, Ps, Ts_ns, min_ref_contrast=0.05, max_t1_multiple=20.0):
    P0 = np.asarray(P0, dtype=float)
    P1 = np.asarray(P1, dtype=float)
    Ps = np.asarray(Ps, dtype=float)
    contrast = P1 - P0
    valid_contrast = np.isfinite(contrast) & (contrast >= float(min_ref_contrast))
    inverted = np.isfinite(contrast) & (contrast <= -float(min_ref_contrast))
    denom_safe = np.where(valid_contrast, contrast, np.nan)
    pe = (Ps - P0) / denom_safe
    with np.errstate(divide="ignore", invalid="ignore"):
        T1_3pt_us_raw = -(Ts_ns / 1e3) / np.log(pe)
    valid_pe = np.isfinite(pe) & (pe > 0.0) & (pe < 1.0)
    valid_t1 = np.isfinite(T1_3pt_us_raw)
    max_t1_us = None
    if max_t1_multiple is not None:
        max_t1_us = float(max_t1_multiple) * (Ts_ns / 1e3)
        valid_t1 &= T1_3pt_us_raw <= max_t1_us
    valid_mask = valid_contrast & valid_pe & valid_t1
    T1_3pt_us_plot = np.where(valid_mask, T1_3pt_us_raw, np.nan)
    n_inv = int(np.count_nonzero(inverted))
    if n_inv:
        print(f"[3pt] {n_inv} point(s) have P1 < P0 by more than {min_ref_contrast:g}: "
              f"the pi made the qubit look LESS excited than no pi.  That is a readout "
              f"polarity or pi failure, not a T1, and those points are dropped.  "
              f"(They used to pass, because the contrast test took |P1-P0|.)")
    return {"contrast": contrast, "pe": pe, "T1_3pt_us_raw": T1_3pt_us_raw,
            "T1_3pt_us_plot": T1_3pt_us_plot, "n_sign_inverted": n_inv,
            "valid_mask": valid_mask.astype(np.int8), "max_t1_us": max_t1_us}


def _safe_inverse_t1_us(T1_us, T1_err_us=None):
    T1_us = np.asarray(T1_us, dtype=float)
    inv = np.where(np.isfinite(T1_us) & (T1_us > 0), 1.0 / T1_us, np.nan)
    if T1_err_us is None:
        return inv
    T1_err_us = np.asarray(T1_err_us, dtype=float)
    inv_err = np.where(np.isfinite(T1_err_us) & np.isfinite(T1_us) & (T1_us > 0),
                       T1_err_us / T1_us ** 2, np.nan)
    return inv, inv_err


def _exp_decay_model(t, P0, P1, T1):
    return P0 + (P1 - P0) * np.exp(-t / T1)


def _fit_T1_map(ss, t_us, fit_clip=(0.0, 1.0), require_monotone=False,
                min_contrast=0.05, max_t1_multiple=2.0, max_err_fraction=0.5,
                return_diagnostics=False):
    from scipy.optimize import curve_fit
    ss = np.asarray(ss, dtype=float)
    t_us = np.asarray(t_us, dtype=float)
    n_dc = ss.shape[0]
    T1_fit = np.full(n_dc, np.nan)
    T1_err = np.full(n_dc, np.nan)
    fit_ok = np.zeros(n_dc, dtype=np.int8)
    contrast = np.full(n_dc, np.nan)
    reject = np.zeros(n_dc, dtype=np.int8)
    lo, hi = fit_clip
    for i in range(n_dc):
        y = ss[i, :]
        finite = np.isfinite(y) & np.isfinite(t_us)
        if finite.sum() < 4:
            continue
        t_fit = t_us[finite]
        fit_y = np.clip(y[finite], lo, hi)
        if require_monotone and np.nanmax(np.diff(fit_y)) > 0.05:
            continue
        p0_seed = float(np.min(fit_y))
        p1_seed = float(np.max(fit_y))
        if p1_seed - p0_seed < 1e-6:
            continue
        mid = p0_seed + (p1_seed - p0_seed) / np.e
        try:
            t_mid = t_fit[np.argmin(np.abs(fit_y - mid))]
            t1_seed = max(0.1, float(t_mid) / np.log(2))
        except Exception:
            t1_seed = max(0.1, float(np.median(t_fit)))
        try:
            popt, pcov = curve_fit(_exp_decay_model, t_fit, fit_y,
                                   p0=[p0_seed, p1_seed, t1_seed],
                                   bounds=([0.0, 0.0, 0.01], [1.0, 1.0, 1e6]),
                                   maxfev=20000)
            T1_fit[i] = popt[2]
            err = np.sqrt(pcov[2, 2]) if np.isfinite(pcov[2, 2]) else np.nan
            T1_err[i] = err
            contrast[i] = float(popt[1] - popt[0])
            span = float(np.nanmax(t_fit))
            if not np.isfinite(popt[2]):
                reject[i] = 1
            elif contrast[i] <= 0:
                reject[i] = 2
            elif contrast[i] < float(min_contrast):
                reject[i] = 3
            elif popt[2] > float(max_t1_multiple) * span:
                reject[i] = 4
            elif np.isfinite(err) and err > float(max_err_fraction) * popt[2]:
                reject[i] = 5
            fit_ok[i] = 0 if reject[i] else 1
        except Exception:
            continue
    if return_diagnostics:
        return T1_fit, T1_err, fit_ok, {"fit_contrast": contrast,
                                        "reject_code": reject}
    return T1_fit, T1_err, fit_ok


def _csv_base_from_pickle(pname):
    return pname[:-4] if str(pname).endswith(".pkl") else str(pname)


def _write_csv_rows(csv_path, fieldnames, rows):
    tmp = str(csv_path) + ".tmp"
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, csv_path)
    return csv_path


def _save_flux_curve_csv(csv_path, dc_vec, columns, extra_columns=None):
    extra_columns = dict(extra_columns or {})
    fieldnames = ["scan_index", "dc_target_V"] + list(extra_columns.keys()) + list(columns.keys())
    rows = []
    for i, dc in enumerate(np.asarray(dc_vec, dtype=float)):
        row = {"scan_index": i, "dc_target_V": float(dc)}
        row.update(extra_columns)
        for k, v in columns.items():
            row[k] = np.asarray(v).ravel()[i]
        rows.append(row)
    return _write_csv_rows(csv_path, fieldnames, rows)


def _save_flux_map_csv(csv_path, dc_vec, t_us, map2d, value_name="population_pe",
                       extra_columns=None):
    extra_columns = dict(extra_columns or {})
    fieldnames = (["scan_index", "t_index", "dc_target_V", "t_wait_us"]
                  + list(extra_columns.keys()) + [value_name])
    map2d = np.asarray(map2d, dtype=float)
    rows = []
    for i, dc in enumerate(np.asarray(dc_vec, dtype=float)):
        for k, t in enumerate(np.asarray(t_us, dtype=float)):
            row = {"scan_index": i, "t_index": k, "dc_target_V": float(dc),
                   "t_wait_us": float(t)}
            row.update(extra_columns)
            row[value_name] = map2d[i, k]
            rows.append(row)
    return _write_csv_rows(csv_path, fieldnames, rows)


def build_wall_clock_repeat_metadata(run_start_dt, series_start_dt, run_index):
    elapsed_minutes = (run_start_dt - series_start_dt).total_seconds() / 60.0
    return {
        "wall_clock_run_index": int(run_index),
        "wall_clock_run_started_at_iso": run_start_dt.isoformat(timespec="seconds"),
        "wall_clock_series_started_at_iso": series_start_dt.isoformat(timespec="seconds"),
        "wall_clock_elapsed_minutes_from_first_run": float(elapsed_minutes),
    }


def get_wall_clock_repeat_spec(exp):
    data = exp.data
    if isinstance(exp, T13PointVsFlux):
        return {"metric_values": data["inv_T1_3pt_per_us"],
                "metric_column_name": "inv_T1_3pt_per_us",
                "extra_metric_matrices": {"T1_3pt_us": data["T1_3pt_us"]},
                "colorbar_label": "1 / T1 (1/us)",
                "plot_title": f"{exp.element} 1/T1_3pt vs flux and wall clock",
                "file_tag": "T1_3pt"}
    if isinstance(exp, T1FullCurveVsFlux):
        return {"metric_values": data["inv_T1_fit_per_us"],
                "metric_column_name": "inv_T1_fit_per_us",
                "extra_metric_matrices": {"T1_fit_us": data["T1_fit_us"]},
                "colorbar_label": "1 / T1 (1/us)",
                "plot_title": f"{exp.element} 1/T1 vs flux and wall clock",
                "file_tag": "T1_fit"}
    raise TypeError(f"Unsupported experiment type for wall-clock repeat: {type(exp)}")


def get_wall_clock_repeat_full_spec(exp):
    data = exp.data
    if isinstance(exp, T1FullCurveVsFlux):
        scalar_columns = {}
        for key in ("T1_fit_err_us", "inv_T1_fit_err_per_us", "fit_success",
                    "fit_contrast", "fit_reject_code"):
            if key in data:
                scalar_columns[key] = data[key]
        return {"axes": {"delay_time_us": np.asarray(data["t_vec_ns"], dtype=float) / 1e3},
                "scalar_columns": scalar_columns,
                "array_columns": {"population_pe": data["ss_data"]}}
    if isinstance(exp, T13PointVsFlux):
        return {"axes": {},
                "scalar_columns": {
                    "Ts_ns": float(int(exp.Ts_ns)),
                    "Ts_effective_ns": float(data["Ts_effective_ns"]),
                    "three_point_ref_hold_us": float(data["three_point_ref_hold_us"]),
                    "three_point_matched_refs": float(
                        bool(data["three_point_matched_refs"])),
                    "P0": data["P0"], "P1": data["P1"], "Ps": data["Ps"],
                    "ref_contrast_3pt": data["ref_contrast_3pt"],
                    "T1_3pt_valid_mask": data["T1_3pt_valid_mask"]},
                "array_columns": {}}
    return None


def save_wall_clock_repeat_outputs(csv_base_path, dc_vec, run_metadata_list,
                                   metric_matrix, metric_column_name, colorbar_label,
                                   plot_title, file_tag, extra_metric_matrices=None):
    metric_matrix = np.asarray(metric_matrix, dtype=float)
    if metric_matrix.ndim != 2:
        raise ValueError("metric_matrix must be 2D (n_runs, n_dc).")
    extra_metric_matrices = {k: np.asarray(v, dtype=float)
                             for k, v in dict(extra_metric_matrices or {}).items()}
    for k, v in extra_metric_matrices.items():
        if v.shape != metric_matrix.shape:
            raise ValueError(f"extra metric '{k}' shape mismatch.")
    dc_vec = np.asarray(dc_vec, dtype=float)
    meta_keys = ["wall_clock_run_index", "wall_clock_run_started_at_iso",
                 "wall_clock_series_started_at_iso",
                 "wall_clock_elapsed_minutes_from_first_run"]
    fieldnames = meta_keys + ["scan_index", "dc_target_V", metric_column_name] \
        + list(extra_metric_matrices.keys())
    rows = []
    for r, md in enumerate(run_metadata_list):
        for i, dc in enumerate(dc_vec):
            row = {k: md[k] for k in meta_keys}
            row.update({"scan_index": i, "dc_target_V": float(dc),
                        metric_column_name: metric_matrix[r, i]})
            for k, v in extra_metric_matrices.items():
                row[k] = v[r, i]
            rows.append(row)
    csv_path = f"{csv_base_path}_{file_tag}_vs_wall_clock.csv"
    _write_csv_rows(csv_path, fieldnames, rows)

    elapsed = np.array([md["wall_clock_elapsed_minutes_from_first_run"]
                        for md in run_metadata_list], dtype=float)
    fig, ax = plt.subplots(constrained_layout=True)
    X, Y = np.meshgrid(elapsed, dc_vec)
    pcm = ax.pcolormesh(X, Y, metric_matrix.T, shading="nearest")
    fig.colorbar(pcm, ax=ax, label=colorbar_label)
    ax.set_xlabel("Wall clock time after first run start (min)")
    ax.set_ylabel("Flux DC target")
    ax.set_title(plot_title)
    png_path = f"{csv_base_path}_{file_tag}_vs_wall_clock.png"
    fig.savefig(png_path, bbox_inches="tight")
    plt.close(fig)
    return csv_path, png_path


def save_wall_clock_repeat_full_outputs(csv_base_path, file_tag, per_run_full_data):
    if not per_run_full_data:
        return None
    meta_keys = ["wall_clock_run_index", "wall_clock_run_started_at_iso",
                 "wall_clock_series_started_at_iso",
                 "wall_clock_elapsed_minutes_from_first_run"]
    first = per_run_full_data[0]
    metric_name = first["metric_column_name"]
    extra_keys = list(dict(first.get("extra_metric_matrices", {})).keys())
    axes = dict(first.get("axes", {}))
    if len(axes) > 1:
        raise ValueError("At most one extra axis is supported in the one-stop CSV.")
    axis_key = next(iter(axes.keys())) if axes else None
    scalar_keys = list(dict(first.get("scalar_columns", {})).keys())
    array_keys = list(dict(first.get("array_columns", {})).keys())
    fieldnames = (meta_keys + ["scan_index", "dc_target_V", metric_name] + extra_keys
                  + ([axis_key] if axis_key else []) + scalar_keys + array_keys)

    def _scalar_at(value, dc_idx):
        arr = np.asarray(value)
        if arr.ndim == 0:
            return float(arr)
        try:
            return float(arr.ravel()[dc_idx])
        except Exception:
            return np.nan

    rows = []
    for run in per_run_full_data:
        md = run["run_metadata"]
        dc_vec = np.asarray(run["dc_vec"], dtype=float)
        metric = np.asarray(run["metric_values"], dtype=float)
        extras = {k: np.asarray(v, dtype=float)
                  for k, v in dict(run.get("extra_metric_matrices", {})).items()}
        run_axes = dict(run.get("axes", {}))
        scalars = dict(run.get("scalar_columns", {}))
        arrays = {k: np.asarray(v, dtype=float)
                  for k, v in dict(run.get("array_columns", {})).items()}
        axis_vals = np.asarray(run_axes[axis_key], dtype=float) if axis_key else None
        for i, dc in enumerate(dc_vec):
            base = {k: md[k] for k in meta_keys}
            base.update({"scan_index": i, "dc_target_V": float(dc),
                         metric_name: metric[i] if i < metric.size else np.nan})
            for k in extra_keys:
                base[k] = _scalar_at(extras.get(k, np.nan), i)
            for k in scalar_keys:
                base[k] = _scalar_at(scalars.get(k, np.nan), i)
            if axis_key is None:
                rows.append(base)
            else:
                for a_idx, a_val in enumerate(axis_vals):
                    row = dict(base)
                    row[axis_key] = float(a_val)
                    for k in array_keys:
                        arr = arrays.get(k)
                        row[k] = (float(arr[i, a_idx])
                                  if arr is not None and arr.shape[0] > i and arr.shape[1] > a_idx
                                  else np.nan)
                    rows.append(row)
    csv_path = f"{csv_base_path}_{file_tag}_vs_wall_clock_full.csv"
    return _write_csv_rows(csv_path, fieldnames, rows)


class FFT1Program(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _set_qubit_pulse(self, gain=None, freq_mhz=None):
        cfg = self.cfg
        freq = self.freq2reg(
            float(freq_mhz) if freq_mhz is not None
            else cfg.get("qubit_pi_freq", cfg["qubit_freq"]), gen_ch=cfg["qubit_ch"])
        g = int(cfg["qubit_pi_gain"] if gain is None else gain)
        if cfg.get("qubit_pulse_style", "arb") == "flat_top":
            self.set_pulse_registers(
                ch=cfg["qubit_ch"], style="flat_top", freq=freq, phase=0, gain=g,
                waveform="qubit",
                length=self.us2cycles(cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))
        else:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"], style="arb", freq=freq,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=g,
                waveform="qubit")

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_park_hold(self)
        if cfg.get("do_ff", True) and not getattr(self, "do_park_hold", False):
            ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self._read_freq_reg = read_freq
        add_qubit_gaussian(self)
        self._set_qubit_pulse()

        set_readout_pulse(self, read_freq)

        self.do_herald_read = bool(active_reset.heralds(cfg))
        self.do_park_hold = bool(ff_pulse.park_hold_configured(cfg))
        self.ff_park_segs = ff_pulse.build_park_hold(
            self, hold_us=ff_pulse.flux_settle_us(cfg))
        if self.do_park_hold and self.ff_park_segs is None:
            raise RuntimeError(
                "ff_park_gain=%s is set but the park ramp was not built; "
                "the flux would be stepped on and never released"
                % cfg.get("ff_park_gain"))
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        self.stepping = abs(float(cfg["ff_gain"]) - park_gain) > 0
        if cfg.get("do_ff", True) and self.stepping:
            stepping = True
            self.ff_settle_us = (ff_pulse.flux_settle_us(cfg) if stepping else 0.0)
            self.ff_segs = ff_pulse.build_ramp_hold_ramp(
                self, hold_us=float(cfg["ff_hold"]) + self.ff_settle_us,
                ff_gain=cfg["ff_gain"], dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US), dt_def_us=cfg.get("dt_pulsedef", 0.002),
                compensation=ff_pulse.load_compensation(cfg),
                distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_park_up(self, self.ff_park_segs)
        if active_reset.uses_feedback(cfg):
            read_gain = cfg.get("reset_read_pulse_gain", None)
            pi_gain = cfg.get("reset_pi_gain", None)
            pi_freq = cfg.get("reset_pi_freq", None)
            if read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg, gain=int(read_gain))
            if pi_gain is not None or pi_freq is not None:
                self._set_qubit_pulse(
                    gain=int(pi_gain) if pi_gain is not None else cfg["qubit_pi_gain"],
                    freq_mhz=float(pi_freq) if pi_freq is not None
                    else cfg.get("qubit_pi_freq", cfg["qubit_freq"]))
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
            post_freq = cfg.get("post_reset_pi_freq", None)
            if pi_gain is not None or pi_freq is not None or post_freq is not None:
                self._set_qubit_pulse(
                    freq_mhz=float(post_freq) if post_freq is not None else None)
            if read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg)
        if self.do_herald_read:
            self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                         adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                         wait=True,
                         syncdelay=self.us2cycles(cfg.get("herald_delay", 8.0)))
        if cfg.get("do_pi", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        if cfg.get("do_ff", True) and self.stepping:
            ff_pulse.play_ramp_up_hold(self, self.ff_segs,
                                       dt_play_us=cfg.get("dt_pulseplay", 5.0))
            self.sync_all(self.us2cycles(0.01))
            ff_pulse.play_ramp_down(self, self.ff_segs)
            self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))
        else:
            self.sync_all(self.us2cycles(max(float(cfg["ff_hold"]), 0.01)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_park_down(self, self.ff_park_segs)
        self.sync_all(self.us2cycles(cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = 1 if active_reset.heralds(self.cfg) else 0
        super().acquire(soc, load_pulses=load_pulses,
                        readouts_per_experiment=1 + n_herald + n_reset,
                        progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = 1 if active_reset.heralds(self.cfg) else 0
        h = n_reset
        f = n_reset + n_herald
        reads = 1 + n_herald + n_reset
        buf_i = self.di_buf[0].reshape((self.cfg["reps"], reads))
        buf_q = self.dq_buf[0].reshape((self.cfg["reps"], reads))
        i0 = buf_i[:, h] / length
        q0 = buf_q[:, h] / length
        i1 = buf_i[:, f] / length
        q1 = buf_q[:, f] / length
        return i0, q0, i1, q1


class _T1VsFluxBase(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='data', cfg=None, meta_dict=None, dc_vec=None, shots=2000,
                 calib_params=None, park_voltage=None, flux_settle_time_us=None,
                 reset_mode="passive", flux_tail_compensation=None,
                 repeat_metadata=None, write_outputs=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if calib_params is None:
            calib_params = cfg.get("calib_params") if cfg else None
        if calib_params is None:
            raise ValueError("calib_params is required (run SingleShot1Q first).")
        if reset_mode not in active_reset.RESET_MODES:
            raise ValueError(f"reset_mode must be one of {active_reset.RESET_MODES}, "
                             f"got {reset_mode!r}")
        if active_reset.uses_feedback(reset_mode) and self.soccfg is not None and not \
                active_reset.active_reset_supported(self.soccfg, cfg["ro_chs"][0]):
            raise RuntimeError(
                f"reset_mode={reset_mode!r} needs a readout that feeds back into the tProc "
                f"(soccfg readout {cfg['ro_chs'][0]} has tproc_ch<0).  Run mActiveResetProbe "
                "to confirm; this firmware may not support active reset -- use 'passive'.")
        self.element = str(path)
        self.calib_params = calib_params
        self.dc_vec = np.asarray(dc_vec if dc_vec is not None else cfg["ff_gain_vec"],
                                 dtype=float)
        self.shots = int(shots)
        self.park_voltage = (park_voltage if park_voltage is not None
                             else cfg.get("ff_park_gain", 0))
        self.flux_settle_time_us = (float(flux_settle_time_us)
                                    if flux_settle_time_us is not None
                                    else ff_pulse.flux_settle_us(cfg))
        cfg["flux_settle_time_us"] = self.flux_settle_time_us
        self.reset_mode = reset_mode
        cfg["reset_mode"] = reset_mode
        self.repeat_metadata = dict(repeat_metadata or {})
        self.write_outputs = bool(write_outputs)
        if flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = flux_tail_compensation
        cfg["shots"] = self.shots

        self.data = {"qubit": self.element, "dc_vec": self.dc_vec, "shots": self.shots,
                     "park_voltage": self.park_voltage,
                     "flux_settle_time_us": self.flux_settle_time_us,
                     "flux_tail_compensation": cfg.get("flux_tail_compensation"),
                     "meta_dict": dict(cfg), "calib_params": calib_params,
                     "reset_mode": reset_mode,
                     "repeat_metadata": self.repeat_metadata or None}
        if self.repeat_metadata:
            self.data.update(self.repeat_metadata)

    def _run_point_counts(self, ff_gain, wait_us, do_pi=True, do_ff=True, reps=None):
        cfg = self.cfg
        cfg["ff_gain"] = float(ff_gain)
        cfg["ff_hold"] = float(wait_us)
        cfg["do_pi"] = bool(do_pi)
        cfg["do_ff"] = bool(do_ff)
        if reps is not None:
            cfg["shots"] = int(reps)
        with suppress_stdout():
            prog = FFT1Program(self.soccfg, cfg)
            i0, q0, i1, q1 = acquire_with_retry(prog, self.soc, load_pulses=True)
        final = np.asarray(discriminate_shots(i1, q1, self.calib_params))
        if active_reset.heralds(self.reset_mode):
            keep = active_reset.herald_keep(i0, q0, self.calib_params)
            return float(np.sum(final[keep])), int(np.sum(keep))
        return float(np.sum(final)), int(final.size)

    def _run_point(self, ff_gain, wait_us, do_pi=True, do_ff=True):
        exc, kept = self._run_point_counts(ff_gain, wait_us, do_pi=do_pi, do_ff=do_ff)
        if kept == 0:
            return np.nan
        return float(exc / kept)

    def _interleaved_populations(self, point_specs, start_time=None, live=None,
                                group_size=1):
        shots = int(self.cfg.get("shots", self.shots))
        rounds = resolve_rounds(self.cfg, shots, default=self.cfg.get("t1_rounds"))
        n = len(point_specs)
        group_size = max(int(group_size), 1)
        if n % group_size:
            raise ValueError(f"point_specs length {n} is not a multiple of "
                             f"group_size {group_size}")
        n_groups = n // group_size
        exc = np.zeros(n)
        kept = np.zeros(n)
        self._partial = (exc, kept)
        saved_shots = self.cfg.get("shots")
        reps_per_round = split_reps(shots, rounds)
        nz_rounds = sum(1 for reps in reps_per_round if reps > 0)
        total_units = nz_rounds * n
        done_units = 0
        if start_time is not None:
            reps0 = next((reps for reps in reps_per_round if reps > 0), 0)
            print(f"[acquire] shot-interleaved: {n} points x {nz_rounds} rounds x ~{reps0} "
                  f"reps = {shots} shots/point  ->  progress counts the {total_units} "
                  f"programs (NOT shots)", flush=True)
        attempted = np.zeros(n)
        rng = order_rng(self.cfg)
        orders = []
        for r, reps in enumerate(reps_per_round):
            if reps <= 0:
                continue
            order = visit_order(n_groups, self.cfg, rng)
            orders.append(order.tolist())
            for gi in order:
                for idx in range(gi * group_size, (gi + 1) * group_size):
                    g, w, dp, df = point_specs[idx]
                    e, k = self._run_point_counts(g, w, do_pi=dp, do_ff=df, reps=reps)
                    exc[idx] += e
                    kept[idx] += k
                    attempted[idx] += reps
                    done_units += 1
                    if start_time is not None:
                        progress_counter(done_units - 1, total_units,
                                         start_time=start_time)
            if live is not None:
                with np.errstate(invalid="ignore", divide="ignore"):
                    live(r, rounds, np.where(kept > 0, exc / kept, np.nan))
        self.cfg["shots"] = saved_shots
        self.point_visit_orders = orders
        with np.errstate(invalid="ignore", divide="ignore"):
            self.keep_fraction = np.where(attempted > 0, kept / attempted, np.nan)
            return np.where(kept > 0, exc / kept, np.nan)

    def _park_T1_probe(self, probe_cfg, suffix_tag):
        p = dict(shots_T1=1000, t_min_us=1.0, t_max_us=300.0, t_points=71, num_pulses=1)
        for k, v in (probe_cfg or {}).items():
            if k.endswith("_ns"):
                p[k[:-3] + "_us"] = float(v) / 1e3
            else:
                p[k] = v
        shots_saved = self.cfg["shots"]
        self.cfg["shots"] = int(p["shots_T1"])
        t_vec_us = np.logspace(np.log10(max(p["t_min_us"], 0.016)),
                               np.log10(p["t_max_us"]), int(p["t_points"]))
        print(f"[{suffix_tag}] park T1 probe: {len(t_vec_us)} waits x {self.cfg['shots']} shots")
        specs = [(self.park_voltage, float(t), True, True) for t in t_vec_us]
        pe = self._interleaved_populations(specs)
        self.cfg["shots"] = shots_saved
        T1_fit, _, ok = _fit_T1_map(pe[None, :], t_vec_us)
        if not ok[0]:
            raise RuntimeError("Park T1 probe fit failed.")
        return float(T1_fit[0])


class T13PointVsFlux(_T1VsFluxBase):

    def __init__(self, *args, Ts_ns=None, min_ref_contrast=0.05,
                 max_plot_t1_multiple=20.0, **kw):
        super().__init__(*args, **kw)
        self.min_ref_contrast = float(min_ref_contrast)
        self.max_plot_t1_multiple = max_plot_t1_multiple
        self.data.update({"min_ref_contrast": self.min_ref_contrast,
                          "max_plot_t1_multiple": max_plot_t1_multiple})
        if Ts_ns is None:
            raise ValueError(
                "Ts_ns is required: the 3-point method runs at ONE fixed decay "
                "delay.  Pick it from the known T1 range (the estimator's variance "
                "is minimal at Ts ~= T1 and it is only defined while the decay has "
                "neither vanished nor stayed put); production uses 60 us.")
        self.Ts_ns = int(Ts_ns)
        self.data["Ts_ns"] = self.Ts_ns

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        dc_vec = self.dc_vec
        Ts_us = self.Ts_ns / 1e3
        matched = bool(self.cfg.get("three_point_matched_refs", True))
        t_ref_us = float(self.cfg.get("three_point_ref_hold_us", 1.0))
        if matched and not (0.0 < t_ref_us < Ts_us):
            raise ValueError(f"three_point_ref_hold_us={t_ref_us} must be >0 and "
                             f"< Ts={Ts_us}")
        Ts_eff_ns = (self.Ts_ns - t_ref_us * 1e3) if matched else self.Ts_ns
        if matched:
            print(f"[3pt] flux-matched references: P0/P1 take the SAME flux excursion as "
                  f"Ps (hold {t_ref_us:g}us),")
            print(f"      so the reset residual cancels.  effective decay window = "
                  f"Ts - t_ref = {Ts_eff_ns / 1e3:g} us")
        else:
            print(f"[3pt] LEGACY references: P0/P1 measured at park with no flux pulse. "
                  f"Any reset residual")
            print(f"      that the flux excursion would have removed biases T1 low.")
        start_time = time.time()
        specs = []
        for dc in dc_vec:
            if matched:
                specs.append((float(dc), t_ref_us, False, True))
                specs.append((float(dc), t_ref_us, True, True))
            else:
                specs.append((self.park_voltage, 0.0, False, False))
                specs.append((self.park_voltage, 0.0, True, False))
            specs.append((float(dc), Ts_us, True, True))
        pe = self._interleaved_populations(specs, group_size=3,
                                           start_time=start_time if progress else None)
        P0 = pe[0::3]
        P1 = pe[1::3]
        Ps = pe[2::3]
        self.data["three_point_matched_refs"] = matched
        self.data["three_point_ref_hold_us"] = t_ref_us if matched else 0.0
        self.data["Ts_effective_ns"] = float(Ts_eff_ns)

        est = _compute_3pt_t1(P0, P1, Ps, Ts_eff_ns,
                              min_ref_contrast=self.min_ref_contrast,
                              max_t1_multiple=self.max_plot_t1_multiple)
        inv = _safe_inverse_t1_us(est["T1_3pt_us_plot"])
        self.data.update({"P0": P0, "P1": P1, "Ps": Ps,
                          "ref_contrast_3pt": est["contrast"], "pe_Ts": est["pe"],
                          "T1_3pt_us_raw": est["T1_3pt_us_raw"],
                          "T1_3pt_us": est["T1_3pt_us_plot"],
                          "inv_T1_3pt_per_us": inv,
                          "T1_3pt_valid_mask": est["valid_mask"],
                          "T1_3pt_max_plot_us": est["max_t1_us"]})

        if self.write_outputs:
            base = _csv_base_from_pickle(self.pname)
            fig, ax = plt.subplots(constrained_layout=True)
            ax.plot(dc_vec, P0, "-", label="P0 (no pi)")
            ax.plot(dc_vec, P1, "-", label="P1 (pi, t=0)")
            ax.plot(dc_vec, Ps, "-", label=f"Ps (pi, hold Ts={Ts_us:.3g} us)")
            ax.set_xlabel("Flux DC target")
            ax.set_ylabel("P(excited) (SS-classified)")
            ax.set_title(f"{self.element} 3-point raw references")
            ax.legend()
            fig.savefig(self.iname[:-4] + "_3pt_P0P1Ps.png", bbox_inches="tight")
            plt.close(fig)

            fig, ax = plt.subplots(constrained_layout=True)
            ax.plot(dc_vec, self.data["T1_3pt_us"], "-")
            ax.set_xlabel("Flux DC target")
            ax.set_ylabel("T1 (us) from 3-point estimator")
            ax.set_title(f"{self.element} T1_3pt vs flux (Ts={Ts_us:.3g} us)")
            fig.savefig(self.iname[:-4] + "_3pt_T1.png", bbox_inches="tight")
            plt.close(fig)

            fig, ax = plt.subplots(constrained_layout=True)
            ax.plot(dc_vec, inv, "-")
            ax.set_xlabel("Flux DC target")
            ax.set_ylabel("1 / T1 (1/us) from 3-point estimator")
            ax.set_title(f"{self.element} 1/T1_3pt vs flux (Ts={Ts_us:.3g} us)")
            fig.savefig(self.iname[:-4] + "_3pt_invT1.png", bbox_inches="tight")
            plt.close(fig)

            invalid_mask = est["valid_mask"] == 0
            if np.any(invalid_mask):
                fig, ax = plt.subplots(constrained_layout=True)
                ax.plot(dc_vec, est["contrast"], "-", label="P1 - P0")
                ax.plot(dc_vec[invalid_mask], est["contrast"][invalid_mask], "rx",
                        ms=7, label="masked T1 points")
                ax.axhline(self.min_ref_contrast, color="k", linestyle="--",
                           linewidth=1, label="min contrast threshold")
                ax.set_xlabel("Flux DC target")
                ax.set_ylabel("Reference contrast")
                ax.set_title(f"{self.element} 3-point estimator validity")
                ax.legend()
                fig.savefig(self.iname[:-4] + "_3pt_validity.png", bbox_inches="tight")
                plt.close(fig)

            _save_flux_curve_csv(
                base + "_3pt_summary.csv", dc_vec,
                {"P0": P0, "P1": P1, "Ps": Ps,
                 "ref_contrast": est["contrast"], "pe_estimator": est["pe"],
                 "T1_3pt_us_raw": est["T1_3pt_us_raw"],
                 "T1_3pt_us_plot": est["T1_3pt_us_plot"],
                 "inv_T1_3pt_per_us": inv, "valid_mask": est["valid_mask"]},
                extra_columns=self.repeat_metadata)

        self.data["time"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if self.write_outputs:
            self.pickle_data()
        return {"config": self.cfg, "data": self.data}

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in self.data.items()
               if isinstance(v, np.ndarray)}
        super().save_data(data=arr)


class T1FullCurveVsFlux(_T1VsFluxBase):

    def __init__(self, *args, auto_tmax_factor=3.0, T1_probe_cfg=None,
                 t_min_ns_default=1000.0, t_points_default=41, t_max_ns=None,
                 fit_clip=(0.0, 1.0), require_monotone=False,
                 min_contrast=0.05, max_t1_multiple=20.0, **kw):
        super().__init__(*args, **kw)
        self.min_contrast = float(min_contrast)
        self.max_t1_multiple = float(max_t1_multiple)
        self.auto_tmax_factor = float(auto_tmax_factor)
        self.T1_probe_cfg = T1_probe_cfg
        self.t_min_ns_default = float(t_min_ns_default)
        self.t_points_default = int(t_points_default)
        self.t_max_ns_user = t_max_ns
        self.fit_clip = fit_clip
        self.require_monotone = bool(require_monotone)
        self.data.update({"auto_tmax_factor": self.auto_tmax_factor,
                          "auto_T1_probe_cfg": T1_probe_cfg,
                          "t_max_ns_user": t_max_ns, "fit_clip": fit_clip,
                          "require_monotone": self.require_monotone,
                          "write_outputs": self.write_outputs})
        self._build_t_vec()

    def _build_t_vec(self):
        t_min = max(16.0, self.t_min_ns_default)
        if self.t_max_ns_user is not None:
            t_max = float(self.t_max_ns_user)
            if t_max <= t_min:
                raise ValueError("t_max_ns must exceed t_min_ns.")
            t_vec_ns = np.logspace(np.log10(t_min), np.log10(t_max), self.t_points_default)
            print(f"[FIXED t_vec] t_max={t_max / 1e3:.3g} us, points={len(t_vec_ns)} "
                  f"(park-T1 probe skipped)")
        else:
            probe_window_us = float(dict(self.T1_probe_cfg or {}).get("t_max_us", 300.0))
            T1_us = self._park_T1_probe(self.T1_probe_cfg, "AUTO t_vec")
            if T1_us > probe_window_us:
                raise RuntimeError(
                    f"Park T1 probe returned {T1_us:.3g} us from a window that only "
                    f"reaches {probe_window_us:g} us, so the decay was never observed "
                    f"and the fit is an extrapolation.  t_max would be set to "
                    f"{self.auto_tmax_factor * T1_us:.3g} us for every shot of the "
                    f"whole scan.  Refusing.  Either widen T1_probe_cfg['t_max_us'] "
                    f"past the real park T1, or set t_max_us explicitly to skip the "
                    f"probe.")
            t_max = self.auto_tmax_factor * T1_us * 1e3
            t_vec_ns = np.logspace(np.log10(t_min), np.log10(max(t_max, t_min * 2)),
                                   self.t_points_default)
            print(f"[AUTO t_vec] T1_park={T1_us:.3g} us -> t_max={t_max / 1e3:.3g} us, "
                  f"points={len(t_vec_ns)}")
            self.data.update({"auto_T1_park_us_for_tvec": T1_us, "auto_t_max_ns": t_max})
        t_vec_ns = np.unique(np.round(t_vec_ns).astype(int))
        self.data["t_vec_ns_requested"] = t_vec_ns
        self.t_vec_ns = t_vec_ns.astype(float)
        self.data["t_vec_ns"] = self.t_vec_ns
        self.data["wall_clock_note"] = None

    def _wait_mask_for_dc(self, dc_index):
        return np.ones(len(self.t_vec_ns), dtype=bool)

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        dc_vec = self.dc_vec
        t_us = self.t_vec_ns / 1e3
        ss = np.full((len(dc_vec), len(t_us)), np.nan)
        valid = np.zeros((len(dc_vec), len(t_us)), dtype=np.int8)
        start_time = time.time()
        specs = []
        index_map = []
        for i, dc in enumerate(dc_vec):
            mask = self._wait_mask_for_dc(i)
            for k, t in enumerate(t_us):
                if not mask[k]:
                    continue
                specs.append((float(dc), float(t), True, True))
                index_map.append((i, k))
                valid[i, k] = 1
        try:
            pe = self._interleaved_populations(
                specs, start_time=start_time if progress else None)
            self.data["interrupted"] = False
        except KeyboardInterrupt:
            exc_a, kept_a = self._partial
            with np.errstate(invalid="ignore", divide="ignore"):
                pe = np.where(kept_a > 0, exc_a / kept_a, np.nan)
            self.data["interrupted"] = True
            print(f"\n[6] interrupted mid-pass -- fitting and saving the partial map "
                  f"({int(np.sum(kept_a > 0))}/{len(specs)} points have shots).",
                  flush=True)
        for (i, k), val in zip(index_map, pe):
            ss[i, k] = val
        self._finish_acquire(ss, valid, t_us)
        self.data["time"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if self.write_outputs:
            self.pickle_data()
        return {"config": self.cfg, "data": self.data}

    def _title_suffix(self):
        return ""

    def _finish_acquire(self, ss, valid, t_us):
        self.data["ss_data"] = ss
        T1_fit, T1_err, fit_ok, diag = _fit_T1_map(
            ss, t_us, fit_clip=self.fit_clip, require_monotone=self.require_monotone,
            min_contrast=self.min_contrast, max_t1_multiple=self.max_t1_multiple,
            return_diagnostics=True)
        inv, inv_err = _safe_inverse_t1_us(T1_fit, T1_err)
        self.data.update({"T1_fit_us": T1_fit, "T1_fit_err_us": T1_err,
                          "inv_T1_fit_per_us": inv, "inv_T1_fit_err_per_us": inv_err,
                          "fit_success": fit_ok,
                          "fit_contrast": diag["fit_contrast"],
                          "fit_reject_code": diag["reject_code"]})
        n_bad = int(np.sum(diag["reject_code"] > 0))
        if n_bad:
            labels = {1: "non-finite T1", 2: "sign-inverted (rising) trace",
                      3: f"contrast below {self.min_contrast:g}",
                      4: f"T1 beyond {self.max_t1_multiple:g}x the measured window",
                      5: "fit error above half the fitted T1"}
            counts = {c: int(np.sum(diag["reject_code"] == c))
                      for c in sorted(set(diag["reject_code"].tolist())) if c}
            detail = ", ".join(f"{labels[c]}: {n}" for c, n in counts.items())
            print(f"[full-curve fit] rejected {n_bad}/{len(T1_fit)} DC points ({detail}).  "
                  f"They are flagged fit_success=0 in the CSV, not silently averaged in.")
        if self.write_outputs:
            base = _csv_base_from_pickle(self.pname)
            dc_vec = self.dc_vec
            sfx = self._title_suffix()

            fig, ax = plt.subplots(constrained_layout=True)
            X, Y = np.meshgrid(t_us, dc_vec)
            pcm = ax.pcolormesh(X, Y, ss, shading="nearest")
            fig.colorbar(pcm, ax=ax, label="P(e)")
            ax.set_xscale("log")
            ax.set_xlabel("Wait time t (us)")
            ax.set_ylabel("Flux DC target")
            ax.set_title(f"{self.element} full T1 curves vs flux (P(e){sfx})")
            fig.savefig(self.iname[:-4] + "_T1map.png", bbox_inches="tight")
            plt.close(fig)

            fig, ax = plt.subplots(constrained_layout=True)
            ax.errorbar(dc_vec, T1_fit, yerr=T1_err, fmt="-", capsize=2)
            ax.set_xlabel("Flux DC target")
            ax.set_ylabel("T1 (us)")
            ax.set_title(f"{self.element} T1 vs flux (full decay fit{sfx})")
            fig.savefig(self.iname[:-4] + "_T1_vs_flux.png", bbox_inches="tight")
            plt.close(fig)

            fig, ax = plt.subplots(constrained_layout=True)
            ax.errorbar(dc_vec, inv, yerr=inv_err, fmt="-", capsize=2)
            ax.set_xlabel("Flux DC target")
            ax.set_ylabel("1 / T1 (1/us)")
            ax.set_title(f"{self.element} 1/T1 vs flux (full decay fit{sfx})")
            fig.savefig(self.iname[:-4] + "_invT1_vs_flux.png", bbox_inches="tight")
            plt.close(fig)

            _save_flux_curve_csv(base + "_full_t1_summary.csv", dc_vec,
                                 self._summary_columns(),
                                 extra_columns=self.repeat_metadata)
            _save_flux_map_csv(base + "_full_t1_map.csv", dc_vec, t_us, ss,
                               value_name="population_pe",
                               extra_columns=self.repeat_metadata)

    def _summary_columns(self):
        return {"T1_fit_us": self.data["T1_fit_us"],
                "T1_fit_err_us": self.data["T1_fit_err_us"],
                "inv_T1_fit_per_us": self.data["inv_T1_fit_per_us"],
                "inv_T1_fit_err_per_us": self.data["inv_T1_fit_err_per_us"],
                "fit_success": self.data["fit_success"],
                "fit_contrast": self.data["fit_contrast"],
                "fit_reject_code": self.data["fit_reject_code"]}

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in self.data.items() if isinstance(v, np.ndarray)}
        super().save_data(data=arr)


class T1FullCurveVsFluxFromFit(T1FullCurveVsFlux):

    def __init__(self, *args, notebook_fit_params=None, quality_factor=None, **kw):
        self._notebook_raw = notebook_fit_params
        self.quality_factor = quality_factor
        self.notebook_fit_params, self.flux_fit_params = \
            _coerce_notebook_fit_params(notebook_fit_params)
        super().__init__(*args, **kw)
        self.data.update({"notebook_fit_params": self.notebook_fit_params,
                          "flux_fit_params": self.flux_fit_params,
                          "supplied_quality_factor": quality_factor})
        if self.write_outputs:
            self.pickle_data()

    def _build_t_vec(self):
        t_min = max(16.0, self.t_min_ns_default)
        park_f_hz = _predict_qubit_frequency_hz_from_flux_fit(
            [self.park_voltage], self.flux_fit_params)[0]
        if self.quality_factor is not None:
            estimated_Q = float(self.quality_factor)
            T1_us = estimated_Q / (2.0 * np.pi * park_f_hz) * 1e6
            print(f"[t_vec from SUPPLIED Q] Q={estimated_Q:.6g}, "
                  f"f_park={park_f_hz / 1e9:.6g} GHz -> implied T1_park={T1_us:.3g} us "
                  f"(park-T1 probe skipped)")
        else:
            T1_us = self._park_T1_probe(self.T1_probe_cfg, "AUTO t_vec")
            estimated_Q = 2.0 * np.pi * park_f_hz * T1_us * 1e-6
        predicted_f_hz = _predict_qubit_frequency_hz_from_flux_fit(
            self.dc_vec, self.flux_fit_params)
        predicted_T1_us = estimated_Q / (2.0 * np.pi * predicted_f_hz) * 1e6
        local_t_max_ns = self.auto_tmax_factor * predicted_T1_us * 1e3
        local_t_max_ns = np.maximum(local_t_max_ns, max(16.0, t_min))
        global_t_max = max(np.nanmax(local_t_max_ns), t_min * 2)
        t_vec_ns = np.logspace(np.log10(t_min), np.log10(global_t_max),
                               self.t_points_default)
        print(f"[AUTO t_vec from qubit fit] T1_park={T1_us:.3g} us, "
              f"f_park={park_f_hz / 1e9:.6g} GHz, Q={estimated_Q:.6g} -> "
              f"global t_max={global_t_max / 1e3:.3g} us, points={len(t_vec_ns)}")
        t_vec_ns = np.unique(np.round(t_vec_ns).astype(int))
        self.t_vec_ns = t_vec_ns.astype(float)
        self._local_t_max_ns = local_t_max_ns
        self.data.update({
            "auto_T1_park_us_for_tvec": T1_us,
            "park_qubit_freq_hz_for_tvec": park_f_hz,
            "park_qubit_freq_ghz_for_tvec": park_f_hz / 1e9,
            "estimated_Q_for_tvec": estimated_Q,
            "predicted_qubit_freq_hz_per_dc": predicted_f_hz,
            "predicted_qubit_freq_ghz_per_dc": predicted_f_hz / 1e9,
            "predicted_T1_us_per_dc": predicted_T1_us,
            "local_t_max_ns_per_dc": local_t_max_ns,
            "auto_t_max_ns": global_t_max,
            "t_vec_ns_requested": t_vec_ns, "t_vec_ns": self.t_vec_ns})

    def _wait_mask_for_dc(self, dc_index):
        return self.t_vec_ns <= self._local_t_max_ns[dc_index]

    def _title_suffix(self):
        return ", qubit-fit t_max"

    def _finish_acquire(self, ss, valid, t_us):
        ss_masked = np.where(valid > 0.5, ss, np.nan)
        self.data.update({"ss_data_raw": ss, "valid_mask_data": valid})
        super()._finish_acquire(ss_masked, valid, t_us)

    def _summary_columns(self):
        cols = {"predicted_qubit_freq_GHz": self.data["predicted_qubit_freq_ghz_per_dc"],
                "predicted_T1_us_from_Q": self.data["predicted_T1_us_per_dc"],
                "local_t_max_ns": self.data["local_t_max_ns_per_dc"]}
        cols.update(super()._summary_columns())
        return cols
