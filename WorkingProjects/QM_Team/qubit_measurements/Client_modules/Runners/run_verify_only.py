"""Run ONLY the ModifiedRamsey verification, using a runner's device parameters.

Running the runner itself to get at RunVerifyModifiedRamsey also executes every
other flag that happens to be enabled in it (on 2026-07-28 that meant an
unintended 21x21 SingleShot_ReadoutOptimize sweep). This driver executes the
runner's parameter section only -- everything above its "3. EXECUTE" banner --
so the device parameters stay single-sourced, then builds the context and runs
the verification stage by itself.

    python WorkingProjects/.../Runners/run_verify_only.py [runner.py]

Defaults to TATQ01-SiO2_BFG.py next to this file.
"""

import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXECUTE_BANNER = "# 3. EXECUTE"


def load_runner_params(runner_path):
    """Exec a runner's parameter section and return its namespace."""
    src = io.open(runner_path, encoding="utf-8").read()
    if _EXECUTE_BANNER not in src:
        raise RuntimeError(
            f"{runner_path} has no '{_EXECUTE_BANNER}' banner; cannot separate "
            "parameters from the execute block.")
    head = src.split(_EXECUTE_BANNER)[0]
    ns = {"__file__": runner_path, "__name__": "_runner_params"}
    exec(compile(head, runner_path, "exec"), ns)
    return ns


def main(runner_path=None):
    runner_path = runner_path or os.path.join(_HERE, "TATQ01-SiO2_BFG.py")
    ns = load_runner_params(runner_path)
    print(f"[verify-only] parameters from {os.path.basename(runner_path)}: "
          f"Qubit_Readout={ns['Qubit_Readout']}, UseYoko={ns['UseYoko']}")

    ctx = ns["build_context"](
        ns["Qubit_Parameters"], ns["Qubit_Readout"], ns["Qubit_Pulse"],
        ns["start_voltage"],
        Transmission_params=ns["Transmission_params"],
        Spec_relevant_params=ns["Spec_relevant_params"],
        tl=ns["tl"], ts=ns["ts"], charge_params=ns["charge_params"],
        cavity_min=ns["cavity_min"], yoko_fixed=ns["yoko_fixed"],
        use_yoko=ns["UseYoko"], yoko_addr=ns["yoko_addr"],
    )
    try:
        result = ns["run_verify_modified_ramsey"](
            ctx, ns.get("VerifyModifiedRamsey_params", {}))
    finally:
        ctx.yoko.close()

    board = result.get("board") or {}
    offline = result.get("offline") or {}
    ok = bool(offline.get("passed", True)) and bool(board.get("passed", False))
    print(f"[verify-only] offline={offline.get('passed')} board={board.get('passed')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
