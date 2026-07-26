import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)

_ADDR_I, _ADDR_Q = 100, 101
_REG_I, _REG_Q = 30, 31


class ReadProbeProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 100)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_static_park(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]), gen_ch=cfg["qubit_ch"])
        add_qubit_gaussian(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq, phase=0,
                                 gain=int(cfg["probe_gain"]), waveform="qubit")
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_static_park(
            self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        page = self.ch_page(cfg["qubit_ch"])
        tproc_ch = int(cfg["tproc_ch"])
        if int(cfg["probe_gain"]) != 0:
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.2))
        self.read(tproc_ch, page, "lower", _REG_I)
        self.read(tproc_ch, page, "upper", _REG_Q)
        self.memwi(page, _REG_I, _ADDR_I)
        self.memwi(page, _REG_Q, _ADDR_Q)
        self.sync_all(self.us2cycles(cfg.get("relax_delay", 500.0)))


class ResetCheckProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 2000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_static_park(self)
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
        ff_pulse.play_static_park(
            self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        if cfg.get("do_reset", False):
            ar.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg.get("relax_delay", 500.0)))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = (int(self.cfg.get("reset_max_iters", 3)) if self.cfg.get("do_reset", False)
                 else 0) + 1
        avg_di, avg_dq = super().acquire(soc, readouts_per_experiment=reads,
                                         load_pulses=load_pulses, progress=progress)
        return float(np.asarray(avg_di)[0][-1]), float(np.asarray(avg_dq)[0][-1])


class ActiveResetProbe(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Active_Reset_Probe', cfg=None, meta_dict=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.raw_shots = None

    def _read_dmem(self, addr):
        for getter in (lambda: self.soc.tproc.single_read(addr),
                       lambda: self.soc.tproc.read_dmem(addr, 1)[0],
                       lambda: self.soc.read_dmem(addr, 1)[0]):
            try:
                return ar.to_signed32(getter())
            except Exception:
                continue
        raise RuntimeError("could not read tProc data memory via the soc proxy; the "
                           "single_read/read_dmem API differs on this board -- tell me the error.")

    def _raw_shots(self, program):
        try:
            lower = np.asarray(program.di_buf[0]).ravel()
            upper = np.asarray(program.dq_buf[0]).ravel()
            good = np.isfinite(lower) & np.isfinite(upper)
            lower, upper = lower[good], upper[good]
            if lower.size >= 20:
                lower = np.asarray([ar.to_signed32(v) for v in lower], dtype=np.int64)
                upper = np.asarray([ar.to_signed32(v) for v in upper], dtype=np.int64)
                return lower, upper
        except Exception:
            pass
        return (np.asarray([self._read_dmem(_ADDR_I)], dtype=np.int64),
                np.asarray([self._read_dmem(_ADDR_Q)], dtype=np.int64))

    @staticmethod
    def _fit_raw_discriminator(ground, excited):
        ground = np.asarray(ground, dtype=np.int64).ravel()
        excited = np.asarray(excited, dtype=np.int64).ravel()
        values = np.unique(np.concatenate((ground, excited)))
        candidates = np.unique(np.concatenate((values, values + 1)))
        best = None
        for ground_below in (True, False):
            for threshold in candidates:
                if ground_below:
                    p_e_given_g = float(np.mean(ground >= threshold))
                    p_g_given_e = float(np.mean(excited < threshold))
                else:
                    p_e_given_g = float(np.mean(ground <= threshold))
                    p_g_given_e = float(np.mean(excited > threshold))
                fidelity = 1.0 - 0.5 * (p_e_given_g + p_g_given_e)
                item = {
                    "threshold_raw": int(threshold),
                    "ground_below": bool(ground_below),
                    "fidelity": fidelity,
                    "p_e_given_g": p_e_given_g,
                    "p_g_given_e": p_g_given_e,
                }
                if best is None or item["fidelity"] > best["fidelity"]:
                    best = item
        return best

    @staticmethod
    def _score_raw_discriminator(ground, excited, discriminator):
        ground = np.asarray(ground, dtype=np.int64).ravel()
        excited = np.asarray(excited, dtype=np.int64).ravel()
        threshold = int(discriminator["threshold_raw"])
        if bool(discriminator["ground_below"]):
            p_e_given_g = float(np.mean(ground >= threshold))
            p_g_given_e = float(np.mean(excited < threshold))
        else:
            p_e_given_g = float(np.mean(ground <= threshold))
            p_g_given_e = float(np.mean(excited > threshold))
        return {
            "fidelity": 1.0 - 0.5 * (p_e_given_g + p_g_given_e),
            "p_e_given_g": p_e_given_g,
            "p_g_given_e": p_g_given_e,
        }

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]
        tproc_ch = ar.feedback_channel(self.soccfg, ro_ch)
        print("=" * 68)
        print(f"[active-reset probe] readout {ro_ch}: tproc_ch = {tproc_ch}")
        if tproc_ch < 0:
            print("  -> this firmware does NOT route the readout into the tProc.")
            print("  -> ACTIVE RESET IS NOT POSSIBLE on this board; keep reset_mode='passive'.")
            print("=" * 68)
            self.data = {'tproc_ch': tproc_ch, 'supported': False,
                         'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            return {'config': cfg, 'data': self.data}

        print("  -> feedback path present; measuring raw read values for |g> and |e> ...")
        cfg["tproc_ch"] = tproc_ch
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 200)))
        results = {}
        raw_shots = {}
        for label, gain in [("ground", 0), ("excited", int(cfg.get("qubit_pi_gain", cfg["qubit_gain"])))]:
            cfg["probe_gain"] = gain
            prog = ReadProbeProgram(self.soccfg, cfg)
            avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            lower, upper = self._raw_shots(prog)
            raw_shots[label] = {"lower": lower, "upper": upper}
            raw_i = int(round(float(np.median(lower))))
            raw_q = int(round(float(np.median(upper))))
            host_i = float(np.asarray(avgi).ravel()[0])
            results[label] = {
                "raw_lower": raw_i, "raw_upper": raw_q, "host_avgi": host_i,
                "raw_lower_mad": float(np.median(np.abs(lower - np.median(lower)))),
                "raw_upper_mad": float(np.median(np.abs(upper - np.median(upper)))),
                "shots": int(min(lower.size, upper.size)),
            }
            print(f"    {label:8s}: read lower(I?)={raw_i:>12d}  upper(Q?)={raw_q:>12d}  "
                  f"| host avgi={host_i:+.4g} ({results[label]['shots']} buffered shots)")

        g, e = results["ground"], results["excited"]
        sep_lower = abs(e["raw_lower"] - g["raw_lower"])
        sep_upper = abs(e["raw_upper"] - g["raw_upper"])
        oper = "lower" if sep_lower >= sep_upper else "upper"
        ground_raw = raw_shots["ground"][oper]
        excited_raw = raw_shots["excited"][oper]
        if min(ground_raw.size, excited_raw.size) >= 4:
            discrimination = self._fit_raw_discriminator(
                ground_raw[::2], excited_raw[::2])
            audit = self._score_raw_discriminator(
                ground_raw[1::2], excited_raw[1::2], discrimination)
            discrimination["training_fidelity"] = discrimination["fidelity"]
            discrimination.update(audit)
            audit_shots = int(min(ground_raw[1::2].size, excited_raw[1::2].size))
        else:
            discrimination = self._fit_raw_discriminator(ground_raw, excited_raw)
            discrimination["training_fidelity"] = discrimination["fidelity"]
            discrimination.update({"fidelity": float("nan"),
                                   "p_e_given_g": float("nan"),
                                   "p_g_given_e": float("nan")})
            audit_shots = 0
        thr = int(discrimination["threshold_raw"])
        ground_below = bool(discrimination["ground_below"])
        print("-" * 68)
        print(f"  discriminating half: '{oper}' (|g>-|e> separation "
              f"{max(sep_lower, sep_upper)} vs {min(sep_lower, sep_upper)} on the other)")
        print(f"  -> active_reset_block(oper='{oper}', threshold_raw={thr}, "
              f"ground_below={ground_below})")
        print(f"  held-out raw assignment: F={discrimination['fidelity']:.3f} "
              f"[P(e|g)={discrimination['p_e_given_g']:.3f}, "
              f"P(g|e)={discrimination['p_g_given_e']:.3f}]")
        if max(sep_lower, sep_upper) < 3 * max(1, min(sep_lower, sep_upper)):
            print("  WARNING: |g> and |e> barely separate in the raw read -- discrimination "
                  "is marginal.  Improve readout SNR / set the readout phase so the blobs "
                  "split along one quadrature before trusting active reset.")
        print("=" * 68)

        # Keep the raw threshold-training/audit distributions available to an owning
        # autotuner without forcing them into the probe's compact JSON/HDF5 summary.
        self.raw_shots = raw_shots
        self.data = {
            'tproc_ch': tproc_ch, 'supported': True, 'results': results,
            'recommended': {'oper': oper, 'threshold_raw': thr, 'ground_below': ground_below},
            'raw_assignment_fidelity': discrimination['fidelity'],
            'raw_assignment_training_fidelity': discrimination['training_fidelity'],
            'raw_assignment_shots': audit_shots,
            'raw_assignment_errors': {
                'p_e_given_g': discrimination['p_e_given_g'],
                'p_g_given_e': discrimination['p_g_given_e'],
            },
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _ge_raw(self, cfg):
        out = {}
        for label, gain in (("g", 0),
                            ("e", int(cfg.get("qubit_pi_gain", cfg["qubit_gain"])))):
            c = dict(cfg)
            c["probe_gain"] = int(gain)
            prog = ReadProbeProgram(self.soccfg, c)
            avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            lower, upper = self._raw_shots(prog)
            out[label] = {"lower": int(round(float(np.median(lower)))),
                          "upper": int(round(float(np.median(upper)))),
                          "I": float(np.asarray(avgi).ravel()[0]),
                          "Q": float(np.asarray(avgq).ravel()[0])}
        return out

    def calibrate_res_phase(self, phases=None, sweep_shots=800, check_shots=3000):
        cfg = dict(self.cfg)
        ro_ch = cfg["ro_chs"][0]
        tproc_ch = ar.feedback_channel(self.soccfg, ro_ch)
        print("=" * 72)
        print(f"[res-phase cal] tproc_ch={tproc_ch}")
        if tproc_ch < 0:
            print("  feedback path absent -> active reset impossible; nothing to align.")
            print("=" * 72)
            self.data = {'supported': False,
                         'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            return {'config': cfg, 'data': self.data}
        cfg["tproc_ch"] = tproc_ch
        cfg["reps"] = cfg["shots"] = int(sweep_shots)
        if phases is None:
            phases = np.arange(0.0, 180.0, 15.0)
        print(f"  sweeping res_phase to put |g>/|e> on ONE quadrature "
              f"({len(phases)} phases x {sweep_shots} shots):")
        rows = []
        for ph in phases:
            cfg["res_phase"] = float(ph)
            ge = self._ge_raw(cfg)
            sl = abs(ge["e"]["lower"] - ge["g"]["lower"])
            su = abs(ge["e"]["upper"] - ge["g"]["upper"])
            pur = sl / (sl + su + 1e-9)
            rows.append({"res_phase": float(ph), "sep_lower": sl, "sep_upper": su,
                         "purity": pur, "ge": ge})
            print(f"    res_phase={ph:6.1f} deg: lower={sl:>9d} upper={su:>9d}  "
                  f"purity(lower)={pur:.2f}")
        max_sl = max((r["sep_lower"] for r in rows), default=1) or 1
        eligible = [r for r in rows if r["sep_lower"] >= 0.3 * max_sl] or rows
        best = max(eligible, key=lambda r: r["purity"])
        gl, el = best["ge"]["g"]["lower"], best["ge"]["e"]["lower"]
        thr = int(round(0.5 * (gl + el)))
        ground_below = gl < el
        clean = best["purity"] >= 0.85 and best["sep_lower"] >= 3 * max(1, best["sep_upper"])
        print("-" * 72)
        print(f"  BEST res_phase = {best['res_phase']:.1f} deg "
              f"(lower separation {best['sep_lower']}, purity {best['purity']:.2f})")
        print(f"  -> set BaseConfig['res_phase'] = {best['res_phase']:.1f}")
        print(f"  -> aligned discrimination: oper='lower', threshold_raw={thr}, "
              f"ground_below={ground_below}")
        print("  discrimination is " + ("CLEAN (separation now on one quadrature)" if clean
              else "still MARGINAL after alignment -- readout SNR limited, not a phase problem"))

        resid = self._residual_at(best["res_phase"], thr, ground_below, int(check_shots))
        self.data = {
            'tproc_ch': tproc_ch, 'supported': True,
            'best_res_phase': best["res_phase"], 'sweep': [
                {k: r[k] for k in ("res_phase", "sep_lower", "sep_upper", "purity")}
                for r in rows],
            'recommended': {'oper': 'lower', 'threshold_raw': thr,
                            'ground_below': bool(ground_below)},
            'clean': bool(clean), 'residual': resid,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _residual_at(self, res_phase, threshold_raw, ground_below, shots):
        cfg = dict(self.cfg)
        cfg["res_phase"] = float(res_phase)
        cfg["reps"] = cfg["shots"] = int(shots)
        cfg["tproc_ch"] = ar.feedback_channel(self.soccfg, cfg["ro_chs"][0])
        cfg["reset_oper"] = "lower"
        cfg["reset_threshold_raw"] = int(threshold_raw)
        cfg["reset_ground_below"] = bool(ground_below)
        cfg.setdefault("reset_max_iters", 3)
        ge = self._ge_raw(cfg)
        Ig, Qg = ge["g"]["I"], ge["g"]["Q"]
        Ie, Qe = ge["e"]["I"], ge["e"]["Q"]
        dx, dy = Ie - Ig, Qe - Qg
        denom = dx * dx + dy * dy

        def _resid(Ir, Qr):
            return (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")

        cb = dict(cfg); cb["prep_excited"] = True; cb["do_reset"] = False
        r0 = _resid(*ResetCheckProgram(self.soccfg, cb).acquire(self.soc, load_pulses=True))
        crg = dict(cfg); crg["prep_excited"] = False; crg["do_reset"] = True
        rg = _resid(*ResetCheckProgram(self.soccfg, crg).acquire(self.soc, load_pulses=True))
        cre = dict(cfg); cre["prep_excited"] = True; cre["do_reset"] = True
        re = _resid(*ResetCheckProgram(self.soccfg, cre).acquire(self.soc, load_pulses=True))
        works = bool(abs(r0 - 1.0) <= 0.3 and abs(rg) <= 0.2 and abs(re) <= 0.2)
        print("-" * 72)
        print(f"  end-to-end check at res_phase={res_phase:.1f} deg:")
        print(f"    no-reset baseline (must be ~1.0): {r0:+.3f}")
        print(f"    reset prepared |g> (want ~0):    {rg:+.3f}")
        print(f"    reset prepared |e> (want ~0):    {re:+.3f}")
        print(f"  -> ACTIVE RESET {'WORKS' if works else 'NOT confirmed'} "
              f"(residuals g={rg:+.3f}, e={re:+.3f}; baseline {r0:+.3f})")
        print("=" * 72)
        return {"baseline": r0, "reset_ground": rg, "reset_excited": re,
                "reset": re, "works": works}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'probe': self.data})
