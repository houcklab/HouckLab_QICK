"""Single-shot readout with the qubit drive off: IQ cloud + telegraph statistics.

No |e> reference is prepared, so no readout fidelity is reported. Shots arrive in
acquisition order at the scheduled tProc cadence, so the record is also a uniformly
sampled time series; saved under the ModifiedRamsey key names so
analyze_ModifiedRamseyParity (fit_two_state_hmm, psd_rate_estimate) can consume it.
"""

import time

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram

from qicklab.analysis.undriven import (
    analyze_undriven_cloud,
    analyze_undriven_timeseries,
    block_average_shots,
    project_onto_axis,
)
from qicklab.core.acquisition import raw_shot_buffers
from qicklab.core.experiment import ExperimentClass
from qicklab.hardware.yoko import ramp_to


class UndrivenSingleShotProgram(AveragerProgram):
    """Readout-only single-shot program: probe the resonator, never touch the qubit."""

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        # rounds must stay 1: acc_buf is overwritten each round (Helpers/shot_buffers).
        cfg["rounds"] = 1

        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        if not cfg["ro_chs"]:
            raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
        for delay_key in ("adc_trig_offset", "relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        # Resonator tone starts at t=0 but ADC integration starts adc_trig_offset
        # later, so the tone must cover offset + window, rounded up across the
        # generator and readout clocks.
        required_tone_us = cfg["adc_trig_offset"] + cfg["readout_length"]
        cfg.setdefault("length", required_tone_us)
        if cfg["length"] < required_tone_us:
            raise ValueError(
                "cfg['length'] must cover cfg['adc_trig_offset'] + "
                f"cfg['readout_length'] ({cfg['length']} us < "
                f"{required_tone_us} us)"
            )

        self.adc_trig_offset_cycles = self.us2cycles(cfg["adc_trig_offset"])
        requested_tone_cycles = self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"])
        self.readout_window_cycles = {
            ch: self.us2cycles(cfg["readout_length"], ro_ch=ch) for ch in cfg["ro_chs"]
        }

        f_time = self.soccfg["tprocs"][0]["f_time"]
        res_f_fabric = self.soccfg["gens"][cfg["res_ch"]]["f_fabric"]
        adc_end_tproc = max(
            self.adc_trig_offset_cycles
            + self.readout_window_cycles[ch] * f_time / self.soccfg["readouts"][ch]["f_output"]
            for ch in cfg["ro_chs"]
        )
        required_tone_cycles = int(np.ceil(adc_end_tproc * res_f_fabric / f_time - 1e-12))
        self.readout_tone_cycles = max(requested_tone_cycles, required_tone_cycles)

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        self.sync_all(200)

    def body(self):
        self.sync_all()
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def acquire(self, soc, load_pulses=True, progress=False):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []
        # di_buf/dq_buf are rep-averaged in qick >=0.2.29x; acc_buf keeps the raw
        # per-shot stream in acquisition order (see Helpers/shot_buffers).
        di_buf, dq_buf = raw_shot_buffers(self)
        for i in range(len(di_buf)):
            ro_ch = self.cfg["ro_chs"][i]
            norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
            all_i.append(di_buf[i].reshape((1, self.cfg["reps"])) / norm)
            all_q.append(dq_buf[i].reshape((1, self.cfg["reps"])) / norm)
        return all_i, all_q

    def scheduled_rep_period_cycles(self):
        """Per-shot period of the emitted tProc schedule, in tProc cycles.

        Only synci immediates advance tProc time; the waiti from
        measure(wait=True) does not.
        """
        plist = self.prog_list
        start = next(i for i, x in enumerate(plist) if x.get("label") == "LOOP_J")
        end = next(i for i, x in enumerate(plist) if x["name"] == "loopnz")
        t = 0
        for inst in plist[start:end]:
            if inst["name"] == "synci":
                t += inst["args"][0]
            elif inst["name"] == "sync":
                raise RuntimeError(
                    "register-based sync inside the rep loop: the shot period "
                    "is no longer a compile-time constant, so the time axis of "
                    "the single-shot series cannot be derived from the schedule"
                )
        return int(t)

    def scheduled_rep_period_us(self):
        f_time = float(self.soccfg["tprocs"][0]["f_time"])
        return self.scheduled_rep_period_cycles() / f_time


# Cloud scalars kept per point: also the *_raw columns and the sweep summary.
_CLOUD_SCALARS = ("n_blobs", "separation_sigma", "secondary_population", "sigma_along_axis")
_CLOUD_KEYS = (
    "labels",
    "projection",
    "center",
    "cov",
    "axis",
    "axis_angle",
    "n_blobs",
    "blob_weights",
    "blob_means_proj",
    "blob_sigmas_proj",
    "blob_centers_iq",
    "separation_sigma",
    "secondary_population",
    "bic_1",
    "bic_2",
    "rms_radius",
    "sigma_along_axis",
    "sigma_across_axis",
)
# Written with a ts_ prefix; acf_fit_ok is int-cast separately.
_TS_KEYS = (
    "threshold",
    "states",
    "n_transitions",
    "n_01",
    "n_10",
    "occupancy",
    "time_in_state_us",
    "dwell_mean_us",
    "dwell_counted",
    "gamma01_hz",
    "gamma10_hz",
    "gamma_mean_hz",
    "tau_dwell_us",
    "samples_per_dwell",
    "acf_tau_corr_us",
    "acf_gamma_hz",
    "acf_amplitude",
    "acf_noise_variance",
    "acf_lags_us",
    "acf",
    "bin_sizes",
    "bin_dt_us",
    "bin_rate_hz",
    "bin_n_switches",
)
_SWEEP_TS_SCALARS = ("gamma_mean_hz", "acf_gamma_hz")


class UndrivenSingleShot(ExperimentClass):
    """Acquire + display the undriven single-shot IQ cloud and its telegraph stats.

    cfg: as SingleShotProgramFFMUX, plus optional blob_min_separation_sigma
    (default 2.0), shot_average, ts_bin_sizes, Read_Indeces, and charge_sweep.
    With shot_average > 1 the primary keys hold the AVERAGED points; the raw
    per-shot cloud is kept under *_raw.

    charge_sweep steps the yoko through voltage_start/end/step (half-open, needs
    yoko=), acquiring at each bias and returning to the starting voltage. Per-point
    records are prefixed V<k>_ in one h5 beside sweep_* summary arrays, which
    display() plots against voltage. charge_settle_s waits after each ramp.
    """

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
        yoko=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )
        self.yoko = yoko

    def _read_indices(self, n_reads):
        read_indices = self.cfg.get("Read_Indeces", None)
        if read_indices is None:
            return list(range(n_reads))
        return np.atleast_1d(read_indices).astype(int).tolist()[:n_reads]

    def _sweep_voltages(self):
        """Charge-bias points for the sweep, or None when it is switched off."""
        if not self.cfg.get("charge_sweep", False):
            return None
        if self.yoko is None:
            raise ValueError(
                "cfg['charge_sweep'] needs a yoko: UndrivenSingleShot(..., yoko=ctx.yoko)"
            )
        missing = [k for k in ("voltage_start", "voltage_end", "voltage_step") if k not in self.cfg]
        if missing:
            # rebuild_singleshot_config() drops charge_params, so these arrive
            # through US_params -> overrides rather than from the base config.
            raise ValueError(
                f"cfg['charge_sweep'] needs {missing} in the config (set them in US_params)"
            )
        if self.cfg["voltage_step"] == 0:
            raise ValueError("cfg['voltage_step'] must be non-zero")
        # half-open like np.arange: voltage_end itself is not measured
        v = np.arange(self.cfg["voltage_start"], self.cfg["voltage_end"], self.cfg["voltage_step"])
        if v.size == 0:
            raise ValueError(
                f"empty charge sweep: voltage_start={self.cfg['voltage_start']} "
                f"voltage_end={self.cfg['voltage_end']} "
                f"voltage_step={self.cfg['voltage_step']} (check the step sign)"
            )
        if np.any(np.abs(v) > 10):
            # ramp_to only rejects target > 10, so a negative typo slips past it
            raise ValueError(f"charge sweep exceeds +-10 V: {v.min()} to {v.max()}")
        return v

    def acquire(self, progress=False):
        voltages = self._sweep_voltages()
        if voltages is None:
            return self._acquire_at_bias()

        v_return = float(self.yoko.query(":SOUR:LEV?"))
        settle_s = float(self.cfg.get("charge_settle_s", 0.0))
        merged, summary = {}, {}
        # finally: an abort (error, Ctrl-C) must not leave the bias parked at an
        # arbitrary point, since every later measurement in the run would use it.
        try:
            for k, voltage in enumerate(voltages):
                print(f"[UndrivenSingleShot] charge bias {k + 1}/{len(voltages)}: {voltage:.6f} V")
                ramp_to(self.yoko, float(voltage))
                if settle_s:
                    time.sleep(settle_s)
                self.cfg["current_voltage"] = float(voltage)
                for key, val in self._acquire_at_bias()["data"].items():
                    merged[f"V{k}_{key}"] = val
                for read_index in self.results:
                    for name in _CLOUD_SCALARS:
                        summary.setdefault(f"sweep_{name}{read_index}", []).append(
                            self.results[read_index][name]
                        )
                    for name in _SWEEP_TS_SCALARS:
                        summary.setdefault(f"sweep_{name}{read_index}", []).append(
                            self.timeseries[read_index][name]
                        )
        finally:
            ramp_to(self.yoko, v_return)

        merged["sweep_voltages"] = np.asarray(voltages, dtype=float)
        merged["read_indices"] = np.asarray(sorted(self.results))
        merged.update({k: np.asarray(v, dtype=float) for k, v in summary.items()})
        # Keep the unprefixed ModifiedRamsey aliases pointing at the first bias
        # point, so an offline loader keyed on them still opens a sweep file.
        for key in (
            "shots_i",
            "shots_q",
            "shot_index",
            "shot_time_us",
            "scheduled_rep_period_us",
            "gap_indices",
        ):
            merged[key] = merged["V0_" + key]
        self.data = {"config": self.cfg, "data": merged}
        return self.data

    def _acquire_at_bias(self):
        self.data = {"config": self.cfg, "data": {}}

        prog = UndrivenSingleShotProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True)

        read_indices = self._read_indices(len(shots_i))
        min_sep = self.cfg.get("blob_min_separation_sigma", 2.0)
        n_avg = max(1, int(self.cfg.get("shot_average", 1)))
        bin_sizes = tuple(self.cfg.get("ts_bin_sizes", (1, 2, 4, 8, 16, 32, 64)))

        # sampling interval comes from the emitted tProc schedule, not a wall clock
        rep_period_us = float(prog.scheduled_rep_period_us())

        d = self.data["data"]
        d["read_indices"] = np.asarray(read_indices)
        d["scheduled_rep_period_us"] = rep_period_us
        d["shot_average"] = n_avg
        d["timeseries_dt_us"] = rep_period_us * n_avg
        # no gaps (rounds == 1); kept empty so the ModifiedRamsey loader sees one schema
        d["gap_indices"] = np.zeros(0, dtype=int)
        self.results = {}
        self.timeseries = {}

        print(
            f"[UndrivenSingleShot] shot period {rep_period_us:.3f} us "
            f"(scheduled tProc schedule), shot_average={n_avg} -> "
            f"time-series sample period {rep_period_us * n_avg:.3f} us"
        )

        for i, read_index in enumerate(read_indices):
            i_shots = np.asarray(shots_i[i][0])
            q_shots = np.asarray(shots_q[i][0])
            tag = str(read_index)

            raw = analyze_undriven_cloud(i_shots, q_shots, min_separation_sigma=min_sep)

            if n_avg > 1:
                i_ts, q_ts, idx_center, n_dropped = block_average_shots(i_shots, q_shots, n_avg)
                res = analyze_undriven_cloud(i_ts, q_ts, min_separation_sigma=min_sep)
                if n_dropped:
                    print(
                        f"    dropped {n_dropped} trailing shot(s) that do "
                        f"not fill a block of {n_avg}"
                    )
                if res["n_shots"] < 32:
                    print(
                        f"    WARNING: only {res['n_shots']} averaged points; "
                        f"the time series is too short to say much"
                    )
            else:
                i_ts, q_ts = i_shots, q_shots
                idx_center = np.arange(i_shots.size, dtype=float)
                n_dropped = 0
                res = raw

            self.results[read_index] = res

            # projection is affine, so block-averaging commutes with it: raw and
            # averaged traces share one axis, and at n_avg == 1 they are identical.
            raw_proj = (
                res["projection"]
                if n_avg == 1
                else project_onto_axis(i_shots, q_shots, res["center"], res["axis"])
            )
            ts = analyze_undriven_timeseries(
                res,
                rep_period_us * n_avg,
                raw_projection=raw_proj,
                raw_dt_us=rep_period_us,
                bin_sizes=bin_sizes,
            )
            self.timeseries[read_index] = ts

            # i/q/labels/... describe the points the blob fit saw: raw when
            # shot_average == 1, averaged otherwise.
            d["i" + tag] = i_ts
            d["q" + tag] = q_ts
            for name in _CLOUD_KEYS:
                d[name + tag] = res[name]
            for name in _CLOUD_SCALARS:
                d[name + "_raw" + tag] = raw[name]
            d["i_raw" + tag] = i_shots
            d["q_raw" + tag] = q_shots
            d["projection_raw" + tag] = raw_proj
            d["n_dropped" + tag] = n_dropped

            shot_index = np.arange(i_shots.size, dtype=float)
            d["shot_index" + tag] = shot_index
            d["shot_time_us" + tag] = shot_index * rep_period_us
            d["ts_index" + tag] = idx_center
            d["ts_time_us" + tag] = idx_center * rep_period_us

            for name in _TS_KEYS:
                d["ts_" + name + tag] = ts[name]
            d["ts_acf_fit_ok" + tag] = int(ts["acf_fit_ok"])

            self._print_read_summary(read_index, raw, res, ts, min_sep, n_avg)

        first = str(read_indices[0])
        d["shots_i"] = d["i_raw" + first]
        d["shots_q"] = d["q_raw" + first]
        d["shot_index"] = d["shot_index" + first]
        d["shot_time_us"] = d["shot_time_us" + first]

        return self.data

    def _print_read_summary(self, read_index, raw, res, ts, min_sep, n_avg):
        what = f"{n_avg}-shot averages" if n_avg > 1 else "raw shots"
        print(
            f"[UndrivenSingleShot] Read {read_index} ({what}): "
            f"N={res['n_shots']}, "
            f"center=({res['center'][0]:.3f}, {res['center'][1]:.3f}), "
            f"cloud sigma major/minor={res['sigma_along_axis']:.3f}/"
            f"{res['sigma_across_axis']:.3f}, n_blobs={res['n_blobs']}"
        )
        if n_avg > 1:
            print(
                f"    raw per-shot cloud for comparison: n_blobs="
                f"{raw['n_blobs']}, separation={raw['separation_sigma']:.2f} "
                f"sigma, sigma along axis={raw['sigma_along_axis']:.3f}"
            )
        if res["n_blobs"] == 2:
            print(
                f"    two blobs: separation={res['separation_sigma']:.2f} sigma, "
                f"secondary population={100 * res['secondary_population']:.2f}%, "
                f"BIC 1-comp={res['bic_1']:.1f} vs 2-comp={res['bic_2']:.1f}"
            )
            print(
                f"    per-blob width along axis = "
                f"{res['blob_sigmas_proj'][0]:.3f} / "
                f"{res['blob_sigmas_proj'][1]:.3f} "
                f"(weights {res['blob_weights'][0]:.3f} / "
                f"{res['blob_weights'][1]:.3f}); centers "
                f"({res['blob_centers_iq'][0][0]:.3f}, "
                f"{res['blob_centers_iq'][0][1]:.3f}) and "
                f"({res['blob_centers_iq'][1][0]:.3f}, "
                f"{res['blob_centers_iq'][1][1]:.3f})"
            )
        elif res["n_blobs"] == 1:
            print(
                f"    single blob (BIC 1-comp={res['bic_1']:.1f} vs "
                f"2-comp={res['bic_2']:.1f}, best 2-comp separation="
                f"{res['separation_sigma']:.2f} sigma < "
                f"{min_sep} sigma threshold)"
            )

        span_ms = ts["n_samples"] * ts["dt_us"] * 1e-3
        print(
            f"    time series: {ts['n_samples']} points at "
            f"{ts['dt_us']:.1f} us ({span_ms:.1f} ms total)"
        )
        if ts["n_transitions"] and np.isfinite(ts["threshold"]):
            print(
                f"    {ts['n_transitions']} threshold crossings "
                f"({ts['n_01']} up / {ts['n_10']} down), occupancy "
                f"{100 * ts['occupancy'][0]:.1f}% / "
                f"{100 * ts['occupancy'][1]:.1f}%"
            )
            print(
                f"    dwell (Markov ML) state0={ts['tau_dwell_us'][0] * 1e-3:.3f} ms, "
                f"state1={ts['tau_dwell_us'][1] * 1e-3:.3f} ms; rates "
                f"gamma01={ts['gamma01_hz']:.1f} Hz, "
                f"gamma10={ts['gamma10_hz']:.1f} Hz"
            )
        if ts["acf_fit_ok"]:
            print(
                f"    autocorrelation (threshold-free): tau_corr="
                f"{ts['acf_tau_corr_us'] * 1e-3:.3f} ms -> gamma="
                f"{ts['acf_gamma_hz']:.1f} Hz, tau_dwell="
                f"{2 * ts['acf_tau_corr_us'] * 1e-3:.3f} ms"
            )
        if ts["bin_sizes"].size:
            sweep = ", ".join(f"{b}:{r:.1f}Hz" for b, r in zip(ts["bin_sizes"], ts["bin_rate_hz"]))
            print(f"    switch rate vs shots averaged -> {sweep}")
        for w in ts["warnings"]:
            print(f"    WARNING: {w}")

    @staticmethod
    def _time_unit(span_us):
        if span_us >= 1e6:
            return "s", 1e-6
        if span_us >= 1e3:
            return "ms", 1e-3
        return "us", 1.0

    def display(
        self, data=None, plotDisp=False, figNum=1, ran=None, max_trace_points=200_000, **kwargs
    ):
        if data is None:
            data = self.data
        d = data["data"]
        if "sweep_voltages" in d:
            return self._display_charge_sweep(d, plotDisp, figNum)

        read_indices = [int(r) for r in np.atleast_1d(d["read_indices"])]
        n_rows = len(read_indices)
        n_avg = int(np.asarray(d.get("shot_average", 1)))
        rep_period_us = float(np.asarray(d.get("scheduled_rep_period_us", np.nan)))

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig = plt.figure(figNum, figsize=(13.5, 8.4 * n_rows))
        gs = fig.add_gridspec(2 * n_rows, 6, height_ratios=[1.15, 1.0] * n_rows)

        for row, read_index in enumerate(read_indices):
            tag = str(read_index)
            i_shots = np.asarray(d["i" + tag])
            q_shots = np.asarray(d["q" + tag])
            labels = np.asarray(d["labels" + tag])
            proj = np.asarray(d["projection" + tag])
            center = np.asarray(d["center" + tag])
            centers_iq = np.asarray(d["blob_centers_iq" + tag])
            weights = np.asarray(d["blob_weights" + tag])
            means = np.asarray(d["blob_means_proj" + tag])
            sigmas = np.asarray(d["blob_sigmas_proj" + tag])
            n_blobs = int(np.asarray(d["n_blobs" + tag]))
            sep_sigma = float(np.asarray(d["separation_sigma" + tag]))
            p_secondary = float(np.asarray(d["secondary_population" + tag]))
            i_raw = np.asarray(d.get("i_raw" + tag, i_shots))
            q_raw = np.asarray(d.get("q_raw" + tag, q_shots))
            raw_proj = np.asarray(d.get("projection_raw" + tag, proj))

            avg_label = f"{n_avg}-shot averages" if n_avg > 1 else "raw shots"

            ax = fig.add_subplot(gs[2 * row, 0:3])
            if n_avg > 1:
                ax.plot(
                    i_raw,
                    q_raw,
                    ".",
                    markersize=2.0,
                    alpha=0.12,
                    color="0.6",
                    zorder=1,
                    label="raw shots",
                )
            if n_blobs == 2:
                for lbl, colour in ((0, "tab:blue"), (1, "tab:red")):
                    sel = labels == lbl
                    ax.plot(
                        i_shots[sel],
                        q_shots[sel],
                        ".",
                        markersize=2.5,
                        alpha=0.35,
                        color=colour,
                        zorder=2,
                        label=f"blob {lbl} ({100 * weights[lbl]:.1f}%)",
                    )
                for lbl in (0, 1):
                    if not np.any(np.isnan(centers_iq[lbl])):
                        ax.plot(
                            centers_iq[lbl][0],
                            centers_iq[lbl][1],
                            "kx",
                            markersize=11,
                            markeredgewidth=2,
                            zorder=3,
                        )
            else:
                ax.plot(
                    i_shots,
                    q_shots,
                    ".",
                    markersize=2.5,
                    alpha=0.35,
                    color="tab:blue",
                    zorder=2,
                    label=avg_label,
                )
                ax.plot(center[0], center[1], "kx", markersize=11, markeredgewidth=2, zorder=3)
            ax.legend(markerscale=4, fontsize=8)
            ax.set_xlabel("I")
            ax.set_ylabel("Q")
            # Frame on the ANALYSED points. With shot_average > 1 the raw cloud
            # is sqrt(n) wider and would squash the averaged blobs into a few
            # pixels; letting it spill outside the frame keeps them readable,
            # and the histogram panel still shows both spreads on one axis.
            if i_shots.size:
                mid_i = 0.5 * (float(i_shots.max()) + float(i_shots.min()))
                mid_q = 0.5 * (float(q_shots.max()) + float(q_shots.min()))
                half = 0.55 * max(
                    float(i_shots.max() - i_shots.min()),
                    float(q_shots.max() - q_shots.min()),
                    1e-12,
                )
                ax.set_xlim(mid_i - half, mid_i + half)
                ax.set_ylim(mid_q - half, mid_q + half)
            ax.set_aspect("equal", adjustable="box")
            ax.grid(True, alpha=0.3)
            ax.set_title(f"Read {read_index}: undriven IQ cloud (N={len(i_shots)} {avg_label})")

            ax = fig.add_subplot(gs[2 * row, 3:6])
            nbins = max(30, int(np.sqrt(max(len(proj), 1))))
            if n_avg > 1:
                ax.hist(
                    raw_proj, bins=nbins, color="0.85", density=True, label="raw shots", zorder=0
                )
            counts, edges, _ = ax.hist(
                proj, bins=nbins, color="0.6", density=True, label=avg_label, zorder=1
            )
            grid = np.linspace(edges[0], edges[-1], 500)
            if np.isfinite(means[0]) and sigmas[0] > 0:
                components = {}
                total = np.zeros_like(grid)
                for lbl in range(2):
                    if not np.isfinite(means[lbl]) or not (sigmas[lbl] > 0):
                        continue
                    comp = (
                        weights[lbl]
                        / (sigmas[lbl] * np.sqrt(2 * np.pi))
                        * np.exp(-0.5 * ((grid - means[lbl]) / sigmas[lbl]) ** 2)
                    )
                    components[lbl] = comp
                    total = total + comp
                ax.plot(
                    grid,
                    total,
                    "k-",
                    linewidth=1.6,
                    zorder=2,
                    label=f"{max(n_blobs, 1)}-Gaussian fit",
                )
                if n_blobs == 2:
                    # drawn on top of the total, which would otherwise hide the
                    # dominant component exactly
                    for lbl, colour in ((0, "tab:blue"), (1, "tab:red")):
                        if lbl in components:
                            ax.plot(
                                grid,
                                components[lbl],
                                "--",
                                linewidth=1.4,
                                color=colour,
                                zorder=3,
                                label=f"blob {lbl} ({100 * weights[lbl]:.1f}%)",
                            )
            threshold = float(np.asarray(d.get("ts_threshold" + tag, np.nan)))
            if np.isfinite(threshold):
                ax.axvline(
                    threshold,
                    color="k",
                    linestyle="--",
                    linewidth=1.2,
                    zorder=4,
                    label="decision threshold",
                )
            ax.legend(fontsize=8)
            ax.set_xlabel("projection onto principal axis")
            ax.set_ylabel("density")
            ax.grid(True, alpha=0.3)
            if n_blobs == 2:
                sub = (
                    f"2 blobs, separation {sep_sigma:.2f} sigma, secondary {100 * p_secondary:.2f}%"
                )
            elif n_blobs == 1:
                sub = "1 blob (no second blob resolved)"
            else:
                sub = "fit unavailable"
            ax.set_title(f"Read {read_index}: {sub}")

            ax = fig.add_subplot(gs[2 * row + 1, 0:4])
            self._plot_timeseries(ax, d, tag, read_index, n_avg, rep_period_us, max_trace_points)

            ax = fig.add_subplot(gs[2 * row + 1, 4:6])
            self._plot_rate_vs_bin(ax, d, tag, n_avg)

        period_txt = "unknown" if not np.isfinite(rep_period_us) else f"{rep_period_us:.1f} us"
        fig.suptitle(
            f"{self.titlename} — no qubit drive\n"
            f"readout {self.cfg['readout_length']} us @ "
            f"{self.cfg['pulse_freq']} MHz, gain {self.cfg['pulse_gain']}, "
            f"relax_delay {self.cfg['relax_delay']} us, "
            f"shot period {period_txt}, shot_average {n_avg}"
        )
        fig.tight_layout(rect=(0, 0, 1, 0.955))
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            plt.close(fig)

    def _display_charge_sweep(self, d, plotDisp, figNum):
        v = np.asarray(d["sweep_voltages"], dtype=float)
        read_indices = [int(r) for r in np.atleast_1d(d["read_indices"])]

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axes = plt.subplots(3, 1, num=figNum, figsize=(8.5, 10.0), sharex=True)
        for read_index in read_indices:
            tag = str(read_index)
            axes[0].plot(v, d["sweep_separation_sigma" + tag], "o-", label=f"read {read_index}")
            axes[1].plot(
                v,
                100 * np.asarray(d["sweep_secondary_population" + tag]),
                "o-",
                label=f"read {read_index}",
            )
            axes[2].plot(
                v, d["sweep_gamma_mean_hz" + tag], "o-", label=f"read {read_index} threshold"
            )
            axes[2].plot(v, d["sweep_acf_gamma_hz" + tag], "s--", label=f"read {read_index} ACF")
        axes[0].axhline(
            self.cfg.get("blob_min_separation_sigma", 2.0),
            color="k",
            linestyle=":",
            linewidth=1.0,
            label="2-blob threshold",
        )
        axes[0].set_ylabel("blob separation (sigma)")
        axes[1].set_ylabel("secondary population (%)")
        axes[2].set_ylabel("switch rate (Hz)")
        axes[2].set_xlabel("charge bias (V)")
        for ax in axes:
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8)

        fig.suptitle(
            f"{self.titlename} — no qubit drive, charge sweep\n"
            f"{v.size} bias points {v[0]:.4f} to {v[-1]:.4f} V, "
            f"readout {self.cfg['readout_length']} us @ "
            f"{self.cfg['pulse_freq']} MHz, gain {self.cfg['pulse_gain']}"
        )
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            plt.close(fig)

    def _plot_timeseries(self, ax, d, tag, read_index, n_avg, rep_period_us, max_points):
        t_avg_us = np.asarray(d.get("ts_time_us" + tag, np.zeros(0)))
        proj = np.asarray(d["projection" + tag])
        t_raw_us = np.asarray(d.get("shot_time_us" + tag, t_avg_us))
        raw_proj = np.asarray(d.get("projection_raw" + tag, proj))
        states = np.asarray(d.get("ts_states" + tag, np.zeros(proj.size, int)))
        threshold = float(np.asarray(d.get("ts_threshold" + tag, np.nan)))
        means = np.asarray(d["blob_means_proj" + tag])
        n_blobs = int(np.asarray(d["n_blobs" + tag]))

        if t_avg_us.size == 0 or proj.size == 0:
            ax.set_title(f"Read {read_index}: no time series")
            return

        span_us = float(t_avg_us[-1] - t_avg_us[0]) if t_avg_us.size > 1 else 0.0
        unit, scale = self._time_unit(span_us)

        # Decimate only the drawing, never the analysis.
        step_raw = max(1, raw_proj.size // max_points)
        step_avg = max(1, proj.size // max_points)

        if n_avg > 1:
            ax.plot(
                t_raw_us[::step_raw] * scale,
                raw_proj[::step_raw],
                "-",
                color="0.85",
                linewidth=0.5,
                zorder=0,
                label="raw shots",
            )
        ax.plot(
            t_avg_us[::step_avg] * scale,
            proj[::step_avg],
            "-",
            color="0.45",
            linewidth=0.7,
            zorder=1,
        )
        if n_blobs == 2 and np.isfinite(threshold):
            for lbl, colour in ((0, "tab:blue"), (1, "tab:red")):
                sel = states[::step_avg] == lbl
                ax.plot(
                    t_avg_us[::step_avg][sel] * scale,
                    proj[::step_avg][sel],
                    ".",
                    markersize=3.0,
                    alpha=0.7,
                    color=colour,
                    zorder=2,
                    label=f"blob {lbl}",
                )
                if np.isfinite(means[lbl]):
                    ax.axhline(
                        means[lbl], color=colour, linestyle=":", linewidth=1.0, alpha=0.7, zorder=1
                    )
            ax.axhline(
                threshold, color="k", linestyle="--", linewidth=1.2, zorder=3, label="threshold"
            )
        else:
            ax.plot(
                t_avg_us[::step_avg] * scale,
                proj[::step_avg],
                ".",
                markersize=3.0,
                alpha=0.6,
                color="tab:blue",
                zorder=2,
            )
        ax.legend(markerscale=3, fontsize=8, loc="upper right", ncol=2)
        ax.set_xlabel(f"time ({unit})")
        ax.set_ylabel("projection onto blob axis")
        ax.grid(True, alpha=0.3)
        # Frame on the analysed trace (same reasoning as the IQ panel): the raw
        # trace is sqrt(n_avg) noisier and would flatten the telegraph. It stays
        # drawn, spilling past the frame, so the noise it carries is still
        # obvious. Keep the threshold and both blob means inside the view.
        lo, hi = float(proj.min()), float(proj.max())
        for extra in (threshold, means[0], means[1]):
            if np.isfinite(extra):
                lo, hi = min(lo, float(extra)), max(hi, float(extra))
        pad = 0.10 * max(hi - lo, 1e-12)
        ax.set_ylim(lo - pad, hi + 2.2 * pad)  # headroom for the legend

        dt_us = rep_period_us * n_avg
        bits = [f"sample {dt_us:.0f} us"]
        n_trans = int(np.asarray(d.get("ts_n_transitions" + tag, 0)))
        if n_blobs == 2 and np.isfinite(threshold):
            tau = np.asarray(d.get("ts_tau_dwell_us" + tag, np.array([np.nan, np.nan])))
            bits.append(f"{n_trans} crossings")
            bits.append(f"dwell {tau[0] * 1e-3:.2f}/{tau[1] * 1e-3:.2f} ms")
        else:
            bits.append("no second blob: no state assigned")
        acf_ok = bool(np.asarray(d.get("ts_acf_fit_ok" + tag, 0)))
        if acf_ok:
            tau_c = float(np.asarray(d["ts_acf_tau_corr_us" + tag]))
            bits.append(f"ACF tau_dwell {2 * tau_c * 1e-3:.2f} ms")
        ax.set_title(
            f"Read {read_index}: time series between the blobs\n" + ", ".join(bits), fontsize=10
        )

    def _plot_rate_vs_bin(self, ax, d, tag, n_avg):
        sizes = np.asarray(d.get("ts_bin_sizes" + tag, np.zeros(0)))
        rates = np.asarray(d.get("ts_bin_rate_hz" + tag, np.zeros(0)))
        if sizes.size == 0 or not np.any(np.isfinite(rates)):
            ax.text(
                0.5,
                0.5,
                "no bin-size sweep\n(blobs not resolved)",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=9,
                color="0.4",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            return
        ax.plot(sizes, rates, "o-", color="tab:purple", markersize=5)
        if n_avg in set(int(s) for s in sizes):
            k = int(np.flatnonzero(sizes == n_avg)[0])
            ax.plot(
                [n_avg],
                [rates[k]],
                "o",
                markersize=11,
                markerfacecolor="none",
                markeredgecolor="k",
                markeredgewidth=1.6,
                label=f"shot_average={n_avg}",
            )
            ax.legend(fontsize=8)
        ax.set_xscale("log", base=2)
        # A noise-dominated sweep spans decades; a linear axis then hides the
        # plateau the knob is supposed to be set from.
        good = rates[np.isfinite(rates) & (rates > 0)]
        if good.size and good.max() / good.min() > 20:
            ax.set_yscale("log")
        ax.set_xlabel("shots averaged per point")
        ax.set_ylabel("switch rate (Hz)")
        ax.grid(True, alpha=0.3, which="both")
        ax.set_title("rate vs averaging\n(plateau = real, falling = noise)", fontsize=9)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
