import csv
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
    resolve_rounds, split_reps, suppress_stdout)
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
    valid_contrast = np.isfinite(contrast) & (np.abs(contrast) >= float(min_ref_contrast))
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
    return {"contrast": contrast, "pe": pe, "T1_3pt_us_raw": T1_3pt_us_raw,
            "T1_3pt_us_plot": T1_3pt_us_plot,
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


def _fit_T1_map(ss, t_us, fit_clip=(0.0, 1.0), require_monotone=False):
    from scipy.optimize import curve_fit
    ss = np.asarray(ss, dtype=float)
    t_us = np.asarray(t_us, dtype=float)
    n_dc = ss.shape[0]
    T1_fit = np.full(n_dc, np.nan)
    T1_err = np.full(n_dc, np.nan)
    fit_ok = np.zeros(n_dc, dtype=np.int8)
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
            fit_ok[i] = 1
        except Exception:
            continue
    return T1_fit, T1_err, fit_ok


def _csv_base_from_pickle(pname):
    return pname[:-4] if str(pname).endswith(".pkl") else str(pname)


def _write_csv_rows(csv_path, fieldnames, rows):
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
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
        for key in ("T1_fit_err_us", "inv_T1_fit_err_per_us", "fit_success"):
            if key in data:
                scalar_columns[key] = data[key]
        return {"axes": {"delay_time_us": np.asarray(data["t_vec_ns"], dtype=float) / 1e3},
                "scalar_columns": scalar_columns,
                "array_columns": {"population_pe": data["ss_data"]}}
    if isinstance(exp, T13PointVsFlux):
        return {"axes": {},
                "scalar_columns": {"Ts_ns": float(int(exp.Ts_ns)),
                                   "P0": data["P0"], "P1": data["P1"], "Ps": data["Ps"]},
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

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        if cfg.get("do_ff", True):
            ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   gen_ch=cfg["qubit_ch"])

        style = cfg.get("qubit_pulse_style", "arb")
        if style == "flat_top":
            add_qubit_gaussian(self)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="flat_top", freq=qubit_freq, phase=0,
                                     gain=cfg["qubit_pi_gain"], waveform="qubit",
                                     length=self.us2cycles(cfg["flat_top_length"],
                                                           gen_ch=cfg["qubit_ch"]))
        else:
            add_qubit_gaussian(self)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                     gain=cfg["qubit_pi_gain"], waveform="qubit")

        set_readout_pulse(self, read_freq)

        if cfg.get("do_ff", True):
            self.ff_segs = ff_pulse.build_ramp_hold_ramp(
                self, hold_us=cfg["ff_hold"],
                ff_gain=cfg["ff_gain"], dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", 0.02), dt_def_us=cfg.get("dt_pulsedef", 0.002),
                compensation=ff_pulse.load_compensation(cfg),
                distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if cfg.get("do_ff", True):
            ff_pulse.assert_park(self, self.ff_segs)
        if str(cfg.get("reset_mode", "passive")).lower() == "feedback":
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg.get("herald_delay", 4.4)))
        if cfg.get("do_pi", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        if cfg.get("do_ff", True):
            ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
            self.sync_all(self.us2cycles(0.01))
            ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(cfg.get("flux_settle_time", 100) / 1000.0))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        super().acquire(soc, load_pulses=load_pulses, readouts_per_experiment=2 + n_reset,
                        progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        h, f = n_reset, n_reset + 1
        reads = 2 + n_reset
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
                 calib_params=None, park_voltage=None, flux_settle_time_ns=None,
                 reset_mode="passive", flux_tail_compensation=None,
                 repeat_metadata=None, write_outputs=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if calib_params is None:
            calib_params = cfg.get("calib_params") if cfg else None
        if calib_params is None:
            raise ValueError("calib_params is required (run SingleShot1Q first).")
        if reset_mode not in ("passive", "active", "feedback"):
            raise ValueError(f"reset_mode must be 'passive', 'active', or 'feedback', got {reset_mode!r}")
        if reset_mode == "feedback" and self.soccfg is not None and not \
                active_reset.active_reset_supported(self.soccfg, cfg["ro_chs"][0]):
            raise RuntimeError(
                "reset_mode='feedback' needs a readout that feeds back into the tProc "
                f"(soccfg readout {cfg['ro_chs'][0]} has tproc_ch<0).  Run mActiveResetProbe "
                "to confirm; this firmware may not support active reset -- use 'passive'.")
        self.element = str(path)
        self.calib_params = calib_params
        self.dc_vec = np.asarray(dc_vec if dc_vec is not None else cfg["ff_gain_vec"],
                                 dtype=float)
        self.shots = int(shots)
        self.park_voltage = (park_voltage if park_voltage is not None
                             else cfg.get("ff_park_gain", 0))
        self.flux_settle_time_ns = (flux_settle_time_ns if flux_settle_time_ns is not None
                                    else cfg.get("flux_settle_time", 100))
        cfg["flux_settle_time"] = self.flux_settle_time_ns
        self.reset_mode = reset_mode
        cfg["reset_mode"] = reset_mode
        self.repeat_metadata = dict(repeat_metadata or {})
        self.write_outputs = bool(write_outputs)
        if flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = flux_tail_compensation
        cfg["shots"] = self.shots

        self.data = {"qubit": self.element, "dc_vec": self.dc_vec, "shots": self.shots,
                     "park_voltage": self.park_voltage,
                     "flux_settle_time_ns": self.flux_settle_time_ns,
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
            i0, q0, i1, q1 = prog.acquire(self.soc, load_pulses=True)
        final = np.asarray(discriminate_shots(i1, q1, self.calib_params))
        if self.reset_mode == "active":
            herald_calib = dict(self.calib_params)
            herald_calib["threshold"] = self.calib_params.get(
                "ground_threshold", self.calib_params["threshold"])
            herald = np.asarray(discriminate_shots(i0, q0, herald_calib))
            keep = herald == 0
            return float(np.sum(final[keep])), int(np.sum(keep))
        return float(np.sum(final)), int(final.size)

    def _run_point(self, ff_gain, wait_us, do_pi=True, do_ff=True):
        exc, kept = self._run_point_counts(ff_gain, wait_us, do_pi=do_pi, do_ff=do_ff)
        if kept == 0:
            return np.nan
        return float(exc / kept)

    def _interleaved_populations(self, point_specs, start_time=None, live=None):
        shots = int(self.cfg.get("shots", self.shots))
        rounds = resolve_rounds(self.cfg, shots, default=self.cfg.get("t1_rounds"))
        n = len(point_specs)
        exc = np.zeros(n)
        kept = np.zeros(n)
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
        for r, reps in enumerate(reps_per_round):
            if reps <= 0:
                continue
            for idx, (g, w, dp, df) in enumerate(point_specs):
                e, k = self._run_point_counts(g, w, do_pi=dp, do_ff=df, reps=reps)
                exc[idx] += e
                kept[idx] += k
                done_units += 1
                if start_time is not None:
                    progress_counter(done_units - 1, total_units, start_time=start_time)
            if live is not None:
                with np.errstate(invalid="ignore", divide="ignore"):
                    live(r, rounds, np.where(kept > 0, exc / kept, np.nan))
        self.cfg["shots"] = saved_shots
        with np.errstate(invalid="ignore", divide="ignore"):
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
                 max_plot_t1_multiple=20.0, auto_Ts_factor=0.5, T1_probe_cfg=None,
                 run_park_T1_if_Ts_none=True, **kw):
        super().__init__(*args, **kw)
        self.min_ref_contrast = float(min_ref_contrast)
        self.max_plot_t1_multiple = max_plot_t1_multiple
        self.auto_Ts_factor = float(auto_Ts_factor)
        self.T1_probe_cfg = T1_probe_cfg
        self.data.update({"min_ref_contrast": self.min_ref_contrast,
                          "max_plot_t1_multiple": max_plot_t1_multiple,
                          "auto_Ts_factor": self.auto_Ts_factor,
                          "auto_T1_probe_cfg": T1_probe_cfg})
        if Ts_ns is None:
            if not run_park_T1_if_Ts_none:
                raise ValueError("Ts_ns is None and run_park_T1_if_Ts_none is False.")
            T1_us = self._park_T1_probe(T1_probe_cfg, "AUTO Ts")
            Ts_us = self.auto_Ts_factor * T1_us
            Ts_ns = int(np.round(Ts_us * 1e3))
            print(f"[AUTO Ts] T1_park={T1_us:.3g} us -> Ts={Ts_us:.3g} us ({Ts_ns} ns)")
            self.data.update({"auto_T1_park_us": T1_us, "auto_Ts_us": Ts_us,
                              "auto_Ts_ns": Ts_ns})
        self.Ts_ns = int(Ts_ns)
        self.data["Ts_ns"] = self.Ts_ns

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        dc_vec = self.dc_vec
        Ts_us = self.Ts_ns / 1e3
        start_time = time.time()
        specs = []
        for dc in dc_vec:
            specs.append((self.park_voltage, 0.0, False, False))
            specs.append((self.park_voltage, 0.0, True, False))
            specs.append((float(dc), Ts_us, True, True))
        pe = self._interleaved_populations(specs, start_time=start_time)
        P0 = pe[0::3]
        P1 = pe[1::3]
        Ps = pe[2::3]

        est = _compute_3pt_t1(P0, P1, Ps, self.Ts_ns,
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
                 fit_clip=(0.0, 1.0), require_monotone=False, **kw):
        super().__init__(*args, **kw)
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
            T1_us = self._park_T1_probe(self.T1_probe_cfg, "AUTO t_vec")
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
        pe = self._interleaved_populations(specs, start_time=start_time)
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
        T1_fit, T1_err, fit_ok = _fit_T1_map(ss, t_us, fit_clip=self.fit_clip,
                                             require_monotone=self.require_monotone)
        inv, inv_err = _safe_inverse_t1_us(T1_fit, T1_err)
        self.data.update({"T1_fit_us": T1_fit, "T1_fit_err_us": T1_err,
                          "inv_T1_fit_per_us": inv, "inv_T1_fit_err_per_us": inv_err,
                          "fit_success": fit_ok})
        if self.write_outputs:
            base = _csv_base_from_pickle(self.pname)
            dc_vec = self.dc_vec
            sfx = self._title_suffix()

            fig, ax = plt.subplots(constrained_layout=True)
            X, Y = np.meshgrid(t_us, dc_vec)
            pcm = ax.pcolormesh(X, Y, ss, shading="nearest")
            fig.colorbar(pcm, ax=ax, label="P(e)")
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
                "fit_success": self.data["fit_success"]}

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
