import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.fitting import fit_exp_decay
from qicklab.analysis.iq import min_q_range_phase
from qicklab.core.experiment import ExperimentClass


class T1Program(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=f_ge,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=cfg["pi_gain"],
                waveform="qubit",
                length=flattop_length,
            )
            self.pulse_qubit_lenth += flattop_length
        else:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=f_ge,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["pi_gain"],
                waveform="qubit",
            )

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all()
        self.trigger(
            pins=[0],
            t=self.us2cycles(0.01 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.01))
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, "+", self.us2cycles(self.cfg["step"]))


class T1FF(ExperimentClass):
    """T1: pi pulse, register-swept wait (from the pulse end), readout; min-Q-range IQ
    rotation and a single-exponential fit (docs/experiments/t1.md)."""

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

    def acquire(self, progress=False, debug=False):
        prog = T1Program(self.soccfg, self.cfg)

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

        avgi = np.asarray(avgi, dtype=np.float64)
        avgq = np.asarray(avgq, dtype=np.float64)

        signal = (avgi + 1j * avgq) * np.exp(
            1j
            * (
                2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
                + self.cfg["cavity_winding_offset"]
            )
        )
        avgi = signal.real
        avgq = signal.imag

        data = {
            "config": self.cfg,
            "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq, "qfreq": self.cfg["f_ge"]},
        }
        if "rotation_angle" in self.cfg:
            data["rotation_angle"] = self.cfg["rotation_angle"]
        if "min_max" in self.cfg:
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
        plt.plot(x_pts, avgi, "o", label="i", color="orange")
        plt.plot(x_pts, T1_fit, "-", label="fit", color="black")
        plt.ylabel("a.u.")
        if "min_max" in data:
            plt.ylabel("Population")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(
            "Qubit: "
            + str(self.cfg["Qubit_number"])
            + " ; "
            + self.titlename
            + "  ; T1 = "
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
        plt.plot(x_pts, avgq, "o", label="q")

        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + "Q_Data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        new_name = self.fname[:-3] + "_Q" + str(self.cfg["Qubit_number"]) + ".h5"
        self.fname = new_name
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
