"""
Active-reset validation -- the one-number yes/no that the FULL feedback loop resets the
qubit (not just that the read works, which mActiveResetProbe already showed).

Runs three configs and reads the FINAL measurement each time:
  |g> ref   : no pi, no reset                       -> (Ig, Qg)
  |e> ref   : pi, no reset                          -> (Ie, Qe)
  |e>+reset : pi, then the active-reset feedback    -> (Ir, Qr)

Metric: the residual excited fraction = projection of (reset - |g>) onto the (|e> - |g>)
readout vector.  ~0 -> the qubit was driven to ground (reset works); ~1 -> still excited.
Uses the full IQ vector (no assumption about which quadrature discriminates), so it is
robust even though this board's separation is on Q, not I.

Self-contained buffer handling: the fixed-count reset adds exactly reset_max_iters readout
triggers, so readouts_per_experiment = (max_iters if reset else 0) + 1 and the final
measurement is the LAST readout.  This is purely diagnostic -- it changes no calibration.
Run it (board back up) BEFORE trusting reset_mode='feedback' in the T1/SS Rabis.
"""

import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar


class ResetValidationProgram(AveragerProgram):
    """prep (cfg['prep_excited']) -> optional active reset (cfg['do_reset']) -> final measure.
    acquire() returns the FINAL measurement's rep-averaged (I, Q)."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 2000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]), gen_ch=cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"]) * 4)
        # pulse register sits at the pi gain -> used for BOTH the |e> prep and the reset pi
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq, phase=0,
                                 gain=int(cfg["qubit_pi_gain"]), waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if cfg.get("prep_excited", True):
            self.pulse(ch=cfg["qubit_ch"])           # |e> prep
            self.sync_all(self.us2cycles(0.01))
        if cfg.get("do_reset", False):
            ar.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "upper"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg.get("relax_delay", 500.0)))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        reads = (int(self.cfg.get("reset_max_iters", 3)) if self.cfg.get("do_reset", False) else 0) + 1
        avg_di, avg_dq = super().acquire(soc, readouts_per_experiment=reads,
                                         load_pulses=load_pulses, progress=progress)
        # the final measurement is the LAST readout of the experiment
        return float(np.asarray(avg_di)[0][-1]), float(np.asarray(avg_dq)[0][-1])


class ActiveResetValidation(ExperimentClass):
    """Prep |e> -> active reset -> measure; report residual excited fraction vs |g>/|e> refs."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Active_Reset_Validation', cfg=None, meta_dict=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg.setdefault("shots", 2000)
        cfg["reps"] = int(cfg["shots"])
        cfg.setdefault("relax_delay", 500.0)
        ro_ch = cfg["ro_chs"][0]
        tproc_ch = ar.feedback_channel(self.soccfg, ro_ch)
        print("=" * 68)
        print(f"[reset validation] tproc_ch={tproc_ch}, threshold_raw={cfg.get('reset_threshold_raw')}, "
              f"oper={cfg.get('reset_oper')}, ground_below={cfg.get('reset_ground_below')}, "
              f"max_iters={cfg.get('reset_max_iters', 3)}")
        if tproc_ch < 0:
            print("  feedback path absent (tproc_ch<0) -> cannot validate active reset.")
            print("=" * 68)
            self.data = {'supported': False,
                         'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            return {'config': cfg, 'data': self.data}
        if cfg.get("reset_threshold_raw") is None:
            raise ValueError("reset_threshold_raw is required (run mActiveResetProbe first).")

        def _run(prep_excited, do_reset):
            cfg["prep_excited"] = prep_excited
            cfg["do_reset"] = do_reset
            return ResetValidationProgram(self.soccfg, cfg).acquire(self.soc, load_pulses=True)

        Ig, Qg = _run(False, False)     # |g> reference
        Ie, Qe = _run(True, False)      # |e> reference
        Ir, Qr = _run(True, True)       # |e> then active reset

        dx, dy = Ie - Ig, Qe - Qg
        denom = dx * dx + dy * dy
        residual = (((Ir - Ig) * dx + (Qr - Qg) * dy) / denom) if denom > 0 else float("nan")
        sep = float(np.hypot(dx, dy))
        print(f"  |g> ref     : I={Ig:+.5g}  Q={Qg:+.5g}")
        print(f"  |e> ref     : I={Ie:+.5g}  Q={Qe:+.5g}   (|e>-|g> separation {sep:.4g})")
        print(f"  |e> + reset : I={Ir:+.5g}  Q={Qr:+.5g}")
        print("-" * 68)
        print(f"  RESIDUAL EXCITED FRACTION after active reset = {residual:.3f}")
        print("     (0 = driven fully to |g>, 1 = still |e>)")
        if not np.isfinite(residual):
            print("  -> |g> and |e> readouts coincide; can't tell (check pi + readout).")
        elif residual < 0.15:
            print("  -> ACTIVE RESET WORKS: the feedback loop drives |e> to ground.")
        elif residual < 0.5:
            print("  -> PARTIAL reset: raise reset_max_iters, or check the threshold/oper.")
        else:
            print("  -> reset NOT working: check threshold_raw/oper/ground_below, the read, or "
                  "whether the pi flips the qubit at all.")
        print("=" * 68)

        self.data = {
            'supported': True, 'g_ref': (Ig, Qg), 'e_ref': (Ie, Qe), 'reset': (Ir, Qr),
            'residual_excited': residual, 'separation': sep,
            'reset_params': {k: cfg.get(k) for k in
                             ("reset_threshold_raw", "reset_oper", "reset_ground_below", "reset_max_iters")},
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'validation': self.data})
