"""play a long duration pulse for spectrum analysis"""

from qick.asm_v2 import AveragerProgramV2

from WorkingProjects.gates_team.CoreLib.socProxy import makeProxy


class PulseTest(AveragerProgramV2):
    """ """

    def _initialize(self, cfg):
        self.declare_gen(
            ch=cfg["gen_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
        )

        self.add_pulse(
            ch=cfg["gen_ch"],
            name="mypulse",
            style="const",
            freq=cfg["freq"],
            length=cfg["pulse_length"],
            phase=cfg["phase"],
            gain=cfg["gain"],
            mode="periodic",
        )

    def _body(self, cfg):
        self.pulse(cfg["gen_ch"], name="mypulse")


if __name__ == "__main__":
    config = {
        "gen_ch": 8,
        "nqz": 1,
        "mixer_freq": 800,
        "reps": 1,
        "pulse_length": 60,
        "freq": 1500,  # difference between freq and mixer_freq must be within mixer range/2
        "period": 2,
        "phrst": 1,
        "phase": 0,
        "gain": 0,  # from -1 to +1
    }

    soc, soccfg = makeProxy()
    prog = PulseTest(soccfg, cfg=config, final_delay=0, reps=config["reps"])
    prog.config_all(soc)

    # Set Nyquist Zone.
    dacid = soccfg["gens"][config["gen_ch"]]["dac"]
    soc.rf.set_nyquist(dacid, nqz=config["nqz"])

    # Set Filter.
    soc.rfb_set_gen_filter(gen_ch=config["gen_ch"], fc=3, ftype="lowpass")

    # Set attenuator on DAC.
    soc.rfb_set_gen_rf(gen_ch=config["gen_ch"], att1=0, att2=10)

    soc.tproc.start()
