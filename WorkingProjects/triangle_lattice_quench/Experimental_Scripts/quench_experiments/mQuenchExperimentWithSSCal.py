"""
mQuenchExperimentWithSSCal.py
=============================

Near-verbatim duplicate of ``mQuenchExperiment.py`` (sibling file in this
directory) with an integrated SingleShot **pre-acquire** calibration loop
built into the base class ``RampQuenchBase_SS``.

What this file is
-----------------
A drop-in alternative to ``mQuenchExperiment.py`` for the 8-qubit triangular-
ladder simulator. Every class behaves identically to its non-_SS counterpart
except that a fresh SingleShot readout calibration is performed for each
qubit in ``cfg['Qubit_Readout_List']`` *before* the quench sweep starts.
The resulting ``angle``, ``threshold``, and ``confusion_matrix`` lists are
written into ``self.cfg`` so that the downstream ``population_corrected``
analysis uses freshly calibrated discriminators.

Rename convention
-----------------
Every top-level class from ``mQuenchExperiment.py`` gets a ``_SS`` suffix.
References inside the file (e.g. ``self.Program = QuenchProgram``) have
been updated to point at ``QuenchProgram_SS``. The mapping is:

    QuenchProgram             -> QuenchProgram_SS
    RampQuenchBase            -> RampQuenchBase_SS
    RampQuenchDynamics        -> RampQuenchDynamics_SS
    RampQuenchFreq            -> RampQuenchFreq_SS
    RampQuenchSweepRampTime   -> RampQuenchSweepRampTime_SS
    RampQuenchSweepQuenchTime -> RampQuenchSweepQuenchTime_SS
    RampQuenchRabi            -> RampQuenchRabi_SS

Source of the SS calibration loop
---------------------------------
The pre-acquire SingleShot loop is lifted from
``WorkingProjects/triangle_lattice_quench/Run_Experiments/Legacy_CALIBRATE_SINGLESHOT_READOUTS.py::
characterize_readout``. It loops over each qubit in ``Qubit_Readout``,
points the drive at that qubit using
``Qubit_Parameters[str(Q)]['Qubit']`` and ``Qubit_Parameters[str(Q)]['Pulse_FF']``,
runs ``SingleShotFFMUX(...).acquire()``, and extracts the per-readout
``angle``, ``threshold``, and a 2x2 confusion matrix built from
``ng_contrast`` / ``ne_contrast``.

Required cfg keys for the SS step
---------------------------------
- ``Qubit_Readout_List`` : list of qubit labels (ints / strings keying
  ``Qubit_Parameters``) to calibrate before the quench sweep.
- Either ``cfg['Qubit_Parameters']`` is provided, or the module-level
  ``Qubit_Parameters_Master.py`` is importable on ``PYTHONPATH``. If
  neither is available the SS step raises a clear ``RuntimeError``.
- All cfg keys that ``SingleShotFFMUX`` itself needs (``FF_Qubits``,
  ``qubit_ch``, ``res_ch``, ``ro_chs``, ``readout_lengths``, ``res_freqs``,
  ``res_gains``, ``res_length``, ``mixer_freq``, ``qubit_mixer_freq``,
  ``qubit_nqz``, ``res_nqz``, ``adc_trig_delays``, ``reps``,
  ``relax_delay``, ``number_of_pulses``, ``Pulse``, ``Shots``, ...) - these
  are already required by the standard quench experiment and reused here.

Optional cfg knobs (SS-step-specific)
-------------------------------------
- ``ss_shots`` : int, default ``8000``. Number of single-shot acquisitions
  per qubit during the pre-acquire calibration.
- ``ss_save`` : bool, default ``False``. If True, the per-qubit
  SingleShot result is written to disk via ``SingleShotFFMUX.save_data``.
  Errors during the save are caught and logged but never propagated.
- ``qubit_LO`` : float, default ``0``. Subtracted from the qubit-parameter
  frequency to produce the drive setpoint passed to ``SingleShotFFMUX``.

Use in Desq
-----------
In the Desq GUI:

1. Click ``Load Exp`` and pick this file
   (``mQuenchExperimentWithSSCal.py``).
2. From the class dropdown select one of:
     - ``RampQuenchDynamics_SS``
     - ``RampQuenchFreq_SS``
     - ``RampQuenchSweepRampTime_SS``
     - ``RampQuenchSweepQuenchTime_SS``
     - ``RampQuenchRabi_SS``
3. Fill in the Experiment Config exactly as you would for the
   corresponding non-_SS class in ``mQuenchExperiment.py``, plus set
   ``Qubit_Readout_List`` (and optionally ``ss_shots`` / ``ss_save``).
4. Hit ``Run``. The SingleShot calibration loop runs first; on success
   the quench sweep starts immediately and uses the freshly measured
   ``angle`` / ``threshold`` / ``confusion_matrix``. If the SS step
   fails the quench sweep is **not** started and a ``RuntimeError`` is
   raised with the original traceback printed.
"""

import math

import numpy as np
from matplotlib import pyplot as plt

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF

# --- Additional imports for the SingleShot pre-acquire calibration loop ---
import copy
import traceback
from datetime import datetime
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

try:
    from WorkingProjects.triangle_lattice_quench.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import Qubit_Parameters as _MODULE_QP
except Exception as _exc:
    _MODULE_QP = None
    print(f"[mQuenchExperimentWithSSCal] Note: module-level Qubit_Parameters import failed ({_exc!r}); "
          "will require cfg['Qubit_Parameters'] at acquire() time.")


class QuenchProgram_SS(FFAveragerProgramV2):
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        # print(cfg["res_freqs"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])

        FF.FFDefinitions(self)

        # qubit init pulses (one Gaussian envelope per pulse)
        for i in range(len(self.cfg["qubit_gains"])):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=90,
                           gain=self.cfg["qubit_gains"][i])

        # qubit quench pulse (uses first pulse's sigma envelope)
        quench_freq = cfg["quench_freq"]
        quench_gain = cfg["quench_gain"]
        quench_phase = cfg["quench_phase"]

        self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_quench', style="arb", envelope=f"qubit0",
                       freq=quench_freq,
                       phase=quench_phase,
                       gain=quench_gain)

        self.qubit_total_length_us = 4 * sum(cfg["sigma"])


    def _body(self, cfg):

        ### Init Pulse
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        if self.cfg['init_pulse']:
            for i in range(len(self.cfg["qubit_gains"])):
                time_ = FF_Delay_time if i == 0 else 'auto'
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_{i}', t=time_)

        self.delay_auto()

        ### Ramp
        if self.cfg["expt_samples_ramp"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_ramp"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_ramp"], waveform_label='FFRamp')
            self.delay_auto()

        ### Quench
        if self.cfg["expt_samples_quench"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_quench"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_quench"], waveform_label='FFQuench')
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_quench', t='auto')
            self.delay_auto()

        ### Dynamics
        # print(f'dynamics')
        # print(self.cfg["IQArray_dynamics"])
        if self.cfg["expt_samples_dynamics"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_dynamics"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_dynamics"], waveform_label='FFDynamics')
            self.delay_auto()

        ### Readout

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        self.delay_auto()


class RampQuenchBase_SS(SweepExperiment1D_lines):
    def init_sweep_vars(self):

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = None
        self.x_points = None
        self.xlabel = None

        self.cfg['init_pulse'] = self.cfg.get('init_pulse', True)


    def set_up_instance(self):

        ### round samples to nearest integer
        self.cfg['expt_samples_ramp'] = round(self.cfg['expt_samples_ramp'])
        self.cfg['expt_samples_quench'] = round(self.cfg['expt_samples_quench'])
        self.cfg['expt_samples_dynamics'] = round(self.cfg['expt_samples_dynamics'])


        ### option to offset step pulses
        t_offset = self.cfg.get('t_offset',0)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif isinstance(t_offset, (list, np.ndarray, tuple)):
            np.array(t_offset, dtype=int)
        else:
            raise TypeError('t_offset must be an int or array like of ints')


        t_offset -= np.min(t_offset)
        # print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())
        ff_ro_pad = math.ceil(np.max(t_offset) / 16) * 16

        ### Ramp
        IQArray_ramp = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'Gain_RampInit',
                                                                           'Gain_Expt', self.cfg['expt_samples_ramp'])

        self.cfg["IQArray_ramp"] = IQArray_ramp

        ### Quench
        # TODO for now reuse the Gain_BS label, might want to change in future
        gain_ramp = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_quench = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_dynamics = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Dynamics')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')

        # print(f'gain_ramp: {gain_ramp}')
        # print(f'gain_quench: {gain_quench}')
        # print(f'gain_readout: {gain_readout}')

        IQArray_quench = []
        for j in range(len(gain_ramp)):
            ramp = gain_ramp[j]
            quench = gain_quench[j]

            arr = np.concatenate([np.full(t_offset[j], ramp),
                                  np.full(self.cfg['expt_samples_quench'], quench)])
            arr = Compensate(arr - ramp, ramp, j + 1)
            IQArray_quench.append(arr)

        ### Dynamics
        IQArray_dynamics = []
        for j in range(len(gain_quench)):
            ramp = gain_ramp[j]
            quench = gain_quench[j]


            arr = np.concatenate([np.full(t_offset[j], quench),
                                  np.full(self.cfg['expt_samples_dynamics'], ramp)])
            arr = Compensate(arr - quench, quench, j + 1)
            IQArray_dynamics.append(arr)

        ### Readout
        IQArray_readout = []
        for j in range(len(gain_ramp)):
            ramp = gain_ramp[j]
            readout = gain_readout[j]

            arr = np.concatenate([np.full(t_offset[j], ramp),
                                  np.full(ff_ro_pad - t_offset[j], readout)])
            arr = Compensate(arr - ramp, ramp, j + 1)
            IQArray_readout.append(arr)

        self.cfg["IQArray_quench"] = IQArray_quench
        self.cfg["IQArray_dynamics"] = IQArray_dynamics
        self.cfg["IQArray_readout"] = IQArray_readout

        # print(f'expt_samples_ramp: {self.cfg["expt_samples_ramp"]}')
        # print(f'expt_samples_quench: {self.cfg["expt_samples_quench"]}')
        # print(f'expt_samples_dynamics: {self.cfg["expt_samples_dynamics"]}')

        # total_IQArray = [np.concatenate([IQArray_ramp[i], IQArray_quench[i], IQArray_dynamics[i], IQArray_readout[i]]) for i in range(len(IQArray_quench))]
        #
        # if False and self.cfg['expt_samples_dynamics'] > 150:
        #     plt.figure()
        #     for i in range(len(total_IQArray)):
        #         print(f'Q{i+1}: {total_IQArray[i]}')
        #         plt.plot(total_IQArray[i], label=f'Q{i+1}')
        #     plt.axvline(self.cfg['expt_samples_ramp'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'] + self.cfg['expt_samples_dynamics'], color='purple', linestyle='--')
        #     plt.legend()
        #     plt.show()

    # ------------------------------------------------------------------
    # SingleShot pre-acquire calibration
    # ------------------------------------------------------------------
    def _run_singleshot_calibration(self):
        """Run a SingleShotFFMUX acquisition per qubit listed in
        ``cfg['Qubit_Readout_List']`` and return ``(angles, thresholds,
        conf_mats)`` indexed by readout position.

        Mirrors ``characterize_readout`` in
        ``Run_Experiments/Legacy_CALIBRATE_SINGLESHOT_READOUTS.py``: for each
        qubit the drive is repointed at that qubit's parameters
        (frequency, gain, sigma, Pulse_FF distribution) and a fresh
        SingleShot acquisition is run, then ``angle``, ``threshold``,
        ``ng_contrast``, and ``ne_contrast`` are pulled at this qubit's
        readout index.
        """
        Qubit_Readout = self.cfg["Qubit_Readout_List"]
        Qubit_Parameters = self.cfg.get("Qubit_Parameters", _MODULE_QP)
        if Qubit_Parameters is None:
            raise RuntimeError(
                "RampQuenchBase_SS._run_singleshot_calibration: no Qubit_Parameters "
                "available. Either set cfg['Qubit_Parameters'] or make sure "
                "WorkingProjects.triangle_lattice_quench.Run_Experiments."
                "qubit_parameter_files.Qubit_Parameters_Master is importable on "
                "PYTHONPATH."
            )

        qubit_LO = self.cfg.get("qubit_LO", 0)
        n_shots = int(self.cfg.get("ss_shots", 8000))
        do_save = bool(self.cfg.get("ss_save", False))

        banner = "=" * 64
        print(banner)
        print(f"[mQuenchExperimentWithSSCal] SingleShot pre-acquire calibration "
              f"starting at {datetime.now().isoformat(timespec='seconds')}")
        print(f"  Qubits to calibrate: {list(Qubit_Readout)}")
        print(f"  ss_shots={n_shots}, ss_save={do_save}, qubit_LO={qubit_LO}")
        print(banner)

        angles = []
        thresholds = []
        conf_mats = []

        for ro_ind, Qubit in enumerate(Qubit_Readout):
            qpQ = Qubit_Parameters[str(Qubit)]

            ss_cfg = copy.deepcopy(self.cfg)
            ss_cfg["FF_Qubits"] = copy.deepcopy(self.cfg["FF_Qubits"])
            ss_cfg["Shots"] = n_shots

            ss_cfg["qubit_freqs"] = [qpQ["Qubit"]["Frequency"] - qubit_LO]
            ss_cfg["qubit_gains"] = [qpQ["Qubit"]["Gain"] / 32766.0]
            ss_cfg["sigma"] = [qpQ["Qubit"]["sigma"]]

            for q_idx, gain in enumerate(qpQ["Pulse_FF"]):
                ss_cfg["FF_Qubits"][str(q_idx + 1)]["Gain_Pulse"] = gain

            ss_expt = SingleShotFFMUX(
                soc=self.soc,
                soccfg=self.soccfg,
                path=f"SingleShot_PreQuench_Q{Qubit}",
                outerFolder=self.outerFolder,
                cfg=ss_cfg,
            )
            data = ss_expt.acquire()

            angle = float(data["data"]["angle"][ro_ind])
            threshold = float(data["data"]["threshold"][ro_ind])
            ng = float(data["data"]["ng_contrast"][ro_ind])
            ne = float(data["data"]["ne_contrast"][ro_ind])

            conf_mat = np.array([[1 - ng, ne],
                                 [ng, 1 - ne]])

            angles.append(angle)
            thresholds.append(threshold)
            conf_mats.append(conf_mat)

            print(f"  Q{Qubit} (ro_ind={ro_ind}):  F={1-ng-ne:.3f},  "
                  f"angle={angle:+.3f} rad,  thr={threshold:+.4f},  "
                  f"ne={ne:.3f}, ng={ng:.3f}")

            if do_save:
                try:
                    ss_expt.save_data(data=data)
                except Exception as save_exc:
                    print(f"  [warn] save_data failed for Q{Qubit}: {save_exc!r}")

        print(banner)
        print(f"[mQuenchExperimentWithSSCal] SingleShot pre-acquire calibration "
              f"finished at {datetime.now().isoformat(timespec='seconds')}")
        print(banner)

        return angles, thresholds, conf_mats

    def acquire(self, progress=False):
        """Run the SingleShot pre-acquire calibration, then defer to the
        standard sweep ``acquire``. If the SS step fails the quench sweep
        is **not** started: the traceback is printed and a
        :class:`RuntimeError` is raised.
        """
        try:
            angles, thresholds, conf_mats = self._run_singleshot_calibration()
        except Exception:
            traceback.print_exc()
            raise RuntimeError(
                "SingleShot pre-calibration failed; quench sweep NOT started."
            )

        self.cfg["angle"] = angles
        self.cfg["threshold"] = thresholds
        self.cfg["confusion_matrix"] = conf_mats

        return super().acquire(progress=progress)


class RampQuenchDynamics_SS(RampQuenchBase_SS):
    def init_sweep_vars(self):

        super().init_sweep_vars()

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_dynamics'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting



class RampQuenchFreq_SS(RampQuenchBase_SS):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = 'quench_freq'
        self.x_points = np.linspace(self.cfg['freq_start'], self.cfg['freq_end'],
                                    self.cfg['freq_num_points'])
        self.xlabel = 'Frequency (MHz)'  # for plotting


class RampQuenchSweepRampTime_SS(RampQuenchBase_SS):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_ramp'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting

class RampQuenchSweepQuenchTime_SS(RampQuenchBase_SS):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_quench'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting



class RampQuenchRabi_SS(RampQuenchBase_SS):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram_SS
        self.z_value = 'population_corrected'

        self.x_key = 'quench_gain'
        self.x_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'],
                                    self.cfg['gain_num_points'])

        self.xlabel = 'gain (a.u.)'  # for plotting

