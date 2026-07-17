"""
TLS spectroscopy pipeline (QICK port of Houck-Lab-Qua/.../Flux_Tunable/TLSSpectroscopy.py),
configured for FTTv02_SiOxJJ qubit 4 in the ALL-FAST-FLUX (no-Yoko) workflow.

All flux control is the ff_ch DAC (gen 3 -> DAC 3_230 P/N); the static park is
``ff_park_gain`` (held via stdysel='last').  Flux-axis units everywhere are ff_gain
DAC units.  Step ordering for this workflow:

  4  qubit spec vs ff_gain (long-time)   -> FLUX_FIT_PARAMS (DAC units) + f_q map
  3a flux step-response FIT               -> predistortion JSON
  3b flux step-response CORRECT           -> verify settling is flat
  5  single-shot readout calibration      -> calib_params (threshold/theta)
  6  T1 vs ff_gain (THE TLS MAP)          -> T1 / 1/T1 dips vs qubit frequency

(Steps 1-2, resonator/spec vs DC flux, are OPTIONAL Yoko-swept extras kept for
completeness; they are not needed here because readout always happens at park.)

Run from the HouckLab_QICK repo root on the measurement PC:
    python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy
"""

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig, FLUX_FIT_PARAMS, FF_PARK_GAIN, FF_STEP_TARGET_GAIN, outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmissionVsFlux import TransmissionVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpecVsFlux import QubitSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import QubitFluxStepResponse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitLongTimeSpecVsFlux import QubitLongTimeSpecVsFlux
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    T1FullCurveVsFlux, T13PointVsFlux, run_wall_clock_repeat,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx


QUBIT = "q4"   # data subfolder under outerFolder (matches the existing .../RFSOC/q4/)


# ---- per-step parameters (edit + flip 'run' flags) --------------------------
P4_LONG_TIME = dict(
    run=False, reps=100,
    # spec window: park f01 ~ 2557 MHz; flux tuning pulls it DOWN from there
    qubit_freq_start=2250.0, qubit_freq_stop=2570.0, qubit_freq_expts=161,   # 2 MHz steps
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=61,
    long_time_us=5.0, average_window_us=2.0, average_step_us=0.5,
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
)

P3_STEP_RESPONSE = dict(
    run_fit=False, run_correct=False, reps=200,
    qubit_gain=2000,                     # weak spec probe (QUA spec_amp=0.2 analog)
    qubit_freq_start=2350.0, qubit_freq_stop=2570.0, qubit_freq_expts=111,
    ff_gain=FF_STEP_TARGET_GAIN,         # step target (DAC); pick from step 4's map
    t_min_us=1.0, t_max_us=200.0, t_step_us=4.0,
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
    piecewise_min_multiplier=0.5, piecewise_max_multiplier=1.5, correction_gain=0.75,
)

P5_SS_CAL = dict(run=False, ss_shots=2000, min_F=0.60)

P6_3PT_T1 = dict(
    run=False, shots=2000,
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=201,
    freq_step_mhz=1,        # freq-UNIFORM flux scan from the flux fit (QUA beat);
                            # None -> plain gain-linspace of ff_gain_num points
    Ts_us=100.0,            # None -> auto: Ts = auto_Ts_factor * T1_park (probe below)
    auto_Ts_factor=0.5, run_park_T1_if_Ts_none=True,
    T1_probe_cfg=dict(shots_T1=1000, t_min_us=1.0, t_max_us=300.0, t_points=71),
    min_ref_contrast=0.05, relax_delay=5000,
    ff_ramp_length=0.02, dt_pulseplay=5.0, dt_pulsedef=0.002,
    wall_clock_duration_min=None,
)

P6_FULL_T1 = dict(
    run=False, shots=1000,
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=101,
    freq_step_mhz=2,        # freq-uniform flux scan (QUA beat); None -> linspace
    t_min_us=1.0, t_max_us=300.0, t_points=41, relax_delay=5000,
    ff_ramp_length=0.02, dt_pulseplay=5.0, dt_pulsedef=0.002,
    wall_clock_duration_min=None,
)

# ---- OPTIONAL Yoko-swept steps 1-2 (not part of the all-FF workflow) --------
P1_RESONATOR = dict(
    run=False, reps=200,
    trans_freq_start=7246.0, trans_freq_stop=7252.0, TransNumPoints=241,
    yokoVoltageStart=-0.4, yokoVoltageStop=0.4, yokoVoltageNumPoints=161,
)
P2_QUBIT_SPEC = dict(
    run=False, reps=500, qubit_gain=7000, qubit_length=0.5,
    qubit_freq_start=2250.0, qubit_freq_stop=2570.0, qubit_freq_expts=321,
    yokoVoltageStart=-0.4, yokoVoltageStop=0.4, yokoVoltageNumPoints=161,
)
YOKO_VISA = None   # set a VISA address AND flip the run flags above to use them


# ---- step functions ---------------------------------------------------------
def run_step4(soc, soccfg, correction_json=None):
    """Spec vs ff_gain at long delays: settling check + f_q(ff_gain) map + the
    transmon-arc fit (FLUX_FIT_PARAMS in DAC units).  Runs FIRST in this workflow."""
    p = P4_LONG_TIME
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) \
        if correction_json else None
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_freq_start", "qubit_freq_stop", "qubit_freq_expts",
                         "ff_gain_start", "ff_gain_stop", "ff_gain_num", "long_time_us",
                         "average_window_us", "average_step_us",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    exp = QubitLongTimeSpecVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                  cfg=cfg, flux_tail_compensation=comp)
    data = exp.acquire()
    ff_g = data['data']['ff_gains']
    fq = data['data']['long_time_freq_ghz']
    good = np.isfinite(fq)
    ff_gain_to_freq = None
    if good.sum() >= 2:
        gg, ff_ = ff_g[good], fq[good]
        ff_gain_to_freq = lambda g: float(np.interp(g, gg, ff_))
    return ff_gain_to_freq, data['data'].get('flux_fit_params')


def run_step3a(soc, soccfg, flux_fit_params):
    if flux_fit_params is None:
        raise RuntimeError("Step 3a needs FLUX_FIT_PARAMS (ff_gain DAC units). "
                           "Run step 4 first (it fits and prints them), then paste "
                           "them into Calib/initialize.py or rerun with step 4 on.")
    p = P3_STEP_RESPONSE
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_freq_start", "qubit_freq_stop",
                         "qubit_freq_expts", "ff_gain",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    cfg["t_vec_us"] = np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"])
    exp = QubitFluxStepResponse(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                cfg=cfg, flux_fit_params=flux_fit_params, run_fit=True,
                                qubit_name=QUBIT,
                                piecewise_min_multiplier=p["piecewise_min_multiplier"],
                                piecewise_max_multiplier=p["piecewise_max_multiplier"],
                                correction_gain=p["correction_gain"])
    data = exp.acquire()
    return data['data'].get('rise_decay_bump_dc_compensation_json')


def run_step3b(soc, soccfg, flux_fit_params, correction_json):
    p = P3_STEP_RESPONSE
    if correction_json is None:
        correction_json = QubitLongTimeSpecVsFlux.find_latest_dc_compensation_json(
            outerFolder, QUBIT)
        if correction_json is None:
            raise RuntimeError("No correction JSON found; run step 3a first.")
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_freq_start", "qubit_freq_stop",
                         "qubit_freq_expts", "ff_gain",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    cfg["t_vec_us"] = np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"])
    exp = QubitFluxStepResponse(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                cfg=cfg, flux_fit_params=flux_fit_params, run_fit=False,
                                correction_json=correction_json, qubit_name=QUBIT)
    exp.acquire()
    return correction_json


def run_step5(soc, soccfg):
    p = P5_SS_CAL
    cfg = BaseConfig | {"shots": p["ss_shots"]}
    cfg["qubit_pulse_style"] = "arb"
    cfg["qubit_gain"] = BaseConfig["qubit_pi_gain"]   # excited blob = pi pulse
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                      cfg=cfg, min_F=p["min_F"])
    ss.acquire()
    print(f"[5] calib_params = {ss.calib_params}")
    return ss.calib_params


def _t1_base(p, comp):
    base = BaseConfig | {k: p[k] for k in p if k not in
                         ("run", "wall_clock_duration_min")}
    base["qubit_pulse_style"] = "arb"
    if comp is not None:
        base["flux_tail_compensation"] = comp
    return base


def _build_ff_gain_vec(p, flux_fit_params, tag):
    """Freq-UNIFORM flux vector from the flux fit (QUA _build_freq_uniform_dc_vec
    beat), falling back to a plain gain-linspace when no fit/step is available."""
    step_mhz = p.get("freq_step_mhz")
    if step_mhz and flux_fit_params is not None:
        vec = fx.build_freq_uniform_dc_vec(p["ff_gain_start"], p["ff_gain_stop"],
                                           float(step_mhz) * 1e6, flux_fit_params)
        f_edges = fx.estimate_fit_frequency_ghz_array(
            flux_fit_params, np.array([vec.min(), vec.max()]))
        print(f"[6] freq-uniform ff_gain scan from flux fit: {len(vec)} points at "
              f"{step_mhz:g} MHz steps (gain {vec.min():g}..{vec.max():g}, "
              f"f {min(f_edges):.3f}..{max(f_edges):.3f} GHz)")
        return vec
    if step_mhz:
        print(f"[6] freq_step_mhz set but no FLUX_FIT_PARAMS -> gain-linspace "
              f"({tag}); run step 4 first for a freq-uniform scan.")
    return np.linspace(p["ff_gain_start"], p["ff_gain_stop"], int(p["ff_gain_num"]))


def run_step6_3pt(soc, soccfg, calib_params, correction_json, ff_gain_to_freq,
                  flux_fit_params=None):
    p = P6_3PT_T1
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) \
        if correction_json else None
    base = _t1_base(p, comp)
    ff_gains = _build_ff_gain_vec(p, flux_fit_params, "3pt")
    base["ff_gain_vec"] = ff_gains
    wc = p["wall_clock_duration_min"]
    print(f"[6] 3-point T1 vs flux (distortion-{'corrected' if comp else 'UNcorrected'}): "
          f"{len(ff_gains)} flux points, "
          f"{'single pass' if not wc else f'wall-clock {wc:g} min'}")

    def factory():
        return T13PointVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                              cfg=dict(base), calib_params=calib_params,
                              ff_gain_to_freq=ff_gain_to_freq,
                              suffix="TLS_3pt_T1_vs_Flux")

    if wc:
        csv = outerFolder + f"/{QUBIT}/TLS_3pt_T1_wall_clock.csv"
        run_wall_clock_repeat(factory, "inv_T1_3pt_per_us", ff_gains, csv,
                              duration_min=wc)
    else:
        factory().acquire()


def run_step6_full(soc, soccfg, calib_params, correction_json, ff_gain_to_freq,
                   flux_fit_params=None):
    p = P6_FULL_T1
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) \
        if correction_json else None
    base = _t1_base(p, comp)
    ff_gains = _build_ff_gain_vec(p, flux_fit_params, "full")
    base["ff_gain_vec"] = ff_gains
    wc = p["wall_clock_duration_min"]
    print(f"[6] Full T1 vs flux (distortion-{'corrected' if comp else 'UNcorrected'}): "
          f"{len(ff_gains)} flux points, "
          f"{'single pass' if not wc else f'wall-clock {wc:g} min'}")

    def factory():
        return T1FullCurveVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                 cfg=dict(base), calib_params=calib_params,
                                 ff_gain_to_freq=ff_gain_to_freq,
                                 suffix="TLS_Full_T1_vs_Flux")

    if wc:
        csv = outerFolder + f"/{QUBIT}/TLS_Full_T1_wall_clock.csv"
        run_wall_clock_repeat(factory, "inv_T1_per_us", ff_gains, csv,
                              duration_min=wc)
    else:
        factory().acquire()


# ---- optional Yoko-swept steps 1-2 ------------------------------------------
def _make_yoko():
    import pyvisa as visa
    from WorkingProjects.TLS_Spectroscopy.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
    yoko = YOKOGS200(YOKO_VISA, rm=visa.ResourceManager())
    yoko.SetMode('voltage')
    return yoko


def run_step1(soc, soccfg, yoko):
    p = P1_RESONATOR
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "trans_freq_start", "trans_freq_stop", "TransNumPoints",
                         "yokoVoltageStart", "yokoVoltageStop", "yokoVoltageNumPoints")}
    exp = TransmissionVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                             cfg=cfg, flux_source=yoko)
    data = exp.acquire()
    return data['data'].get('resonator_lookup_csv')


def run_step2(soc, soccfg, yoko, resonator_lookup_csv=None):
    p = P2_QUBIT_SPEC
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_length", "qubit_freq_start",
                         "qubit_freq_stop", "qubit_freq_expts",
                         "yokoVoltageStart", "yokoVoltageStop", "yokoVoltageNumPoints")}
    cfg["qubit_pulse_style"] = "const"
    exp = QubitSpecVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                          cfg=cfg, flux_source=yoko, resonator_lookup_csv=resonator_lookup_csv)
    exp.acquire()


def main():
    soc, soccfg = makeProxy()

    print("=" * 70)
    print(f"TLS spectroscopy pipeline (all-fast-flux) | FTTv02_SiOxJJ {QUBIT}")
    print(f"park ff_gain = {BaseConfig['ff_park_gain']} DAC | "
          f"step-response target = {P3_STEP_RESPONSE['ff_gain']} DAC | ff_ch = {BaseConfig['ff_ch']}")
    steps = [("4_spec_vs_ff_gain (map + flux fit)", P4_LONG_TIME["run"]),
             ("3a_step_response_fit", P3_STEP_RESPONSE["run_fit"]),
             ("3b_step_response_correct", P3_STEP_RESPONSE["run_correct"]),
             ("5_single_shot_cal", P5_SS_CAL["run"]),
             ("6_3pt_t1_vs_flux", P6_3PT_T1["run"]),
             ("6_full_t1_vs_flux", P6_FULL_T1["run"]),
             ("1_resonator_vs_flux (optional, Yoko)", P1_RESONATOR["run"]),
             ("2_qubit_spec_vs_flux (optional, Yoko)", P2_QUBIT_SPEC["run"])]
    for name, on in steps:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    flux_fit_params = FLUX_FIT_PARAMS
    correction_json = None
    calib_params = None
    ff_gain_to_freq = None
    resonator_lookup_csv = None

    if P4_LONG_TIME["run"]:
        ff_gain_to_freq, fit = run_step4(soc, soccfg, correction_json)
        if fit is not None:
            flux_fit_params = fit
    if P3_STEP_RESPONSE["run_fit"]:
        correction_json = run_step3a(soc, soccfg, flux_fit_params)
    if P3_STEP_RESPONSE["run_correct"]:
        correction_json = run_step3b(soc, soccfg, flux_fit_params, correction_json)
    if P5_SS_CAL["run"]:
        calib_params = run_step5(soc, soccfg)
    if P6_3PT_T1["run"]:
        if calib_params is None:
            print("[6] Step 5 was skipped; running single-shot calibration for the T1.")
            calib_params = run_step5(soc, soccfg)
        run_step6_3pt(soc, soccfg, calib_params, correction_json, ff_gain_to_freq,
                      flux_fit_params)
    if P6_FULL_T1["run"]:
        if calib_params is None:
            print("[6] Step 5 was skipped; running single-shot calibration for the T1.")
            calib_params = run_step5(soc, soccfg)
        run_step6_full(soc, soccfg, calib_params, correction_json, ff_gain_to_freq,
                       flux_fit_params)

    if P1_RESONATOR["run"] or P2_QUBIT_SPEC["run"]:
        if YOKO_VISA is None:
            raise RuntimeError("Steps 1-2 are Yoko-swept: set YOKO_VISA to use them.")
        yoko = _make_yoko()
        if P1_RESONATOR["run"]:
            resonator_lookup_csv = run_step1(soc, soccfg, yoko)
        if P2_QUBIT_SPEC["run"]:
            run_step2(soc, soccfg, yoko, resonator_lookup_csv)

    print("\nTLS spectroscopy pipeline complete.")


if __name__ == "__main__":
    main()
