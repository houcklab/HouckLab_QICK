import os
import time

import numpy as np
import matplotlib.pyplot as plt
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter


class TransmissionProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        ff_pulse.declare_park_hold(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        set_readout_pulse(self, f_res)
        self.ff_park_segs = ff_pulse.build_park_hold(
            self, hold_us=ff_pulse.flux_settle_us(cfg))
        self.synci(200)

    def body(self):
        ff_pulse.play_park_up(self, self.ff_park_segs)
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(0.01))
        ff_pulse.play_park_down(self, self.ff_park_segs)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


class TransmissionVsFlux(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Resonator_Spec_vs_Flux', cfg=None, flux_source=None,
                 meta_dict=None, save_resonator_lookup=True, magnet_relax=0.1, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.flux_source = flux_source
        self.save_resonator_lookup = save_resonator_lookup
        self.magnet_relax = magnet_relax

    def _freq_vec(self):
        cfg = self.cfg
        if "trans_freq_start" in cfg and "trans_freq_stop" in cfg:
            return np.linspace(cfg["trans_freq_start"], cfg["trans_freq_stop"],
                               int(cfg["TransNumPoints"]))
        center, span = cfg["read_pulse_freq"], cfg["TransSpan"]
        return np.linspace(center - span, center + span, int(cfg["TransNumPoints"]))

    def _volt_vec(self):
        cfg = self.cfg
        return np.linspace(cfg["yokoVoltageStart"], cfg["yokoVoltageStop"],
                           int(cfg["yokoVoltageNumPoints"]))

    def _acquire_one_trace(self, fpts, progress=False):
        I = np.zeros(len(fpts))
        Q = np.zeros(len(fpts))
        for j, f in enumerate(fpts):
            self.cfg["read_pulse_freq"] = float(f)
            prog = TransmissionProgram(self.soccfg, self.cfg)
            res = prog.acquire(self.soc, load_pulses=True, progress=False)
            I[j] = np.array(res[0]).mean()
            Q[j] = np.array(res[1]).mean()
        return I, Q

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        fpts = self._freq_vec()
        volts = self._volt_vec()
        f_axis_ghz = (fpts + cfg.get("cavity_LO", 0) / 1e6) / 1e3

        Z_mag = np.full((len(volts), len(fpts)), np.nan)
        Z_phase = np.full((len(volts), len(fpts)), np.nan)
        dip_freq = np.full(len(volts), np.nan)

        if self.flux_source is not None:
            self.flux_source.SetVoltage(float(volts[0]))
            time.sleep(self.magnet_relax)

        start = time.time()
        for i, v in enumerate(volts):
            if self.flux_source is not None:
                self.flux_source.SetVoltage(float(v))
                time.sleep(self.magnet_relax)
            I, Q = self._acquire_one_trace(fpts)
            sig = I + 1j * Q
            mag = np.abs(sig)
            Z_mag[i, :] = 20 * np.log10(mag + 1e-12)
            Z_phase[i, :] = np.unwrap(np.angle(sig))
            dip_freq[i] = fpts[int(np.argmin(mag))]
            if progress:
                progress_counter(i, len(volts), start_time=start, label="transmission vs flux")

        data = {'config': cfg,
                'data': {'fpts': fpts, 'volts': volts,
                         'mag_db': Z_mag, 'phase': Z_phase, 'dip_freq': dip_freq}}
        self.data = data

        params, _ = ff.fit_cosine_vs_flux(volts, dip_freq)
        if params is not None:
            data['data']['resonator_cosine_fit'] = params

        lookup_csv = None
        if self.save_resonator_lookup:
            lookup_csv = self.iname[:-4] + "_resonator_lookup.csv"
            hdr = "dc_offset_V,resonator_dip_freq_MHz,resonator_dip_freq_abs_MHz"
            abs_dip = dip_freq + cfg.get("cavity_LO", 0) / 1e6
            np.savetxt(lookup_csv,
                       np.column_stack([volts, dip_freq, abs_dip]),
                       delimiter=",", header=hdr, comments="")
            data['data']['resonator_lookup_csv'] = lookup_csv
            print(f"[1] resonator lookup CSV: {lookup_csv}")

        self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        f_axis = (d['fpts'] + self.cfg.get("cavity_LO", 0) / 1e6) / 1e3
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(1, 1, figsize=(8, 6), num=figNum)
        extent = [f_axis[0], f_axis[-1], d['volts'][0], d['volts'][-1]]
        im = ax.imshow(d['mag_db'], aspect='auto', origin='lower', extent=extent,
                       interpolation='none')
        ax.scatter((d['dip_freq'] + self.cfg.get("cavity_LO", 0) / 1e6) / 1e3, d['volts'],
                   s=8, c='r', marker='x', label='dip')
        ax.set_xlabel("Readout frequency (GHz)")
        ax.set_ylabel("Yoko voltage (V)")
        ax.set_title("Resonator transmission |S21| (dB) vs flux")
        fig.colorbar(im, ax=ax, label="|S21| (dB)")
        ax.legend(loc='upper right')
        plt.tight_layout()
        plt.savefig(self.iname)
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf()
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
