import time
import datetime

import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter, LiveFigure
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    interleaved_average, resolve_rounds, suppress_stdout)


class FFTransProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        set_readout_pulse(self, f_res)
        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=max(cfg.get("ff_settle_us", 20.0), cfg.get("dt_pulseplay", 5.0)),
            ff_gain=cfg["ff_gain"], dt_play_us=cfg.get("dt_pulseplay", 5.0),
            ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US), dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.assert_park(self, self.ff_segs)
        self.sync_all(self.us2cycles(0.05))
        ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(cfg["relax_delay"]))


class TransmissionVsFFGain(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Resonator_Spec_vs_Flux', cfg=None, meta_dict=None,
                 save_resonator_lookup=True, resonator_lookup_smooth_points=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.save_resonator_lookup = bool(save_resonator_lookup)
        self.resonator_lookup_smooth_points = resonator_lookup_smooth_points

    def _freq_vec(self):
        cfg = self.cfg
        if "trans_freq_vec" in cfg:
            return np.asarray(cfg["trans_freq_vec"], dtype=float)
        return np.linspace(cfg["trans_freq_start"], cfg["trans_freq_stop"],
                           int(cfg["TransNumPoints"]))

    def _gain_vec(self):
        cfg = self.cfg
        if "ff_gain_vec" in cfg:
            return np.asarray(cfg["ff_gain_vec"], dtype=float)
        return np.linspace(cfg["ff_gain_start"], cfg["ff_gain_stop"], int(cfg["ff_gain_num"]))

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        f_vec = self._freq_vec()
        dc_vec = self._gain_vec()
        r_lo = 0.0
        qubit_lo_hz = cfg.get("qubit_freq", 0.0) * 1e6

        self.data = {'qubit': self.path, 'f_vec': f_vec, 'dc_vec': dc_vec,
                     'meta_dict': dict(cfg)}

        R = np.full((len(f_vec), len(dc_vec)), np.nan)
        phase_raw = np.full((len(f_vec), len(dc_vec)), np.nan)

        shots = int(cfg.get("reps", cfg.get("shots", 200)))
        rounds = resolve_rounds(cfg, shots, default=cfg.get("trans_rounds"))
        n_f, n_dc = len(f_vec), len(dc_vec)
        points = [(i_dc, j_f) for i_dc in range(n_dc) for j_f in range(n_f)]

        def run_point(idx, reps):
            i_dc, j_f = points[idx]
            cfg["ff_gain"] = float(dc_vec[i_dc])
            cfg["read_pulse_freq"] = float(f_vec[j_f])
            cfg["reps"] = int(reps)
            with suppress_stdout():
                prog = FFTransProgram(self.soccfg, cfg)
                res = prog.acquire(self.soc, load_pulses=True, progress=False)
            return np.array(res[0]).mean() + 1j * np.array(res[1]).mean()

        live = LiveFigure(figsize=(8, 7)) if plotDisp else None
        start_time = time.time()
        interrupted = False

        def _fill_map(running):
            Smap = np.asarray(running).reshape(n_dc, n_f).T
            R[:, :] = 20 * np.log10(np.abs(Smap) + 1e-12)
            phase_raw[:, :] = np.angle(Smap)
            self.data.update({"IQ_mag": R.copy(), "IQ_phase": phase_raw.copy()})

        def prog_cb(done, total):
            progress_counter(done - 1, total, start_time=start_time)

        def live_cb(rnd, running):
            nonlocal interrupted
            _fill_map(running)
            if live is None:
                return
            plt.figure(live.fig.number)
            if n_dc <= 1:
                plt.clf()
                plt.suptitle(f"Resonator transmission - {self.path}  "
                             f"(shot-interleaved, {rounds} rounds)")
                plt.plot(f_vec, R[:, 0])
                plt.xlabel("Readout freq [MHz]")
                plt.ylabel("Amplitude (dBm)")
            else:
                plt.subplot(211); plt.cla()
                plt.suptitle(f"Resonator spectroscopy - {self.path}  "
                             f"(shot-interleaved, {rounds} rounds)")
                plt.title(r"Amplitude (dBm)")
                plt.pcolor(dc_vec, f_vec, R)
                plt.ylabel("Readout freq [MHz]")
                plt.subplot(212); plt.cla()
                plt.title("Phase (rad)")
                plt.pcolor(dc_vec, f_vec, signal.detrend(np.unwrap(phase_raw, axis=-1), axis=-1))
                plt.xlabel("Flux bias [ff_gain DAC]")
                plt.ylabel("Readout freq [MHz]")
            live.refresh(pause=0.5)
            plt.tight_layout()
            if not live.is_open:
                interrupted = True
                raise KeyboardInterrupt

        try:
            S_mean = interleaved_average(run_point, len(points), shots,
                                         rounds=rounds, live=live_cb, progress=prog_cb)
            _fill_map(S_mean)
        except KeyboardInterrupt:
            pass
        if live is not None:
            live.close()
        if interrupted:
            self.pickle_data()
            return {'config': cfg, 'data': self.data}

        minima = np.zeros(len(dc_vec))
        for i in range(len(dc_vec)):
            minima[i] = f_vec[np.argmin(R.T[i])]

        minima_lookup, smooth_window = ff.smooth_resonator_dip_trace(
            minima, self.resonator_lookup_smooth_points)

        if len(dc_vec) <= 1:
            dip_mhz = float(minima[0])
            self.data['resonator_dip_freq_mhz'] = dip_mhz
            print(f"Resonator dip at {dip_mhz:.4f} MHz (ff_gain={float(dc_vec[0]):+.0f} DAC) "
                  f"-> set BaseConfig['read_pulse_freq'].")
            while plt.fignum_exists(num=figNum):
                figNum += 1
            plt.figure(figNum)
            plt.suptitle(f"Resonator transmission - {self.path}")
            plt.plot(f_vec, R.T[0], ".-")
            plt.axvline(dip_mhz, color="red", linestyle="--",
                        label=f"dip {dip_mhz:.4f} MHz")
            plt.xlabel("Readout freq [MHz]")
            plt.ylabel("|S21| [a.u.]")
            plt.legend(loc="best", fontsize=8)
            plt.savefig(self.iname, bbox_inches="tight")
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            self.data['time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.pickle_data()
            return {'config': cfg, 'data': self.data}

        _dip_hz = np.asarray(minima_lookup) * 1e6 + r_lo
        _imax = int(np.nanargmax(_dip_hz))
        _imin = int(np.nanargmin(_dip_hz))
        print(f"Resonator dip MAX freq {_dip_hz[_imax] / 1e9:.6f} GHz at DC = {dc_vec[_imax]:+.5f} DAC")
        print(f"Resonator dip MIN freq {_dip_hz[_imin] / 1e9:.6f} GHz at DC = {dc_vec[_imin]:+.5f} DAC")
        print(f"DC scan range: {float(np.min(dc_vec)):+.5f} .. {float(np.max(dc_vec)):+.5f} DAC")

        if self.save_resonator_lookup:
            import os
            lookup_csv_path = os.path.splitext(self.iname)[0] + "_resonator_lookup.csv"
            np.savetxt(lookup_csv_path,
                       np.column_stack([dc_vec, minima_lookup * 1e6,
                                        minima_lookup * 1e6 + r_lo, minima * 1e6]),
                       delimiter=",",
                       header="dc_offset_V,resonator_dip_if_Hz,resonator_dip_freq_Hz,resonator_dip_if_raw_Hz",
                       comments="")
            self.data['resonator_lookup_csv'] = lookup_csv_path
            self.data['resonator_lookup_dc_V'] = dc_vec
            self.data['resonator_lookup_dip_if_Hz'] = minima_lookup * 1e6
            self.data['resonator_lookup_dip_if_raw_Hz'] = minima * 1e6
            self.data['resonator_lookup_smooth_points'] = int(smooth_window)
            print(f"Saved resonator dip lookup table: {lookup_csv_path}"
                  + (f" (smoothed, window={smooth_window} pts)" if smooth_window
                     else " (raw, no smoothing)"))

            fig_lut = plt.figure()
            plt.suptitle(f"Resonator dip lookup (measured) - {self.path}")
            plt.pcolor(dc_vec, f_vec, R)
            plt.plot(dc_vec, minima, "x", color="red", markersize=3,
                     label="Measured dips (raw)")
            order = np.argsort(dc_vec)
            lut_dc, lut_if = dc_vec[order], np.asarray(minima_lookup)[order]
            dense_dc = np.linspace(lut_dc.min(), lut_dc.max(), max(1000, lut_dc.size))
            dense_if = np.interp(dense_dc, lut_dc, lut_if)
            plt.plot(dense_dc, dense_if, "-", color="cyan", linewidth=1.4,
                     label=(f"Smoothed lookup (w={smooth_window} pts, used downstream)"
                            if smooth_window else "Interpolated lookup (used downstream)"))
            plt.xlabel("Flux bias [ff_gain DAC]")
            plt.ylabel("Readout freq [MHz]")
            plt.legend(loc="best", fontsize=8)
            lookup_png_path = os.path.splitext(self.iname)[0] + "_resonator_lookup.png"
            fig_lut.savefig(lookup_png_path, bbox_inches="tight")
            plt.close(fig_lut)
            self.data['resonator_lookup_png'] = lookup_png_path
            print(f"Saved resonator dip lookup plot: {lookup_png_path}")

        fit_params, initial_guess = ff.cosine_fit_qua(dc_vec, minima)
        print("initial guesses", ','.join(map(str, initial_guess)))
        print("cosine fit parameters (legacy)", ','.join(map(str, fit_params)))
        self.data['resonator_fit_parameters_cosine'] = [float(v) for v in fit_params]
        fitted_curve = ff.cosine_vs_flux(dc_vec, *fit_params)

        dispersive_params = None
        try:
            period_seed = 1.0 / fit_params[1]
            dispersive_params, disp_rms_hz = ff.fit_resonator_dispersive(
                dc_vec, minima_lookup * 1e6, r_lo, qubit_lo_hz,
                cfg.get('anharmonicity', -0.2e9) or -0.2e9, period_seed)
            print("dispersive fit parameters [f_bare_Hz,g_Hz,EJmax_GHz,Ec_GHz,period_V,offset_V,d]")
            print(','.join(map(str, dispersive_params)))
            print(f"dispersive fit RMS = {disp_rms_hz / 1e3:.1f} kHz (all params free)")
            self.data['resonator_fit_parameters_dispersive'] = dispersive_params
        except Exception as exc:
            print(f"Dispersive resonator fit failed ({exc}); cosine fit (legacy) remains available.")

        while plt.fignum_exists(num=figNum):
            figNum += 1
        plt.figure(figNum)
        plt.suptitle(f"Resonator spectroscopy - {self.path}")
        plt.pcolor(dc_vec, f_vec, R)
        plt.plot(dc_vec, fitted_curve, label="Cosine fit (legacy)", color="black")
        if dispersive_params is not None:
            dispersive_curve = (ff.resonator_dispersive_func_hz(dc_vec, *dispersive_params)
                                - r_lo) / 1e6
            plt.plot(dc_vec, dispersive_curve, "--", color="red", label="Dispersive model fit")
        plt.xlabel("Flux bias [ff_gain DAC]")
        plt.ylabel("Readout freq [MHz]")
        plt.legend(loc="best", fontsize=8)
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)

        self.data['time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        arr = {k: v for k, v in data['data'].items()
               if not isinstance(v, (str, dict)) and v is not None}
        super().save_data(data=arr)
