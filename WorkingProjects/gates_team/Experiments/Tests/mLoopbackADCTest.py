"""loopback test with a readout tone"""

from qick.asm_v2 import AveragerProgramV2

from WorkingProjects.gates_team.CoreLib.socProxy import makeProxy
import matplotlib.pyplot as plt


class LoopbackProgram(AveragerProgramV2):
    def _initialize(self, cfg):
        ro_ch = cfg["ro_ch"]
        gen_ch = cfg["gen_ch"]

        self.declare_gen(
            ch=gen_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=ro_ch
        )

        self.declare_readout(ch=ro_ch, length=cfg["ro_len"])

        self.add_readoutconfig(
            ch=ro_ch, name="myro", freq=cfg["freq"], gen_ch=gen_ch, outsel="product"
        )

        self.add_cosine(
            ch=gen_ch, name="ramp", length=cfg["ramp_len"], even_length=True
        )

        self.add_pulse(
            ch=gen_ch,
            name="mypulse",
            ro_ch=ro_ch,
            style="const",
            # style="flat_top",
            # envelope="ramp",
            freq=cfg["freq"],
            length=cfg["flat_len"],
            phase=cfg["phase"],
            gain=cfg["gain"],
        )

        self.send_readoutconfig(ch=cfg["ro_ch"], name="myro", t=0)

    def _body(self, cfg):
        self.delay_auto()
        self.pulse(ch=cfg["gen_ch"], name="mypulse", t=0.0)
        self.trigger(ros=[cfg["ro_ch"]], pins=[0], t=cfg["trig_time"], mr=True)


if __name__ == "__main__":
    config = {
        "gen_ch": 8,
        "ro_ch": 10,
        "mixer_freq": 3500,
        "freq": 4000,
        "nqz": 2,
        "trig_time": 0.0,
        "ro_len": 3.0,
        "flat_len": 1.0,
        "ramp_len": 1.0,
        "phase": 0,
        "gain": 0,
    }

    soc, soccfg = makeProxy()
    prog = LoopbackProgram(soccfg, reps=1, final_delay=0.5, cfg=config)
    freq = config["freq"]

    soc.rfb_set_gen_filter(config["gen_ch"], fc=freq / 1000, ftype="bandpass", bw=1.0)
    soc.rfb_set_ro_filter(config["ro_ch"], fc=freq / 1000, ftype="bandpass", bw=1.0)

    # Set attenuator on DAC.
    soc.rfb_set_gen_rf(config["gen_ch"], 10, 20)

    # Set attenuator on ADC.
    soc.rfb_set_ro_rf(config["ro_ch"], 25)

    # observe pulse envelope
    iq_list = prog.acquire_decimated(soc, rounds=1)
    t = prog.get_time_axis(ro_index=0)
    iq = iq_list[0]
    plt.plot(t, iq[:, 0], label="I value")
    plt.plot(t, iq[:, 1], label="Q value")
    plt.legend()
    plt.ylabel("amplitude [ADU]")
    plt.xlabel("time [us]")
    plt.show()

    # observe time-domain waveform
    # soc.arm_mr(ch=config["ro_ch"])
    # iq_list = prog.acquire_decimated(soc, rounds=1)
    # iq_mr = soc.get_mr()[:800]
    # t = prog.get_time_axis_mr(config["ro_ch"], iq_mr)
    # plt.plot(t, iq_mr[:, 0], label="I")
    # plt.plot(t, iq_mr[:, 1], label="Q")
    # plt.xlabel("us")
    # plt.legend()
    # plt.show()
