"""
STEP 6 of the TLS pipeline: T1 vs (fast-flux) flux -- the actual TLS spectroscopy.

QUA analog: LabCode/Experiments/Flux_Sweeps/m_swap_spec_vs_flux.py
            (T1FullCurveVsFlux, T13PointVsFlux, + wall-clock repeat helpers)
QICK model: escher FF_fromParth/mFF_T1_wPulsePreDist + FFRampHoldTest (predistorted
            fast-flux ramp-hold) + mT1_PS_sse (post-selected T1).

Physics: a two-level-system (TLS) defect sits at a fixed frequency.  When the
flux-tuned qubit crosses a TLS resonance, energy swaps into the defect and the
qubit T1 DIPS.  So we measure T1 (or 1/T1) as a function of the fast-flux target;
TLS defects show up as sharp dips in T1 (peaks in 1/T1) at specific fluxes
(equivalently qubit frequencies, via the step-4 f_q(ff_gain) map).

Per flux point the sequence is:
    herald readout (park) -> pi (park) -> ramp to target -> HOLD = the T1 wait
    (decay at the detuned point, predistorted) -> ramp back -> final readout (park)
Post-selection keeps shots that started in |g>; P(e) vs wait is fit to an
exponential T1.  A 3-point variant (P0/P1/Ps) gives a fast closed-form estimate.

Flux-axis note: as in step 4, the swept "flux target" is the fast-flux gain
``ff_gain`` (DAC units); pass a step-4 f_q(ff_gain) map to plot T1 vs qubit freq.
"""

import time

import numpy as np
import matplotlib.pyplot as plt
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import rotate_and_threshold


class FFT1Program(AveragerProgram):
    """One (flux target, wait) T1 point with herald + final single-shot readouts.

    Sequence: herald measure -> [optional pi] -> ramp to target -> hold (=wait) ->
    ramp back -> final measure.  reps single shots; two readouts per rep.
    cfg: ff_gain (target), ff_hold (wait us), do_pi (bool).
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = cfg["shots"]
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   gen_ch=cfg["qubit_ch"])

        # pi pulse (gaussian arb by default)
        style = cfg.get("qubit_pulse_style", "arb")
        if style == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="flat_top", freq=qubit_freq, phase=0,
                                     gain=cfg["qubit_pi_gain"], waveform="qubit",
                                     length=self.us2cycles(cfg["flat_top_length"]))
        else:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                     gain=cfg["qubit_pi_gain"], waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=max(cfg["ff_hold"], cfg.get("dt_pulseplay", 5.0)),
            ff_gain=cfg["ff_gain"], dt_play_us=cfg.get("dt_pulseplay", 5.0),
            ramp_us=cfg.get("ff_ramp_length", 0.02), dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.assert_park(self, self.ff_segs)
        # herald readout (post-selection reference) at park
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg.get("herald_delay", 0.5)))
        # prepare |e>
        if cfg.get("do_pi", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        # decay at the detuned flux point during the hold (= wait)
        ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))
        ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(cfg.get("pre_meas_delay", 0.1)))
        # final readout at park
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        super().acquire(soc, load_pulses=load_pulses, readouts_per_experiment=2,
                        progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        raw = np.array(self.get_raw())  # [ro, expts=1, reps, readouts=2, IQ]
        i0 = raw[0, 0, :, 0, 0] / length
        q0 = raw[0, 0, :, 0, 1] / length
        i1 = raw[0, 0, :, 1, 0] / length
        q1 = raw[0, 0, :, 1, 1] / length
        return i0, q0, i1, q1


def _pe_postselected(i0, q0, i1, q1, calib_params, post_select=True):
    """Excited-state population of the FINAL shot, optionally post-selected on the
    herald being ground."""
    final = rotate_and_threshold(i1, q1, calib_params)
    if not post_select:
        return float(np.mean(final))
    herald = rotate_and_threshold(i0, q0, calib_params)
    keep = herald == 0
    if keep.sum() == 0:
        return np.nan
    return float(np.mean(final[keep]))


# --------------------------------------------------------------------------- #
class _T1VsFluxBase(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='T1_vs_Flux', cfg=None, meta_dict=None, calib_params=None,
                 ff_gain_to_freq=None, post_select=True, repeat_metadata=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.calib_params = calib_params if calib_params is not None else cfg.get("calib_params")
        if self.calib_params is None:
            raise ValueError("T1-vs-flux needs calib_params from step 5 (SingleShot1Q).")
        self.ff_gain_to_freq = ff_gain_to_freq   # optional callable ff_gain -> f_q GHz
        self.post_select = post_select
        self.repeat_metadata = repeat_metadata

    def _ff_gain_vec(self):
        cfg = self.cfg
        if "ff_gain_vec" in cfg:
            return np.asarray(cfg["ff_gain_vec"], dtype=float)
        return np.linspace(cfg["ff_gain_start"], cfg["ff_gain_stop"], int(cfg["ff_gain_num"]))

    def _run_point(self, ff_gain, wait_us, do_pi=True):
        cfg = self.cfg
        cfg["ff_gain"] = float(ff_gain)
        cfg["ff_hold"] = float(wait_us)
        cfg["do_pi"] = bool(do_pi)
        prog = FFT1Program(self.soccfg, cfg)
        i0, q0, i1, q1 = prog.acquire(self.soc, load_pulses=True)
        return _pe_postselected(i0, q0, i1, q1, self.calib_params, self.post_select)

    def _freq_axis(self, ff_gains):
        if self.ff_gain_to_freq is None:
            return None
        return np.array([self.ff_gain_to_freq(g) for g in ff_gains])


class T1FullCurveVsFlux(_T1VsFluxBase):
    """Full T1 decay curve at each fast-flux target; the robust TLS scan.

    cfg keys: ff_gain_vec (DAC), wait_vec_us (T1 delay grid), shots, qubit_pi_gain.
    """

    def _wait_vec(self):
        cfg = self.cfg
        if "wait_vec_us" in cfg:
            return np.asarray(cfg["wait_vec_us"], dtype=float)
        return np.geomspace(max(cfg["t_min_us"], 0.05), cfg["t_max_us"], int(cfg["t_points"]))

    def acquire(self, progress=False, plotDisp=False, figNum=1, write_outputs=True):
        ff_gains = self._ff_gain_vec()
        waits = self._wait_vec()
        pe = np.full((len(ff_gains), len(waits)), np.nan)
        T1 = np.full(len(ff_gains), np.nan)
        T1_err = np.full(len(ff_gains), np.nan)

        start = time.time()
        for i, g in enumerate(ff_gains):
            for k, w in enumerate(waits):
                pe[i, k] = self._run_point(g, w, do_pi=True)
            pars, perr = ff.fit_T1(waits, pe[i, :])
            if pars is not None:
                T1[i] = pars['T1']
                T1_err[i] = perr['T1'] if perr else np.nan
            if i == 0:
                print(f"[6] ~{(time.time()-start)*len(ff_gains)/60:.1f} min for "
                      f"{len(ff_gains)} flux x {len(waits)} waits")

        inv_T1 = np.where(np.isfinite(T1) & (T1 > 0), 1.0 / T1, np.nan)
        freq = self._freq_axis(ff_gains)
        data = {'config': self.cfg, 'data': {
            'ff_gains': ff_gains, 'wait_vec_us': waits, 'pe': pe,
            'T1_us': T1, 'T1_err_us': T1_err, 'inv_T1_per_us': inv_T1,
            'qubit_freq_ghz': freq, 'repeat_metadata': self.repeat_metadata}}
        self.data = data
        if write_outputs:
            self._write_csv(data)
            self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def _write_csv(self, data):
        d = data['data']
        summ = self.iname[:-4] + "_full_t1_summary.csv"
        cols = [d['ff_gains'], d['T1_us'], d['T1_err_us'], d['inv_T1_per_us']]
        hdr = "ff_gain,T1_us,T1_err_us,inv_T1_per_us"
        if d['qubit_freq_ghz'] is not None:
            cols = [d['ff_gains'], d['qubit_freq_ghz']] + cols[1:]
            hdr = "ff_gain,qubit_freq_ghz,T1_us,T1_err_us,inv_T1_per_us"
        np.savetxt(summ, np.column_stack(cols), delimiter=",", header=hdr, comments="")
        data['data']['summary_csv'] = summ
        print(f"[6] T1-vs-flux summary CSV: {summ}")

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        x = d['qubit_freq_ghz'] if d['qubit_freq_ghz'] is not None else d['ff_gains']
        xlabel = "Qubit frequency (GHz)" if d['qubit_freq_ghz'] is not None else "Fast-flux gain (DAC)"
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(9, 8), num=figNum)
        axs[0].plot(x, d['T1_us'], 'k.-')
        axs[0].set_ylabel("T1 (us)"); axs[0].set_xlabel(xlabel)
        axs[0].set_title("T1 vs flux (TLS dips)")
        axs[1].plot(x, d['inv_T1_per_us'], 'r.-')
        axs[1].set_ylabel("1/T1 (1/us)"); axs[1].set_xlabel(xlabel)
        axs[1].set_title("1/T1 vs flux (TLS peaks)")
        plt.tight_layout()
        plt.savefig(self.iname)
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            fig.clf(); plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in data['data'].items()
               if not isinstance(v, (str, dict)) and v is not None}
        super().save_data(data=arr)


class T13PointVsFlux(_T1VsFluxBase):
    """Fast 3-point T1 estimate at each fast-flux target (P0/P1/Ps closed form).

    T1 = -Ts / ln((Ps - P0)/(P1 - P0)).  cfg: ff_gain_vec, Ts_us, shots, qubit_pi_gain.
    If Ts_us is None, a park T1 probe picks Ts = auto_Ts_factor * T1_park
    (QUA _auto_choose_Ts_via_park_T1 beat; knobs: auto_Ts_factor, T1_probe_cfg,
    run_park_T1_if_Ts_none).
    """

    def _auto_Ts_from_park_T1(self):
        """Measure T1 at the park point and return auto_Ts_factor * T1_park (us)."""
        cfg = self.cfg
        probe = dict(shots_T1=1000, t_min_us=1.0, t_max_us=300.0, t_points=71)
        probe.update(cfg.get("T1_probe_cfg") or {})
        park = float(cfg.get("ff_park_gain", 0))
        shots_saved = cfg["shots"]
        cfg["shots"] = int(probe["shots_T1"])
        waits = np.geomspace(max(probe["t_min_us"], 0.05), probe["t_max_us"],
                             int(probe["t_points"]))
        print(f"[6] Ts_us is None -> park T1 probe ({len(waits)} waits x "
              f"{cfg['shots']} shots at ff_gain={park:g}) ...")
        pe = np.array([self._run_point(park, w, do_pi=True) for w in waits])
        cfg["shots"] = shots_saved
        pars, _ = ff.fit_T1(waits, pe)
        if pars is None:
            raise RuntimeError("Park T1 probe fit failed; set Ts_us explicitly.")
        t1_park = float(pars['T1'])
        factor = float(cfg.get("auto_Ts_factor", 0.5))
        Ts = factor * t1_park
        print(f"[6] park T1 = {t1_park:.1f} us -> Ts = {factor:g} x T1_park = {Ts:.1f} us")
        self._park_probe = {'t1_park_us': t1_park, 'waits_us': waits, 'pe': pe}
        return Ts

    def acquire(self, progress=False, plotDisp=False, figNum=1, write_outputs=True):
        cfg = self.cfg
        ff_gains = self._ff_gain_vec()
        if cfg.get("Ts_us") is None:
            if not cfg.get("run_park_T1_if_Ts_none", True):
                raise RuntimeError("Ts_us is None and run_park_T1_if_Ts_none is False.")
            cfg["Ts_us"] = self._auto_Ts_from_park_T1()
        Ts = float(cfg["Ts_us"])
        min_contrast = float(cfg.get("min_ref_contrast", 0.05))
        P0 = np.full(len(ff_gains), np.nan)
        P1 = np.full(len(ff_gains), np.nan)
        Ps = np.full(len(ff_gains), np.nan)
        T1 = np.full(len(ff_gains), np.nan)

        # QUA convention: the P0/P1 references are measured AT PARK (no detuned
        # hold) each flux point -- interleaved so they track drift; only Ps decays
        # at the target.  The minimal park dwell is one dt_pulseplay segment.
        park = float(cfg.get("ff_park_gain", 0))
        w0 = cfg.get("dt_pulseplay", 5.0)
        start = time.time()
        for i, g in enumerate(ff_gains):
            P0[i] = self._run_point(park, w0, do_pi=False)  # thermal ref (park, no pi)
            P1[i] = self._run_point(park, w0, do_pi=True)   # pi ref (park, ~zero delay)
            Ps[i] = self._run_point(g, Ts, do_pi=True)      # pi + hold Ts at target
            contrast = P1[i] - P0[i]
            if abs(contrast) >= min_contrast:
                pe = (Ps[i] - P0[i]) / contrast
                if 0 < pe < 1:
                    T1[i] = -Ts / np.log(pe)
            if i == 0:
                print(f"[6] ~{(time.time()-start)*len(ff_gains)/60:.1f} min for "
                      f"{len(ff_gains)} flux x 3 points")

        inv_T1 = np.where(np.isfinite(T1) & (T1 > 0), 1.0 / T1, np.nan)
        freq = self._freq_axis(ff_gains)
        data = {'config': cfg, 'data': {
            'ff_gains': ff_gains, 'P0': P0, 'P1': P1, 'Ps': Ps, 'Ts_us': Ts,
            'T1_3pt_us': T1, 'inv_T1_3pt_per_us': inv_T1, 'qubit_freq_ghz': freq,
            't1_park_us': getattr(self, '_park_probe', {}).get('t1_park_us'),
            'repeat_metadata': self.repeat_metadata}}
        self.data = data
        if write_outputs:
            summ = self.iname[:-4] + "_3pt_summary.csv"
            cols = [ff_gains, P0, P1, Ps, T1, inv_T1]
            hdr = "ff_gain,P0,P1,Ps,T1_3pt_us,inv_T1_3pt_per_us"
            if freq is not None:
                cols = [ff_gains, freq, P0, P1, Ps, T1, inv_T1]
                hdr = "ff_gain,qubit_freq_ghz,P0,P1,Ps,T1_3pt_us,inv_T1_3pt_per_us"
            np.savetxt(summ, np.column_stack(cols), delimiter=",", header=hdr, comments="")
            data['data']['summary_csv'] = summ
            print(f"[6] 3-point T1-vs-flux summary CSV: {summ}")
            self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        x = d['qubit_freq_ghz'] if d['qubit_freq_ghz'] is not None else d['ff_gains']
        xlabel = "Qubit frequency (GHz)" if d['qubit_freq_ghz'] is not None else "Fast-flux gain (DAC)"
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(1, 1, figsize=(9, 5), num=figNum)
        ax.plot(x, d['inv_T1_3pt_per_us'], 'r.-')
        ax.set_xlabel(xlabel); ax.set_ylabel("1/T1 (1/us)")
        ax.set_title("3-point 1/T1 vs flux (TLS peaks)")
        plt.tight_layout()
        plt.savefig(self.iname)
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            fig.clf(); plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in data['data'].items()
               if not isinstance(v, (str, dict)) and v is not None}
        super().save_data(data=arr)


# --------------------------------------------------------------------------- #
#  Wall-clock repeat: rerun the flux sweep for a duration, stack into one CSV
#  (mirrors the QUA _run_one_stop_t1 / save_wall_clock_repeat_full_outputs).
# --------------------------------------------------------------------------- #
def run_wall_clock_repeat(factory, metric_key, ff_gains, csv_path,
                          duration_min=None, now_fn=None):
    """Rerun the flux sweep repeatedly (TLS drift/blink over hours), appending the
    per-run metric (e.g. inv_T1) into one accumulating CSV.

    factory()   -> an experiment instance whose .acquire() returns data.
    metric_key  -> key in data['data'] to stack (1D over ff_gains).
    now_fn      -> callable returning a float 'seconds since epoch' (injected so the
                   workflow layer/tests can control time; Date.now is unavailable in
                   some sandboxes).  Defaults to time.time.
    """
    import time as _time
    import datetime as _dt
    now_fn = now_fn or _time.time
    series_start = now_fn()
    series_iso = _dt.datetime.fromtimestamp(series_start).isoformat(timespec='seconds')
    rows = []
    run_index = 0
    while True:
        run_start = now_fn()
        run_iso = _dt.datetime.fromtimestamp(run_start).isoformat(timespec='seconds')
        elapsed_min = (run_start - series_start) / 60.0
        if duration_min is not None:
            print(f"  [6] wall-clock run {run_index + 1} (elapsed {elapsed_min:.1f} min)")
        exp = factory()
        data = exp.acquire(write_outputs=True)
        metric = np.asarray(data['data'][metric_key], dtype=float)
        for g, m in zip(ff_gains, metric):
            rows.append([run_index, run_iso, series_iso, f"{elapsed_min:.3f}",
                         f"{g:.6g}", f"{m:.8g}"])
        np.savetxt(csv_path, np.array(rows, dtype=object), delimiter=",", fmt="%s",
                   header=("wall_clock_run_index,wall_clock_run_started_at_iso,"
                           "wall_clock_series_started_at_iso,"
                           "wall_clock_elapsed_minutes_from_first_run,ff_gain,"
                           + metric_key),
                   comments="")
        print(f"  [6] one-stop CSV updated after run {run_index + 1}: {csv_path}")
        run_index += 1
        if duration_min is None or (now_fn() - series_start) >= duration_min * 60.0:
            break
    return csv_path
