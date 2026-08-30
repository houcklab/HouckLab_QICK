import contextlib
import gc

import numpy as np
from qick import AveragerProgram
import matplotlib.pyplot as plt

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import (
    ActiveResetProbe)


class BenchResetProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 2000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_park_hold(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"],
                                                       ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                  ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   gen_ch=cfg["qubit_ch"])
        add_qubit_gaussian(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=0, gain=int(cfg["qubit_pi_gain"]),
                                 waveform="qubit")
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.play_park_pulse(self, settle_us=cfg.get("ff_park_settle_us", 0.05))
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.01))
        scheme = str(cfg.get("reset_scheme", "none"))
        if scheme == "old":
            ar.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)), allow_legacy=True)
        elif scheme in ("rot2", "rot3", "rot3nl"):
            rot.active_reset_rot_block(
                self, ro_ch=cfg["ro_chs"][0],
                c_int=cfg["rot_c_int"], s_int=cfg["rot_s_int"],
                excite_threshold=cfg["rot_excite_threshold"],
                ground_threshold=cfg.get("rot_ground_threshold"),
                latch_sink=cfg.get("rot_latch_sink"),
                max_iters=int(cfg.get("reset_max_iters", 3)),
                three_zone=(scheme in ("rot3", "rot3nl")),
                use_latch=(scheme == "rot3"))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(cfg.get("relax_delay", 2500.0)))

    def reads_per_rep(self):
        n = int(self.cfg.get("reset_max_iters", 3))
        return (n if str(self.cfg.get("reset_scheme", "none")) != "none" else 0) + 1

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = self.reads_per_rep()
        super().acquire(soc, readouts_per_experiment=reads,
                        load_pulses=load_pulses, progress=progress)
        self.readouts_per_rep = reads
        return self.final_shots()

    def final_shots(self):
        reads = int(getattr(self, "readouts_per_rep", 1))
        out = []
        for buf in (self.di_buf, self.dq_buf):
            v = np.asarray([ar.to_signed32(x) for x in np.asarray(buf[0]).ravel()],
                           dtype=np.int64)
            n = v.size // reads
            out.append(v[:n * reads].reshape(n, reads)[:, -1])
        return out[0], out[1]


def raw_final_shots(soc, soccfg, cfg, prep_excited, scheme):
    c = dict(cfg)
    c["prep_excited"] = bool(prep_excited)
    c["reset_scheme"] = str(scheme)
    prog = BenchResetProgram(soccfg, c)
    i_final, q_final = prog.acquire(soc, load_pulses=True, progress=False)
    plt.close("all")
    gc.collect()
    return np.asarray(i_final, dtype=np.int64), np.asarray(q_final, dtype=np.int64)


def mean_final_iq(soc, soccfg, cfg, prep_excited, scheme):
    i_final, q_final = raw_final_shots(soc, soccfg, cfg, prep_excited, scheme)
    return float(np.mean(i_final)), float(np.mean(q_final))


def measure_refs(soc, soccfg, cfg):
    ig, qg = mean_final_iq(soc, soccfg, cfg, False, "none")
    ie, qe = mean_final_iq(soc, soccfg, cfg, True, "none")
    return rot.reference_axis(ig, qg, ie, qe)


def measure_residuals(soc, soccfg, cfg, refs):
    out = {}
    for prep in (False, True):
        ir, qr = mean_final_iq(soc, soccfg, cfg, prep,
                               cfg.get("reset_scheme", "none"))
        out["e" if prep else "g"] = rot.population_from_iq(ir, qr, refs)
    return out


RESIDUAL_SANE_LO = -0.15
RESIDUAL_SANE_HI = 0.75
REF_SEP_BAND = (0.55, 1.8)


def residuals_sane(res, lo=RESIDUAL_SANE_LO, hi=RESIDUAL_SANE_HI):
    return all(np.isfinite(v) and lo <= float(v) <= hi for v in res.values())


def refs_sane(refs, expected_sep, band=REF_SEP_BAND):
    if expected_sep is None or not np.isfinite(expected_sep) or expected_sep <= 0:
        return True
    ratio = float(refs["separation"]) / float(expected_sep)
    return band[0] <= ratio <= band[1]


def calibration_consistent(fit, refs, tol=0.4):
    raw = fit["raw"]
    gi, gq = float(np.median(raw["lg"])), float(np.median(raw["ug"]))
    ei, eq = float(np.median(raw["le"])), float(np.median(raw["ue"]))
    sep = max(float(refs["separation"]), 1.0)
    dg = float(np.hypot(gi - refs["ig"], gq - refs["qg"]))
    de = float(np.hypot(ei - (refs["ig"] + refs["dx"]),
                        eq - (refs["qg"] + refs["dy"])))
    mismatch = max(dg, de) / sep
    return bool(mismatch < tol), mismatch


def probe_and_fit_consistent(soc, soccfg, cfg, iters, eta_fallback, refs_shots=2000,
                             retries=1, **kw):
    fit = None
    for attempt in range(int(retries) + 1):
        fit = probe_and_fit(soc, soccfg, cfg, iters, eta_fallback, **kw)
        if fit is None:
            return None
        refs_cfg = dict(cfg)
        refs_cfg["shots"] = refs_cfg["reps"] = int(refs_shots)
        refs = measure_refs(soc, soccfg, refs_cfg)
        ok, mismatch = calibration_consistent(fit, refs)
        if ok:
            return fit
        print(f"    the probe calibration disagrees with a fresh reference "
              f"measurement (blob centers off by {mismatch:.2f} of the separation) "
              f"-- a glitch during the probe is suspected"
              f"{'; re-probing' if attempt < retries else ''}", flush=True)
    print("    calibration never became self-consistent -- treating this "
          "calibration as unusable", flush=True)
    return None


def measure_refs_guarded(soc, soccfg, cfg, expected_sep=None, retries=1):
    refs = measure_refs(soc, soccfg, cfg)
    tries = 0
    while not refs_sane(refs, expected_sep) and tries < int(retries):
        print(f"    reference separation {refs['separation']:.0f} is far from the "
              f"expected {float(expected_sep):.0f} -- glitch suspected, re-measuring "
              f"the references", flush=True)
        refs = measure_refs(soc, soccfg, cfg)
        tries += 1
    return refs, refs_sane(refs, expected_sep)


def fit_legacy_from_raw(lg, ug, le, ue, iters, eta):
    return rot.fit_legacy_from_raw(lg, ug, le, ue, iters, eta)


def fit_from_raw(lg, ug, le, ue, iters, eta):
    return rot.fit_raw_calibration(lg, ug, le, ue, iters, eta)


def probe_and_fit(soc, soccfg, cfg, iters, eta_fallback, path="q4", outer_folder="",
                  suffix="ResetBench_Probe"):
    probe = ActiveResetProbe(soc=soc, soccfg=soccfg, path=path,
                             outerFolder=outer_folder, suffix=suffix, cfg=dict(cfg))
    data = probe.acquire().get("data", {})
    plt.close("all")
    gc.collect()
    raw = getattr(probe, "raw_shots", None)
    if not raw or "ground" not in raw or "excited" not in raw:
        print("    probe exposed no raw_shots -- cannot fit the rotation.")
        return None
    eta = (data.get("reset_threshold_tuning") or {}).get("pi_efficiency")
    if eta is None or not np.isfinite(eta) or eta <= 0:
        eta = float(eta_fallback)
    fit = fit_from_raw(raw["ground"]["lower"], raw["ground"]["upper"],
                       raw["excited"]["lower"], raw["excited"]["upper"],
                       iters, eta)
    fit.update({"probe_floor": data.get("reset_floor"),
                "probe_errors": data.get("raw_assignment_errors", {}),
                "probe_raw_F": data.get("raw_assignment_fidelity"),
                "probe_recommended": data.get("recommended")})
    return fit


def print_fit(fit):
    rep = fit["report"]
    plan = fit["plan"]
    print(f"  theta = {np.rad2deg(fit['theta']):+7.2f} deg | 2^{fit['shift']} -> "
          f"C={fit['c_int']}, S={fit['s_int']} | headroom "
          f"{fit['headroom_worst']:.2e} / {rot.INT32_MAX:.2e}")
    print(f"  asm plan: acc = {plan['c_abs']}*I {plan['combine_op']} "
          f"{plan['s_abs']}*Q   (multiply immediates are non-negative by "
          f"construction; excited_above={plan['excited_above']}, "
          f"latch sink {fit['latch_sink']})")
    print(f"  separation:  lower {rep['sep_lower']:8.0f}   upper {rep['sep_upper']:8.0f}"
          f"   best single {rep['sep_best_single']:8.0f}   rotated "
          f"{rep['sep_rotated']:8.0f}   gain {rep['gain_vs_best_single']:.2f}x")


def arm_cfg(cfg, scheme, fit, legacy=None):
    out = dict(cfg)
    out["reset_scheme"] = str(scheme)
    if scheme == "none":
        return out
    if scheme == "old":
        rec = legacy if legacy is not None else fit["old"]
        if rec is None:
            raise RuntimeError("no legacy threshold fit available for the 'old' arm")
        out.update({"reset_threshold_raw": int(rec["threshold_raw"]),
                    "reset_oper": str(rec.get("oper", fit["oper"])),
                    "reset_ground_below": bool(rec["ground_below"])})
        return out
    thr = fit["three"] if scheme in ("rot3", "rot3nl") else fit["two"]
    out.update({"rot_c_int": fit["c_int"], "rot_s_int": fit["s_int"],
                "rot_excite_threshold": thr["excite_threshold"],
                "rot_ground_threshold": thr.get("ground_threshold"),
                "rot_latch_sink": fit["latch_sink"]})
    return out


def rot_reset_params(fit, max_iters):
    return rot.reset_params_from_fit(fit, max_iters)


def _dispatching_reset_block(original):
    def dispatch(prog, **kw):
        params = None
        try:
            params = prog.cfg.get("rot_reset")
        except Exception:
            params = None
        if not params:
            kw["allow_legacy"] = True
            return original(prog, **kw)
        return rot.active_reset_rot_block(
            prog, ro_ch=kw.get("ro_ch", 0),
            c_int=params["c_int"], s_int=params["s_int"],
            excite_threshold=params["excite_threshold"],
            max_iters=int(params.get("max_iters", kw.get("max_iters", 3))),
            three_zone=False, use_latch=False)
    return dispatch


@contextlib.contextmanager
def patched_production_reset():
    original = ar.active_reset_block
    ar.active_reset_block = _dispatching_reset_block(original)
    try:
        yield
    finally:
        ar.active_reset_block = original
