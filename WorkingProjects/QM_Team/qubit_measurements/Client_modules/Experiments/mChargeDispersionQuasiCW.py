from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from datetime import datetime


class ChargeDispersionQuasiCWProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
            ro_ch=cfg["ro_chs"][0],) # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"],  "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"]))
            self.qubit_length_us = cfg["qubit_length"]
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))


    def body(self):
        self.sync_all()
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(self.us2cycles(0.5))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class ChargeDispersionQuasiCW(ExperimentClass):
    """
    Quasi-CW charge dispersion experiment.
    Runs the pulse-measure loop in hardware using cfg["reps"] and returns
    repetition-resolved data in one acquire call.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.prog = ChargeDispersionQuasiCWProg(self.soccfg, self.cfg)

    def acquire(self, progress=False, debug=False, load_pulses=True, print_time=False):
        if print_time:
            start_real = datetime.now()

        prog = self.prog

        # This still returns averaged data, but more importantly it also fills
        # prog.di_buf and prog.dq_buf with the raw repetition stream.
        x_pts, avgi_avg, avgq_avg = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=load_pulses,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=progress
        )

        # averaged outputs
        avgi_avg = np.asarray(avgi_avg)
        avgq_avg = np.asarray(avgq_avg)

        signal_avg = (avgi_avg + 1j * avgq_avg) * np.exp(
            1j * (
                2 * np.pi * self.cfg['cavity_winding_freq'] * self.cfg["pulse_freq"]
                + self.cfg['cavity_winding_offset']
            )
        )

        # raw repetition-resolved outputs
        # prog.di_buf/prog.dq_buf contain one entry per hardware shot
        raw_i = np.asarray(prog.di_buf[0])   # ADC 0
        raw_q = np.asarray(prog.dq_buf[0])   # ADC 0

        reps = int(self.cfg["reps"])
        expts = int(self.cfg["expts"])

        # RAverager ordering is expt outer, reps inner in the tProc program.
        # Depending on buffer order, one of these reshape conventions is right.
        # The usual desired final shape is (repetitions, expts).
        raw_i = raw_i.reshape(expts, reps).T
        raw_q = raw_q.reshape(expts, reps).T

        raw_signal = (raw_i + 1j * raw_q) * np.exp(
            1j * (
                2 * np.pi * self.cfg['cavity_winding_freq'] * self.cfg["pulse_freq"]
                + self.cfg['cavity_winding_offset']
            )
        )

        if print_time:
            elapsed = datetime.now() - start_real
            print("Elapsed time for one hardware acquire:", elapsed)

        data = {
            'x_pts': np.asarray(x_pts),
            'avgi': signal_avg.real,
            'avgq': signal_avg.imag,
            'raw_i': raw_signal.real,
            'raw_q': raw_signal.imag,
            'raw_amp': np.abs(raw_signal) ** 2,
            'amps_per_rep': np.mean(np.abs(raw_signal) ** 2, axis=1),  # one scalar per repetition
        }

        self.data = {'data': data}
        return self.data


