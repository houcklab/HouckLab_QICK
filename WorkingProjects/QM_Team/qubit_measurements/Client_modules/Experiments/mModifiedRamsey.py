from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


class ModifiedRamseyProgram(AveragerProgram):
    """
    Fixed-tau Ramsey for charge-parity switching detection.

    Sequence per shot:
        pi/2 (phase=0, at f_ge=f_upper) -> wait tau -> pi/2 (phase=180 deg) -> readout

    tau = 1 / (2 * cfg["df"]),  df in MHz => tau in us.

    In the rotating frame locked to f_upper:
      - Upper parity (freq = f_upper): accumulates 0 relative phase -> projected to |0>
      - Lower parity (freq = f_lower): accumulates pi relative phase  -> projected to |1>

    cfg["f_ge"]    : higher qubit frequency (upper parity), in MHz
    cfg["df"]      : peak separation |f_upper - f_lower|, in MHz
    cfg["pi2_gain"]: DAC gain for the pi/2 pulse
    cfg["sigma"]   : Gaussian pulse sigma, in us (pulse length = 4*sigma)
    cfg["reps"]    : number of single-shot measurements to collect
    No relax delay is used — the measurement projects the qubit and acts as reset.
    """

    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")

        # tau = 1 / (2 * df)
        tau_us = 1.0 / (2.0 * cfg["df"])
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(tau_us))
        # second pi/2 phase is fixed at 180 degrees for every shot
        self.regwi(self.q_rp, self.r_phase2,
                   self.deg2reg(180, gen_ch=cfg["qubit_ch"]))

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4,
                                                  gen_ch=cfg["qubit_ch"])
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
        # First pi/2 at phase 0
        self.regwi(self.q_rp, self.r_phase, 0)
        self.pulse(ch=self.cfg["qubit_ch"])

        # Load 180-degree phase for the second pi/2 pulse, then wait tau
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        # Second pi/2 at phase 180 deg  (i.e. -pi/2)
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Readout with no relax delay — the measurement itself acts as the reset
        # by projecting the qubit to a definite state before the next shot.
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
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

    Required cfg keys (in addition to BaseConfig):
        f_ge       : higher qubit frequency from two-tone fit [MHz]
        df         : charge-dispersion peak separation [MHz]; sets tau = 1/(2*df)
        pi2_gain   : gain for the pi/2 Gaussian pulse
        sigma      : Gaussian sigma [us]
        reps       : number of single-shot measurements
        relax_delay: wait between shots [us]; set to >= 3-5 * T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path,
                         outerFolder=outerFolder, prefix=prefix,
                         cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True,
                                         progress=progress)

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()

        data = {
            'config': self.cfg,
            'data': {
                'shots_i': shots_i,
                'shots_q': shots_q,
                'tau_us': 1.0 / (2.0 * self.cfg["df"]),
                'f_ge': self.cfg["f_ge"],
                'df': self.cfg["df"],
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
        df = data['data']['df']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, '.', alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis('equal')
        plt.title(self.titlename + f"\ntau={tau_us:.4f} us, df={df:.4f} MHz")
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
