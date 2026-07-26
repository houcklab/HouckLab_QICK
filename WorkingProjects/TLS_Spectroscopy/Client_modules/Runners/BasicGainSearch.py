"""Stage 2 of the basic auto tuner: maximize fidelity over readout and X180 gain.

Paste the ``DISCOVERY`` block printed by ``BasicDiscovery.py`` below.  This runner
takes those frequencies and the Gaussian sigma as given and searches only
``read_pulse_gain`` and ``qubit_pi_gain``, refining them coarse-to-fine down to the
configured target step.  It never writes ``initialize.py``.
"""

import copy

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mBasicAutoTuner import (
    BASIC_DEFAULTS,
    BasicAutoTuner,
    configure_gain_only_search,
    configure_gain_search_stage,
    configure_readout_length_mode,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.BasicAutoTune import (
    _print_best,
)

QUBIT = "q4"
LIVE_PLOTS = False

# True: report one gain-optimized calibration at every integer readout duration from
# 1 through 20 us.  False: use only BaseConfig["read_length"].
RUN_1_TO_20_US_MODE = False

# Paste the block printed by BasicDiscovery.py here.
DISCOVERY = {
    "read_pulse_freq": 7248.967089,
    "read_pulse_gain": 3700,
    "read_length": 10.0,
    "qubit_pi_freq": 2534.350291,
    "qubit_pi_gain": 2689,
    "sigma": 0.5,
    "qubit_drag_beta": 0.0,
    "qualified_transition_frequencies_mhz": [2534.350291],
}

P_GAIN = configure_gain_search_stage(
    configure_gain_only_search(
        configure_readout_length_mode(
            BASIC_DEFAULTS,
            DISCOVERY["read_length"] if not RUN_1_TO_20_US_MODE
            else BaseConfig["read_length"],
            scan_1_to_20_us=RUN_1_TO_20_US_MODE,
        ),
        DISCOVERY["sigma"],
    ),
    DISCOVERY,
)


def _print_gain_convergence(result):
    portfolio = result.get("duration_portfolio", {})
    entries = portfolio.get("entries", []) if isinstance(portfolio, dict) else []
    if not entries:
        return
    print("\n[gain-search] GAIN CONVERGENCE")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        search = entry.get("search", {})
        zoom = search.get("deterministic_gain_zoom", {}) if isinstance(
            search, dict) else {}
        vertex = search.get("gain_vertex", {}) if isinstance(search, dict) else {}
        selected = entry.get("selected")
        if not isinstance(selected, dict):
            continue
        print("   %5.1f us  read %6d DAC  X180 %6d DAC  |  final step %s/%s DAC "
              "in %s rounds%s"
              % (float(entry.get("read_length_us", float("nan"))),
                 int(round(float(selected.get("read_pulse_gain", 0)))),
                 int(round(float(selected.get("qubit_pi_gain", 0)))),
                 zoom.get("final_read_step_dac"),
                 zoom.get("final_qubit_step_dac"),
                 zoom.get("round_count"),
                 "; stopped on the noise floor"
                 if zoom.get("stopped_on_noise_floor") else ""))
        for axis in ("read", "qubit"):
            fit = vertex.get(axis) if isinstance(vertex, dict) else None
            if isinstance(fit, dict) and fit.get("ok"):
                se = fit.get("vertex_se_dac")
                print("             %-5s interpolated optimum %s DAC%s"
                      % (axis, fit.get("vertex_dac"),
                         "" if se is None else " +/- %.0f DAC (statistical)" % se))


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg.update({
        "read_pulse_freq": DISCOVERY["read_pulse_freq"],
        "read_pulse_gain": int(DISCOVERY["read_pulse_gain"]),
        "read_length": float(DISCOVERY["read_length"]),
        "qubit_freq": DISCOVERY["qubit_pi_freq"],
        "qubit_pi_freq": DISCOVERY["qubit_pi_freq"],
        "qubit_pi_gain": int(DISCOVERY["qubit_pi_gain"]),
        "qubit_gain": int(DISCOVERY["qubit_pi_gain"]),
        "sigma": float(DISCOVERY["sigma"]),
        "qubit_drag_beta": float(DISCOVERY.get("qubit_drag_beta", 0.0)),
    })
    experiment = BasicAutoTuner(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix="Basic_Gain_Search", cfg=cfg, params=copy.deepcopy(P_GAIN),
    )
    acquired = None
    error = None
    try:
        acquired = experiment.acquire(plotDisp=LIVE_PLOTS)
    except KeyboardInterrupt:
        error = "interrupted by operator"
        print("\n[gain-search] interrupted; preserving the best completed point.")
    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        print("\n[gain-search] acquisition stopped (%s); preserving partial data."
              % error)
    finally:
        for name in ("save_data", "save_plot"):
            saver = getattr(experiment, name, None)
            if callable(saver):
                try:
                    saver()
                except Exception as exc:
                    print("[gain-search] %s failed: %s" % (name, exc))

    result = {}
    if isinstance(acquired, dict):
        nested = acquired.get("data")
        result = nested if isinstance(nested, dict) else acquired
    elif isinstance(getattr(experiment, "data", None), dict):
        result = experiment.data

    best = _print_best(result)
    _print_gain_convergence(result)
    if getattr(experiment, "iname", None):
        print("   Summary plot: %s" % experiment.iname)
    print("\n[gain-search] BaseConfig is untouched; choose a row manually.")
    return 0 if best is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
