"""Stage 1 of the basic auto tuner: find the resonator and the qubit transition.

This runner stops immediately after the pre-expensive qualification gate and prints a
paste-ready block for ``BasicGainSearch.py``.  It never optimizes gains and never
writes ``initialize.py``.
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
    configure_discovery_stage,
)

QUBIT = "q4"
LIVE_PLOTS = False

P_DISCOVERY = configure_discovery_stage(BASIC_DEFAULTS)


def _print_handoff(result):
    handoff = result.get("discovery_handoff")
    if not isinstance(handoff, dict):
        print("\n[discovery] no handoff was produced; the resonator and qubit "
              "transition were not both confirmed.")
        gate = result.get("pre_expensive_gate", {})
        for failure in (gate.get("failures", [])
                        if isinstance(gate, dict) else []):
            print("   %s" % failure)
        return False
    print("\n[discovery] STAGE 1 COMPLETE -- paste this into BasicGainSearch.py:")
    print("\nDISCOVERY = {")
    for key in ("read_pulse_freq", "read_pulse_gain", "read_length",
                "qubit_pi_freq", "qubit_pi_gain", "sigma", "qubit_drag_beta"):
        value = handoff.get(key)
        print("    %-34s %r," % ('"%s":' % key, value))
    print("    %-34s %r," % ('"qualified_transition_frequencies_mhz":',
                             handoff.get("qualified_transition_frequencies_mhz")))
    print("}")
    print("\n[discovery] context (not pasted):")
    print("   resonator            %s MHz" % handoff.get("resonator_frequency_mhz"))
    print("   resonator candidates %s" % handoff.get("resonator_candidates_mhz"))
    print("   spectroscopy lines   %s" % handoff.get("spectroscopy_candidates_mhz"))
    print("   verified             %s" % handoff.get("discovery_verified"))
    return True


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    experiment = BasicAutoTuner(
        soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
        suffix="Basic_Discovery", cfg=cfg,
        params=copy.deepcopy(P_DISCOVERY),
    )
    acquired = None
    error = None
    try:
        acquired = experiment.acquire(plotDisp=LIVE_PLOTS)
    except KeyboardInterrupt:
        error = "interrupted by operator"
        print("\n[discovery] interrupted; preserving completed measurements.")
    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        print("\n[discovery] acquisition stopped (%s); preserving partial data."
              % error)
    finally:
        for name in ("save_data", "save_plot"):
            saver = getattr(experiment, name, None)
            if callable(saver):
                try:
                    saver()
                except Exception as exc:
                    print("[discovery] %s failed: %s" % (name, exc))

    result = {}
    if isinstance(acquired, dict):
        nested = acquired.get("data")
        result = nested if isinstance(nested, dict) else acquired
    elif isinstance(getattr(experiment, "data", None), dict):
        result = experiment.data

    ok = _print_handoff(result)
    if getattr(experiment, "iname", None):
        print("   Summary plot: %s" % experiment.iname)
    print("\n[discovery] BaseConfig is untouched.")
    return 0 if ok and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
