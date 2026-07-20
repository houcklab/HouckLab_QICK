"""
Active-reset validation -- the one-number yes/no that the FULL feedback loop resets the
qubit (not just that the read works, which mActiveResetProbe already showed).

Runs three configs and reads the FINAL measurement each time:
  |g> ref   : no pi, no reset                       -> (Ig, Qg)
  |e> ref   : pi, no reset                          -> (Ie, Qe)
  |e>+reset : pi, then the active-reset feedback    -> (Ir, Qr)

Metric: the residual excited fraction = projection of (reset - |g>) onto the (|e> - |g>)
readout vector.  ~0 -> the qubit was driven to ground (reset works); ~1 -> still excited.
Uses the full IQ vector (no assumption about which quadrature discriminates), so it is
robust even though this board's separation is on Q, not I.

Self-contained buffer handling: the fixed-count reset adds exactly reset_max_iters readout
triggers, so readouts_per_experiment = (max_iters if reset else 0) + 1 and the final
measurement is the LAST readout.  This is purely diagnostic -- it changes no calibration.
Run it (board back up) BEFORE trusting reset_mode='feedback' in the T1/SS Rabis.
"""

import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, _ADDR_I, _ADDR_Q)


class ResetValidationProgram(AveragerProgram):
    """prep (cfg['prep_excited']) -> optional active reset (cfg['do_reset']) -> final measure.
    acquire() returns the FINAL measurement's rep-averaged (I, Q)."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 2000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]), gen_ch=cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
        # pulse register sits at the pi gain -> used for BOTH the |e> prep and the reset pi
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq, phase=0,
                                 gain=int(cfg["qubit_pi_gain"]), waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])           # |e> prep
            self.sync_all(self.us2cycles(0.01))
        if cfg.get("do_reset", False):
            ar.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "upper"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg.get("relax_delay", 500.0)))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = (int(self.cfg.get("reset_max_iters", 3)) if self.cfg.get("do_reset", False) else 0) + 1
        avg_di, avg_dq = super().acquire(soc, readouts_per_experiment=reads,
                                         load_pulses=load_pulses, progress=progress)
        # the final measurement is the LAST readout of the experiment
        return float(np.asarray(avg_di)[0][-1]), float(np.asarray(avg_dq)[0][-1])


class ActiveResetValidation(ExperimentClass):
    """Prep |e> -> active reset -> measure; report residual excited fraction vs |g>/|e> refs."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Active_Reset_Validation', cfg=None, meta_dict=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)

    def _read_dmem(self, addr):
        """Read one tProc data-memory word back through the Pyro proxy (best-effort)."""
        for getter in (lambda: self.soc.tproc.single_read(addr),
                       lambda: self.soc.tproc.read_dmem(addr, 1)[0],
                       lambda: self.soc.read_dmem(addr, 1)[0]):
            try:
                return int(getter())
            except Exception:
                continue
        raise RuntimeError("could not read tProc data memory via the soc proxy.")

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg.setdefault("shots", 2000)
        cfg["reps"] = int(cfg["shots"])
        cfg.setdefault("relax_delay", 500.0)
        ro_ch = cfg["ro_chs"][0]
        tproc_ch = ar.feedback_channel(self.soccfg, ro_ch)
        oper = str(cfg.get("reset_oper", "upper"))
        thr = cfg.get("reset_threshold_raw")
        pi_gain = int(cfg["qubit_pi_gain"])
        print("=" * 72)
        print(f"[reset validation] tproc_ch={tproc_ch}, stored threshold_raw={thr}, oper={oper}, "
              f"ground_below={cfg.get('reset_ground_below')}, pi_gain={pi_gain}")
        if tproc_ch < 0:
            print("  feedback path absent (tproc_ch<0) -> cannot validate active reset.")
            print("=" * 72)
            self.data = {'supported': False,
                         'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            return {'config': cfg, 'data': self.data}
        if thr is None:
            raise ValueError("reset_threshold_raw is required (run mActiveResetProbe first).")
        cfg["tproc_ch"] = tproc_ch

        # ---- (1) CURRENT raw |g>/|e> reads -> is the stored threshold still valid? ----------
        def _raw_read(gain):
            cfg["probe_gain"] = int(gain)
            avgi, avgq = ReadProbeProgram(self.soccfg, cfg).acquire(self.soc, load_pulses=True,
                                                                    progress=False)
            return (float(np.asarray(avgi).ravel()[0]), float(np.asarray(avgq).ravel()[0]),
                    self._read_dmem(_ADDR_I), self._read_dmem(_ADDR_Q))   # host I,Q ; raw lower,upper

        Ig, Qg, gl, gu = _raw_read(0)            # |g>
        Ie, Qe, el, eu = _raw_read(pi_gain)      # |e>
        gv, ev = ((gu, eu) if oper == "upper" else (gl, el))
        cur_mid = int(round(0.5 * (gv + ev)))
        sep_raw = abs(ev - gv)
        thr_between = min(gv, ev) < thr < max(gv, ev)
        print("-" * 72)
        print("  CURRENT raw reads (this session):")
        print(f"    |g>: lower={gl:>12d} upper={gu:>12d}   |e>: lower={el:>12d} upper={eu:>12d}")
        print(f"    on '{oper}' half: |g>={gv}  |e>={ev}  separation={sep_raw}  midpoint={cur_mid}")
        print(f"    stored threshold {thr}: {'BETWEEN |g> and |e> (ok)' if thr_between else '*** OUTSIDE [|g>,|e>] -- STALE ***'}")
        if not thr_between:
            print(f"    ==> update RESET_THRESHOLD_RAW to ~{cur_mid} (and RESET_GROUND_BELOW="
                  f"{gv < ev}); readout drifted since the probe.")
        host_sep = float(np.hypot(Ie - Ig, Qe - Qg))
        print(f"    host |e>-|g> separation = {host_sep:.4g}  (|g> I={Ig:+.4g} Q={Qg:+.4g} ; "
              f"|e> I={Ie:+.4g} Q={Qe:+.4g})")

        # ---- (2) residual-excited vs max_iters (the trend diagnoses the failure mode) --------
        dx, dy = Ie - Ig, Qe - Qg
        denom = dx * dx + dy * dy

        def _resid(Ir, Qr):
            return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")

        def _reset_run(k):
            cfg["prep_excited"] = True
            cfg["do_reset"] = bool(k > 0)
            cfg["reset_max_iters"] = int(k)
            Ir, Qr = ResetValidationProgram(self.soccfg, cfg).acquire(self.soc, load_pulses=True)
            return Ir, Qr, _resid(Ir, Qr)

        iters_list = [0, 1, 2, 3, 5]
        sweep = []
        print("-" * 72)
        print("  residual-excited vs max_iters  (0 = full |e>, 1 = still excited):")
        for k in iters_list:
            Ir, Qr, res = _reset_run(k)
            sweep.append({"max_iters": k, "residual": res, "I": Ir, "Q": Qr})
            print(f"    max_iters={k}:  residual={res:+.3f}   (reset I={Ir:+.4g} Q={Qr:+.4g})")

        by_k = {s["max_iters"]: s["residual"] for s in sweep}
        r0 = by_k[0]                                          # no-reset baseline (~1 if prep good)
        r1 = by_k[1]                                          # one pass
        rmax = by_k[max(iters_list)]                          # most passes
        best = min((s for s in sweep if s["max_iters"] > 0), key=lambda s: s["residual"])
        rbest = best["residual"]
        print("-" * 72)
        print(f"  no-reset baseline (max_iters=0) = {r0:+.3f}   best = {rbest:+.3f} "
              f"at max_iters={best['max_iters']}")
        if not thr_between:
            print("  -> THRESHOLD is STALE (see above): set RESET_THRESHOLD_RAW/GROUND_BELOW to "
                  "the current values, then re-run.  (Other diagnoses unreliable until fixed.)")
        elif rbest < 0.15:
            print("  -> ACTIVE RESET WORKS: the feedback loop drives |e> to ground.")
        elif abs(rbest - r0) < 0.12:
            print("  -> reset does NOTHING vs baseline: the conditional isn't firing as intended "
                  "-> discrimination broken (oper/ground_below sign, threshold, or read timing).")
        elif rmax < r1 - 0.10:
            print("  -> reset CONVERGING (residual still dropping at max iters) but not finished: "
                  "the pi is under-rotated (weak/detuned).  Calibrate the pi (run SS_Cal+Rabi) "
                  "and/or raise RESET_MAX_ITERS.")
        else:
            print("  -> reset PLATEAUS partway (helps but caps out): most likely an under-rotated "
                  "pi -- calibrate it (SS_Cal+Rabi) -- or marginal discrimination.")
        print("=" * 72)

        self.data = {
            'supported': True, 'g_ref': (Ig, Qg), 'e_ref': (Ie, Qe),
            'raw': {'g_lower': gl, 'g_upper': gu, 'e_lower': el, 'e_upper': eu,
                    'oper': oper, 'current_midpoint': cur_mid, 'stored_threshold': thr,
                    'threshold_valid': bool(thr_between)},
            'iters_sweep': sweep, 'best': best, 'baseline_residual': r0,
            'reset_params': {k: cfg.get(k) for k in
                             ("reset_threshold_raw", "reset_oper", "reset_ground_below")},
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'validation': self.data})
