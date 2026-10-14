"""Interleaved UndrivenSingleShot -> T1 -> T2R -> T2E loop, swapping config regimes per step.

Call in regime A (ctx.config is restored on exit); every record is tagged with interleave_* keys:
docs/experiments/interleaved_coherence.md
"""

from qicklab.core.config import rebuild_singleshot_config
from qicklab.core.io import timestamp
from qicklab.runs.coherence import run_t1, run_t2, run_t2e
from qicklab.runs.single_shot import run_undriven_single_shot


def run_interleaved_coherence(ctx, IL_params, US_params, T1T2_params, T2E_params, SS_params):
    coh_cfg = ctx.config
    rebuild_singleshot_config(ctx, SS_params)
    ss_cfg = ctx.config

    # one pass per cycle, never blocking on a plot window
    once = {"repetitions": 1, "plotDisp": False}
    steps = (
        (
            "UndrivenSingleShot",
            ss_cfg,
            run_undriven_single_shot,
            US_params | {"Repeat": 1, "plotDisp": False},
        ),
        ("T1", coh_cfg, run_t1, T1T2_params | once),
        ("T2R", coh_cfg, run_t2, T1T2_params | once),
        ("T2E", coh_cfg, run_t2e, T2E_params | once),
    )

    n_cycles = max(1, int(IL_params.get("cycles", 1)))
    enabled = [name for name, *_ in steps if IL_params.get(name, False)]
    if not enabled:
        print("[Interleave] no experiments enabled; nothing to do.")
        return
    run_id = timestamp()
    print(f"[Interleave] run {run_id}: {n_cycles} cycle(s) of: {' -> '.join(enabled)}")

    try:
        for k in range(n_cycles):
            for name, cfg, run, params in steps:
                if not IL_params.get(name, False):
                    continue
                print(f"\n[Interleave] cycle {k + 1}/{n_cycles}: {name}")
                # tags the .json + h5 config attr of whatever this step saves
                ctx.config = cfg | {
                    "interleave_run_id": run_id,
                    "interleave_cycle": k,
                    "interleave_cycles_total": n_cycles,
                    "interleave_step": name,
                }
                run(ctx, params)
    finally:
        ctx.config = coh_cfg
