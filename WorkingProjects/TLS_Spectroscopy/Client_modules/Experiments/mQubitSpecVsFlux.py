import time

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter


class QubitSpecProgram(RAveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        style = cfg.get("qubit_pulse_style", "const")
        if style == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                     gain=cfg["qubit_gain"], waveform="qubit")
        elif style == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="flat_top", freq=self.f_start,
                                     phase=0, gain=cfg["qubit_gain"], waveform="qubit",
                                     length=self.us2cycles(cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))
        else:
            kw = dict(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
                      gain=cfg["qubit_gain"],
                      length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
            if cfg.get("qubit_mode_periodic", False):
                kw["mode"] = "periodic"
            self.set_pulse_registers(**kw)

        set_readout_pulse(self, f_res)
        self.sync_all(self.us2cycles(1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class QubitSpecVsFlux(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Qubit_Spec_vs_Flux', cfg=None, flux_source=None,
                 resonator_lookup_csv=None, resonator_cosine_fit=None,
                 meta_dict=None, magnet_relax=0.1, fit_flux=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.flux_source = flux_source
        self.magnet_relax = magnet_relax
        self.fit_flux = fit_flux
        self._lookup = None
        if resonator_lookup_csv is not None:
            tbl = np.genfromtxt(resonator_lookup_csv, delimiter=",", names=True)
            self._lookup = (np.atleast_1d(tbl['dc_offset_V']),
                            np.atleast_1d(tbl['resonator_dip_freq_MHz']))
        self.resonator_cosine_fit = resonator_cosine_fit

    def _readout_freq_at(self, v):
        if self._lookup is not None:
            return float(np.interp(v, self._lookup[0], self._lookup[1]))
        if self.resonator_cosine_fit is not None:
            p = self.resonator_cosine_fit
            return float(ff.cosine_vs_flux(v, p['amplitude'], p['frequency'], p['phi'], p['offset']))
        return float(self.cfg["read_pulse_freq"])

    def _volt_vec(self):
        cfg = self.cfg
        return np.linspace(cfg["yokoVoltageStart"], cfg["yokoVoltageStop"],
                           int(cfg["yokoVoltageNumPoints"]))

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        cfg["start"] = cfg["qubit_freq_start"]
        cfg["expts"] = int(cfg["qubit_freq_expts"])
        cfg["step"] = (cfg["qubit_freq_stop"] - cfg["qubit_freq_start"]) / (cfg["expts"] - 1)
        fpts = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"], cfg["expts"])
        volts = self._volt_vec()

        Z_mag = np.full((len(volts), len(fpts)), np.nan)
        Z_phase = np.full((len(volts), len(fpts)), np.nan)
        qubit_dip = np.full(len(volts), np.nan)

        if self.flux_source is not None:
            self.flux_source.SetVoltage(float(volts[0]))
            time.sleep(self.magnet_relax)

        start = time.time()
        for i, v in enumerate(volts):
            if self.flux_source is not None:
                self.flux_source.SetVoltage(float(v))
                time.sleep(self.magnet_relax)
            cfg["read_pulse_freq"] = self._readout_freq_at(v)
            prog = QubitSpecProgram(self.soccfg, cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            sig = np.array(avgi[0][0]) + 1j * np.array(avgq[0][0])
            mag = np.abs(sig)
            Z_mag[i, :] = mag
            Z_phase[i, :] = np.unwrap(np.angle(sig))
            if progress:
                progress_counter(i, len(volts), start_time=start, label="qubit spec vs flux")
            sp, _ = ff.fit_spec_dip(fpts, mag, kind='auto')
            if sp is not None:
                qubit_dip[i] = sp['f0']
            if i == 0:
                print(f"[2] ~{(time.time()-start)*len(volts)/60:.1f} min for "
                      f"{len(volts)} flux x {cfg['expts']} freq points")

        data = {'config': cfg,
                'data': {'fpts': fpts, 'volts': volts, 'magnitude': Z_mag,
                         'phase': Z_phase, 'qubit_dip_MHz': qubit_dip}}
        self.data = data

        raw_csv = self.iname[:-4] + "_raw_sweep.csv"
        rows = []
        for i, v in enumerate(volts):
            for j, f in enumerate(fpts):
                rows.append([v, f, Z_mag[i, j], Z_phase[i, j]])
        np.savetxt(raw_csv, np.array(rows), delimiter=",",
                   header="dc_offset_V,frequency_MHz,magnitude,phase_rad", comments="")
        data['data']['raw_sweep_csv'] = raw_csv
        print(f"[2] raw sweep CSV: {raw_csv}")

        if self.fit_flux:
            params, perr = fx.fit_qubit_freq_vs_flux(volts, qubit_dip / 1e3)
            if params is not None:
                data['data']['flux_fit_params'] = params
                print("[2] FLUX_FIT_PARAMS = [")
                print("      %.8f,  # EJmax (GHz)" % params[0])
                print("      %.8f,  # Ec (GHz)" % params[1])
                print("      %.8f,  # period (V)" % params[2])
                print("      %.8f,  # sweet-spot offset (V)" % params[3])
                print("      %.8f,  # d (asymmetry)" % params[4])
                print("      0.0,          # tilt (GHz/V)")
                print("    ]")
            else:
                print("[2] transmon-arc fit failed; inspect the raw_sweep CSV and fit offline.")

        self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(1, 1, figsize=(8, 6), num=figNum)
        extent = [d['fpts'][0] / 1e3, d['fpts'][-1] / 1e3, d['volts'][0], d['volts'][-1]]
        im = ax.imshow(d['magnitude'], aspect='auto', origin='lower', extent=extent,
                       interpolation='none')
        ax.scatter(d['qubit_dip_MHz'] / 1e3, d['volts'], s=8, c='r', marker='x')
        if 'flux_fit_params' in d:
            fq = fx.estimate_fit_frequency_ghz_array(d['flux_fit_params'], d['volts'])
            ax.plot(fq, d['volts'], 'w--', lw=1, label='transmon fit')
            ax.legend(loc='upper right')
        ax.set_xlabel("Qubit frequency (GHz)")
        ax.set_ylabel("Yoko voltage (V)")
        ax.set_title("Qubit spectroscopy vs flux")
        fig.colorbar(im, ax=ax, label="|IQ| (a.u.)")
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
