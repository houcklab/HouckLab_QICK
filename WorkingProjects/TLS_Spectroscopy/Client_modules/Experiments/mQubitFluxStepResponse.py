"""
STEP 3 of the TLS pipeline: fast-flux step response + predistortion.

QUA analog: LabCode/Experiments/Flux_Predistortion/m_qubit_step_response.py
            + LabCode/Control/Flux_Tunable/flux_predistortion.py (_run_qubit_flux_step_response)
QICK model: escher FF_fromParth/mFFSpecVsDelay + mFFRampHoldTest_wPulsePreDist, using
            Helpers/ff_pulse.py (predistorted ramp-hold on ff_ch) and
            Helpers/flux_predistortion.py (rise_decay_bump fit + piecewise solve).

Two modes:
  FIT     (run_fit=True):  play a BARE flux step to the target, probe the qubit
          frequency vs hold delay t (spec-vs-delay), extract f_q(t), normalize to a
          voltage step response via the flux fit, fit rise_decay_bump, solve the
          piecewise DC correction, and save a *_rise_decay_bump_dc_compensation.json.
  CORRECT (run_correct=True): reload that JSON, replay the step PREDISTORTED, and
          verify the qubit frequency is flat vs delay (residual settling nulled).

Flux model: the DC baseline (park = baseline_dc_offset) is the Yokogawa bias; the
step to the target is the additional fast-flux excursion on ff_ch (ff_gain DAC units).
The qubit probe fires while the flux is HELD at target (ff pulses use stdysel='last',
so the DAC holds the level between the hold staircase and the ramp-down).
"""

import time

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_predistortion as fpd
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse


class FFStepResponseSpecProgram(RAveragerProgram):
    """One spec slice (hardware qubit-freq sweep) at hold delay cfg['ff_hold'] after a flux step.

    Sequence: ramp flux up -> hold at target for ff_hold (predistorted if compensation
    present) -> qubit spec pulse (freq swept) while held -> ramp flux back to park ->
    read out at park.
    """

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

        # short const spec probe (QUA constant_tone of cw_amp/cw_len)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                                 gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=f_res, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))

        # build the predistorted ramp-hold-ramp for this delay (hold = ff_hold)
        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=cfg["ff_hold"], ff_gain=cfg["ff_gain"],
            dt_play_us=cfg.get("dt_pulseplay", 5.0), ramp_us=cfg.get("ff_ramp_length", 0.02),
            dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.sync_all(self.us2cycles(1))

    def body(self):
        cfg = self.cfg
        ff_pulse.assert_park(self, self.ff_segs)
        self.sync_all(self.us2cycles(0.05))
        ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))          # flux held at target (stdysel='last')
        self.pulse(ch=cfg["qubit_ch"])                # spec probe at the target flux point
        self.sync_all(self.us2cycles(0.01))
        ff_pulse.play_ramp_down(self, self.ff_segs)   # back to park
        self.sync_all(self.us2cycles(cfg.get("pre_meas_delay", 0.1)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitFluxStepResponse(ExperimentClass):
    """Measure/fit (or verify) the fast-flux step response and its predistortion.

    cfg keys (measurement): qubit_freq_start/stop/expts (MHz), t_vec_us (delay axis),
      ff_gain (DAC), baseline_dc_offset, dc_offset (target, V), flux_fit_params.
    cfg keys (predistortion): flux_tail_compensation (dict or JSON path, correct mode).
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Flux_Step_Response', cfg=None, meta_dict=None,
                 flux_fit_params=None, run_fit=False, correction_json=None,
                 piecewise_min_multiplier=0.5, piecewise_max_multiplier=1.5,
                 correction_gain=1.0, qubit_name='q1', **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.flux_fit_params = flux_fit_params if flux_fit_params is not None \
            else cfg.get("flux_fit_params")
        self.run_fit = run_fit
        self.correction_json = correction_json
        self.min_mult = piecewise_min_multiplier
        self.max_mult = piecewise_max_multiplier
        self.correction_gain = correction_gain
        self.qubit_name = qubit_name

    def _t_vec(self):
        cfg = self.cfg
        if "t_vec_us" in cfg:
            return np.asarray(cfg["t_vec_us"], dtype=float)
        return np.arange(cfg["t_min_us"], cfg["t_max_us"], cfg["t_step_us"])

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        cfg["start"] = cfg["qubit_freq_start"]
        cfg["expts"] = int(cfg["qubit_freq_expts"])
        cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / (cfg["expts"] - 1)
        fpts = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])
        t_vec = self._t_vec()

        # correct mode: load the compensation into cfg so the program predistorts
        if not self.run_fit and self.correction_json is not None:
            cfg["flux_tail_compensation"] = fpd.load_compensation_json(self.correction_json)

        Z_mag = np.full((len(t_vec), len(fpts)), np.nan)
        fq_ghz = np.full(len(t_vec), np.nan)

        start = time.time()
        for i, t in enumerate(t_vec):
            cfg["ff_hold"] = float(t)
            prog = FFStepResponseSpecProgram(self.soccfg, cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            mag = np.abs(np.array(avgi[0][0]) + 1j * np.array(avgq[0][0]))
            Z_mag[i, :] = mag
            sp, _ = ff.fit_spec_dip(fpts, mag, kind='auto')
            if sp is not None:
                fq_ghz[i] = sp['f0'] / 1e3
            if i == 0:
                print(f"[3] ~{(time.time()-start)*len(t_vec)/60:.1f} min for "
                      f"{len(t_vec)} delays x {cfg['expts']} freq points")

        data = {'config': cfg, 'data': {'t_vec_us': t_vec, 'fpts_MHz': fpts,
                                        'magnitude': Z_mag, 'fq_ghz': fq_ghz}}
        self.data = data

        # --- normalized step responses ---
        # Flux-axis units: whatever FLUX_FIT_PARAMS was fit in.  In the all-FF
        # workflow that is ff_gain DAC units: baseline = park, target = ff_gain.
        # (Volt keys kept for the optional Yoko-swept mode.)
        baseline_v = cfg.get("baseline_dc_offset", cfg.get("ff_park_gain", 0))
        target_v = cfg.get("dc_offset", cfg["ff_gain"])
        if self.flux_fit_params is not None:
            f_base = fx.estimate_fit_frequency_ghz(self.flux_fit_params, baseline_v)
            f_targ = fx.estimate_fit_frequency_ghz(self.flux_fit_params, target_v)
            denom = (f_targ - f_base) or np.nan
            freq_step_resp = (fq_ghz - f_base) / denom
            v_eff = fx.frequency_to_local_flux_branch(self.flux_fit_params, fq_ghz,
                                                      baseline_v, target_v)
            volt_step_resp = (v_eff - baseline_v) / ((target_v - baseline_v) or np.nan)
            data['data'].update(freq_step_response=freq_step_resp,
                                voltage_step_response=volt_step_resp,
                                effective_dc_offset_V=v_eff)
        else:
            volt_step_resp = None
            print("[3] no flux_fit_params -> skipping voltage-domain normalization")

        # --- fit + solve + save compensation (FIT mode only) ---
        if self.run_fit:
            if volt_step_resp is None:
                raise RuntimeError("run_fit requires flux_fit_params to normalize the step response.")
            t_ns = t_vec * 1e3
            resp = volt_step_resp
            model = fpd.fit_rise_decay_bump_response_model(t_ns, resp)
            edges = fpd.default_dc_tail_segment_edges(float(t_ns[-1]))
            comp = fpd.calculate_piecewise_dc_correction(
                t_ns, resp, edges, desired_response='median',
                min_multiplier=self.min_mult, max_multiplier=self.max_mult,
                correction_gain=self.correction_gain)
            json_path = self.iname[:-4] + "_rise_decay_bump_dc_compensation.json"
            fpd.save_compensation_json(
                json_path, comp,
                metadata={'qubit': self.qubit_name, 'dc_offset': target_v,
                          'baseline_dc_offset': baseline_v, 'ff_gain': cfg["ff_gain"],
                          'created_at': self.date_string + "_" + self.time_string},
                rise_decay_bump_model=model)
            data['data']['rise_decay_bump_dc_compensation_json'] = json_path
            data['data']['rise_decay_bump_model'] = model
            data['data']['compensation'] = comp
            print(f"[3a] saved compensation JSON: {json_path}")
            print(f"[3a] fit success={model.get('success')}, "
                  f"solve success={comp.get('success')}, "
                  f"segments={len(comp['segment_edges_ns'])}")
        else:
            # correct mode: report residual flatness
            resid = np.nanstd(fq_ghz) * 1e3  # MHz
            data['data']['residual_flatness_MHz'] = resid
            print(f"[3b] post-correction qubit-freq flatness: std = {resid:.3f} MHz "
                  f"(smaller is better)")

        self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(9, 9), num=figNum)
        extent = [d['fpts_MHz'][0] / 1e3, d['fpts_MHz'][-1] / 1e3,
                  d['t_vec_us'][0], d['t_vec_us'][-1]]
        axs[0].imshow(d['magnitude'], aspect='auto', origin='lower', extent=extent,
                      interpolation='none')
        axs[0].plot(d['fq_ghz'], d['t_vec_us'], 'r.-', ms=3, lw=0.8)
        axs[0].set_xlabel("Qubit frequency (GHz)")
        axs[0].set_ylabel("Hold delay t (us)")
        axs[0].set_title("Spec vs delay after flux step")
        if 'voltage_step_response' in d:
            axs[1].plot(d['t_vec_us'], d['voltage_step_response'], 'k.-', label='voltage step response')
            if 'rise_decay_bump_model' in d and d['rise_decay_bump_model'].get('success'):
                m = d['rise_decay_bump_model']
                fitc = fpd.rise_decay_bump_model(d['t_vec_us'] * 1e3, m['asymptote'],
                        m['late_amplitude'], m['late_tau_ns'], m['bump_amplitude'],
                        m['rise_tau_ns'], m['bump_tau_ns'])
                axs[1].plot(d['t_vec_us'], fitc, 'r--', label='rise_decay_bump fit')
            axs[1].axhline(1.0, color='g', ls=':', lw=1, label='target')
            axs[1].set_xlabel("Hold delay t (us)")
            axs[1].set_ylabel("normalized step response")
            axs[1].legend()
        else:
            axs[1].plot(d['t_vec_us'], d['fq_ghz'], 'k.-')
            axs[1].set_xlabel("Hold delay t (us)"); axs[1].set_ylabel("f_q (GHz)")
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
        # store only array-like entries in h5; dicts (model/comp) go to JSON attrs
        arr = {k: v for k, v in data['data'].items()
               if not isinstance(v, dict) and not isinstance(v, str)}
        super().save_data(data=arr)
