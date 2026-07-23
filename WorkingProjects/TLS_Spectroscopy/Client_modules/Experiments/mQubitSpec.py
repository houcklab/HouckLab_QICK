import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse


class QubitSpecProgram(RAveragerProgram):
    """QUA m_qubit_spec pulse sequence, faithfully:

        for_(n < shots):
            for_each_(f, f_vec):
                update_frequency(qubit, f)
                play("constant_tone", qubit)
                align()
                measure_1q()

    A constant tone is swept across the qubit drive frequency and the resonator is read
    after each drive.  There is deliberately NO qubit reset between frequency points -- the
    QUA source comments it out ("just looking for a feature, not a pi pulse"), so this is a
    driven-steady-state sweep.  The frequency is swept in hardware on the qubit generator's
    frequency register (RAveragerProgram)."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start,
                                 phase=0, gain=int(cfg["qubit_gain"]),
                                 length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
        set_readout_pulse(self, read_freq)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.02))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitSpec(ExperimentClass):
    """QICK port of QUA m_qubit_spec.QubitSpec: a 1D qubit-drive-frequency sweep with a
    constant tone.  Plots magnitude (dB) and phase against the qubit drive frequency in two
    stacked panels (both with frequency on x, exactly like the QUA experiment) and reports
    the spectral feature (the |S21| dip)."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec', cfg=None, meta_dict=None, f_min=None, f_max=None,
                 f_step=None, plot=True, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.f_min = float(f_min)
        self.f_max = float(f_max)
        self.f_step = float(f_step)
        self.f_vec = np.arange(self.f_min, self.f_max, self.f_step)
        self.plot = bool(plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 1000)))
        cfg["start"] = float(self.f_min)
        cfg["step"] = float(self.f_step)
        cfg["expts"] = int(len(self.f_vec))
        prog = QubitSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=progress)
        I = np.asarray(avgi[0][0], dtype=float)
        Q = np.asarray(avgq[0][0], dtype=float)
        f = self.f_vec[:len(I)]
        mag_dbm = 20.0 * np.log10(np.hypot(I, Q) + 1e-12)
        phase = np.arctan2(Q, I)
        self.data = {
            'meta_dict': dict(cfg), 'f_vec': f, 'IQ_magnitude_dBm': mag_dbm,
            'IQ_phase': phase,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[qubit spec] swept {f[0]:.0f}-{f[-1]:.0f} MHz at gain {cfg.get('qubit_gain')} "
              f"-- read the qubit feature off the plot (QUA QubitSpec does not auto-pick a "
              f"line; a strong wide sweep also excites TLS/modes).")
        if self.plot:
            fig, ax = plt.subplots(2, 1, constrained_layout=True, figsize=(7, 6))
            ax[0].plot(f, mag_dbm, ".-")
            ax[0].set_ylabel("Transmission (dB)")
            ax[0].set_title(f"{self.element} Qubit Spec, gain {cfg.get('qubit_gain')}, "
                            f"len {cfg.get('qubit_length')} us")
            ax[1].plot(f, phase, ".-")
            ax[1].set_xlabel("Qubit frequency (MHz)")
            ax[1].set_ylabel("Phase (rad)")
            plt.savefig(self.iname, bbox_inches="tight")
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            else:
                plt.close(fig)
        if self.save:
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        arr = {'f_vec': self.data['f_vec'],
               'IQ_magnitude_dBm': self.data['IQ_magnitude_dBm'],
               'IQ_phase': self.data['IQ_phase']}
        super().save_data(data=arr)
