import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.fitting import fit_exp_decay
from qicklab.analysis.iq import min_q_range_phase
from qicklab.core.experiment import ExperimentClass


class T2EProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg
        # n + 1 equal waits: each pi inverts the phase, so a static detuning cancels only
        # for odd n (docs/experiments/t2_echo.md#refocusing-condition)
        n = cfg["num_pi_pulses"]
        if n < 1 or n % 2 == 0:
            raise ValueError(
                f"num_pi_pulses = {n}: must be odd and >= 1. The echo uses n + 1 equal waits "
                "and each pi pulse inverts the accumulated phase, so a static detuning is "
                "refocused only for odd n (an even n leaves one wait of Ramsey phase; n = 0 "
                "is a Ramsey). See docs/experiments/t2_echo.md."
            )

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.f_ge = f_ge

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.trigger(
            pins=[0],
            t=self.us2cycles(0.01 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )
        if self.cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.setup_and_pulse(
                self.cfg["qubit_ch"],
                style="flat_top",
                freq=self.f_ge,
                phase=0,
                gain=self.cfg["pi2_gain"],
                waveform="qubit",
                length=flattop_length,
                t=self.us2cycles(0.01),
            )
        else:
            self.setup_and_pulse(
                ch=self.cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge,
                phase=0,
                gain=self.cfg["pi2_gain"],
                waveform="qubit",
                t=self.us2cycles(0.01),
            )

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)
        # pi/2 at 0 deg, pi at 90 deg (CPMG); edge-to-edge waits: docs/experiments/t2_echo.md
        for i in range(self.cfg["num_pi_pulses"]):
            self.trigger(
                pins=[0],
                t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                width=self.trig_length,
            )
            if self.cfg["flattop_length"] != None:
                self.setup_and_pulse(
                    self.cfg["qubit_ch"],
                    style="flat_top",
                    freq=self.f_ge,
                    phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]),
                    gain=self.cfg["pi_gain"],
                    waveform="qubit",
                    length=flattop_length,
                )
            else:
                self.setup_and_pulse(
                    ch=self.cfg["qubit_ch"],
                    style="arb",
                    freq=self.f_ge,
                    phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]),
                    gain=self.cfg["pi_gain"],
                    waveform="qubit",
                )
            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        self.trigger(
            pins=[0],
            t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )
        if self.cfg["flattop_length"] != None:
            self.setup_and_pulse(
                self.cfg["qubit_ch"],
                style="flat_top",
                freq=self.f_ge,
                phase=0,
                gain=self.cfg["pi2_gain"],
                waveform="qubit",
                length=flattop_length,
            )
        else:
            self.setup_and_pulse(
                ch=self.cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge,
                phase=0,
                gain=self.cfg["pi2_gain"],
                waveform="qubit",
            )
        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(
            self.q_rp,
            self.r_wait,
            self.r_wait,
            "+",
            self.us2cycles(self.cfg["step"] / (self.cfg["num_pi_pulses"] + 1)),
        )


class T2EMUX(ExperimentClass):
    """Hahn / CPMG echo with num_pi_pulses pi pulses, register-swept total free evolution;
    exponential fit gives T2E. Step quantisation: docs/experiments/t2_echo.md."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False):
        prog = T2EProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=True,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=False,
        )
        print(
            x_pts,
        )
        data = {
            "config": self.cfg,
            "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq, "qfreq": self.cfg["f_ge"]},
        }
        if "rotation_angle" in self.cfg:
            if self.cfg["min_max"] != None:
                data["rotation_angle"] = self.cfg["rotation_angle"]
        if "min_max" in self.cfg:
            if self.cfg["min_max"] != None:
                data["min_max"] = self.cfg["min_max"]
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data["data"]["x_pts"]
        avgi = data["data"]["avgi"][0][0]
        avgq = data["data"]["avgq"][0][0]

        if "rotation_angle" not in self.cfg:
            rotation_angle = min_q_range_phase(avgi, avgq, 200)
        elif self.cfg["rotation_angle"] == None:
            rotation_angle = min_q_range_phase(avgi, avgq, 200)
        else:
            rotation_angle = self.cfg["rotation_angle"]
        rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)

        avgi = rotated_IQ.real
        avgq = rotated_IQ.imag

        if "min_max" in data:
            ground = data["min_max"][0]
            excited = data["min_max"][-1]
            avgi = (avgi - ground) / (excited - ground)

        T1_fit, T1_est, T1_err = fit_exp_decay(x_pts, avgi)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, "o-", label="i", color="orange")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.plot(x_pts, T1_fit, "-", label="fit", color="black")
        plt.title(
            "Num Pulses: "
            + str(self.cfg["num_pi_pulses"])
            + " ; "
            + self.titlename
            + "  ; T2E = "
            + str(round(T1_est, 1))
            + r" $\pm$ "
            + str(round(T1_err, 1))
            + "us"
        )

        plt.savefig(self.iname[:-4] + "I_Data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum + 1)
        plt.plot(x_pts, avgq, "o-", label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title("Num Pulses: " + str(self.cfg["num_pi_pulses"]) + " ; " + self.titlename)

        plt.savefig(self.iname[:-4] + "Q_Data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        new_name = self.fname[:-3] + "_n" + str(self.cfg["num_pi_pulses"]) + ".h5"
        self.fname = new_name
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
