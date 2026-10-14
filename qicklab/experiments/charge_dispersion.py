from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram, RAveragerProgram

from qicklab.core.experiment import ExperimentClass


class ChargeDispersionProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # df in MHz -> wait 1/df us (1/df vs 1/(2 df): docs/experiments/charge_dispersion.md)
        t_wait_us = 1.0 / cfg["df"]
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(t_wait_us))

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
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=f_ge,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit",
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all()

        self.sync(self.q_rp, self.r_wait)

        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )


class ChargeDispersion(ExperimentClass):
    """Single-point fixed-wait Ramsey (pi/2 - 1/df - pi/2) for charge-parity readout.

    docs/experiments/charge_dispersion.md."""

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
        prog = ChargeDispersionProgram(self.soccfg, self.cfg)

        avgi, avgq = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=True,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=False,
        )

        data = {
            "config": self.cfg,
            "data": {
                "avgi": avgi,
                "avgq": avgq,
                "amp": np.abs(np.asarray(avgi) + 1j * np.asarray(avgq)),
            },
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        avgi = np.array(data["data"]["avgi"]).squeeze()
        avgq = np.array(data["data"]["avgq"]).squeeze()
        amp = np.array(data["data"]["amp"]).squeeze()

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot([0], [avgi], "o", label="I")
        plt.plot([0], [avgq], "o", label="Q")
        plt.plot([0], [amp], "o", label="|I+iQ|")
        plt.ylabel("a.u.")
        plt.xlabel("single point")
        plt.legend()
        plt.title(self.titlename + f"  (df = {self.cfg['df']})")

        plt.savefig(self.iname[:-4] + "_ChargeDispersion.png")

        print(f"df = {self.cfg['df']}")
        print(f"wait time = {1.0 / self.cfg['df']:.6f} us")
        print(f"I = {avgi}")
        print(f"Q = {avgq}")
        print(f"|I+iQ| = {amp}")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


class ChargeDispersionQuasiCWProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
            ro_ch=cfg["ro_chs"][0],
        )
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        if cfg["Gauss"]:
            # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.pulse_sigma,
                length=self.pulse_qubit_lenth,
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_start,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit",
            )
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="const",
                freq=self.f_start,
                phase=0,
                gain=cfg["qubit_gain"],
                length=self.us2cycles(cfg["qubit_length"]),
            )
            self.qubit_length_us = cfg["qubit_length"]
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

    def body(self):
        self.sync_all()
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))
        self.sync_all(self.us2cycles(0.5))
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=[0, 1],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(10),
        )

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, "+", self.f_step)


class ChargeDispersionQuasiCW(ExperimentClass):
    """Quasi-CW two-tone: the pulse-measure loop runs in hardware (cfg["reps"]) and one acquire
    returns the repetition-resolved raw IQ. The program can sweep r_freq; the runner passes
    step=0, expts=1 (fixed frequency). docs/experiments/charge_dispersion.md."""

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
        self.prog = ChargeDispersionQuasiCWProg(self.soccfg, self.cfg)

    def acquire(self, progress=False, debug=False, load_pulses=True, print_time=False):
        if print_time:
            start_real = datetime.now()

        prog = self.prog

        # The averages are incidental; acquire also fills di_buf/dq_buf with one entry per shot.
        x_pts, avgi_avg, avgq_avg = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=load_pulses,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=progress,
        )

        avgi_avg = np.asarray(avgi_avg)
        avgq_avg = np.asarray(avgq_avg)

        winding = np.exp(
            1j
            * (
                2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
                + self.cfg["cavity_winding_offset"]
            )
        )
        signal_avg = (avgi_avg + 1j * avgq_avg) * winding

        raw_i = np.asarray(prog.di_buf[0])  # ADC 0
        raw_q = np.asarray(prog.dq_buf[0])

        reps = int(self.cfg["reps"])
        expts = int(self.cfg["expts"])

        # qick 0.2.334 acc_buf loop_dims are [expts, reps] (expts outer) -> (reps, expts).
        raw_i = raw_i.reshape(expts, reps).T
        raw_q = raw_q.reshape(expts, reps).T

        raw_signal = (raw_i + 1j * raw_q) * winding

        if print_time:
            elapsed = datetime.now() - start_real
            print("Elapsed time for one hardware acquire:", elapsed)

        data = {
            "x_pts": np.asarray(x_pts),
            "avgi": signal_avg.real,
            "avgq": signal_avg.imag,
            "raw_i": raw_signal.real,
            "raw_q": raw_signal.imag,
            "raw_amp": np.abs(raw_signal) ** 2,
            "amps_per_rep": np.mean(np.abs(raw_signal) ** 2, axis=1),  # one scalar per repetition
        }

        self.data = {"data": data}
        return self.data
