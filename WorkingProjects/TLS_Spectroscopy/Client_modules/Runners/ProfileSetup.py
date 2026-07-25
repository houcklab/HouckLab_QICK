import os
import sys
import time

import numpy as np

_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "WorkingProjects")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
    _d = os.path.dirname(_d)

from qick import RAveragerProgram
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse)


class _SetupProbe(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        cfg["start"] = int(cfg["amp_start"])
        cfg["step"] = int(cfg["amp_step"])
        cfg["expts"] = int(cfg["amp_expts"])
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro in cfg["ro_chs"]:
            self.declare_readout(ch=ro, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        rf = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        add_qubit_gaussian(self)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb",
                                 freq=self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"]),
                                 phase=0, gain=cfg["start"], waveform="qubit")
        set_readout_pulse(self, rf)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.02))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, "+", self.cfg["step"])


def main():
    soc, soccfg = makeProxy()
    cfg = dict(BaseConfig)
    cfg["shots"] = 1000
    cfg["relax_delay"] = 1000.0
    cfg["amp_start"] = int(cfg.get("qubit_pi_gain", cfg.get("qubit_gain", 5000)))
    cfg["amp_step"] = 100
    cfg["amp_expts"] = 1

    def T(label, fn):
        t = time.time()
        r = fn()
        print(f"{label:38s}: {time.time() - t:7.3f} s")
        return r

    print("=== per-experiment setup profile (SS-cal-like: 2 generators + gaussian + readout) ===")
    prog = T("program build (host compile)", lambda: _SetupProbe(soccfg, cfg))
    T("config_all  #1 (uncached RFDC)", lambda: prog.config_all(soc, load_pulses=True))
    T("config_all  #2 (RFDC now cached)", lambda: prog.config_all(soc, load_pulses=True))
    print("  -- one config_all, broken into its four remote steps --")
    T("  load_pulses  (waveform upload)", lambda: prog.load_pulses(soc))
    T("  config_gens  (RFDC nyquist/mixer)", lambda: prog.config_gens(soc))
    T("  config_readouts", lambda: prog.config_readouts(soc))
    T("  load_program (tProc upload)", lambda: prog.load_program(soc))
    T("full acquire (config_all + 1000 shots)", lambda: prog.acquire(soc, load_pulses=True, progress=False))
    print("\nRead it as: setup = config_all #2; RFDC-first-time = (#1 - #2); "
          "acquisition loop = full acquire - config_all #2.")


if __name__ == "__main__":
    main()
