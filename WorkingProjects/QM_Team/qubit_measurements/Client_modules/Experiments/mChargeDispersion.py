from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


def rotate_iq(avgi, avgq):
    sig = np.asarray(avgi) + 1j * np.asarray(avgq)
    theta = -np.angle(np.mean(sig))
    sig_rot = sig * np.exp(1j * theta)
    return sig_rot


class ChargeDispersionProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # Fixed wait time for charge-dispersion experiment:
        # assumes df is in MHz, so 1/df is in us
        t_wait_us = 1.0 / cfg["df"]
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(t_wait_us))

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])          # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"]) # Qubit

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        f_res = self.freq2reg(
            cfg["pulse_freq"],
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0]
        )
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=f_ge,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit"
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"])
        )

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        # First pi/2
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all()

        # Fixed wait = 1/df
        self.sync(self.q_rp, self.r_wait)

        # Second pi/2
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Readout
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"])
        )


class ChargeDispersion(ExperimentClass):
    """
    Fixed-wait Ramsey-style charge-dispersion experiment.
    Wait time is set by 1/df from cfg["df"].
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress
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
            'config': self.cfg,
            'data': {
                'avgi': avgi,
                'avgq': avgq,
                'amp': np.abs(np.asarray(avgi) + 1j * np.asarray(avgq))
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        avgi = np.array(data['data']['avgi']).squeeze()
        avgq = np.array(data['data']['avgq']).squeeze()
        amp = np.array(data['data']['amp']).squeeze()

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot([0], [avgi], 'o', label='I')
        plt.plot([0], [avgq], 'o', label='Q')
        plt.plot([0], [amp], 'o', label='|I+iQ|')
        plt.ylabel("a.u.")
        plt.xlabel("single point")
        plt.legend()
        plt.title(self.titlename + f"  (df = {self.cfg['df']})")

        plt.savefig(self.iname[:-4] + '_ChargeDispersion.png')

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
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])