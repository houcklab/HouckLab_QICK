"""Interleaved UndrivenSingleShot + coherence loop.

One cycle runs, in order: UndrivenSingleShot -> T1 -> T2R -> T2E, each toggled
independently in IL_params. The cycle repeats IL_params["cycles"] times, so a
long unattended run alternates parity/blob records with the coherence numbers
measured under the same conditions.

Config regimes: UndrivenSingleShot needs the single-shot config
(rebuild_singleshot_config, SS_params readout window) while T1/T2R/T2E need the
pre-rebuild config built by build_context. Both are built once here and swapped
per step, so call this BEFORE the runner's own rebuild_singleshot_config() —
ctx.config is restored on the way out and that call then behaves identically.

Every step writes its own timestamped h5/png/json exactly as the standalone
runs do; nothing is displayed on screen mid-loop (a blocking plot window would
stall the loop).

Each record is tagged with its position in the loop via four config keys —
interleave_run_id, interleave_cycle, interleave_cycles_total, interleave_step —
which save_config() writes into BOTH the .json and the h5 "config" attribute, so
the four steps of one cycle can be grouped offline:

    import json, h5py
    with h5py.File(fname) as f:
        c = json.loads(f.attrs["config"])
    c["interleave_cycle"], c["interleave_run_id"]

run_id is the wall-clock start of the loop, so records from separate invocations
on the same day stay distinguishable.
"""

from datetime import datetime

from .context import rebuild_singleshot_config
from .coherence import run_t1, run_t2, run_t2e
from .singleshot import run_undriven_single_shot


def run_interleaved_coherence(ctx, IL_params, US_params, T1T2_params,
                              T2E_params, SS_params):
    coh_cfg = ctx.config
    rebuild_singleshot_config(ctx, SS_params)
    ss_cfg = ctx.config

    # one pass per cycle, never blocking on a plot window
    once = {"repetitions": 1, "plotDisp": False}
    steps = (
        ("UndrivenSingleShot", ss_cfg, run_undriven_single_shot,
         US_params | {"Repeat": 1, "plotDisp": False}),
        ("T1",  coh_cfg, run_t1,  T1T2_params | once),
        ("T2R", coh_cfg, run_t2,  T1T2_params | once),
        ("T2E", coh_cfg, run_t2e, T2E_params | once),
    )

    n_cycles = max(1, int(IL_params.get("cycles", 1)))
    enabled = [name for name, *_ in steps if IL_params.get(name, False)]
    if not enabled:
        print("[Interleave] no experiments enabled; nothing to do.")
        return
    run_id = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    print(f"[Interleave] run {run_id}: {n_cycles} cycle(s) of: "
          f"{' -> '.join(enabled)}")

    try:
        for k in range(n_cycles):
            for name, cfg, run, params in steps:
                if not IL_params.get(name, False):
                    continue
                print(f"\n[Interleave] cycle {k + 1}/{n_cycles}: {name}")
                # tags the .json + h5 config attr of whatever this step saves
                ctx.config = cfg | {"interleave_run_id": run_id,
                                    "interleave_cycle": k,
                                    "interleave_cycles_total": n_cycles,
                                    "interleave_step": name}
                run(ctx, params)
    finally:
        ctx.config = coh_cfg
