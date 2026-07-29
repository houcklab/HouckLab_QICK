import os
import inspect
import time
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import trace_extraction as trx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter, LiveFigure
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    interleaved_average, resolve_rounds, suppress_stdout)


def _build_resonator_curve(meta_dict, dc_vec, resonator_lookup_csv=None):
    dc_vec = np.asarray(dc_vec, dtype=float)
    if resonator_lookup_csv is not None:
        table = np.genfromtxt(resonator_lookup_csv, delimiter=",", skip_header=1)
        if table.ndim == 1:
            table = table[None, :]
        lut_dc = np.asarray(table[:, 0], dtype=float)
        lut_if = np.asarray(table[:, 1], dtype=float)
        order = np.argsort(lut_dc)
        lut_dc, lut_if = lut_dc[order], lut_if[order]
        if dc_vec.size and (dc_vec.min() < lut_dc.min() - 1e-9 or dc_vec.max() > lut_dc.max() + 1e-9):
            print(f"WARNING: dc_vec [{dc_vec.min():+.4f}, {dc_vec.max():+.4f}] V extends beyond the "
                  f"resonator lookup range [{lut_dc.min():+.4f}, {lut_dc.max():+.4f}] V; edge values used.")
        print(f"Using resonator dip lookup table for readout IF: {resonator_lookup_csv}")
        return np.asarray(np.round(np.interp(dc_vec, lut_dc, lut_if)), dtype=np.int64)
    fit_params = meta_dict.get("resonator_fit_parameters")
    r_if = float(meta_dict["r_IF"])
    if fit_params is None:
        return np.full(len(dc_vec), int(round(r_if)), dtype=np.int64)
    if len(fit_params) == 7:
        vals = ff.resonator_dispersive_func_hz(dc_vec, *fit_params)
    else:
        vals = ff.cosine_vs_flux(dc_vec, *fit_params)
    vals = np.asarray(vals, dtype=float)
    bad = ~np.isfinite(vals) | (vals <= 0) | (np.abs(vals - r_if) > 2e9)
    if np.any(bad):
        example = float(vals[bad][0]) / 1e6
        print(f"WARNING: resonator_fit_parameters gave {int(np.count_nonzero(bad))}/{vals.size} "
              f"out-of-range readout IF value(s) (e.g. {example:.1f} MHz); using the flat "
              f"r_IF={r_if / 1e6:.4f} MHz there. Set RESONATOR_FIT_PARAMS=None (a flat readout "
              f"is correct for a resonator that barely tunes).")
        vals = np.where(bad, r_if, vals)
    return np.asarray(np.round(vals), dtype=np.int64)


class FFStepResponseSpecProgram(RAveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                 gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
        set_readout_pulse(self, f_res)

        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=cfg["ff_hold"], ff_gain=cfg["ff_gain"],
            dt_play_us=cfg.get("dt_pulseplay", 5.0), ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
            dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.sync_all(self.us2cycles(1))

    def body(self):
        cfg = self.cfg
        ff_pulse.assert_park(self, self.ff_segs)
        rearm = cfg.get("baseline_rearm_us", 0.0)
        self.sync_all(self.us2cycles(max(rearm, 0.05)))
        ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        if cfg.get("readout_after_park", True):
            ff_pulse.play_ramp_down(self, self.ff_segs)
            self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))
            self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                         adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                         wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))
        else:
            self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                         adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                         wait=True, syncdelay=self.us2cycles(0.01))
            ff_pulse.play_ramp_down(self, self.ff_segs)
            self.sync_all(self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitFluxStepResponse(ExperimentClass):

    @staticmethod
    def find_latest_rise_decay_bump_dc_compensation_json(
        outer_folder,
        qubit,
        dc_offset=None,
        baseline_dc_offset=None,
        require_success=True,
    ):
        return fpd.find_latest_compensation_json(
            outer_folder, qubit, dc_offset=dc_offset,
            baseline_dc_offset=baseline_dc_offset, require_success=require_success)

    @staticmethod
    def load_piecewise_dc_compensation_json(json_path):
        return fpd.load_compensation_json(json_path)

    @staticmethod
    def _has_real_flux_fit_params(flux_fit_params):
        if flux_fit_params is None:
            return False
        if isinstance(flux_fit_params, dict):
            return any(value is not None for value in flux_fit_params.values())
        try:
            values = list(flux_fit_params)
        except TypeError:
            return True
        return any(value is not None for value in values)

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path='',
        outerFolder='',
        prefix='data',
        suffix='Qubit_Flux_Step_Response',
        cfg=None,
        element=None,
        f_vec=None,
        t_vec=None,
        dc_offset=None,
        shots=None,
        flux_fit_params=None,
        flux_trace_csv=None,
        flux_lookup_mode="auto",
        baseline_dc_offset=0.0,
        live_plot=True,
        fit_predistortion=False,
        fit_n_exp=1,
        fit_tail_fraction=0.25,
        fit_rise_decay_bump_dc_correction=False,
        piecewise_segment_edges_ns=None,
        piecewise_regularization=0.02,
        piecewise_final_weight=0.0,
        piecewise_min_multiplier=0.5,
        piecewise_max_multiplier=1.5,
        piecewise_correction_gain=1.0,
        piecewise_desired_response="median",
        piecewise_response_domain="voltage",
        baseline_rearm_time_ns=None,
        flux_tail_compensation=None,
        compose_with_applied_flux_tail_compensation=False,
        composition_damping=0.5,
        trace_tracking_mode="ridge",
        trace_polarity="bright",
        trace_baseline_window_mhz=25.0,
        trace_max_jump_mhz=4.0,
        trace_smoothness_penalty=0.15,
        trace_local_fit_half_window_mhz=8.0,
        trace_smoothing_window_points=17,
        trace_smoothing_polyorder=2,
        trace_use_smoothed_frequency=True,
        resonator_lookup_csv=None,
        **kw,
    ):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, **kw)
        self.element = str(element if element is not None else path)
        if f_vec is None:
            f_vec = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"],
                                int(cfg["qubit_freq_expts"])) * 1e6
        self.f_vec = np.asarray(f_vec, dtype=float)
        if t_vec is None:
            t_vec = np.asarray(cfg["t_vec_ns"], dtype=float)
        self.t_vec = np.asarray(t_vec, dtype=float)
        self.dc_offset = float(dc_offset if dc_offset is not None else cfg["dc_offset"])
        self.baseline_dc_offset = float(baseline_dc_offset)
        self.shots = int(shots if shots is not None else cfg["reps"])
        self.meta_dict = {
            "q_name": self.element,
            "r_name": f"r{self.element[1:]}" if len(self.element) > 1 else "r",
            "flux_name": f"ff_ch{cfg['ff_ch']}",
            "flux_channel": int(cfg["ff_ch"]),
            "cw_amp": cfg["qubit_gain"],
            "cw_len": float(cfg["qubit_length"]) * 1e3,
            "read_len": float(cfg["read_length"]) * 1e3,
            "reset_time": float(cfg.get("reset_time_ns", 500_000)),
            "q_LO": {"LO_freq": 0.0},
            "r_IF": float(cfg["read_pulse_freq"]) * 1e6,
        }
        self.live_plot_enabled = bool(live_plot)
        self.fit_predistortion = bool(fit_predistortion)
        self.fit_n_exp = int(fit_n_exp)
        self.fit_tail_fraction = float(fit_tail_fraction)
        self.fit_rise_decay_bump_dc_correction = bool(fit_rise_decay_bump_dc_correction)
        self.piecewise_segment_edges_ns = (
            None if piecewise_segment_edges_ns is None else [float(x) for x in piecewise_segment_edges_ns]
        )
        self.piecewise_regularization = float(piecewise_regularization)
        self.piecewise_final_weight = float(piecewise_final_weight)
        self.piecewise_min_multiplier = float(piecewise_min_multiplier)
        self.piecewise_max_multiplier = float(piecewise_max_multiplier)
        self.piecewise_correction_gain = float(piecewise_correction_gain)
        self.piecewise_desired_response = piecewise_desired_response
        self.piecewise_response_domain = str(piecewise_response_domain).strip().lower()
        if self.piecewise_response_domain not in {"frequency", "voltage"}:
            raise ValueError("piecewise_response_domain must be 'frequency' or 'voltage'.")
        self.baseline_rearm_time_ns = int(
            self.meta_dict.get("reset_time", 500_000)
            if baseline_rearm_time_ns is None
            else baseline_rearm_time_ns
        )
        self.flux_tail_compensation = flux_tail_compensation
        self.compose_with_applied_flux_tail_compensation = bool(compose_with_applied_flux_tail_compensation)
        self.composition_damping = float(composition_damping)
        self.trace_tracking_mode = str(trace_tracking_mode).strip().lower()
        if self.trace_tracking_mode not in {"ridge", "independent_slices"}:
            raise ValueError("trace_tracking_mode must be 'ridge' or 'independent_slices'.")
        self.trace_polarity = str(trace_polarity).strip().lower()
        if self.trace_polarity not in {"bright", "dark", "auto"}:
            raise ValueError("trace_polarity must be 'bright', 'dark', or 'auto'.")
        self.trace_baseline_window_mhz = float(trace_baseline_window_mhz)
        self.trace_max_jump_mhz = float(trace_max_jump_mhz)
        self.trace_smoothness_penalty = float(trace_smoothness_penalty)
        self.trace_local_fit_half_window_mhz = float(trace_local_fit_half_window_mhz)
        self.trace_smoothing_window_points = int(trace_smoothing_window_points)
        self.trace_smoothing_polyorder = int(trace_smoothing_polyorder)
        self.trace_use_smoothed_frequency = bool(trace_use_smoothed_frequency)
        self.flux_lookup_mode_requested = str(flux_lookup_mode).strip().lower()
        if self.flux_lookup_mode_requested not in {"auto", "csv", "fit"}:
            raise ValueError(
                "flux_lookup_mode must be one of: 'auto', 'csv', 'fit'."
            )

        self.flux_trace_interp = None
        self.flux_trace_csv = None
        has_real_flux_fit_params = self._has_real_flux_fit_params(flux_fit_params)
        if self.flux_lookup_mode_requested == "csv":
            if flux_trace_csv is None:
                raise ValueError(
                    "flux_lookup_mode='csv' requires flux_trace_csv to be set."
                )
            self.flux_trace_interp = self._load_trace_csv(flux_trace_csv)
            self.flux_trace_csv = flux_trace_csv
            self.flux_fit_params = (
                self._coerce_flux_fit_params(flux_fit_params) if has_real_flux_fit_params
                else None
            )
            self.flux_lookup_method = "trace_interpolation"
            print(f"Using trace interpolation from: {flux_trace_csv}")
        elif self.flux_lookup_mode_requested == "fit":
            if not has_real_flux_fit_params:
                raise ValueError(
                    "flux_lookup_mode='fit' requires flux_fit_params to be set."
                )
            self.flux_fit_params = self._coerce_flux_fit_params(flux_fit_params)
            self.flux_lookup_method = "parametric_model"
            print("Using parametric model from flux_fit_params")
        else:
            if flux_trace_csv is not None:
                self.flux_trace_interp = self._load_trace_csv(flux_trace_csv)
                self.flux_trace_csv = flux_trace_csv
                self.flux_fit_params = (
                    self._coerce_flux_fit_params(flux_fit_params) if has_real_flux_fit_params
                    else None
                )
                self.flux_lookup_method = "trace_interpolation"
                print(f"Using trace interpolation from: {flux_trace_csv}")
            else:
                if not has_real_flux_fit_params:
                    raise ValueError(
                        "Either flux_trace_csv or flux_fit_params must be provided."
                    )
                self.flux_fit_params = self._coerce_flux_fit_params(flux_fit_params)
                self.flux_lookup_method = "parametric_model"
                print("Using parametric model (no trace CSV provided)")

        self.resonator_lookup_csv = resonator_lookup_csv
        self.resonator_if = int(_build_resonator_curve(
            {**self.meta_dict, "resonator_fit_parameters": cfg.get("resonator_fit_parameters")},
            np.asarray([self.dc_offset]), resonator_lookup_csv)[0])

        self.data = {
            'qubit': self.element,
            'f_vec': self.f_vec,
            't_vec': self.t_vec,
            'dc_offset': self.dc_offset,
            'baseline_dc_offset': self.baseline_dc_offset,
            'shots': self.shots,
            'meta_dict': self.meta_dict,
            'flux_fit_params': dict(self.flux_fit_params) if self.flux_fit_params else None,
            'flux_trace_csv': self.flux_trace_csv,
            'flux_lookup_mode_requested': self.flux_lookup_mode_requested,
            'flux_lookup_method': self.flux_lookup_method,
            'live_plot': self.live_plot_enabled,
            'fit_predistortion': self.fit_predistortion,
            'fit_n_exp': self.fit_n_exp,
            'fit_tail_fraction': self.fit_tail_fraction,
            'fit_rise_decay_bump_dc_correction': self.fit_rise_decay_bump_dc_correction,
            'piecewise_segment_edges_ns': self.piecewise_segment_edges_ns,
            'piecewise_regularization': self.piecewise_regularization,
            'piecewise_final_weight': self.piecewise_final_weight,
            'piecewise_min_multiplier': self.piecewise_min_multiplier,
            'piecewise_max_multiplier': self.piecewise_max_multiplier,
            'piecewise_correction_gain': self.piecewise_correction_gain,
            'piecewise_desired_response': self.piecewise_desired_response,
            'piecewise_response_domain': self.piecewise_response_domain,
            'baseline_rearm_time_ns': self.baseline_rearm_time_ns,
            'applied_flux_tail_compensation': self.flux_tail_compensation,
            'compose_with_applied_flux_tail_compensation': self.compose_with_applied_flux_tail_compensation,
            'composition_damping': self.composition_damping,
            'trace_tracking_mode': self.trace_tracking_mode,
            'trace_polarity': self.trace_polarity,
            'trace_baseline_window_mhz': self.trace_baseline_window_mhz,
            'trace_max_jump_mhz': self.trace_max_jump_mhz,
            'trace_smoothness_penalty': self.trace_smoothness_penalty,
            'trace_local_fit_half_window_mhz': self.trace_local_fit_half_window_mhz,
            'trace_smoothing_window_points': self.trace_smoothing_window_points,
            'trace_smoothing_polyorder': self.trace_smoothing_polyorder,
            'trace_use_smoothed_frequency': self.trace_use_smoothed_frequency,
        }

    @staticmethod
    def _load_trace_csv(csv_path):
        from scipy.interpolate import interp1d
        data = np.genfromtxt(csv_path, delimiter=',', skip_header=1)
        dc_v = data[:, 0]
        freq_ghz = data[:, 2]
        valid = np.isfinite(dc_v) & np.isfinite(freq_ghz)
        dc_v = dc_v[valid]
        freq_ghz = freq_ghz[valid]
        if len(dc_v) < 5:
            raise ValueError(f"Trace CSV {csv_path} has fewer than 5 valid points.")
        order = np.argsort(dc_v)
        return interp1d(dc_v[order], freq_ghz[order], kind='cubic',
                        fill_value='extrapolate')

    @staticmethod
    def _coerce_flux_fit_params(flux_fit_params):
        required = ("EJmax", "Ec", "period_volts", "phase_offset_volts", "d")
        if isinstance(flux_fit_params, dict):
            missing = [key for key in required if key not in flux_fit_params]
            if missing:
                raise ValueError(f"Missing flux-fit parameters: {missing}")
            invalid = [key for key in required if flux_fit_params[key] is None]
            if invalid:
                raise ValueError(
                    f"Set flux_fit_params in the control script before running. Missing values for: {invalid}"
                )
            parsed = {key: float(flux_fit_params[key]) for key in required}
            if "tilt_slope" in flux_fit_params and flux_fit_params["tilt_slope"] is not None:
                parsed["tilt_slope"] = float(flux_fit_params["tilt_slope"])
            if not all(np.isfinite(parsed[key]) for key in required):
                raise ValueError("All flux_fit_params values must be finite numbers.")
            if "tilt_slope" in parsed and not np.isfinite(parsed["tilt_slope"]):
                raise ValueError("flux_fit_params tilt_slope must be a finite number.")
            return parsed
        try:
            values = list(flux_fit_params)
        except TypeError as exc:
            raise ValueError(
                "flux_fit_params must be a dict or a sequence in the order "
                "[EJmax, Ec, period_volts, phase_offset_volts, d] "
                "or [EJmax, Ec, period_volts, phase_offset_volts, d, tilt_slope]."
            ) from exc
        if len(values) not in (5, 6):
            raise ValueError(
                "flux_fit_params must have 5 or 6 values in the order "
                "[EJmax, Ec, period_volts, phase_offset_volts, d, (optional) tilt_slope]."
            )
        if any(value is None for value in values):
            raise ValueError(
                "Set flux_fit_params in the control script before running. "
                "Expected [EJmax, Ec, period_volts, phase_offset_volts, d, (optional) tilt_slope]."
            )
        parsed = {key: float(value) for key, value in zip(required, values[:5])}
        if len(values) == 6:
            parsed["tilt_slope"] = float(values[5])
        if not all(np.isfinite(parsed[key]) for key in required):
            raise ValueError("All flux_fit_params values must be finite numbers.")
        if "tilt_slope" in parsed and not np.isfinite(parsed["tilt_slope"]):
            raise ValueError("flux_fit_params tilt_slope must be a finite number.")
        return parsed

    def _evaluate_flux_model_frequency(self, dc_offset_volts):
        dc_offset_array = np.asarray(dc_offset_volts, dtype=float)
        base_frequency_ghz = np.asarray(
            fx.flux_tunable_transmon_frequency(
                x=dc_offset_array,
                EJmax=self.flux_fit_params["EJmax"],
                Ec=self.flux_fit_params["Ec"],
                period_volts=self.flux_fit_params["period_volts"],
                phase_offset_volts=self.flux_fit_params["phase_offset_volts"],
                d=self.flux_fit_params["d"],
            ),
            dtype=float,
        )
        tilt_slope = float(self.flux_fit_params.get("tilt_slope", 0.0))
        frequency_ghz = base_frequency_ghz + tilt_slope * dc_offset_array
        if np.ndim(dc_offset_volts) == 0:
            return float(frequency_ghz)
        return frequency_ghz

    def _make_save_figure(self, figsize=None):
        if self.live_plot_enabled:
            return plt.figure(figsize=figsize)
        fig = Figure(figsize=figsize)
        FigureCanvasAgg(fig)
        return fig

    def _compute_expected_frequencies(self):
        if self.flux_trace_interp is not None:
            baseline_frequency_ghz = float(self.flux_trace_interp(self.baseline_dc_offset))
            target_frequency_ghz = float(self.flux_trace_interp(self.dc_offset))
        else:
            baseline_frequency_ghz = self._evaluate_flux_model_frequency(self.baseline_dc_offset)
            target_frequency_ghz = self._evaluate_flux_model_frequency(self.dc_offset)
        frequency_margin_ghz = max(0.040, 0.50 * abs(target_frequency_ghz - baseline_frequency_ghz))
        return baseline_frequency_ghz, target_frequency_ghz, frequency_margin_ghz

    def _frequency_to_local_flux_branch(self, frequency_ghz):
        frequency_ghz = np.asarray(frequency_ghz, dtype=float)
        if self.flux_fit_params is None:
            return np.full_like(frequency_ghz, np.nan, dtype=float)

        def _sample_branch(pad_frac):
            pad = pad_frac * abs(self.dc_offset - self.baseline_dc_offset)
            lo = min(self.baseline_dc_offset, self.dc_offset) - pad
            hi = max(self.baseline_dc_offset, self.dc_offset) + pad
            v = np.linspace(lo, hi, 20_001, dtype=float)
            f = np.asarray(self._evaluate_flux_model_frequency(v), dtype=float)
            ok = np.isfinite(v) & np.isfinite(f)
            return v[ok], f[ok]

        branch_voltage, branch_frequency = _sample_branch(0.25)
        _bf_diff = np.diff(branch_frequency)
        if branch_frequency.size < 3 or not (
            np.all(_bf_diff >= -1e-9) or np.all(_bf_diff <= 1e-9)
        ):
            branch_voltage, branch_frequency = _sample_branch(0.0)
        if branch_voltage.size < 3:
            return np.full_like(frequency_ghz, np.nan, dtype=float)

        frequency_diff = np.diff(branch_frequency)
        monotonic_increasing = np.all(frequency_diff >= -1e-9)
        monotonic_decreasing = np.all(frequency_diff <= 1e-9)
        finite_frequency = np.isfinite(frequency_ghz)
        effective_dc = np.full_like(frequency_ghz, np.nan, dtype=float)

        if monotonic_increasing or monotonic_decreasing:
            if monotonic_decreasing:
                interp_frequency = branch_frequency[::-1]
                interp_voltage = branch_voltage[::-1]
            else:
                interp_frequency = branch_frequency
                interp_voltage = branch_voltage
            effective_dc[finite_frequency] = np.interp(
                frequency_ghz[finite_frequency],
                interp_frequency,
                interp_voltage,
                left=float(interp_voltage[0]),
                right=float(interp_voltage[-1]),
            )
        else:
            for flat_index in np.flatnonzero(finite_frequency):
                nearest_index = int(np.nanargmin(np.abs(branch_frequency - frequency_ghz[flat_index])))
                effective_dc[flat_index] = float(branch_voltage[nearest_index])

        return effective_dc

    def _extract_trace_from_map(self, iq_magnitude_dbm):
        baseline_frequency_ghz, target_frequency_ghz, frequency_margin_ghz = self._compute_expected_frequencies()
        expected_min_ghz = min(baseline_frequency_ghz, target_frequency_ghz) - frequency_margin_ghz
        expected_max_ghz = max(baseline_frequency_ghz, target_frequency_ghz) + frequency_margin_ghz

        frequency_axis_ghz = (self.meta_dict['q_LO']['LO_freq'] + self.f_vec) / 1e9
        expected_window_mask = (
            (frequency_axis_ghz >= expected_min_ghz)
            & (frequency_axis_ghz <= expected_max_ghz)
        )
        self.data["fit_frequency_axis_ghz"] = frequency_axis_ghz
        self.data["fit_frequency_window_mask"] = expected_window_mask.tolist()

        trace_result = trx.extract_trace_from_map(
            iq_magnitude_dbm,
            frequency_axis_ghz,
            self.t_vec,
            baseline_frequency_ghz,
            target_frequency_ghz,
            frequency_margin_ghz,
            trace_tracking_mode=self.trace_tracking_mode,
            trace_polarity=self.trace_polarity,
            trace_baseline_window_mhz=self.trace_baseline_window_mhz,
            trace_max_jump_mhz=self.trace_max_jump_mhz,
            trace_smoothness_penalty=self.trace_smoothness_penalty,
            trace_local_fit_half_window_mhz=self.trace_local_fit_half_window_mhz,
            trace_smoothing_window_points=self.trace_smoothing_window_points,
            trace_smoothing_polyorder=self.trace_smoothing_polyorder,
            trace_use_smoothed_frequency=self.trace_use_smoothed_frequency,
        )

        extracted_qubit_frequency_ghz = np.asarray(trace_result["selected_frequency_ghz"], dtype=float)
        extracted_if_frequency_hz = np.asarray(trace_result["extracted_if_frequency_hz"], dtype=float)
        extracted_fwhm_hz = np.asarray(trace_result["extracted_fwhm_hz"], dtype=float)
        extracted_supported = np.asarray(trace_result["supported"], dtype=bool)
        extraction_method = trace_result["method"]

        step_denominator_ghz = target_frequency_ghz - baseline_frequency_ghz
        if abs(step_denominator_ghz) < 1e-12:
            measured_step_response = np.full(len(self.t_vec), np.nan)
            ideal_step_response = np.full(len(self.t_vec), np.nan)
        else:
            measured_step_response = (
                extracted_qubit_frequency_ghz - baseline_frequency_ghz
            ) / step_denominator_ghz
            ideal_step_response = np.ones(len(self.t_vec), dtype=float)

        effective_dc_offset = self._frequency_to_local_flux_branch(extracted_qubit_frequency_ghz)
        voltage_step_denominator = self.dc_offset - self.baseline_dc_offset
        if abs(voltage_step_denominator) < 1e-15:
            measured_voltage_step_response = np.full(len(self.t_vec), np.nan)
            effective_dc_correction_to_target = np.full(len(self.t_vec), np.nan)
        else:
            measured_voltage_step_response = (
                effective_dc_offset - self.baseline_dc_offset
            ) / voltage_step_denominator
            effective_dc_correction_to_target = self.dc_offset - effective_dc_offset

        self.data.update({
            "baseline_frequency_ghz": baseline_frequency_ghz,
            "target_frequency_ghz": target_frequency_ghz,
            "frequency_margin_ghz": frequency_margin_ghz,
            "expected_frequency_window_ghz": [expected_min_ghz, expected_max_ghz],
            "extracted_qubit_frequency_ghz": extracted_qubit_frequency_ghz,
            "ridge_qubit_frequency_ghz": trace_result.get("ridge_frequency_ghz"),
            "local_lorentzian_qubit_frequency_ghz": trace_result.get("local_frequency_ghz"),
            "smoothed_qubit_frequency_ghz": trace_result.get("smoothed_frequency_ghz"),
            "extracted_if_frequency_hz": extracted_if_frequency_hz,
            "extracted_fwhm_hz": extracted_fwhm_hz,
            "trace_supported": extracted_supported.tolist(),
            "trace_extraction_method": extraction_method,
            "trace_selected_polarity": trace_result.get("polarity", None),
            "measured_step_response": measured_step_response,
            "measured_frequency_step_response": measured_step_response,
            "effective_dc_offset_V": effective_dc_offset,
            "measured_voltage_step_response": measured_voltage_step_response,
            "effective_dc_correction_to_target_V": effective_dc_correction_to_target,
            "ideal_step_response": ideal_step_response,
            "step_response_definition": (
                "(measured_qubit_frequency_ghz - baseline_frequency_ghz) / "
                "(target_frequency_ghz - baseline_frequency_ghz)"
            ),
            "voltage_step_response_definition": (
                "(effective_dc_offset_V - baseline_dc_offset) / "
                "(dc_offset - baseline_dc_offset)"
            ),
        })

    def _fit_predistortion_from_step_response(self):
        if not self.fit_predistortion:
            return None
        raise NotImplementedError(
            "fit_predistortion (OPX output-filter FIR/IIR taps) has no QICK analog; "
            "use fit_rise_decay_bump_dc_correction for the set_dc_offset-style "
            "piecewise tail compensation instead."
        )

    def _response_for_dc_tail_correction(self):
        if self.piecewise_response_domain == "voltage":
            return np.asarray(self.data["measured_voltage_step_response"], dtype=float)
        return np.asarray(self.data["measured_step_response"], dtype=float)

    def _dc_tail_segment_edges(self, time_zeroed_ns):
        if self.piecewise_segment_edges_ns is None:
            max_time_ns = max(float(np.nanmax(time_zeroed_ns)), 4.0)
            return list(fpd.default_dc_tail_segment_edges(max_time_ns))
        segment_edges_ns = np.asarray(self.piecewise_segment_edges_ns, dtype=float)
        segment_edges_ns = np.unique(segment_edges_ns[np.isfinite(segment_edges_ns)])
        if np.any(segment_edges_ns < 0):
            raise ValueError("piecewise_segment_edges_ns must be non-negative.")
        if segment_edges_ns.size == 0 or segment_edges_ns[0] > 0:
            segment_edges_ns = np.concatenate([[0.0], segment_edges_ns])
        return list(segment_edges_ns)

    def _fit_rise_decay_bump_dc_correction_from_step_response(self):
        if not self.fit_rise_decay_bump_dc_correction:
            return None

        response_for_correction = self._response_for_dc_tail_correction()
        finite_count = int(np.count_nonzero(np.isfinite(response_for_correction)))
        print(
            "Calculating rise-decay-bump DC compensation JSON "
            f"(domain={self.piecewise_response_domain}, finite_points={finite_count}/{len(response_for_correction)})"
        )
        try:
            bump_model = fpd.fit_rise_decay_bump_response_model(
                np.asarray(self.t_vec, dtype=float),
                response_for_correction,
                fit_tail_fraction=self.fit_tail_fraction,
            )
            if not bump_model["success"]:
                raise RuntimeError(bump_model["error"])
            segment_edges_ns = self._dc_tail_segment_edges(bump_model["time_zeroed_ns"])
            correction_kwargs = {
                "segment_edges_ns": segment_edges_ns,
                "regularization": self.piecewise_regularization,
                "final_weight": self.piecewise_final_weight,
                "normalize": False,
                "tail_fraction": self.fit_tail_fraction,
                "min_multiplier": self.piecewise_min_multiplier,
                "max_multiplier": self.piecewise_max_multiplier,
                "desired_response": self.piecewise_desired_response,
            }
            supports_correction_gain = (
                "correction_gain" in inspect.signature(fpd.calculate_piecewise_dc_correction).parameters
            )
            if supports_correction_gain:
                correction_kwargs["correction_gain"] = self.piecewise_correction_gain
            fit_result = fpd.calculate_piecewise_dc_correction(
                bump_model["time_ns"],
                bump_model["fit_response"],
                **correction_kwargs,
            )
        except Exception as exc:
            self.data["rise_decay_bump_dc_correction_fit"] = {
                "success": False,
                "error": str(exc),
                "method": "rise_decay_bump_set_dc_offset_correction",
            }
            raise RuntimeError(
                "Rise-decay-bump DC correction fit failed, so no compensation JSON can be saved. "
                f"domain={self.piecewise_response_domain}, "
                f"finite_points={finite_count}/{len(response_for_correction)}, "
                f"error={exc}"
            ) from exc

        model_note = (
            "one late exponential plus an early causal rise-decay bump; "
            "piecewise set_dc_offset correction is solved from the fitted voltage response"
        )
        fit_result.update(
            {
                "success": bool(fit_result["success"]),
                "error": fit_result["error"],
                "method": "rise_decay_bump_set_dc_offset_correction",
                "response_domain": self.piecewise_response_domain,
                "model_fit_response": bump_model["fit_response"],
                "rise_decay_bump_model": bump_model,
                "correction_prediction": fit_result["corrected_response"],
                "correction_gain": float(fit_result.get("correction_gain", self.piecewise_correction_gain)),
                "model_note": model_note,
            }
        )

        desired_level = float(
            fit_result.get(
                "desired_response_level",
                fit_result.get("desired_level", np.nan),
            )
        )
        self.data["rise_decay_bump_dc_correction_fit"] = {
            "success": bool(fit_result["success"]),
            "error": fit_result["error"],
            "method": fit_result["method"],
            "response_domain": fit_result["response_domain"],
            "model_note": model_note,
            "asymptote": float(bump_model["asymptote"]),
            "late_amplitude": float(bump_model["late_amplitude"]),
            "late_tau_ns": float(bump_model["late_tau_ns"]),
            "bump_amplitude": float(bump_model["bump_amplitude"]),
            "rise_tau_ns": float(bump_model["rise_tau_ns"]),
            "bump_tau_ns": float(bump_model["bump_tau_ns"]),
            "segment_edges_ns": fit_result["segment_edges_ns"],
            "multipliers": fit_result["multipliers"],
            "undamped_multipliers": fit_result.get("undamped_multipliers", []),
            "normalization": float(fit_result["normalization"]),
            "desired_response": fit_result.get("desired_response", None),
            "desired_response_level": desired_level,
            "rms": float(fit_result["rms"]),
            "undamped_rms": float(fit_result.get("undamped_rms", np.nan)),
            "model_rms": float(bump_model["rms"]),
            "bic": float(bump_model["bic"]),
            "min_multiplier": float(self.piecewise_min_multiplier),
            "max_multiplier": float(self.piecewise_max_multiplier),
            "correction_gain": float(fit_result.get("correction_gain", self.piecewise_correction_gain)),
            "multiplier_clipped": bool(fit_result["multiplier_clipped"]),
            "time_zeroed_ns": fit_result["time_zeroed_ns"],
            "normalized_response": fit_result["normalized_response"],
            "model_fit_response": bump_model["fit_response"],
            "corrected_response": fit_result["corrected_response"],
            "undamped_corrected_response": fit_result.get("undamped_corrected_response", []),
        }

        filter_json_path = os.path.splitext(self.iname)[0] + "_rise_decay_bump_dc_compensation.json"
        metadata = {
            "qubit": self.element,
            "flux_channel": int(self.meta_dict["flux_channel"]),
            "flux_name": self.meta_dict["flux_name"],
            "dc_offset": self.dc_offset,
            "baseline_dc_offset": self.baseline_dc_offset,
            "source_png": self.iname,
            "source": self.__class__.__name__,
            "intended_use": "rise_decay_bump_set_dc_offset_tail_compensation",
            "fit_ff_ramp_length_us": float(
                self.cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US)),
            "fit_dt_pulseplay_us": float(self.cfg.get("dt_pulseplay", 5.0)),
            "fit_dt_pulsedef_us": float(self.cfg.get("dt_pulsedef", 0.002)),
            "rise_decay_bump_response_domain": self.piecewise_response_domain,
            "rise_decay_bump_desired_response": fit_result.get("desired_response", None),
            "rise_decay_bump_desired_response_level": desired_level,
            "rise_decay_bump_correction_gain": float(
                fit_result.get("correction_gain", self.piecewise_correction_gain)
            ),
            "rise_decay_bump_late_tau_ns": float(bump_model["late_tau_ns"]),
            "rise_decay_bump_rise_tau_ns": float(bump_model["rise_tau_ns"]),
            "rise_decay_bump_bump_tau_ns": float(bump_model["bump_tau_ns"]),
            "model_note": model_note,
        }
        self.data["rise_decay_bump_dc_compensation_json"] = fpd.save_predistortion_json(
            filter_json_path,
            fit_result,
            metadata=metadata,
        )
        if not os.path.isfile(self.data["rise_decay_bump_dc_compensation_json"]):
            raise RuntimeError(
                "save_predistortion_json returned a path, but the rise-decay-bump DC compensation JSON "
                f"does not exist on disk: {self.data['rise_decay_bump_dc_compensation_json']}"
            )
        print(f"Saved rise-decay-bump DC compensation JSON: {self.data['rise_decay_bump_dc_compensation_json']}")
        return fit_result

    def _draw_live_plot(self, fig, iq_magnitude_dbm, iq_phase):
        qubit_frequency_ghz = (self.meta_dict['q_LO']['LO_freq'] + self.f_vec) / 1e9
        plt.figure(fig.number)
        plt.clf()
        ax1 = plt.subplot(211)
        ax1.set_title("Magnitude [dBm]")
        pcm1 = ax1.pcolor(self.t_vec / 1e3, qubit_frequency_ghz, iq_magnitude_dbm)
        plt.colorbar(pcm1, ax=ax1, pad=0.2, label="Magnitude [dBm]")
        ax1.set_ylabel("Qubit frequency [GHz]")
        ax1.set_xlabel("Delay time [us]")
        ax2 = plt.subplot(212)
        ax2.set_title("Phase [rad]")
        pcm2 = ax2.pcolor(self.t_vec / 1e3, qubit_frequency_ghz, iq_phase)
        plt.colorbar(pcm2, ax=ax2, pad=0.2, label="Phase [rad]")
        ax2.set_ylabel("Qubit frequency [GHz]")
        ax2.set_xlabel("Delay time [us]")
        plt.suptitle(
            f"Flux step response spectroscopy, dc offset = {self.dc_offset} DAC, "
            f"spec_amp={self.meta_dict['cw_amp']} DAC, spec_len={self.meta_dict['cw_len']} ns"
        )
        plt.pause(0.5)
        plt.tight_layout()

    def acquire(self, progress=False, plotDisp=None, figNum=1):
        cfg = self.cfg
        if plotDisp is None:
            plotDisp = self.live_plot_enabled
        cfg["start"] = self.f_vec[0] / 1e6
        cfg["expts"] = len(self.f_vec)
        cfg["step"] = ((self.f_vec[-1] - self.f_vec[0]) / max(len(self.f_vec) - 1, 1)) / 1e6
        cfg["reps"] = self.shots
        cfg["ff_gain"] = self.dc_offset
        cfg["ff_park_gain"] = self.baseline_dc_offset
        cfg["baseline_rearm_us"] = self.baseline_rearm_time_ns / 1e3
        cfg.setdefault("dt_pulseplay", 0.5)
        cfg["readout_after_park"] = bool(cfg.get("readout_after_park", False))
        cfg["read_pulse_freq"] = self.resonator_if / 1e6
        _rfp = cfg.get("resonator_fit_parameters")
        _if_src = (f"{len(_rfp)}-param RESONATOR_FIT_PARAMS" if _rfp
                   else "flat r_IF (RESONATOR_FIT_PARAMS=None)")
        if cfg["read_pulse_freq"] <= 0:
            print("*" * 78)
            print(f"WARNING: read_pulse_freq = {cfg['read_pulse_freq']:.4f} MHz is NON-PHYSICAL "
                  f"(<= 0).\n  This port uses direct digital synthesis (mixer_freq=0, cavity_LO=0), so "
                  f"read_pulse_freq\n  must be the ABSOLUTE resonator frequency in MHz (a positive value, "
                  f"~7248.95),\n  NOT an IF/offset relative to an external LO. A negative value aliases and "
                  f"the\n  readout sits off-resonance -> the qubit is invisible in spec.\n  Fix "
                  f"BaseConfig['read_pulse_freq'] in Calib/initialize.py.")
            print("*" * 78)
        print(f"[3] readout {'at PARK' if cfg['readout_after_park'] else 'AT the held flux'}, "
              f"read_pulse_freq = {cfg['read_pulse_freq']:.4f} MHz [IF source: {_if_src}] at "
              f"dc={self.dc_offset:+.0f}; qubit spec {self.f_vec[0]/1e6:.1f}-{self.f_vec[-1]/1e6:.1f} "
              f"MHz @ gain {cfg.get('qubit_gain')}")
        if self.flux_tail_compensation is not None:
            cfg["flux_tail_compensation"] = self.flux_tail_compensation
        else:
            cfg.pop("flux_tail_compensation", None)

        n_f, n_t = len(self.f_vec), len(self.t_vec)
        iq_magnitude_dbm = np.full((n_f, n_t), np.nan)
        iq_phase = np.full((n_f, n_t), np.nan)

        shots = int(self.shots)
        rounds = resolve_rounds(cfg, shots, default=cfg.get("step_rounds"))

        def run_point(idx, reps):
            cfg["ff_hold"] = float(self.t_vec[idx]) / 1e3
            cfg["reps"] = int(reps)
            with suppress_stdout():
                prog = FFStepResponseSpecProgram(self.soccfg, cfg)
                _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            return np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])

        live_fig = LiveFigure() if plotDisp else None
        start_time = time.time()

        def _fill(running):
            cube = np.asarray(running).T
            iq_magnitude_dbm[:, :] = 20 * np.log10(np.abs(cube) + 1e-12)
            iq_phase[:, :] = np.angle(cube)

        def prog_cb(done, total):
            progress_counter(done - 1, total, progress_bar=True, percent=True, start_time=start_time)

        def live_cb(rnd, running):
            _fill(running)
            if live_fig is not None:
                self._draw_live_plot(live_fig.fig, iq_magnitude_dbm, iq_phase)
                if not live_fig.is_open:
                    raise KeyboardInterrupt

        try:
            S_mean = interleaved_average(run_point, n_t, shots, rounds=rounds,
                                         live=live_cb, progress=prog_cb)
            _fill(S_mean)
        except KeyboardInterrupt:
            pass
        cfg["reps"] = shots

        self.data.update({
            "IQ_mag": iq_magnitude_dbm,
            "IQ_phase": iq_phase,
        })
        self._write_raw_sweep_csv()
        if live_fig is not None:
            live_fig.close()
        self._extract_trace_from_map(iq_magnitude_dbm)
        self._fit_predistortion_from_step_response()
        self._fit_rise_decay_bump_dc_correction_from_step_response()
        self.finalize_analysis()
        self.data.update({'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _save_step_response_panel(self, time_us, measured_step_response, ideal_step_response):
        panel_path = os.path.splitext(self.iname)[0] + "_step_response.png"
        fig = self._make_save_figure(figsize=(8, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(time_us, measured_step_response, "o-", ms=4, lw=1.2, color="tab:red", label="Measured step response")
        ax.plot(time_us, ideal_step_response, "o--", ms=3, lw=1.2, color="tab:purple", label="Ideal step response")
        ax.set_xlabel("Delay time [us]")
        ax.set_ylabel("Step response")
        ax.set_title(
            f"Step response, dc offset={self.dc_offset:.6f} DAC\n"
            "0 = baseline, 1 = ideal target, >1 = overshoot"
        )
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")

        finite_response = measured_step_response[np.isfinite(measured_step_response)]
        if finite_response.size:
            ymin = min(np.nanmin(finite_response), 0.95) - 0.01
            ymax = max(np.nanmax(finite_response), 1.0) + 0.01
            ax.set_ylim(ymin, ymax)

        fig.tight_layout()
        self.data["step_response_image"] = panel_path
        print(f"Saving standalone step response figure to: {panel_path}")
        fig.savefig(panel_path, bbox_inches="tight")
        if self.live_plot_enabled:
            plt.close(fig)
        print(f"Saved standalone step response figure: {panel_path}")

    def _write_raw_sweep_csv(self):
        raw_csv_path = os.path.splitext(self.iname)[0] + "_raw_sweep.csv"
        magnitude = np.asarray(self.data["IQ_mag"], dtype=float)
        phase = np.asarray(self.data["IQ_phase"], dtype=float)
        if magnitude.shape != phase.shape:
            raise ValueError("IQ_mag and IQ_phase must have matching shapes to save a raw sweep CSV.")
        if magnitude.shape != (len(self.f_vec), len(self.t_vec)):
            raise ValueError(
                "Unexpected step-response map shape. Expected "
                f"({len(self.f_vec)}, {len(self.t_vec)}), got {magnitude.shape}."
            )

        time_ns = np.asarray(self.t_vec, dtype=float)
        time_us = time_ns / 1e3
        if_hz = np.asarray(self.f_vec, dtype=float)
        q_lo_hz = float(self.meta_dict["q_LO"]["LO_freq"])
        frequency_hz = q_lo_hz + if_hz
        frequency_mhz = frequency_hz / 1e6
        frequency_ghz = frequency_hz / 1e9
        spec_amp_v = float(self.meta_dict.get("cw_amp", np.nan))
        spec_len_ns = float(self.meta_dict.get("cw_len", np.nan))

        freq_grid_hz = np.broadcast_to(frequency_hz[:, None], magnitude.shape)
        freq_grid_mhz = np.broadcast_to(frequency_mhz[:, None], magnitude.shape)
        freq_grid_ghz = np.broadcast_to(frequency_ghz[:, None], magnitude.shape)
        if_grid_hz = np.broadcast_to(if_hz[:, None], magnitude.shape)
        delay_grid_ns = np.broadcast_to(time_ns[None, :], magnitude.shape)
        delay_grid_us = np.broadcast_to(time_us[None, :], magnitude.shape)

        header = (
            "delay_time_us,delay_time_ns,frequency_Hz,frequency_MHz,frequency_GHz,"
            "qubit_frequency_Hz,qubit_frequency_MHz,qubit_frequency_GHz,if_frequency_Hz,"
            "q_lo_frequency_Hz,dc_offset_V,baseline_dc_offset_V,"
            "magnitude_dBm,phase_rad,spec_amp_V,spec_len_ns"
        )
        csv_data = np.column_stack(
            [
                delay_grid_us.ravel(order="C"),
                delay_grid_ns.ravel(order="C"),
                freq_grid_hz.ravel(order="C"),
                freq_grid_mhz.ravel(order="C"),
                freq_grid_ghz.ravel(order="C"),
                freq_grid_hz.ravel(order="C"),
                freq_grid_mhz.ravel(order="C"),
                freq_grid_ghz.ravel(order="C"),
                if_grid_hz.ravel(order="C"),
                np.full(magnitude.size, q_lo_hz, dtype=float),
                np.full(magnitude.size, self.dc_offset, dtype=float),
                np.full(magnitude.size, self.baseline_dc_offset, dtype=float),
                magnitude.ravel(order="C"),
                phase.ravel(order="C"),
                np.full(magnitude.size, spec_amp_v, dtype=float),
                np.full(magnitude.size, spec_len_ns, dtype=float),
            ]
        )
        np.savetxt(raw_csv_path, csv_data, delimiter=",", header=header, comments="")
        self.data["raw_sweep_csv"] = raw_csv_path
        self.data["raw_sweep_csv_path"] = raw_csv_path
        print(f"Saved raw sweep CSV: {raw_csv_path}")

    def _save_frequency_drift_outputs(self, time_us, extracted_frequency_ghz, measured_step_response, ideal_step_response):
        extracted_frequency_ghz = np.asarray(extracted_frequency_ghz, dtype=float)
        measured_step_response = np.asarray(measured_step_response, dtype=float)
        ideal_step_response = np.asarray(ideal_step_response, dtype=float)
        finite_frequency = np.isfinite(extracted_frequency_ghz)
        if not np.any(finite_frequency):
            print("Skipping frequency-drift zoom plot: no finite extracted frequencies.")
            return

        first_frequency_ghz = float(extracted_frequency_ghz[finite_frequency][0])
        median_frequency_ghz = float(np.nanmedian(extracted_frequency_ghz))
        frequency_from_first_mhz = 1e3 * (extracted_frequency_ghz - first_frequency_ghz)
        frequency_from_median_mhz = 1e3 * (extracted_frequency_ghz - median_frequency_ghz)

        csv_path = os.path.splitext(self.iname)[0] + "_frequency_drift.csv"
        trace_supported = np.asarray(
            self.data.get("trace_supported", np.ones_like(extracted_frequency_ghz, dtype=bool)),
            dtype=float,
        )
        extracted_if_frequency_hz = np.asarray(
            self.data.get("extracted_if_frequency_hz", np.full_like(extracted_frequency_ghz, np.nan)),
            dtype=float,
        )
        extracted_fwhm_hz = np.asarray(
            self.data.get("extracted_fwhm_hz", np.full_like(extracted_frequency_ghz, np.nan)),
            dtype=float,
        )
        effective_dc_offset = np.asarray(
            self.data.get("effective_dc_offset_V", np.full_like(extracted_frequency_ghz, np.nan)),
            dtype=float,
        )
        measured_voltage_step_response = np.asarray(
            self.data.get("measured_voltage_step_response", np.full_like(extracted_frequency_ghz, np.nan)),
            dtype=float,
        )
        effective_dc_correction_to_target = np.asarray(
            self.data.get("effective_dc_correction_to_target_V", np.full_like(extracted_frequency_ghz, np.nan)),
            dtype=float,
        )
        csv_data = np.column_stack(
            [
                np.asarray(time_us, dtype=float),
                np.asarray(self.t_vec, dtype=float),
                extracted_frequency_ghz,
                1e3 * extracted_frequency_ghz,
                frequency_from_first_mhz,
                frequency_from_median_mhz,
                extracted_if_frequency_hz,
                extracted_fwhm_hz,
                measured_step_response,
                measured_voltage_step_response,
                effective_dc_offset,
                effective_dc_correction_to_target,
                ideal_step_response,
                trace_supported,
            ]
        )
        csv_header = (
            "delay_time_us,delay_time_ns,extracted_qubit_frequency_GHz,"
            "extracted_qubit_frequency_MHz,frequency_minus_first_MHz,"
            "frequency_minus_median_MHz,extracted_if_frequency_Hz,"
            "extracted_fwhm_Hz,measured_step_response,"
            "measured_voltage_step_response,effective_dc_offset_V,"
            "effective_dc_correction_to_target_V,ideal_step_response,trace_supported"
        )
        np.savetxt(csv_path, csv_data, delimiter=",", header=csv_header, comments="")
        self.data["frequency_drift_csv"] = csv_path
        print(f"Saved frequency drift CSV: {csv_path}")

        zoom_path = os.path.splitext(self.iname)[0] + "_frequency_drift_zoom.png"
        fig = self._make_save_figure(figsize=(8, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(
            time_us,
            frequency_from_first_mhz,
            "o-",
            ms=4,
            lw=1.2,
            color="tab:blue",
            label="Extracted frequency",
        )
        ax.axhline(0.0, color="0.45", ls=":", lw=1.0, label="First point")
        ax.set_xlabel("Delay time [us]")
        ax.set_ylabel("Qubit frequency - first point [MHz]")
        ax.set_title(
            f"Zoomed frequency drift, dc offset={self.dc_offset:.6f} DAC\n"
            f"first = {first_frequency_ghz:.9f} GHz, median = {median_frequency_ghz:.9f} GHz"
        )
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")

        finite_drift = frequency_from_first_mhz[np.isfinite(frequency_from_first_mhz)]
        if finite_drift.size == 1:
            ax.set_ylim(float(finite_drift[0]) - 1.0, float(finite_drift[0]) + 1.0)
        elif finite_drift.size > 1:
            ymin = float(np.nanmin(finite_drift))
            ymax = float(np.nanmax(finite_drift))
            span = max(ymax - ymin, 1.0)
            pad = max(0.10 * span, 0.25)
            ax.set_ylim(ymin - pad, ymax + pad)

        fig.tight_layout()
        self.data["frequency_drift_zoom_image"] = zoom_path
        print(f"Saving zoomed frequency drift figure to: {zoom_path}")
        fig.savefig(zoom_path, bbox_inches="tight")
        if self.live_plot_enabled:
            plt.close(fig)
        print(f"Saved zoomed frequency drift figure: {zoom_path}")

    def finalize_analysis(self):
        fig = self._make_save_figure(figsize=(9, 11))
        fig.suptitle(
            f"Flux step response, dc offset={self.dc_offset:.6f} DAC, "
            f"spec_amp={self.meta_dict['cw_amp']} DAC, spec_len={self.meta_dict['cw_len']} ns"
        )

        time_us = self.t_vec / 1e3
        qubit_frequency_ghz_axis = (self.meta_dict['q_LO']['LO_freq'] + self.f_vec) / 1e9
        extracted_frequency_ghz = np.asarray(self.data["extracted_qubit_frequency_ghz"], dtype=float)
        ideal_frequency_ghz = float(self.data["target_frequency_ghz"])
        baseline_frequency_ghz = float(self.data["baseline_frequency_ghz"])
        measured_step_response = np.asarray(self.data["measured_step_response"], dtype=float)
        measured_voltage_step_response = np.asarray(
            self.data.get("measured_voltage_step_response", np.full_like(measured_step_response, np.nan)),
            dtype=float,
        )
        ideal_step_response = np.asarray(self.data["ideal_step_response"], dtype=float)
        bump_fit = self.data.get("rise_decay_bump_dc_correction_fit", {})
        piecewise_response_domain = bump_fit.get("response_domain", self.piecewise_response_domain)
        if piecewise_response_domain == "voltage":
            correction_plot_response = measured_voltage_step_response
            correction_ylabel = "Voltage-domain step response"
        else:
            correction_plot_response = measured_step_response
            correction_ylabel = "Frequency-domain step response"

        ax1 = fig.add_subplot(311)
        ax1.set_title("Magnitude [dBm]")
        pcm1 = ax1.pcolor(
            time_us,
            qubit_frequency_ghz_axis,
            self.data["IQ_mag"],
            rasterized=True,
        )
        fig.colorbar(pcm1, ax=ax1, pad=0.02, label="Magnitude [dBm]")
        ax1.plot(time_us, extracted_frequency_ghz, "w.", ms=3, label="Measured trace")
        ax1.plot(time_us, np.full_like(time_us, ideal_frequency_ghz), "k--", lw=1.4, label="Ideal target")
        ax1.set_ylabel("Qubit frequency [GHz]")
        ax1.set_xlabel("Delay time [us]")
        ax1.legend(loc="best")

        ax2 = fig.add_subplot(312)
        ax2.plot(time_us, extracted_frequency_ghz, "o", ms=3, color="tab:blue", label="Measured")
        ax2.plot(time_us, np.full_like(time_us, ideal_frequency_ghz), "--", lw=1.4, color="tab:purple", label="Ideal")
        ax2.axhline(baseline_frequency_ghz, color="0.5", ls=":", lw=1.0, label="Baseline")
        ax2.set_ylabel("Qubit frequency [GHz]")
        ax2.set_xlabel("Delay time [us]")
        ax2.set_title(
            f"Ideal target = {ideal_frequency_ghz:.6f} GHz, "
            f"baseline = {baseline_frequency_ghz:.6f} GHz"
        )
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="best")

        ax3 = fig.add_subplot(313)
        ax3.plot(
            time_us,
            correction_plot_response,
            "o-",
            ms=4,
            lw=1.2,
            color="tab:red",
            label=f"Measured {piecewise_response_domain} response",
        )
        ax3.plot(time_us, ideal_step_response, "o--", ms=3, lw=1.2, color="tab:purple", label="Ideal step response")
        if bump_fit.get("success", False):
            ax3.plot(
                np.asarray(bump_fit["time_zeroed_ns"], dtype=float) / 1e3,
                bump_fit["model_fit_response"],
                "--",
                lw=1.5,
                color="tab:green",
                alpha=0.75,
                label="Rise-decay bump fit",
            )
            ax3.plot(
                np.asarray(bump_fit["time_zeroed_ns"], dtype=float) / 1e3,
                bump_fit["corrected_response"],
                "-",
                lw=1.5,
                color="tab:green",
                label="Rise-decay bump DC correction prediction",
            )
        predistortion_fit = self.data.get("predistortion_fit", {})
        if predistortion_fit.get("success", False):
            ax3.plot(
                np.asarray(predistortion_fit["time_zeroed_ns"], dtype=float) / 1e3,
                predistortion_fit["fit_response"],
                "-",
                lw=1.5,
                color="tab:green",
                label="Exponential fit",
            )
            text = (
                f"FIR = {np.array2string(np.asarray(predistortion_fit['feedforward']), precision=6)}\n"
                f"IIR = {np.array2string(np.asarray(predistortion_fit['feedback']), precision=6)}"
            )
            ax3.text(
                0.02,
                0.05,
                text,
                transform=ax3.transAxes,
                fontsize=8,
                verticalalignment="bottom",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
            )
        ax3.set_xlabel("Delay time [us]")
        ax3.set_ylabel(correction_ylabel)
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc="best")

        finite_response = correction_plot_response[np.isfinite(correction_plot_response)]
        if finite_response.size:
            ymin = min(np.nanmin(finite_response), 0.95) - 0.01
            ymax = max(np.nanmax(finite_response), 1.0) + 0.01
            ax3.set_ylim(ymin, ymax)

        self._save_step_response_panel(time_us, correction_plot_response, ideal_step_response)
        self._save_frequency_drift_outputs(
            time_us,
            extracted_frequency_ghz,
            measured_step_response,
            ideal_step_response,
        )

        fig.tight_layout()
        self.data["summary_image"] = self.iname
        print(f"Saving flux step response figure to: {self.iname}")
        fig.savefig(self.iname, bbox_inches="tight")
        if self.live_plot_enabled:
            plt.close(fig)
        print(f"Saved flux step response figure: {self.iname}")

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        d = self.data if data is None else data.get('data', data)
        arr = {}
        for k, v in d.items():
            if isinstance(v, (dict, str)) or v is None:
                continue
            try:
                arr[k] = np.asarray(v, dtype=float)
            except (TypeError, ValueError):
                continue
        super().save_data(data=arr)
