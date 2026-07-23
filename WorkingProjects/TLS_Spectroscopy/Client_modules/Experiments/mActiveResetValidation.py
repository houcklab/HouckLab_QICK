import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ReadProbeProgram, _ADDR_I, _ADDR_Q)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)


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
        add_qubit_gaussian(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq, phase=0,
                                 gain=int(cfg["qubit_pi_gain"]), waveform="qubit")
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])
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
        return float(np.asarray(avg_di)[0][-1]), float(np.asarray(avg_dq)[0][-1])


class ActiveResetValidation(ExperimentClass):
    """Prep |e> -> active reset -> measure; report residual excited fraction vs |g>/|e> refs."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Active_Reset_Validation', cfg=None, meta_dict=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)

    def _read_dmem(self, addr):
        """Read one tProc data-memory word back through the Pyro proxy (best-effort), as a
        SIGNED int (the accumulator is signed; single_read returns it unsigned)."""
        for getter in (lambda: self.soc.tproc.single_read(addr),
                       lambda: self.soc.tproc.read_dmem(addr, 1)[0],
                       lambda: self.soc.read_dmem(addr, 1)[0]):
            try:
                return ar.to_signed32(getter())
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

        def _raw_read(gain):
            cfg["probe_gain"] = int(gain)
            avgi, avgq = ReadProbeProgram(self.soccfg, cfg).acquire(self.soc, load_pulses=True,
                                                                    progress=False)
            return (float(np.asarray(avgi).ravel()[0]), float(np.asarray(avgq).ravel()[0]),
                    self._read_dmem(_ADDR_I), self._read_dmem(_ADDR_Q))

        Ig, Qg, gl, gu = _raw_read(0)
        Ie, Qe, el, eu = _raw_read(pi_gain)
        sep_lower, sep_upper = abs(el - gl), abs(eu - gu)
        rec_oper = "lower" if sep_lower >= sep_upper else "upper"
        rgv, rev = ((gl, el) if rec_oper == "lower" else (gu, eu))
        rec_thr = int(round(0.5 * (rgv + rev)))
        rec_ground_below = rgv < rev
        rec_sep = abs(rev - rgv)
        gv, ev = ((gu, eu) if oper == "upper" else (gl, el))
        thr_between = min(gv, ev) < thr < max(gv, ev)
        sign_ok = (bool(cfg.get("reset_ground_below", True)) == (gv < ev))
        stored_ok = thr_between and sign_ok and (oper == rec_oper)
        host_sep = float(np.hypot(Ie - Ig, Qe - Qg))
        print("-" * 72)
        print("  CURRENT raw reads (signed, this session):")
        print(f"    |g>: lower={gl:>11d} upper={gu:>11d}   |e>: lower={el:>11d} upper={eu:>11d}")
        print(f"    raw separation: lower={sep_lower}  upper={sep_upper}")
        print(f"    STORED config oper={oper} thr={thr} ground_below={cfg.get('reset_ground_below')}"
              f"  ->  {'ok' if stored_ok else '*** STALE ***'}")
        print(f"    RECOMMENDED (from current reads): oper='{rec_oper}' threshold_raw={rec_thr} "
              f"ground_below={rec_ground_below}  (raw separation {rec_sep})")
        if not stored_ok:
            print(f"    ==> set RESET_OPER='{rec_oper}', RESET_THRESHOLD_RAW={rec_thr}, "
                  f"RESET_GROUND_BELOW={rec_ground_below}")
        print(f"    host |e>-|g> separation = {host_sep:.4g}  (|g> I={Ig:+.4g} Q={Qg:+.4g} ; "
              f"|e> I={Ie:+.4g} Q={Qe:+.4g})")
        if host_sep < 0.06:
            print("    *** the |g>/|e> readout contrast is very small: the single-shot readout is "
                  "NOT calibrated at this tuning.  Run SS_Cal (+Rabi for the pi) FIRST -- active "
                  "reset can't discriminate until the blobs separate cleanly on one quadrature.")
        if not stored_ok:
            print(f"    --> running the sweep below with the RECOMMENDED discrimination "
                  f"(oper='{rec_oper}', thr={rec_thr}, ground_below={rec_ground_below}), "
                  f"not the stale stored one.")
            cfg["reset_oper"] = rec_oper
            cfg["reset_threshold_raw"] = int(rec_thr)
            cfg["reset_ground_below"] = bool(rec_ground_below)

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
        # Two passes in OPPOSITE order.  This readout drifts within a batch and every point
        # is a separate acquisition, so a single pass confounds "how good is the reset at k"
        # with "when in the drift was k measured".  Averaging opposite orders cancels a
        # monotonic drift to first order; the pass-to-pass spread is the drift that is left,
        # which is what separates a genuinely unstable reset from a drifting readout.
        res_passes = {k: [] for k in iters_list}
        iq_by_k = {}
        for order in (list(iters_list), list(reversed(iters_list))):
            for k in order:
                Ir, Qr, res = _reset_run(k)
                res_passes[k].append(res)
                iq_by_k[k] = (Ir, Qr)

        sweep = []
        drift_spread = 0.0
        print("-" * 72)
        print("  residual-excited vs max_iters  (0 = full |e>, 1 = still excited; two")
        print("  opposite-order passes, so the +/- is readout drift, not reset instability):")
        for k in iters_list:
            r_mean = float(np.mean(res_passes[k]))
            r_spread = float(abs(res_passes[k][0] - res_passes[k][1]))
            drift_spread = max(drift_spread, r_spread)
            Ir, Qr = iq_by_k[k]
            sweep.append({"max_iters": k, "residual": r_mean, "drift_spread": r_spread,
                          "I": Ir, "Q": Qr})
            print(f"    max_iters={k}:  residual={r_mean:+.3f} (drift +/-{r_spread:.3f})   "
                  f"(reset I={Ir:+.4g} Q={Qr:+.4g})")

        by_k = {s["max_iters"]: s["residual"] for s in sweep}
        r0 = by_k[0]
        resid_on = [by_k[k] for k in iters_list if k > 0]
        rbest, rworst = min(resid_on), max(resid_on)
        on_spread = rworst - rbest
        baseline_sane = abs(r0 - 1.0) <= 0.25
        reduction = (r0 - rbest) / r0 if r0 > 1e-9 else 0.0
        # The residual floor is set by readout misidentification P(g|e): a PERFECT reset
        # cannot push below it, so an absolute "<0.15" bar fails a working reset on a
        # finite-fidelity readout.  The physical question is whether reset drives |e> toward
        # |g> and HOLDS it there -- a large reduction that is stable to within the measured
        # drift.  "Stable" is judged against the drift, not an absolute number.
        stable = on_spread <= max(0.10, 2.0 * drift_spread)
        reduced = rbest <= 0.20
        does_nothing = abs(rbest - r0) < 0.12
        consistent = bool(reduced and stable)
        stale_note = ("" if stored_ok else
                      "\n     Bake the discovered discrimination into production first: "
                      f"RESET_OPER='{rec_oper}', RESET_THRESHOLD_RAW={rec_thr}, "
                      f"RESET_GROUND_BELOW={rec_ground_below}.")
        print("-" * 72)
        print(f"  no-reset baseline (max_iters=0) = {r0:+.3f}  (must be ~1.000 -- it IS the "
              f"|e> reference) -> {'ok' if baseline_sane else '*** INCONSISTENT ***'}")
        print(f"  with reset: best={rbest:+.3f}  worst={rworst:+.3f}  "
              f"(reduced {100 * reduction:.0f}% from baseline; readout drift +/-{drift_spread:.3f})")
        if not baseline_sane:
            print(f"  -> INCONCLUSIVE: the no-reset baseline should be 1.000 by construction but "
                  f"reads {r0:+.3f}.  The reference and sweep disagree, so the residuals are not "
                  "trustworthy (marginal readout SNR / unreliable pi).  Calibrate the readout + "
                  "pi (SS_Cal + Rabi), then re-run.  Do NOT enable reset_mode='feedback' yet.")
        elif host_sep < 0.06:
            print(f"  -> READOUT NOT CALIBRATED (|g>/|e> contrast {host_sep:.3g}): the blobs "
                  "barely separate, so neither the tProc discrimination nor this residual is "
                  "meaningful.  Run SS_Cal + Rabi, re-probe the threshold, then re-run.")
        elif consistent:
            print(f"  -> ACTIVE RESET WORKS: reset drives |e> ({r0:.2f}) down to ~{rbest:.2f} and "
                  f"holds it there across iterations (within the {drift_spread:.2f} readout "
                  f"drift).  The residual floor is readout misidentification P(g|e), not a reset "
                  f"failure -- more iterations cannot beat the readout fidelity." + stale_note)
        elif reduced and not stable:
            print(f"  -> RESET IS ACTING (|e> {r0:.2f} -> ~{rbest:.2f}) but the reset-on points "
                  f"scatter {on_spread:.2f}, more than the {drift_spread:.2f} readout drift "
                  f"explains.  Raise shots or stabilise the readout, then re-run to confirm." + stale_note)
        elif does_nothing:
            print("  -> reset does NOTHING vs baseline: the conditional isn't firing -> "
                  "discrimination broken (oper/ground_below sign, threshold, or read timing)." + stale_note)
        else:
            print(f"  -> reset PARTIAL: residual only reaches {rbest:.2f} (|e> baseline {r0:.2f}) "
                  "-- most likely an under-rotated pi (calibrate it with SS_Cal + Rabi) or "
                  "marginal discrimination." + stale_note)
        print("=" * 72)

        self.data = {
            'supported': True, 'g_ref': (Ig, Qg), 'e_ref': (Ie, Qe),
            'raw': {'g_lower': gl, 'g_upper': gu, 'e_lower': el, 'e_upper': eu,
                    'stored_oper': oper, 'stored_threshold': thr, 'stored_ok': bool(stored_ok),
                    'recommended': {'oper': rec_oper, 'threshold_raw': rec_thr,
                                    'ground_below': bool(rec_ground_below), 'separation': rec_sep}},
            'host_separation': host_sep,
            'iters_sweep': sweep, 'baseline_residual': r0,
            'residual_best': rbest, 'residual_worst': rworst,
            'baseline_sane': bool(baseline_sane), 'consistent': bool(consistent),
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
