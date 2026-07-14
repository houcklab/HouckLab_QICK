"""
TLS spectroscopy pipeline (QICK port of Houck-Lab-Qua/.../Flux_Tunable/TLSSpectroscopy.py).

Six steps, gated by ``run`` flags, sharing config + calibration artifacts:
  1  resonator transmission vs DC flux        -> resonator lookup CSV
  2  qubit spectroscopy vs DC flux            -> FLUX_FIT_PARAMS (transmon arc)
  3a flux step-response FIT                    -> predistortion JSON
  3b flux step-response CORRECT (verify flat)
  4  long-time qubit spec vs fast-flux target -> f_q(ff_gain) settling check + map
  5  single-shot readout calibration          -> calib_params (threshold/theta)
  6  T1 vs fast-flux target (THE TLS MAP)      -> T1 / 1/T1 dips vs qubit frequency

Run from the HouckLab_QICK repo root (so ``WorkingProjects...`` imports resolve):
    python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSSpectroscopy

Steps 1 & 2 sweep the STATIC flux (Yokogawa GS200).  Steps 3, 4, 6 use the FAST-FLUX
DAC pulse (ff_ch), predistorted by the step-3 compensation, with the Yoko parked at
BASELINE_DC_OFFSET.  Every '# DEVICE' number in initialize.py must be tuned on your
cooldown; the numbers below are starting points.
"""

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig, FLUX_FIT_PARAMS, BASELINE_DC_OFFSET, TARGET_DC_OFFSET, outerFolder,
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


QUBIT = "q1"

# ---- static-flux source (Yokogawa GS200).  Set None to leave the bias untouched. ----
SET_YOKO = False
YOKO_VISA = "USB0::0x0B21::0x0039::91S929899::0::INSTR"   # DEVICE


# ---- per-step parameters (edit + flip 'run' flags) --------------------------
P1_RESONATOR = dict(
    run=False, reps=200,
    trans_freq_start=6900.0, trans_freq_stop=6905.0, TransNumPoints=201,   # MHz
    yokoVoltageStart=-0.05, yokoVoltageStop=0.42, yokoVoltageNumPoints=200,
)

P2_QUBIT_SPEC = dict(
    run=False, reps=500, qubit_gain=5000, qubit_length=0.5,
    qubit_freq_start=2100.0, qubit_freq_stop=2500.0, qubit_freq_expts=401,  # MHz
    yokoVoltageStart=-0.02, yokoVoltageStop=0.40, yokoVoltageNumPoints=200,
)

P3_STEP_RESPONSE = dict(
    run_fit=False, run_correct=False, reps=200, qubit_gain=2000, qubit_length=0.5,
    qubit_freq_start=2300.0, qubit_freq_stop=2450.0, qubit_freq_expts=151,   # MHz
    ff_gain=8000,                                     # DAC excursion for the probe step
    t_min_us=1.0, t_max_us=200.0, t_step_us=4.0,      # hold-delay axis
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
    piecewise_min_multiplier=0.5, piecewise_max_multiplier=1.5, correction_gain=0.75,
)

P4_LONG_TIME = dict(
    run=False, reps=100, qubit_gain=5000, qubit_length=0.5,
    qubit_freq_start=1950.0, qubit_freq_stop=2650.0, qubit_freq_expts=141,
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=60,
    long_time_us=5.0, average_window_us=2.0, average_step_us=0.5,
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
)

P5_SS_CAL = dict(run=False, ss_shots=2000, min_F=0.60, qubit_gain=None)  # qubit_gain=pi gain

P6_3PT_T1 = dict(
    run=False, shots=2000, qubit_pi_gain=None,          # set to your pi gain
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=200,
    Ts_us=100.0, min_ref_contrast=0.05,
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
    wall_clock_duration_min=None,
)

P6_FULL_T1 = dict(
    run=False, shots=1000, qubit_pi_gain=None,
    ff_gain_start=0, ff_gain_stop=12000, ff_gain_num=100,
    t_min_us=1.0, t_max_us=300.0, t_points=41,
    ff_ramp_length=0.02, dt_pulseplay=1.0, dt_pulsedef=0.002,
    wall_clock_duration_min=None,
)


def _set_yoko_if_requested(yoko, voltage):
    if not (SET_YOKO and yoko is not None):
        print("SET_YOKO is False: leaving the YOKO bias untouched.")
        return
    print(f"Ramping YOKO to {voltage:+.5f} V ...")
    yoko.SetVoltage(voltage)
    print("YOKO parked.")


# ---- step functions ---------------------------------------------------------
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
    data = exp.acquire()
    return data['data'].get('flux_fit_params')


def run_step3a(soc, soccfg, flux_fit_params):
    p = P3_STEP_RESPONSE
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_length", "qubit_freq_start",
                         "qubit_freq_stop", "qubit_freq_expts", "ff_gain",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    cfg["t_vec_us"] = np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"])
    cfg["baseline_dc_offset"] = BASELINE_DC_OFFSET
    cfg["dc_offset"] = TARGET_DC_OFFSET
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
            outerFolder, QUBIT, baseline_dc_offset=BASELINE_DC_OFFSET, dc_offset=TARGET_DC_OFFSET)
        if correction_json is None:
            raise RuntimeError("No correction JSON found; run step 3a first.")
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_length", "qubit_freq_start",
                         "qubit_freq_stop", "qubit_freq_expts", "ff_gain",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    cfg["t_vec_us"] = np.arange(p["t_min_us"], p["t_max_us"], p["t_step_us"])
    cfg["baseline_dc_offset"] = BASELINE_DC_OFFSET
    cfg["dc_offset"] = TARGET_DC_OFFSET
    exp = QubitFluxStepResponse(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                cfg=cfg, flux_fit_params=flux_fit_params, run_fit=False,
                                correction_json=correction_json, qubit_name=QUBIT)
    exp.acquire()
    return correction_json


def run_step4(soc, soccfg, correction_json):
    p = P4_LONG_TIME
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) if correction_json else None
    cfg = BaseConfig | {k: p[k] for k in
                        ("reps", "qubit_gain", "qubit_length", "qubit_freq_start",
                         "qubit_freq_stop", "qubit_freq_expts", "ff_gain_start",
                         "ff_gain_stop", "ff_gain_num", "long_time_us",
                         "average_window_us", "average_step_us",
                         "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    cfg["qubit_pulse_style"] = "const"
    exp = QubitLongTimeSpecVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                  cfg=cfg, flux_tail_compensation=comp)
    data = exp.acquire()
    # return the f_q(ff_gain) map so step 6 can label T1 vs qubit frequency
    ff_g = data['data']['ff_gains']
    fq = data['data']['long_time_freq_ghz']
    good = np.isfinite(fq)
    if good.sum() >= 2:
        gg, ff_ = ff_g[good], fq[good]
        return lambda g: float(np.interp(g, gg, ff_))
    return None


def run_step5(soc, soccfg):
    p = P5_SS_CAL
    cfg = BaseConfig | {"shots": p["ss_shots"]}
    cfg["qubit_pulse_style"] = "arb"
    if p.get("qubit_gain") is not None:
        cfg["qubit_gain"] = p["qubit_gain"]
    ss = SingleShot1Q(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                      cfg=cfg, min_F=p["min_F"])
    ss.acquire()
    print(f"[5] calib_params = {ss.calib_params}")
    return ss.calib_params


def run_step6_3pt(soc, soccfg, calib_params, correction_json, ff_gain_to_freq):
    p = P6_3PT_T1
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) if correction_json else None
    base = BaseConfig | {k: p[k] for k in
                         ("shots", "ff_gain_start", "ff_gain_stop", "ff_gain_num", "Ts_us",
                          "min_ref_contrast", "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    base["qubit_pulse_style"] = "arb"
    base["qubit_pi_gain"] = p["qubit_pi_gain"]
    if comp is not None:
        base["flux_tail_compensation"] = comp

    def factory():
        cfg = dict(base)
        return T13PointVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                              cfg=cfg, calib_params=calib_params,
                              ff_gain_to_freq=ff_gain_to_freq,
                              suffix="TLS_3pt_T1_vs_Flux")

    ff_gains = np.linspace(p["ff_gain_start"], p["ff_gain_stop"], int(p["ff_gain_num"]))
    if p["wall_clock_duration_min"]:
        csv = outerFolder + f"/{QUBIT}/TLS_3pt_T1_wall_clock.csv"
        run_wall_clock_repeat(factory, "inv_T1_3pt_per_us", ff_gains, csv,
                              duration_min=p["wall_clock_duration_min"])
    else:
        factory().acquire()


def run_step6_full(soc, soccfg, calib_params, correction_json, ff_gain_to_freq):
    p = P6_FULL_T1
    comp = QubitLongTimeSpecVsFlux.load_dc_compensation_json(correction_json) if correction_json else None
    base = BaseConfig | {k: p[k] for k in
                         ("shots", "ff_gain_start", "ff_gain_stop", "ff_gain_num",
                          "t_min_us", "t_max_us", "t_points",
                          "ff_ramp_length", "dt_pulseplay", "dt_pulsedef")}
    base["qubit_pulse_style"] = "arb"
    base["qubit_pi_gain"] = p["qubit_pi_gain"]
    if comp is not None:
        base["flux_tail_compensation"] = comp

    def factory():
        cfg = dict(base)
        return T1FullCurveVsFlux(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                                 cfg=cfg, calib_params=calib_params,
                                 ff_gain_to_freq=ff_gain_to_freq,
                                 suffix="TLS_Full_T1_vs_Flux")

    ff_gains = np.linspace(p["ff_gain_start"], p["ff_gain_stop"], int(p["ff_gain_num"]))
    if p["wall_clock_duration_min"]:
        csv = outerFolder + f"/{QUBIT}/TLS_Full_T1_wall_clock.csv"
        run_wall_clock_repeat(factory, "inv_T1_per_us", ff_gains, csv,
                              duration_min=p["wall_clock_duration_min"])
    else:
        factory().acquire()


def main():
    soc, soccfg = makeProxy()

    yoko = None
    if SET_YOKO:
        import pyvisa as visa
        from WorkingProjects.TLS_Spectroscopy.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
        yoko = YOKOGS200(YOKO_VISA, rm=visa.ResourceManager())
        yoko.SetMode('voltage')

    print("=" * 70)
    print(f"TLS spectroscopy pipeline | {QUBIT}")
    print(f"park/baseline = {BASELINE_DC_OFFSET:+.4f} V | step-response target = {TARGET_DC_OFFSET:+.4f} V")
    steps = [("1_resonator_vs_flux", P1_RESONATOR["run"]),
             ("2_qubit_spec_vs_flux", P2_QUBIT_SPEC["run"]),
             ("3a_step_response_fit", P3_STEP_RESPONSE["run_fit"]),
             ("3b_step_response_correct", P3_STEP_RESPONSE["run_correct"]),
             ("4_long_time_spec", P4_LONG_TIME["run"]),
             ("5_single_shot_cal", P5_SS_CAL["run"]),
             ("6_3pt_t1_vs_flux", P6_3PT_T1["run"]),
             ("6_full_t1_vs_flux", P6_FULL_T1["run"])]
    for name, on in steps:
        print(f"  {'[x]' if on else '[ ]'} {name}")
    print("=" * 70)

    flux_fit_params = FLUX_FIT_PARAMS
    resonator_lookup_csv = None
    correction_json = None
    calib_params = None
    ff_gain_to_freq = None

    if P1_RESONATOR["run"]:
        resonator_lookup_csv = run_step1(soc, soccfg, yoko)
    if P2_QUBIT_SPEC["run"]:
        fit = run_step2(soc, soccfg, yoko, resonator_lookup_csv)
        if fit is not None:
            flux_fit_params = fit
    if P3_STEP_RESPONSE["run_fit"]:
        correction_json = run_step3a(soc, soccfg, flux_fit_params)
    if P3_STEP_RESPONSE["run_correct"]:
        correction_json = run_step3b(soc, soccfg, flux_fit_params, correction_json)
    if P4_LONG_TIME["run"]:
        ff_gain_to_freq = run_step4(soc, soccfg, correction_json)
    if P5_SS_CAL["run"]:
        calib_params = run_step5(soc, soccfg)
    if P6_3PT_T1["run"]:
        if calib_params is None:
            calib_params = run_step5(soc, soccfg)
        run_step6_3pt(soc, soccfg, calib_params, correction_json, ff_gain_to_freq)
    if P6_FULL_T1["run"]:
        if calib_params is None:
            calib_params = run_step5(soc, soccfg)
        run_step6_full(soc, soccfg, calib_params, correction_json, ff_gain_to_freq)

    print("\nTLS spectroscopy pipeline complete.")


if __name__ == "__main__":
    main()
