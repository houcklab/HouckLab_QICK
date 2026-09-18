import copy
from os import environ

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls


def _f(name, default):
    return float(environ.get(name, default))


def _i(name, default):
    return int(environ.get(name, default))


def _flag(name, default="0"):
    return str(environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def build_params():
    p = copy.deepcopy(tls.P3_STEP_RESPONSE)
    p["run_fit"] = True
    p["run_correct"] = False
    p["fit_residual_composition"] = False
    p["correction_fit_start_us"] = _f("Q3_STEP3A_FIT_START_US",
                                      p.get("correction_fit_start_us", 100.0))
    p["t_min_us"] = _f("Q3_STEP3A_DELAY_MIN_US", 1.0)
    p["t_max_us"] = _f("Q3_STEP3A_DELAY_MAX_US", 201.0)
    p["t_step_us"] = _f("Q3_STEP3A_DELAY_STEP_US", 1.0)
    p["t_vec_us"] = None
    p["shots"] = _i("Q3_STEP3A_SHOTS", p.get("shots", 200))
    p["spec_amp"] = _i("Q3_STEP3A_SPEC_AMP", p.get("spec_amp", 25000))
    p["spec_len_us"] = _f("Q3_STEP3A_SPEC_LEN_US", p.get("spec_len_us", 0.5))
    p["freq_step"] = _f("Q3_STEP3A_FREQ_STEP_MHZ", p.get("freq_step", 0.5))
    p["readout_after_park"] = _flag("Q3_STEP3A_READOUT_AFTER_PARK", "0")
    p["live_plot"] = _flag("Q3_STEP3A_LIVE_PLOT", "1")

    fmin = environ.get("Q3_STEP3A_FREQ_MIN_MHZ")
    fmax = environ.get("Q3_STEP3A_FREQ_MAX_MHZ")
    if fmin is not None and fmax is not None:
        lo, hi = float(fmin), float(fmax)
        if not np.isfinite(lo) or not np.isfinite(hi) or lo >= hi:
            raise ValueError("invalid Q3_STEP3A_FREQ_MIN_MHZ / MAX_MHZ")
        p["auto_center_frequency_window"] = False
        p["auto_freq_absolute_min_mhz"] = lo
        p["auto_freq_absolute_max_mhz"] = hi
        p["freq_min"] = lo
        p["freq_max"] = hi

    gain = environ.get("Q3_READOUT_OVERRIDE_GAIN")
    if gain is not None and str(gain).strip() != "":
        p["read_gain"] = int(gain)
    freq = environ.get("Q3_READOUT_OVERRIDE_FREQ_MHZ")
    if freq is not None and str(freq).strip() != "":
        p["read_freq_mhz"] = float(freq)
    rlen = environ.get("Q3_READOUT_OVERRIDE_READ_LEN_US")
    if rlen is not None and str(rlen).strip() != "":
        p["read_len_us"] = float(rlen)
    return p


FIT = _flag("Q3_STEP3A_FIT", "0")


def main():
    p = build_params()
    n_delays = int(np.floor((p["t_max_us"] - p["t_min_us"]) / p["t_step_us"]))
    park = tls._baseline_dc_offset()
    target = float(tls.TARGET_DC_OFFSET)
    fq = tls.fx.estimate_fit_frequency_mhz if hasattr(tls.fx, "estimate_fit_frequency_mhz") else None

    print("")
    print("=========== q3 clean step 3a (uncorrected) ===========")
    print(f"  park ff_gain        : {park:+.0f} DAC")
    print(f"  TARGET ff_gain      : {target:+.0f} DAC")
    print(f"  delays              : {p['t_min_us']:g} .. {p['t_max_us']:g} us step "
          f"{p['t_step_us']:g}  ({n_delays} points)")
    print(f"  frequency step      : {p['freq_step']:g} MHz")
    if not p.get("auto_center_frequency_window", True):
        print(f"  window              : {p['auto_freq_absolute_min_mhz']:.1f} .. "
              f"{p['auto_freq_absolute_max_mhz']:.1f} MHz  (explicit)")
    else:
        print(f"  window              : auto-centred inside "
              f"{p['auto_freq_absolute_min_mhz']:.1f} .. "
              f"{p['auto_freq_absolute_max_mhz']:.1f} MHz")
    print(f"  spec                : amp {p['spec_amp']} len {p['spec_len_us']:g} us")
    print(f"  shots               : {p['shots']}")
    print(f"  readout             : {'PARK' if p['readout_after_park'] else 'TARGET'}")
    if "read_gain" in p:
        print(f"  read gain override  : {p['read_gain']}")
    if "read_freq_mhz" in p:
        print(f"  read freq override  : {p['read_freq_mhz']:.4f} MHz")
    print(f"  correction          : OFF (nothing applied)")
    print(f"  fit a correction    : {'YES' if FIT else 'no'}"
          + (f"  (fit starts at {p['correction_fit_start_us']:g} us)" if FIT else ""))
    print("======================================================")
    print("")

    soc, soccfg = tls.makeProxy()
    tls._set_yoko_if_requested()
    exp = tls._run_step3_experiment(
        p, soc, soccfg, tls.outerFolder,
        suffix="Qubit_Flux_Step_Response_Clean3A",
        flux_tail_compensation=None, fit_rise_decay_bump_dc_correction=FIT,
        live_plot=bool(p.get("live_plot", True)) and tls.LIVE_PLOTS,
    )
    print("")
    print("=========== done ===========")
    if FIT:
        js = exp.data.get("rise_decay_bump_dc_compensation_json")
        if js:
            print(f"  correction JSON: {js}")
            print("  validate it against an independent trace before applying it")
        else:
            print("  the fit did NOT emit a correction JSON; the confidence gate")
            print("  rejected it. Inspect the raw map before lowering any threshold.")
    else:
        print("  no correction was fitted or saved")
    print("============================")
    print("")
    return exp


if __name__ == "__main__":
    main()
