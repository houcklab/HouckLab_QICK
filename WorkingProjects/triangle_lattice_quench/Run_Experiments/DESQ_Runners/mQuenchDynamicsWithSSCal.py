"""`QuenchDynamicsWithSSCal` — RampQuenchDynamics with an integrated
SingleShot readout calibration loop that fires at the start of every run.

What it does
------------
On `acquire()`:
  1. Loops over every qubit in `cfg["Qubit_Readout_List"]`, doing a SingleShot
     measurement (mimicking `Run_Experiments/Legacy_CALIBRATE_SINGLESHOT_READOUTS.py`'s
     `characterize_readout` function).
  2. Collects per-readout `angle`, `threshold`, and `confusion_matrix` (a 2x2
     matrix built from `ne_contrast` and `ng_contrast`).
  3. Injects those lists into `self.cfg` (under the keys `angle`, `threshold`,
     `confusion_matrix`) — same keys `AveragerProgramFF.acquire_populations`
     and `SweepExperimentND.acquire` look up.
  4. Delegates to `RampQuenchDynamics.acquire(progress=progress)` for the actual
     quench sweep.

So clicking Run on this tab does the same two-step that
`early_quench_experiments.py` does:
    exec(open("Legacy_CALIBRATE_SINGLESHOT_READOUTS.py").read())
    RampQuenchDynamics(...).acquire_display_save(...)
— but as a single Desq-loadable experiment, so you get fresh IQ-plane
parameters baked into the cfg every time you run a quench.

How to use in Desq
------------------
1. Set up your Desq config exactly as you do for `RampQuenchDynamics`:
   `BaseConfig`, `Qubit_Parameters`, `FF_Qubits`, `Qubit_Readout`,
   `Qubit_Pulse`, the per-channel `FF_gain<i>_<phase>` variables, then
   `config = update_config(**locals())` in the Config Extractor.
2. Either also extract `Qubit_Parameters` itself into Global Config (so this
   class can pull per-qubit pulse params during the SS loop), OR rely on the
   module-level fallback import below.
3. Load this file via Desq → Load Exp. Pick `QuenchDynamicsWithSSCal`. The
   per-tab Experiment Config takes the same keys `RampQuenchDynamics` does:
   `quench_gain`, `quench_freq`, `quench_phase`, `expt_samples_ramp`, etc.,
   plus the `samples_start / end / num_points` sweep range. Optionally
   `ss_shots` (defaults to 8000) and `ss_save` (defaults to False).
4. Run.

Notes
-----
- The SS-loop part is hardware-side, not extractor-side, so Desq's socProxy
  sandbox does not block it (we have a real `self.soc` / `self.soccfg`
  here, injected by Desq at construction time).
- Each SingleShot in the loop creates a fresh `SingleShotFFMUX` instance.
  Their data are NOT auto-saved by default; set `ss_save=True` if you want
  the per-qubit SS h5 files written alongside the quench output.
- This class is loadable in Desq's `Load Exp` because its MRO includes
  `ExperimentClass` (via RampQuenchDynamics -> RampQuenchBase ->
  SweepExperiment1D_lines -> SweepExperimentND -> ExperimentClass).
"""
import copy
import traceback
from datetime import datetime

import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mQuenchExperiment import (
    RampQuenchDynamics,
)
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import (
    SingleShotFFMUX,
)

# Module-level fallback so the user doesn't HAVE to put Qubit_Parameters in
# the cfg dict. Wrapped in try/except so a missing or differently-named
# qubit-params file does not block class import.
try:
    from WorkingProjects.triangle_lattice_quench.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import (
        Qubit_Parameters as _MODULE_QP,
    )
except Exception as _exc:
    _MODULE_QP = None
    print("[QuenchDynamicsWithSSCal] module-level Qubit_Parameters import "
          f"failed ({_exc!r}); will require cfg['Qubit_Parameters'] at "
          "acquire() time.")


class QuenchDynamicsWithSSCal(RampQuenchDynamics):
    """RampQuenchDynamics + per-readout SingleShot calibration step.

    Configurable cfg keys (in addition to whatever RampQuenchDynamics wants):

    - `Qubit_Parameters` (dict, optional if Qubit_Parameters_Master is importable):
        the per-qubit table used by the SS loop. If absent in cfg, falls back
        to the module-level import.
    - `ss_shots` (int, optional, default 8000):
        shots per SingleShot measurement during the calibration loop.
    - `ss_save` (bool, optional, default False):
        if True, each SingleShot in the loop calls its own save_data().
        Off by default to avoid cluttering the output directory.
    """

    # -----------------------------------------------------------------------
    # Internal: the SingleShot loop, lifted from
    # Run_Experiments/Legacy_CALIBRATE_SINGLESHOT_READOUTS.py:characterize_readout
    # so we don't have to `exec(open(...).read())` (which Desq can't handle).
    # -----------------------------------------------------------------------
    def _run_singleshot_calibration(self):
        Qubit_Readout = self.cfg["Qubit_Readout_List"]
        Qubit_Parameters = self.cfg.get("Qubit_Parameters", _MODULE_QP)
        if Qubit_Parameters is None:
            raise RuntimeError(
                "QuenchDynamicsWithSSCal: need either cfg['Qubit_Parameters'] "
                "or an importable Qubit_Parameters_Master. Neither found."
            )

        qubit_LO = self.cfg.get("qubit_LO", 0)
        n_shots = int(self.cfg.get("ss_shots", 8000))
        do_save = bool(self.cfg.get("ss_save", False))

        angles, thresholds, conf_mats, fidelities = [], [], [], []

        print("=" * 64)
        print(f"[QuenchDynamicsWithSSCal] SingleShot pre-calibration, "
              f"{n_shots} shots/qubit, Qubit_Readout = {list(Qubit_Readout)}")
        print("=" * 64)

        for ro_ind, Qubit in enumerate(Qubit_Readout):
            qpQ = Qubit_Parameters[str(Qubit)]
            # Build a per-iteration cfg copy. Mutating this is safe; the parent
            # quench cfg (self.cfg) and the IQArrays already built in
            # set_up_instance() are not affected.
            ss_cfg = copy.deepcopy(self.cfg)
            ss_cfg["FF_Qubits"] = copy.deepcopy(self.cfg["FF_Qubits"])
            ss_cfg["Shots"] = n_shots
            # Point the single drive at THIS qubit
            ss_cfg["qubit_freqs"] = [qpQ["Qubit"]["Frequency"] - qubit_LO]
            ss_cfg["qubit_gains"] = [qpQ["Qubit"]["Gain"] / 32766.0]
            ss_cfg["sigma"]       = [qpQ["Qubit"]["sigma"]]
            # Distribute this qubit's Pulse_FF across all 8 FF channels
            # (the same crosstalk-compensated array used during quench-prep
            # pulses). Matches characterize_readout exactly.
            for q_idx, gain in enumerate(qpQ["Pulse_FF"]):
                ss_cfg["FF_Qubits"][str(q_idx + 1)]["Gain_Pulse"] = gain

            ss_expt = SingleShotFFMUX(
                soc=self.soc, soccfg=self.soccfg,
                path=f"SingleShot_PreQuench_Q{Qubit}",
                outerFolder=self.outerFolder,
                cfg=ss_cfg,
            )
            data = ss_expt.acquire()

            angle     = float(data["data"]["angle"][ro_ind])
            threshold = float(data["data"]["threshold"][ro_ind])
            ng        = float(data["data"]["ng_contrast"][ro_ind])
            ne        = float(data["data"]["ne_contrast"][ro_ind])
            fid       = 1.0 - ng - ne
            conf_mat  = np.array([[1.0 - ng,         ne],
                                  [      ng,   1.0 - ne]])

            angles.append(angle)
            thresholds.append(threshold)
            conf_mats.append(conf_mat)
            fidelities.append(fid)

            print(f"  Q{Qubit} (ro_ind={ro_ind}):  F={fid:.3f},  "
                  f"angle={angle:+.3f} rad,  thr={threshold:+.4f},  "
                  f"ne={ne:.3f}, ng={ng:.3f}")

            if do_save:
                try:
                    ss_expt.save_data(data=data)
                except Exception as exc:
                    print(f"  [warn] save_data failed for Q{Qubit}: {exc}")

        print("=" * 64)
        print(f"[QuenchDynamicsWithSSCal] SS calibration done at "
              f"{datetime.now():%H:%M:%S}. "
              f"Mean F = {np.mean(fidelities):.3f}.")
        print("=" * 64)

        return angles, thresholds, conf_mats

    # -----------------------------------------------------------------------
    # Override: run SS first, inject angle/threshold/confusion_matrix into
    # self.cfg, then delegate to the parent quench sweep.
    # -----------------------------------------------------------------------
    def acquire(self, progress=False):
        try:
            angles, thresholds, conf_mats = self._run_singleshot_calibration()
        except Exception as exc:
            # If SS calibration blows up, fall back to whatever is already
            # in self.cfg (which may be defaults from build_*_config or
            # missing entirely). Loud failure preferred over silent garbage.
            traceback.print_exc()
            raise RuntimeError(
                "QuenchDynamicsWithSSCal: SingleShot pre-calibration failed; "
                "see traceback above. Quench sweep NOT started."
            ) from exc

        # Inject the freshly calibrated values. `acquire_populations`
        # (in AveragerProgramFF) and `SweepExperimentND.acquire` both read
        # these directly from cfg.
        self.cfg["angle"] = angles
        self.cfg["threshold"] = thresholds
        self.cfg["confusion_matrix"] = conf_mats

        print("[QuenchDynamicsWithSSCal] starting RampQuenchDynamics with "
              "fresh angle / threshold / confusion_matrix in cfg.")
        return super().acquire(progress=progress)
