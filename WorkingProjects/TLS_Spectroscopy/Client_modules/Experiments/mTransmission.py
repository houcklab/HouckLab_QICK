import datetime
import time

import numpy as np
import matplotlib.pyplot as plt
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter


class TransReadProgram(AveragerProgram):

    def initialize(self):
        cfg = self.cfg
        cfg.setdefault("reps", int(cfg.get("shots", 1000)))
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.ff_segs = None
        if cfg.get("ff_ch", None) is not None:
            ff_pulse.declare_ff(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        set_readout_pulse(self, read_freq)
        if cfg.get("ff_ch", None) is not None:
            self.ff_segs = ff_pulse.build_ramp_hold_ramp(
                self,
                hold_us=(float(cfg["read_length"])
                         + float(cfg.get("adc_trig_offset", 0.0)) + 2.0),
                ff_gain=cfg.get("ff_gain", 0),
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                dt_def_us=cfg.get("dt_pulsedef", 0.002))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if self.ff_segs is None:
            self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                         adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                         wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))
            return
        ff_pulse.assert_park(self, self.ff_segs)
        self.sync_all(self.us2cycles(0.05))
        ff_pulse.play_ramp_up_hold(self, self.ff_segs,
                                   dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(cfg["relax_delay"]))


class Transmission(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Transmission', cfg=None, meta_dict=None, f_vec=None,
                 plot=True, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.element = str(path)
        self.f_vec = np.asarray(f_vec, dtype=float)
        self.plot = bool(plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 1000)))
        n = len(self.f_vec)
        mag = np.empty(n, dtype=float)
        start_time = time.time()
        for j, f in enumerate(self.f_vec):
            c = dict(cfg)
            c["read_pulse_freq"] = float(f)
            with suppress_stdout():
                I, Q = TransReadProgram(self.soccfg, c).acquire(self.soc, load_pulses=True,
                                                                progress=False)
            mag[j] = np.hypot(float(np.asarray(I).ravel()[0]), float(np.asarray(Q).ravel()[0]))
            if progress:
                progress_counter(j, n, start_time=start_time, label="transmission")
        mag_dbm = 20.0 * np.log10(mag + 1e-12)
        dip = float(self.f_vec[int(np.argmin(mag_dbm))])
        self.data = {
            'meta_dict': dict(cfg), 'f_vec': self.f_vec, 'IQ_magnitude_dBm': mag_dbm,
            'resonator_dip_freq_mhz': dip,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[transmission] resonator dip at {dip:.4f} MHz "
              f"-> set BaseConfig['read_pulse_freq'].")
        if self.plot:
            fig, ax = plt.subplots(1, 1, constrained_layout=True)
            ax.plot(self.f_vec, mag_dbm, ".-")
            ax.axvline(dip, color="red", linestyle="--", label=f"{dip:.4f} MHz")
            ax.set_xlabel("Readout frequency (MHz)")
            ax.set_ylabel("Power (dB)")
            ax.set_title(f"{self.element} Transmission, F = {dip:.3f} MHz, "
                         f"read gain {cfg.get('read_pulse_gain')}")
            ax.legend(loc="best", fontsize=8)
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
        arr = {'f_vec': self.data['f_vec'], 'IQ_magnitude_dBm': self.data['IQ_magnitude_dBm']}
        super().save_data(data=arr)
