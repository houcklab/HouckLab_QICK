"""
STEPS 2 & 4: qubit spectroscopy vs flux (full-range / long-time) -- QUA-identical.

Port of Houck-Lab-Qua m_qubit_long_time_frequency_vs_flux.py::QubitLongTimeFrequencyVsFlux
(whose machinery also serves step 2 in the all-FF workflow, as QUA's step-2 class
shares the same map+fit structure).  Behaviors mirrored exactly:

- raw (n_freq, n_dc, n_tau) magnitude(dBm)/phase cube kept and ALWAYS dumped to the
  9-column *_raw_sweep.csv (dc_offset_V,frequency_Hz,frequency_GHz,probe_time_ns,
  resonator_if_Hz,readout_resonator_if_Hz,target_resonator_if_Hz,magnitude_dBm,
  phase_rad; C-order ravel) -- the offline re-fit input
- per-(dc,tau) dip extraction: SavGol(9,2,'interp') -> argmin -> 3-point quadratic
  refine (clip +-1) -> local Lorentzian within max(10 MHz, 0.15*span) with the
  containment check; method strings 'local_dip_lorentzian'/'local_smoothed_minimum'
- per-dc robust tau average: MAD rejection with tol = max(6 MHz, 5*1.4826*MAD),
  MEAN of kept, std of kept, n_valid, source 'tau_window_mean'; zero-success
  fallback fits the tau-AVERAGED column ('avg_map_<method>')
- fit_trace artifacts: 13-column *_long_time_frequency.csv, 8-column *_trace.csv
  (consumed by the flux->freq CSV lookup), *_trace_interpolation.png,
  *_long_time_frequency_trace.png, the 2-panel summary PNG, pickle
- advanced_fit: the VERBATIM qubit_spec_trace_fit pipeline (ridge tracking +
  iterative transmon fit) run on a volts-scaled axis (DAC/30000, so the pipeline's
  volts-calibrated constants apply) with the result rescaled back to DAC units for
  print_fit_report's paste-ready FLUX_FIT_PARAMS block + *_raw_map.png /
  *_advanced_fit.png
- resonator-IF bookkeeping via the QUA _build_resonator_curve dispatch (lookup CSV
  -> 4-param cosine -> 7-param dispersive -> flat), progress_counter + live map
  with interrupt-on-close, classmethod JSON helpers with QUA validation semantics.
"""

import os
import copy
import time
import datetime

import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import qubit_spec_trace_fit as qst
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter, LiveFigure
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    interleaved_average, resolve_rounds)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
    FFStepResponseSpecProgram,
)

# DAC-gain -> pseudo-volts scale so the verbatim volts-calibrated trace-fit
# pipeline (trims, DP jump limits, transmon bounds) operates in its home regime.
DAC_TO_VOLT_SCALE = 1.0 / 30000.0


def _odd_savgol_window(requested, n):
    w = min(int(requested), n if n % 2 else n - 1)
    if w % 2 == 0:
        w -= 1
    return max(w, 3)


def _quadratic_refine_x(x, y, idx):
    if idx <= 0 or idx >= len(x) - 1:
        return float(x[idx])
    y0, y1, y2 = y[idx - 1], y[idx], y[idx + 1]
    denom = y0 - 2.0 * y1 + y2
    if not np.isfinite(denom) or abs(denom) < 1e-18:
        return float(x[idx])
    delta = 0.5 * (y0 - y2) / denom
    delta = float(np.clip(delta, -1.0, 1.0))
    return float(x[idx] + delta * (x[idx + 1] - x[idx]))


def _extract_dip_frequency_hz(f_hz, mag_dbm):
    """QUA _extract_dip_frequency_hz verbatim: SavGol -> argmin -> quadratic
    refine -> local Lorentzian with containment; returns (fr_hz, fwhm_hz, method)."""
    f_hz = np.asarray(f_hz, dtype=float)
    mag_dbm = np.asarray(mag_dbm, dtype=float)
    finite = np.isfinite(f_hz) & np.isfinite(mag_dbm)
    f_hz, mag_dbm = f_hz[finite], mag_dbm[finite]
    if f_hz.size < 7:
        raise ValueError("Need at least seven finite points to extract a dip.")
    order = np.argsort(f_hz)
    f_hz, mag_dbm = f_hz[order], mag_dbm[order]

    smooth_window = _odd_savgol_window(9, len(mag_dbm))
    if smooth_window > 3:
        mag_for_min = signal.savgol_filter(mag_dbm, smooth_window,
                                           min(2, smooth_window - 1), mode="interp")
    else:
        mag_for_min = mag_dbm
    rough_idx = int(np.nanargmin(mag_for_min))
    rough_fr_hz = _quadratic_refine_x(f_hz, mag_for_min, rough_idx)

    local_half_width_hz = max(10e6, 0.15 * (f_hz.max() - f_hz.min()))
    local = np.abs(f_hz - rough_fr_hz) <= local_half_width_hz
    if local.sum() >= 7:
        try:
            params, _ = ff.fit_resonator_dip(f_hz[local] / 1e6, mag_dbm[local])
            fr_hz = float(params["fr"]) * 1e6
            fwhm_hz = abs(float(params["fwhm"])) * 1e6
            local_min = float(f_hz[local].min())
            local_max = float(f_hz[local].max())
            if not (local_min <= fr_hz <= local_max):
                raise ValueError("Dip fit center escaped the local search window.")
            return fr_hz, fwhm_hz, "local_dip_lorentzian"
        except Exception:
            pass
    return rough_fr_hz, np.nan, "local_smoothed_minimum"


class QubitLongTimeSpecVsFlux(ExperimentClass):
    """Long-time qubit spec vs fast-flux target (QUA QubitLongTimeFrequencyVsFlux)."""

    # --- predistortion-JSON helpers (QUA classmethods, same validation) ---
    @staticmethod
    def find_latest_dc_compensation_json(outer_folder, qubit, baseline_dc_offset=None,
                                         dc_offset=None, require_success=True):
        return fpd.find_latest_compensation_json(outer_folder, qubit,
                                                 baseline_dc_offset=baseline_dc_offset,
                                                 dc_offset=dc_offset,
                                                 require_success=require_success)

    @staticmethod
    def load_dc_compensation_json(json_path):
        return fpd.load_compensation_json(json_path)

    @staticmethod
    def build_inclusive_sweep(vmin, vmax, step):
        return fpd.build_inclusive_sweep(vmin, vmax, step)

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Long_Time_Frequency_vs_Flux', cfg=None, meta_dict=None,
                 dc_vec=None, long_time_ns=5000.0, average_window_ns=100.0,
                 average_step_ns=16.0, park_voltage=None, inter_target_wait_ns=1000.0,
                 readout_after_park=True, park_readout_settle_ns=None,
                 post_readout_reset_ns=None, flux_tail_compensation=None,
                 fit_trace=True, advanced_fit=False, live_plot=True,
                 resonator_lookup_csv=None, step_tag="4", **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.step_tag = str(step_tag)
        self.element = str(path)
        self.dc_vec = np.asarray(dc_vec if dc_vec is not None else cfg["ff_gain_vec"],
                                 dtype=float)
        # QUA wait normalization: 4 ns grid, minimum 16 ns
        self.long_time_ns = max(16, int(round(float(long_time_ns) / 4.0)) * 4)
        self.average_window_ns = float(average_window_ns)
        self.average_step_ns = max(float(average_step_ns), 4.0)
        self.park_voltage = (park_voltage if park_voltage is not None
                             else cfg.get("ff_park_gain", 0))
        self.inter_target_wait_ns = float(inter_target_wait_ns)
        self.readout_after_park = bool(readout_after_park)
        self.park_readout_settle_ns = (park_readout_settle_ns if park_readout_settle_ns
                                       is not None else cfg.get("flux_settle_time", 0))
        self.post_readout_reset_ns = (post_readout_reset_ns if post_readout_reset_ns
                                      is not None else cfg.get("relax_delay", 0) * 1e3)
        self.fit_trace = bool(fit_trace)
        self.advanced_fit = bool(advanced_fit)
        self.live_plot = bool(live_plot)
        self.resonator_lookup_csv = resonator_lookup_csv
        if flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = flux_tail_compensation

    # --- QUA _build_resonator_curve dispatch (per-DC readout/target IF in Hz) ---
    def _build_resonator_curve(self):
        cfg = self.cfg
        park_if_hz = cfg["read_pulse_freq"] * 1e6
        n = len(self.dc_vec)
        target_if_hz = np.full(n, park_if_hz)
        source = "flat_r_IF"
        if self.resonator_lookup_csv:
            tbl = np.genfromtxt(self.resonator_lookup_csv, delimiter=",", names=True)
            dc_col = np.atleast_1d(tbl["dc_offset_V"])
            if_col = np.atleast_1d(tbl["resonator_dip_if_Hz"])
            target_if_hz = np.interp(self.dc_vec, dc_col, if_col)
            source = "lookup_csv"
        else:
            params = cfg.get("resonator_fit_parameters")
            if params is not None and len(params) == 7:
                target_if_hz = ff.resonator_dispersive_func_hz(self.dc_vec, *params)
                source = "dispersive_fit"
            elif params is not None and len(params) == 4:
                target_if_hz = ff.cosine_vs_flux(self.dc_vec, *params)
                source = "cosine_fit"
        readout_if_hz = np.full(n, park_if_hz) if self.readout_after_park else target_if_hz
        return readout_if_hz, target_if_hz, source

    def _probe_time_window_ns(self):
        center = self.long_time_ns
        if self.average_window_ns <= 0:
            return np.array([center], dtype=float)
        n = int(self.average_window_ns / self.average_step_ns) + 1
        pts = np.linspace(center - self.average_window_ns / 2.0,
                          center + self.average_window_ns / 2.0, max(n, 1))
        pts = np.unique(np.maximum(np.round(pts / 4.0) * 4.0, 16.0))
        return pts

    # ------------------------------------------------------------------ #
    def acquire(self, progress=False, plotDisp=None, figNum=1):
        cfg = self.cfg
        if plotDisp is None:
            plotDisp = self.live_plot
        cfg["start"] = cfg["qubit_freq_start"]
        cfg["expts"] = int(cfg["qubit_freq_expts"])
        cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / (cfg["expts"] - 1)
        fpts_mhz = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])
        dc_vec = self.dc_vec
        t_probe_ns = self._probe_time_window_ns()
        n_f, n_dc, n_tau = len(fpts_mhz), len(dc_vec), len(t_probe_ns)

        readout_if_hz, target_if_hz, curve_source = self._build_resonator_curve()

        mag_dbm = np.full((n_f, n_dc, n_tau), np.nan)
        phase_rad = np.full((n_f, n_dc, n_tau), np.nan)

        # QUA-style shot-interleaved acquisition: the inner qubit-freq sweep is already
        # RAverager-interleaved on the FPGA; here we additionally interleave the OUTER
        # (dc, tau) sweep across `rounds` passes (reps ~= shots/rounds each) so slow
        # drift averages uniformly into the map rather than tilting it along the flux
        # axis.  rounds=1 = the old sequential per-point average; rounds=shots = exact.
        shots = int(cfg.get("reps", 100))
        rounds = resolve_rounds(cfg, shots, default=cfg.get("spec_rounds"))
        points = [(i_dc, k_tau) for i_dc in range(n_dc) for k_tau in range(n_tau)]

        def run_point(idx, reps):
            i_dc, k_tau = points[idx]
            cfg["ff_gain"] = float(dc_vec[i_dc])
            cfg["ff_hold"] = float(t_probe_ns[k_tau]) / 1e3
            cfg["reps"] = int(reps)
            prog = FFStepResponseSpecProgram(self.soccfg, cfg)
            _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            return np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])      # (n_f,) complex

        live = LiveFigure(figsize=(8, 6)) if plotDisp else None
        start_time = time.time()
        interrupted = False

        def _fill(running):
            # (n_points, n_f) -> (n_dc, n_tau, n_f) -> (n_f, n_dc, n_tau)
            cube = np.asarray(running).reshape(n_dc, n_tau, n_f).transpose(2, 0, 1)
            mag_dbm[:, :, :] = 20 * np.log10(np.abs(cube) + 1e-12)
            phase_rad[:, :, :] = np.angle(cube)

        def live_cb(rnd, running):
            nonlocal interrupted
            _fill(running)
            progress_counter(rnd, rounds, start_time=start_time)
            if live is None:
                return
            plt.figure(live.fig.number)
            plt.cla()
            plt.suptitle(f"Long-time qubit spec vs flux - {self.element}  "
                         f"(shot-interleaved, {rounds} rounds)")
            with np.errstate(invalid="ignore"):
                plt.pcolor(dc_vec, fpts_mhz, np.nanmean(mag_dbm, axis=2))
            plt.xlabel("Flux DC target")
            plt.ylabel("Probe freq [MHz]")
            live.refresh(pause=0.5)
            if not live.is_open:
                interrupted = True
                raise KeyboardInterrupt

        try:
            S_mean = interleaved_average(run_point, len(points), shots,
                                         rounds=rounds, live=live_cb)
            _fill(S_mean)
        except KeyboardInterrupt:
            pass
        progress_counter(rounds, rounds, start_time=start_time)
        cfg["reps"] = shots      # restore (run_point set it to the per-round rep count)
        if live is not None:
            live.close()

        self.data = {
            'qubit': self.element, 'dc_vec': dc_vec, 'f_vec': fpts_mhz,
            't_probe_ns': t_probe_ns, 'meta_dict': dict(cfg),
            'magnitude': mag_dbm, 'phase': phase_rad,
            'readout_resonator_if_Hz': readout_if_hz,
            'target_resonator_if_Hz': target_if_hz,
            'resonator_curve_source': curve_source,
            'park_voltage': self.park_voltage, 'long_time_ns': self.long_time_ns,
            'average_window_ns': self.average_window_ns,
            'average_step_ns': self.average_step_ns,
            'readout_after_park': self.readout_after_park,
            'park_readout_settle_ns': self.park_readout_settle_ns,
            'post_readout_reset_ns': self.post_readout_reset_ns,
        }
        if interrupted:
            self.pickle_data()
            return {'config': cfg, 'data': self.data}

        # ---- raw sweep CSV (ALWAYS; the offline re-fit input) ----
        raw_csv_path = os.path.splitext(self.iname)[0] + "_raw_sweep.csv"
        freq_hz = fpts_mhz * 1e6
        F, D, T = np.meshgrid(freq_hz, dc_vec, t_probe_ns, indexing="ij")
        RO = np.broadcast_to(readout_if_hz[None, :, None], mag_dbm.shape)
        TG = np.broadcast_to(target_if_hz[None, :, None], mag_dbm.shape)
        header = ("dc_offset_V,frequency_Hz,frequency_GHz,probe_time_ns,"
                  "resonator_if_Hz,readout_resonator_if_Hz,target_resonator_if_Hz,"
                  "magnitude_dBm,phase_rad")
        csv_data = np.column_stack([
            D.ravel(order="C"), F.ravel(order="C"), (F / 1e9).ravel(order="C"),
            T.ravel(order="C"), RO.ravel(order="C"), RO.ravel(order="C"),
            TG.ravel(order="C"), mag_dbm.ravel(order="C"), phase_rad.ravel(order="C"),
        ])
        np.savetxt(raw_csv_path, csv_data, delimiter=",", header=header, comments="")
        self.data['raw_sweep_csv'] = raw_csv_path
        self.data['raw_sweep_csv_path'] = raw_csv_path

        # ---- long-time frequency extraction (QUA 4a/4b verbatim) ----
        tau_fit_frequency_hz = np.full((n_dc, n_tau), np.nan)
        tau_fit_fwhm_hz = np.full((n_dc, n_tau), np.nan)
        tau_fit_method = np.empty((n_dc, n_tau), dtype=object)
        for i in range(n_dc):
            for k in range(n_tau):
                col = mag_dbm[:, i, k]
                if np.isfinite(col).sum() < 7:
                    continue
                try:
                    fr, fwhm, method = _extract_dip_frequency_hz(freq_hz, col)
                except Exception:
                    continue
                tau_fit_frequency_hz[i, k] = fr
                tau_fit_fwhm_hz[i, k] = fwhm
                tau_fit_method[i, k] = method

        long_time_frequency_hz = np.full(n_dc, np.nan)
        long_time_frequency_ghz = np.full(n_dc, np.nan)
        long_time_frequency_std_ghz = np.full(n_dc, np.nan)
        n_valid_tau_fits = np.zeros(n_dc, dtype=int)
        extraction_source = np.empty(n_dc, dtype=object)
        long_time_mag_dbm = np.nanmean(mag_dbm, axis=2)   # (n_f, n_dc)
        for i in range(n_dc):
            row = tau_fit_frequency_hz[i]
            valid = row[np.isfinite(row)]
            if valid.size:
                center = float(np.nanmedian(valid))
                mad = float(np.nanmedian(np.abs(valid - center)))
                tol_hz = max(6e6, 5 * 1.4826 * mad)
                keep = np.abs(valid - center) <= tol_hz
                if not np.any(keep):
                    keep = np.ones_like(valid, dtype=bool)
                kept = valid[keep]
                long_time_frequency_hz[i] = float(np.nanmean(kept))
                long_time_frequency_ghz[i] = long_time_frequency_hz[i] / 1e9
                long_time_frequency_std_ghz[i] = float(np.nanstd(kept) / 1e9)
                n_valid_tau_fits[i] = int(np.count_nonzero(keep))
                extraction_source[i] = "tau_window_mean"
                continue
            try:
                fr, _fw, method = _extract_dip_frequency_hz(freq_hz, long_time_mag_dbm[:, i])
                long_time_frequency_hz[i] = fr
                long_time_frequency_ghz[i] = fr / 1e9
                long_time_frequency_std_ghz[i] = np.nan
                n_valid_tau_fits[i] = 0
                extraction_source[i] = f"avg_map_{method}"
            except Exception:
                extraction_source[i] = "failed"

        self.data.update({
            'tau_fit_frequency_hz': tau_fit_frequency_hz,
            'tau_fit_fwhm_hz': tau_fit_fwhm_hz,
            'long_time_frequency_hz': long_time_frequency_hz,
            'long_time_frequency_ghz': long_time_frequency_ghz,
            'long_time_frequency_std_ghz': long_time_frequency_std_ghz,
            'n_valid_tau_fits': n_valid_tau_fits,
            'extraction_source': extraction_source.astype(str),
        })
        print(f"[{self.step_tag}] median settling flatness over flux points: "
              f"{np.nanmedian(long_time_frequency_std_ghz) * 1e3:.3f} MHz")

        if self.fit_trace:
            self._write_summary_csv()
            self._write_trace_csv()
            self._save_trace_interpolation_plot()
            self._save_frequency_trace_plot()
            self._draw_summary_plot(long_time_mag_dbm, fpts_mhz, plotDisp)

        if self.advanced_fit:
            try:
                self._run_advanced_fit(long_time_mag_dbm, fpts_mhz)
            except Exception as exc:
                print(f"[{self.step_tag}] advanced fit failed ({exc}); raw map + "
                      f"raw_sweep CSV remain for offline fitting.")

        self.data['time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    # ---- fit_trace artifacts (QUA schemas) ----
    def _write_summary_csv(self):
        import csv as _csv
        path = os.path.splitext(self.iname)[0] + "_long_time_frequency.csv"
        d = self.data
        with open(path, "w", newline="") as fobj:
            writer = _csv.DictWriter(fobj, fieldnames=[
                "dc_offset_V", "long_time_frequency_Hz", "long_time_frequency_GHz",
                "long_time_frequency_std_MHz", "n_valid_tau_fits", "extraction_source",
                "park_voltage_V", "long_time_ns", "average_window_ns", "average_step_ns",
                "readout_after_park", "park_readout_settle_ns", "post_readout_reset_ns"])
            writer.writeheader()
            for i, dc in enumerate(self.dc_vec):
                f_hz = d['long_time_frequency_hz'][i]
                std_ghz = d['long_time_frequency_std_ghz'][i]
                writer.writerow({
                    "dc_offset_V": float(dc),
                    "long_time_frequency_Hz": f_hz if np.isfinite(f_hz) else np.nan,
                    "long_time_frequency_GHz": f_hz / 1e9 if np.isfinite(f_hz) else np.nan,
                    "long_time_frequency_std_MHz": std_ghz * 1e3 if np.isfinite(std_ghz) else np.nan,
                    "n_valid_tau_fits": int(d['n_valid_tau_fits'][i]),
                    "extraction_source": d['extraction_source'][i],
                    "park_voltage_V": float(self.park_voltage),
                    "long_time_ns": int(self.long_time_ns),
                    "average_window_ns": self.average_window_ns,
                    "average_step_ns": self.average_step_ns,
                    "readout_after_park": bool(self.readout_after_park),
                    "park_readout_settle_ns": int(self.park_readout_settle_ns),
                    "post_readout_reset_ns": int(self.post_readout_reset_ns)})
        self.data['summary_csv'] = path

    def _write_trace_csv(self):
        d = self.data
        dc = np.asarray(self.dc_vec, dtype=float)
        f_hz = np.asarray(d['long_time_frequency_hz'], dtype=float)
        good = np.isfinite(dc) & np.isfinite(f_hz)
        if not np.any(good):
            return
        path = os.path.splitext(self.iname)[0] + "_trace.csv"
        header = ("dc_offset_V,trace_frequency_Hz,trace_frequency_GHz,"
                  "readout_after_park,park_voltage_V,long_time_ns,"
                  "park_readout_settle_ns,post_readout_reset_ns")
        n = good.sum()
        csv_data = np.column_stack([
            dc[good], f_hz[good], f_hz[good] / 1e9,
            np.full(n, int(self.readout_after_park)),
            np.full(n, float(self.park_voltage)),
            np.full(n, int(self.long_time_ns)),
            np.full(n, int(self.park_readout_settle_ns)),
            np.full(n, int(self.post_readout_reset_ns))])
        np.savetxt(path, csv_data, delimiter=",", header=header, comments="")
        self.data['trace_csv'] = path
        self.data['trace_csv_path'] = path

    def _save_trace_interpolation_plot(self):
        d = self.data
        dc = np.asarray(self.dc_vec, dtype=float)
        f_ghz = np.asarray(d['long_time_frequency_ghz'], dtype=float)
        good = np.isfinite(f_ghz)
        if good.sum() < 4:
            return
        from scipy.interpolate import interp1d
        path = os.path.splitext(self.iname)[0] + "_trace_interpolation.png"
        order = np.argsort(dc[good])
        xs, ys = dc[good][order], f_ghz[good][order]
        dense = np.linspace(xs.min(), xs.max(), 1000)
        try:
            interp = interp1d(xs, ys, kind="cubic")
            dense_y = interp(dense)
        except Exception:
            dense_y = np.interp(dense, xs, ys)
        fig, ax = plt.subplots(constrained_layout=True)
        ax.plot(xs, ys, "x", color="red", label="long-time frequency")
        ax.plot(dense, dense_y, "-", color="cyan", label="cubic interpolation")
        ax.set_xlabel("Flux DC target")
        ax.set_ylabel("Qubit frequency [GHz]")
        ax.set_title(f"{self.element} long-time frequency trace interpolation")
        ax.legend(loc="best", fontsize=8)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        self.data['trace_interpolation_png'] = path

    def _save_frequency_trace_plot(self):
        d = self.data
        path = os.path.splitext(self.iname)[0] + "_long_time_frequency_trace.png"
        fig, ax = plt.subplots(constrained_layout=True)
        ax.errorbar(self.dc_vec, d['long_time_frequency_ghz'],
                    yerr=d['long_time_frequency_std_ghz'], fmt=".-", capsize=2)
        ax.set_xlabel("Flux DC target")
        ax.set_ylabel("Long-time qubit frequency [GHz]")
        ax.set_title(f"{self.element} long-time frequency vs flux "
                     f"(t = {self.long_time_ns / 1e3:.3g} us)")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        self.data['frequency_trace_png'] = path

    def _draw_summary_plot(self, long_time_mag_dbm, fpts_mhz, plotDisp):
        d = self.data
        fig, axs = plt.subplots(2, 1, figsize=(9, 9), constrained_layout=True)
        pcm = axs[0].pcolormesh(self.dc_vec, fpts_mhz, long_time_mag_dbm,
                                shading="nearest")
        fig.colorbar(pcm, ax=axs[0], label="Magnitude [dBm] (tau-averaged)")
        axs[0].plot(self.dc_vec, d['long_time_frequency_ghz'] * 1e3, "r.-", ms=3, lw=0.8,
                    label="extracted trace")
        axs[0].set_xlabel("Flux DC target")
        axs[0].set_ylabel("Probe freq [MHz]")
        axs[0].set_title(f"{self.element} long-time spec vs flux")
        axs[0].legend(loc="best", fontsize=8)
        axs[1].errorbar(self.dc_vec, d['long_time_frequency_ghz'],
                        yerr=d['long_time_frequency_std_ghz'], fmt=".-", capsize=2)
        axs[1].set_xlabel("Flux DC target")
        axs[1].set_ylabel("Long-time frequency [GHz]")
        fig.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)

    # ---- advanced fit: verbatim pipeline on a volts-scaled axis ----
    def _run_advanced_fit(self, mag_dbm_2d, fpts_mhz):
        dc_scaled = self.dc_vec * DAC_TO_VOLT_SCALE
        freq_ghz = fpts_mhz / 1e3
        raw_map_png = os.path.splitext(self.iname)[0] + "_raw_map.png"
        fig, ax = plt.subplots(1, 1, figsize=(11, 6), constrained_layout=True)
        mesh = ax.pcolormesh(self.dc_vec, freq_ghz, mag_dbm_2d, shading="auto",
                             cmap="viridis")
        fig.colorbar(mesh, ax=ax, pad=0.015, label="Magnitude [dBm]")
        ax.set_xlabel("DC offset [ff_gain DAC]")
        ax.set_ylabel("Probe frequency [GHz]")
        ax.set_title(f"{self.element} raw qubit-spec map")
        fig.savefig(raw_map_png, bbox_inches="tight")
        plt.close(fig)
        self.data['raw_map_png'] = raw_map_png

        result = qst.fit_qubit_spec_map(dc_scaled, freq_ghz, mag_dbm_2d)
        overlay_png = os.path.splitext(self.iname)[0] + "_advanced_fit.png"
        qst.save_fit_overlay_png(overlay_png, dc_scaled, freq_ghz, mag_dbm_2d, result,
                                 title=f"{self.element} advanced qubit-spec fit "
                                       f"(DC axis scaled x{DAC_TO_VOLT_SCALE:g})")
        self.data['advanced_fit_png'] = overlay_png

        # rescale the result back to ff_gain DAC units before reporting/storing
        S = DAC_TO_VOLT_SCALE
        result_dac = copy.deepcopy(result)
        p = result_dac["params"]                 # [EJmax, Ec, period, offset, d, tilt]
        p[2] = p[2] / S
        p[3] = p[3] / S
        if len(p) > 5:
            p[5] = p[5] * S
        result_dac["fit_window_v"] = [v / S for v in result_dac["fit_window_v"]]
        result_dac["extrema"] = [[v / S, f, k] for v, f, k in result_dac["extrema"]]
        result_dac["dc"] = np.asarray(result_dac["dc"]) / S
        qst.print_fit_report(result_dac,
                             label=f"[{self.step_tag}] Advanced qubit-spec fit (ff_gain DAC units)")
        self.data['flux_fit_params'] = [float(v) for v in result_dac["params"]]
        self.data['advanced_fit'] = {
            'params': self.data['flux_fit_params'],
            'rms_mhz': result_dac['rms_mhz'], 'extrema': result_dac['extrema'],
            'fit_window_v': result_dac['fit_window_v'],
            'confident_frac': result_dac['confident_frac']}

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in self.data.items()
               if isinstance(v, np.ndarray) and v.dtype != object}
        super().save_data(data=arr)
