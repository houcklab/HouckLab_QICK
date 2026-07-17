"""
STEP 1 (all-fast-flux variant): resonator transmission vs fast-flux gain.

The bring-up check for the flux wiring: sweep the readout frequency while the
ff DAC HOLDS each flux level, and watch the resonator dip move vs ff_gain.  If
the dip moves, the ff_ch wiring / polarity / rough flux scale are all confirmed
-- no qubit knowledge needed.  Also exports a resonator-vs-ff lookup CSV.

Unlike every other FF experiment in this pipeline (which read out at park), the
readout here deliberately happens AT the held flux -- that is the measurement.
Sequence per shot:  assert park -> ramp to ff_gain + settle (ff_settle_us) ->
measure while held (stdysel='last' keeps the level through the readout) ->
ramp back to park -> relax.

QUA analog: m_transmission_vs_flux.py::TransmissionVsFlux, with the OPX
set_dc_offset axis replaced by the ff DAC gain axis.
"""

import time

import numpy as np
import matplotlib.pyplot as plt
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse


class FFTransProgram(AveragerProgram):
    """One (ff_gain, readout-freq) transmission point, readout at the held flux."""

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        ff_pulse.declare_ff(self)
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch,
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])
        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=f_res, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        # settle hold before the readout window; stdysel='last' keeps the flux at
        # the target THROUGH the measure() that follows
        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=max(cfg.get("ff_settle_us", 20.0), cfg.get("dt_pulseplay", 5.0)),
            ff_gain=cfg["ff_gain"], dt_play_us=cfg.get("dt_pulseplay", 5.0),
            ramp_us=cfg.get("ff_ramp_length", 0.02), dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        ff_pulse.assert_park(self, self.ff_segs)
        self.sync_all(self.us2cycles(0.05))
        ff_pulse.play_ramp_up_hold(self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.01))
        # readout AT the held flux (the point of this experiment)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(cfg["relax_delay"]))


class TransmissionVsFFGain(ExperimentClass):
    """2D resonator transmission vs (readout frequency, fast-flux gain).

    cfg keys: trans_freq_start/trans_freq_stop/TransNumPoints (MHz),
              ff_gain_start/ff_gain_stop/ff_gain_num (or ff_gain_vec, DAC units),
              ff_settle_us, reps, relax_delay (keep small -- no qubit involved).
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Transmission_vs_FF_Gain', cfg=None, meta_dict=None,
                 save_resonator_lookup=True, resonator_lookup_smooth_points=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.save_resonator_lookup = save_resonator_lookup
        self.resonator_lookup_smooth_points = resonator_lookup_smooth_points

    def _freq_vec(self):
        cfg = self.cfg
        return np.linspace(cfg["trans_freq_start"], cfg["trans_freq_stop"],
                           int(cfg["TransNumPoints"]))

    def _gain_vec(self):
        cfg = self.cfg
        if "ff_gain_vec" in cfg:
            return np.asarray(cfg["ff_gain_vec"], dtype=float)
        return np.linspace(cfg["ff_gain_start"], cfg["ff_gain_stop"], int(cfg["ff_gain_num"]))

    def acquire(self, progress=False, plotDisp=False, figNum=1):
        cfg = self.cfg
        fpts = self._freq_vec()
        gains = self._gain_vec()

        Z_mag = np.full((len(gains), len(fpts)), np.nan)
        Z_phase = np.full((len(gains), len(fpts)), np.nan)
        dip_freq = np.full(len(gains), np.nan)

        start = time.time()
        for i, g in enumerate(gains):
            cfg["ff_gain"] = float(g)
            I = np.zeros(len(fpts))
            Q = np.zeros(len(fpts))
            for j, f in enumerate(fpts):
                cfg["read_pulse_freq"] = float(f)
                prog = FFTransProgram(self.soccfg, cfg)
                res = prog.acquire(self.soc, load_pulses=True, progress=False)
                I[j] = np.array(res[0][0][0]).mean()
                Q[j] = np.array(res[0][0][1]).mean()
            sig = I + 1j * Q
            mag = np.abs(sig)
            Z_mag[i, :] = 20 * np.log10(mag + 1e-12)
            Z_phase[i, :] = np.unwrap(np.angle(sig))
            dip_freq[i] = fpts[int(np.argmin(mag))]
            if i == 0:
                per = time.time() - start
                print(f"[1] ~{per*len(gains)/60:.1f} min for {len(gains)} ff_gain x "
                      f"{len(fpts)} freq points")

        data = {'config': cfg, 'data': {'fpts': fpts, 'ff_gains': gains,
                                        'mag_db': Z_mag, 'phase': Z_phase,
                                        'dip_freq_MHz': dip_freq}}
        self.data = data

        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff

        # smoothed dip trace (QUA _smooth_resonator_dip_trace): feeds the saved
        # lookup and the dispersive fit; the cosine fit uses the raw minima
        dip_smoothed, smooth_win = ff.smooth_resonator_dip_trace(
            dip_freq, self.resonator_lookup_smooth_points)
        data['data']['dip_freq_smoothed_MHz'] = dip_smoothed
        data['data']['lookup_smooth_window'] = smooth_win

        # (a) legacy 4-param cosine fit -> resonator_fit_parameters_cosine (the QUA
        # default readout-IF source when USE_RESONATOR_LOOKUP is False)
        cos_params, _ = ff.fit_cosine_vs_flux(gains, dip_freq)
        if cos_params is not None:
            data['data']['resonator_fit_parameters_cosine'] = cos_params

        # (b) 7-param physical dressed-resonator (avoided-crossing) fit ->
        # resonator_fit_parameters_dispersive; failure leaves the cosine fit intact
        period_seed = None
        if cos_params is not None and cos_params.get('frequency'):
            period_seed = 1.0 / abs(cos_params['frequency'])
        anharm_mhz = abs(self.cfg.get("anharmonicity_mhz", -200.0))
        disp_params, disp_rms = ff.fit_resonator_dispersive(
            gains, dip_smoothed, period_seed=period_seed,
            Ec_seed_ghz=anharm_mhz / 1e3)
        if disp_params is not None:
            data['data']['resonator_fit_parameters_dispersive'] = disp_params
            data['data']['resonator_dispersive_rms_MHz'] = disp_rms

        if self.save_resonator_lookup:
            lookup_csv = self.iname[:-4] + "_resonator_lookup.csv"
            np.savetxt(lookup_csv,
                       np.column_stack([gains, dip_smoothed, dip_freq]), delimiter=",",
                       header="ff_gain,resonator_dip_freq_MHz,resonator_dip_freq_raw_MHz",
                       comments="")
            data['data']['resonator_lookup_csv'] = lookup_csv
        span = np.nanmax(dip_freq) - np.nanmin(dip_freq)
        print(f"[1] dip moved {span*1e3:.0f} kHz over ff_gain "
              f"{gains.min():g}..{gains.max():g} "
              f"({'flux line LIVE' if span > 0.02 else 'little/no motion -- check wiring/polarity/range'})")

        self.display(data, plotDisp=plotDisp, figNum=figNum)
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kw):
        if data is None:
            data = self.data
        d = data['data']
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(1, 1, figsize=(8, 6), num=figNum)
        extent = [d['fpts'][0], d['fpts'][-1], d['ff_gains'][0], d['ff_gains'][-1]]
        im = ax.imshow(d['mag_db'], aspect='auto', origin='lower', extent=extent,
                       interpolation='none')
        ax.scatter(d['dip_freq_MHz'], d['ff_gains'], s=8, c='r', marker='x', label='dip')
        # fit overlays (QUA style: cosine black solid, dispersive dashed red)
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as ff
        g_fine = np.linspace(d['ff_gains'][0], d['ff_gains'][-1], 400)
        if 'resonator_fit_parameters_cosine' in d:
            p = d['resonator_fit_parameters_cosine']
            ax.plot(ff.cosine_vs_flux(g_fine, p['amplitude'], p['frequency'],
                                      p['phi'], p['offset']),
                    g_fine, 'k-', lw=1, label='cosine fit')
        if 'resonator_fit_parameters_dispersive' in d:
            ax.plot(ff.resonator_dispersive_func(g_fine,
                                                 *d['resonator_fit_parameters_dispersive']),
                    g_fine, 'r--', lw=1, label='dispersive fit')
        ax.set_xlabel("Readout frequency (MHz)")
        ax.set_ylabel("ff_gain (DAC units)")
        ax.set_title("Resonator transmission |S21| (dB) vs fast-flux gain")
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
        arr = {k: v for k, v in data['data'].items() if not isinstance(v, str)}
        super().save_data(data=arr)
