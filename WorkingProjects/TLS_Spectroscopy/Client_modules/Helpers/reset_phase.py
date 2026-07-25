import datetime

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mActiveResetProbe import ActiveResetProbe
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import config_updater


def calibrate_res_phase(soc, soccfg, base_cfg, path, outer_folder, apply_config=True,
                        sweep_shots=800, check_shots=3000, phase_step_deg=15.0,
                        relax_delay_us=500.0, suffix="Reset_Phase_Cal"):
    cfg = dict(base_cfg)
    cfg["shots"] = cfg["reps"] = int(sweep_shots)
    cfg["relax_delay"] = float(relax_delay_us)
    exp = ActiveResetProbe(soc=soc, soccfg=soccfg, path=path, outerFolder=outer_folder,
                           suffix=suffix, cfg=cfg)
    res = exp.calibrate_res_phase(phases=np.arange(0.0, 180.0, float(phase_step_deg)),
                                  sweep_shots=int(sweep_shots), check_shots=int(check_shots))
    d = res["data"]
    if not d.get("supported", False) or d.get("best_res_phase") is None:
        print("[res-phase cal] feedback path absent -- nothing to align; res_phase unchanged.")
        return None
    best = float(d["best_res_phase"])
    if not apply_config:
        print(f"[res-phase cal] measure-only: best res_phase = {best:.1f} deg "
              f"(initialize.py unchanged)")
        return best
    base_cfg["res_phase"] = best
    try:
        changed = config_updater.update_baseconfig({"res_phase": best})
        config_updater.prune_backups(keep=10)
        config_updater.append_history({
            "kind": "res_phase_cal", "qubit": str(path), "res_phase": best,
            "clean": bool(d.get("clean", False)),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        for k, (o, n) in changed.items():
            print(f"[res-phase cal] initialize.py updated: {k} {o} -> {n}")
    except Exception as exc:
        print(f"[res-phase cal] live cfg set to res_phase={best:.1f} deg, but the "
              f"initialize.py write failed ({exc}); paste it in manually.")
    return best
