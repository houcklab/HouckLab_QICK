import os
import copy
import time
import datetime

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import qubit_spec_trace_fit as qst
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter, LiveFigure
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    interleaved_average, resolve_rounds, suppress_stdout)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
    FFStepResponseSpecProgram,
)

DAC_TO_VOLT_SCALE = 1.0 / 30000.0


class QubitLongTimeSpecVsFlux(ExperimentClass):

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
                 advanced_fit=False, live_plot=True,
                 resonator_lookup_csv=None, step_tag="4", **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.step_tag = str(step_tag)
        self.element = str(path)
        self.dc_vec = np.asarray(dc_vec if dc_vec is not None else cfg["ff_gain_vec"],
                                 dtype=float)
        self.long_time_ns = max(16, int(round(float(long_time_ns) / 4.0)) * 4)
        self.average_window_ns = float(average_window_ns)
        self.average_step_ns = max(float(average_step_ns), 4.0)
        self.park_voltage = (park_voltage if park_voltage is not None
                             else cfg.get("ff_park_gain", 0))
        self.inter_target_wait_ns = float(inter_target_wait_ns)
        self.readout_after_park = bool(readout_after_park)
        self.park_readout_settle_ns = (float(park_readout_settle_ns)
                                       if park_readout_settle_ns is not None
                                       else ff_pulse.flux_settle_us(cfg) * 1e3)
        cfg["flux_settle_time_us"] = self.park_readout_settle_ns / 1e3
        self.post_readout_reset_ns = (post_readout_reset_ns if post_readout_reset_ns
                                      is not None else cfg.get("relax_delay", 0) * 1e3)
        self.advanced_fit = bool(advanced_fit)
        self.live_plot = bool(live_plot)
        self.resonator_lookup_csv = resonator_lookup_csv
        if flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = flux_tail_compensation

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
        target_if_hz = np.asarray(target_if_hz, dtype=float)
        bad = (~np.isfinite(target_if_hz) | (target_if_hz <= 0)
               | (np.abs(target_if_hz - park_if_hz) > 2e9))
        if np.any(bad):
            example = float(target_if_hz[bad][0]) / 1e6
            print(f"WARNING: {source} gave {int(np.count_nonzero(bad))}/{target_if_hz.size} "
                  f"out-of-range readout IF value(s) (e.g. {example:.1f} MHz); using the flat "
                  f"r_IF={park_if_hz / 1e6:.4f} MHz there. Set RESONATOR_FIT_PARAMS=None (a flat "
                  f"readout is correct if the resonator barely tunes).")
            target_if_hz = np.where(bad, park_if_hz, target_if_hz)
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

    def acquire(self, progress=False, plotDisp=None, figNum=1):
        cfg = self.cfg
        if plotDisp is None:
            plotDisp = self.live_plot
        cfg["start"] = cfg["qubit_freq_start"]
        cfg["expts"] = int(cfg["qubit_freq_expts"])
        if "qubit_freq_step" in cfg:
            cfg["step"] = float(cfg["qubit_freq_step"])
            fpts_mhz = cfg["qubit_freq_start"] + cfg["step"] * np.arange(cfg["expts"])
        else:
            cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / (cfg["expts"] - 1)
            fpts_mhz = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])
        dc_vec = self.dc_vec
        t_probe_ns = self._probe_time_window_ns()
        n_f, n_dc, n_tau = len(fpts_mhz), len(dc_vec), len(t_probe_ns)

        readout_if_hz, target_if_hz, curve_source = self._build_resonator_curve()
        cfg["readout_after_park"] = bool(self.readout_after_park)

        mag_dbm = np.full((n_f, n_dc, n_tau), np.nan)
        phase_rad = np.full((n_f, n_dc, n_tau), np.nan)

        shots = int(cfg.get("reps", 100))
        rounds = resolve_rounds(cfg, shots, default=cfg.get("spec_rounds"))
        points = [(i_dc, k_tau) for i_dc in range(n_dc) for k_tau in range(n_tau)]

        def run_point(idx, reps):
            i_dc, k_tau = points[idx]
            cfg["ff_gain"] = float(dc_vec[i_dc])
            cfg["ff_hold"] = float(t_probe_ns[k_tau]) / 1e3
            cfg["reps"] = int(reps)
            cfg["read_pulse_freq"] = float(readout_if_hz[i_dc]) / 1e6
            with suppress_stdout():
                prog = FFStepResponseSpecProgram(self.soccfg, cfg)
                _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            return np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])

        live = LiveFigure(figsize=(8, 6)) if plotDisp else None
        start_time = time.time()
        interrupted = False

        def _fill(running):
            cube = np.asarray(running).reshape(n_dc, n_tau, n_f).transpose(2, 0, 1)
            mag_dbm[:, :, :] = 20 * np.log10(np.abs(cube) + 1e-12)
            phase_rad[:, :, :] = np.angle(cube)

        def prog_cb(done, total):
            progress_counter(done - 1, total, start_time=start_time)

        def live_cb(rnd, running):
            nonlocal interrupted
            _fill(running)
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
                                         rounds=rounds, live=live_cb, progress=prog_cb)
            _fill(S_mean)
        except KeyboardInterrupt:
            pass
        cfg["reps"] = shots
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

        long_time_mag_dbm = np.nanmean(mag_dbm, axis=2)

        if self.advanced_fit:
            try:
                self._run_advanced_fit(long_time_mag_dbm, fpts_mhz)
            except Exception as exc:
                print(f"[{self.step_tag}] advanced fit failed ({exc}); raw map + "
                      f"raw_sweep CSV remain for offline fitting.")

        self.data['time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _run_advanced_fit(self, mag_dbm_2d, fpts_mhz):
        dc_scaled = self.dc_vec * DAC_TO_VOLT_SCALE
        freq_ghz = fpts_mhz / 1e3
        raw_map_png = os.path.splitext(self.iname)[0] + "_raw_map.png"
        phase_2d = np.nanmean(np.asarray(self.data['phase'], dtype=float), axis=2)
        amp_n = mag_dbm_2d - np.nanmedian(mag_dbm_2d, axis=0, keepdims=True)
        ph_n = phase_2d - np.nanmedian(phase_2d, axis=0, keepdims=True)
        fig, ax = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True,
                               sharex=True, sharey=True)
        for a, M, lbl, title in (
                (ax[0, 0], mag_dbm_2d, "Magnitude [dBm]", "amplitude (raw)"),
                (ax[0, 1], amp_n, "Magnitude [dBm] (per-flux normalized)", "amplitude (background removed)"),
                (ax[1, 0], phase_2d, "Phase [rad]", "phase (raw)"),
                (ax[1, 1], ph_n, "Phase [rad] (per-flux normalized)", "phase (background removed)")):
            mesh = a.pcolormesh(self.dc_vec, freq_ghz, M, shading="auto", cmap="viridis")
            fig.colorbar(mesh, ax=a, pad=0.015, label=lbl)
            a.set_title(title)
        for a in ax[1, :]:
            a.set_xlabel("DC offset [ff_gain DAC]")
        for a in ax[:, 0]:
            a.set_ylabel("Probe frequency [GHz]")
        fig.suptitle(f"{self.element} raw qubit-spec map")
        fig.savefig(raw_map_png, bbox_inches="tight")
        plt.close(fig)
        self.data['raw_map_png'] = raw_map_png

        result = qst.fit_qubit_spec_map(dc_scaled, freq_ghz, mag_dbm_2d)
        S = DAC_TO_VOLT_SCALE
        result_dac = copy.deepcopy(result)
        p = result_dac["params"]
        p[2] = p[2] / S
        p[3] = p[3] / S
        if len(p) > 5:
            p[5] = p[5] * S
        result_dac["fit_window_v"] = [v / S for v in result_dac["fit_window_v"]]
        result_dac["extrema"] = [[v / S, f, k] for v, f, k in result_dac["extrema"]]
        result_dac["dc"] = np.asarray(result_dac["dc"]) / S
        overlay_png = os.path.splitext(self.iname)[0] + "_advanced_fit.png"
        qst.save_fit_overlay_png(overlay_png, self.dc_vec, freq_ghz, mag_dbm_2d, result_dac,
                                 title=f"{self.element} advanced qubit-spec fit",
                                 xlabel="DC offset [ff_gain DAC]")
        self.data['advanced_fit_png'] = overlay_png
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
