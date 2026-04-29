from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


class ModifiedRamseyProgram(AveragerProgram):
    """
    Fixed-tau Ramsey for charge-parity switching detection.

    No-pi sequence:
        pi/2 -> wait tau -> pi/2(180 deg) -> readout

    Echo/pi sequence:
        pi/2 -> wait tau/2 -> pi -> wait tau/2 -> pi/2(180 deg) -> readout

    tau = 1 / (2 * cfg["df"]), df in MHz => tau in us.

    cfg["use_pi_pulse"]: if True, inserts a pi pulse in the middle.
    cfg["pi_gain"]     : DAC gain for the pi pulse, required if use_pi_pulse=True.
    """

    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # Total parity-mapping evolution time.
        self.tau_us = 1.0 / (2.0 * cfg["df"])
        self.use_pi_pulse = cfg.get("use_pi_pulse", False)

        # If using echo, split the same total tau around the pi pulse.
        wait_us = self.tau_us / 2.0 if self.use_pi_pulse else self.tau_us
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(wait_us))

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

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
        self.f_ge_reg = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(
            cfg["sigma"] * 4,
            gen_ch=cfg["qubit_ch"]
        )

        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit_pi2",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length
        )

        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit_pi",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length
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
        cfg = self.cfg

        # First pi/2 at phase 0.
        self.regwi(self.q_rp, self.r_phase, 0)
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit_pi2"
        )
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.use_pi_pulse:
            # Echo pi pulse in the middle.
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit_pi"
            )
            self.pulse(ch=cfg["qubit_ch"])

            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        # Final pi/2 at phase 180 deg.
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=self.deg2reg(180, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_gain"],
            waveform="qubit_pi2"
        )
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Readout with no relax delay.
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=0
        )

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True,
                readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=0)
        shots_i = self.di_buf[0].reshape((1, self.cfg["reps"])) / norm
        shots_q = self.dq_buf[0].reshape((1, self.cfg["reps"])) / norm
        return shots_i, shots_q


class ModifiedRamsey(ExperimentClass):
    """
    Repeated fixed-tau Ramsey for charge-parity switching time-series.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
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
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(
            self.soc,
            load_pulses=True,
            progress=progress
        )

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()

        data = {
            'config': self.cfg,
            'data': {
                'shots_i': shots_i,
                'shots_q': shots_q,
                'tau_us': 1.0 / (2.0 * self.cfg["df"]),
                'wait_us': (
                    1.0 / (4.0 * self.cfg["df"])
                    if self.cfg.get("use_pi_pulse", False)
                    else 1.0 / (2.0 * self.cfg["df"])
                ),
                'f_ge': self.cfg["f_ge"],
                'df': self.cfg["df"],
                'use_pi_pulse': self.cfg.get("use_pi_pulse", False),
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        shots_i = np.asarray(data['data']['shots_i'])
        shots_q = np.asarray(data['data']['shots_q'])
        tau_us = data['data']['tau_us']
        wait_us = data['data']['wait_us']
        df = data['data']['df']
        use_pi_pulse = data['data'].get('use_pi_pulse', False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        seq_label = "echo pi" if use_pi_pulse else "no pi"

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, '.', alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis('equal')
        plt.title(
            self.titlename
            + f"\n{seq_label}, tau={tau_us:.4f} us, wait={wait_us:.4f} us, df={df:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])