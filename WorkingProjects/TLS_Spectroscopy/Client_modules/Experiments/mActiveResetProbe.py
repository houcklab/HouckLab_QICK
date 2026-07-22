import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar

_ADDR_I, _ADDR_Q = 100, 101
_REG_I, _REG_Q = 30, 31


class ReadProbeProgram(AveragerProgram):
    """Prep |g> or |e> (cfg['probe_gain']), read out, then pull both accumulator halves
    into registers via the tProc `read` instruction and store them to data memory."""

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 100)))
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
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq, phase=0,
                                 gain=int(cfg["probe_gain"]), waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        page = self.ch_page(cfg["qubit_ch"])
        tproc_ch = int(cfg["tproc_ch"])
        if int(cfg["probe_gain"]) != 0:
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.2))
        self.read(tproc_ch, page, "lower", _REG_I)
        self.read(tproc_ch, page, "upper", _REG_Q)
        self.memwi(page, _REG_I, _ADDR_I)
        self.memwi(page, _REG_Q, _ADDR_Q)
        self.sync_all(self.us2cycles(cfg.get("relax_delay", 500.0)))


class ActiveResetProbe(ExperimentClass):
    """Reports the feedback capability and, if present, the raw |g>/|e> read values so the
    active-reset threshold can be calibrated.  Purely diagnostic -- changes no hardware
    calibration and never runs a feedback loop."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Active_Reset_Probe', cfg=None, meta_dict=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)

    def _read_dmem(self, addr):
        """Read one tProc data-memory word back through the Pyro proxy (best-effort), as a
        SIGNED int (the accumulator is signed; single_read returns it unsigned)."""
        for getter in (lambda: self.soc.tproc.single_read(addr),
                       lambda: self.soc.tproc.read_dmem(addr, 1)[0],
                       lambda: self.soc.read_dmem(addr, 1)[0]):
            try:
                return ar.to_signed32(getter())
            except Exception:
                continue
        raise RuntimeError("could not read tProc data memory via the soc proxy; the "
                           "single_read/read_dmem API differs on this board -- tell me the error.")

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        ro_ch = cfg["ro_chs"][0]
        tproc_ch = ar.feedback_channel(self.soccfg, ro_ch)
        print("=" * 68)
        print(f"[active-reset probe] readout {ro_ch}: tproc_ch = {tproc_ch}")
        if tproc_ch < 0:
            print("  -> this firmware does NOT route the readout into the tProc.")
            print("  -> ACTIVE RESET IS NOT POSSIBLE on this board; keep reset_mode='passive'.")
            print("=" * 68)
            self.data = {'tproc_ch': tproc_ch, 'supported': False,
                         'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            return {'config': cfg, 'data': self.data}

        print("  -> feedback path present; measuring raw read values for |g> and |e> ...")
        cfg["tproc_ch"] = tproc_ch
        cfg.setdefault("reps", int(cfg.get("shots", 200)))
        results = {}
        for label, gain in [("ground", 0), ("excited", int(cfg.get("qubit_pi_gain", cfg["qubit_gain"])))]:
            cfg["probe_gain"] = gain
            prog = ReadProbeProgram(self.soccfg, cfg)
            avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            raw_i = self._read_dmem(_ADDR_I)
            raw_q = self._read_dmem(_ADDR_Q)
            host_i = float(np.asarray(avgi).ravel()[0])
            results[label] = {"raw_lower": raw_i, "raw_upper": raw_q, "host_avgi": host_i}
            print(f"    {label:8s}: read lower(I?)={raw_i:>12d}  upper(Q?)={raw_q:>12d}  "
                  f"| host avgi={host_i:+.4g}")

        g, e = results["ground"], results["excited"]
        sep_lower = abs(e["raw_lower"] - g["raw_lower"])
        sep_upper = abs(e["raw_upper"] - g["raw_upper"])
        oper = "lower" if sep_lower >= sep_upper else "upper"
        gv, ev = (g[f"raw_{oper}"], e[f"raw_{oper}"])
        thr = int(round((gv + ev) / 2))
        ground_below = gv < ev
        print("-" * 68)
        print(f"  discriminating half: '{oper}' (|g>-|e> separation "
              f"{max(sep_lower, sep_upper)} vs {min(sep_lower, sep_upper)} on the other)")
        print(f"  -> active_reset_block(oper='{oper}', threshold_raw={thr}, "
              f"ground_below={ground_below})")
        if max(sep_lower, sep_upper) < 3 * max(1, min(sep_lower, sep_upper)):
            print("  WARNING: |g> and |e> barely separate in the raw read -- discrimination "
                  "is marginal.  Improve readout SNR / set the readout phase so the blobs "
                  "split along one quadrature before trusting active reset.")
        print("=" * 68)

        self.data = {
            'tproc_ch': tproc_ch, 'supported': True, 'results': results,
            'recommended': {'oper': oper, 'threshold_raw': thr, 'ground_below': ground_below},
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'probe': self.data})
