"""
Rabi chevron, single-shot readout -- QICK port of Houck-Lab-Qua
LabCode/Experiments/Rabi/m_Rabi_Chevron_SS.py::RabiChevronSS.

QUA parity, with the ONE unavoidable substitution flagged below:
  * 2D sweep, drive detuning (df) x pulse amplitude (gain); each point plays num_pi
    X180 (or 2*num_pi X90) pulses, then a SINGLE-SHOT readout discriminated with the
    step-5 SS-cal params (scale_factor/threshold/read_theta) -> excited population.
  * QUA used 5x error amplification (num_pi_pulses=5) so a small per-pulse amplitude
    error compounds into a resolvable population shift near the pi point.
  * analyze(): argmax over the (df, gain) population map -> refined pi frequency + gain.

RESET SUBSTITUTION (tProc v1 cannot do the QUA active feedback reset -- measure ->
conditionally replay X180 -> re-measure -> loop): replaced by a passive relax_delay
between shots, exactly as the TLS T1 does.  The single-shot readout, error amplification,
and the population map are otherwise identical to QUA; only the reset physics differs.
`relax_delay` should be ~5x T1 so each shot starts in the ground state.

The shared RabiSSProgram (single-shot hardware gain sweep) is reused by mRabiLinecutSS.
"""

import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import n_drive_pulses


class RabiSSProgram(RAveragerProgram):
    """Hardware gain sweep at a fixed drive frequency (cfg['rabi_drive_freq']); body plays
    cfg['n_pulses'] gaussian pulses at the swept gain, then a single-shot readout with a
    passive relax_delay (the T1-style substitute for QUA active reset).  collect_shots()
    returns per-gain single shots of shape (amp_expts, shots)."""

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        cfg["start"] = int(cfg["amp_start"])
        cfg["step"] = int(cfg["amp_step"])
        cfg["expts"] = int(cfg["amp_expts"])

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        drive_freq = self.freq2reg(cfg["rabi_drive_freq"], gen_ch=cfg["qubit_ch"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]),
                       length=self.us2cycles(cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=drive_freq,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                 gain=cfg["start"], waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        for _ in range(int(cfg["n_pulses"])):
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))  # passive reset

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0])
        raw = np.array(self.get_raw())
        shots_i = raw[0, :, :, 0, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q = raw[0, :, :, 0, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        return shots_i, shots_q


def sweep_gain_populations(experiment, cfg, gains, calib_params):
    """Run one RabiSSProgram (gain sweep at cfg['rabi_drive_freq']) and return the excited
    population per gain (single shots discriminated with the SS-cal params)."""
    shots_i, shots_q = RabiSSProgram(experiment.soccfg, cfg).acquire(experiment.soc, load_pulses=True)
    pops = np.empty(len(gains), dtype=float)
    for j in range(len(gains)):
        pops[j] = discriminate_shots(shots_i[j], shots_q[j], calib_params).mean()
    return pops


class RabiChevronSS(ExperimentClass):
    """2D amp x detuning Rabi chevron, single-shot + N-pi error amplification.  cfg knobs:
    amp_start/amp_stop/amp_expts (DAC), freq_span/freq_points (MHz), num_pi, pulse_type,
    shots.  Requires calib_params from the step-5 single-shot calibration."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Rabi_Chevron_SS', cfg=None, meta_dict=None, calib_params=None,
                 num_pi_pulses=5, pulse_type="X180", live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        if calib_params is None:
            raise ValueError("RabiChevronSS needs calib_params from the single-shot calibration (step 5).")
        self.calib_params = calib_params
        self.element = str(path)
        self.num_pi = int(cfg.get("num_pi", num_pi_pulses))
        self.pulse_type = str(cfg.get("pulse_type", pulse_type)).upper()
        self.live_plot = bool(live_plot)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg["num_pi"] = self.num_pi
        cfg["pulse_type"] = self.pulse_type
        cfg["n_pulses"] = n_drive_pulses(self.pulse_type, self.num_pi)
        cfg["shots"] = int(cfg.get("shots", cfg.get("reps", 200)))

        cfg["amp_start"] = int(round(cfg["amp_start"]))
        cfg["amp_step"] = int(round((cfg["amp_stop"] - cfg["amp_start"]) / max(int(cfg["amp_expts"]) - 1, 1)))
        gains = cfg["amp_start"] + cfg["amp_step"] * np.arange(int(cfg["amp_expts"]))  # actual HW sweep
        df_vec = np.linspace(-cfg["freq_span"] / 2.0, cfg["freq_span"] / 2.0, int(cfg["freq_points"]))
        pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))

        n_f, n_a = len(df_vec), len(gains)
        pop = np.full((n_f, n_a), np.nan)
        print(f"[Rabi Chevron SS] {self.pulse_type} x{self.num_pi} pulses (error-amplified): "
              f"{n_f} detunings x {n_a} gains, {cfg['shots']} shots/pt; passive relax "
              f"{cfg['relax_delay']} us")

        for i, df in enumerate(df_vec):
            cfg["rabi_drive_freq"] = pi_freq + df
            pop[i, :] = sweep_gain_populations(self, cfg, gains, self.calib_params)

        idx = np.unravel_index(np.nanargmax(pop), pop.shape)
        best_df, best_gain = float(df_vec[idx[0]]), float(gains[idx[1]])
        self.data = {
            'config': dict(cfg), 'element': self.element, 'pulse_type': self.pulse_type,
            'number_pulses': self.num_pi, 'shots': cfg["shots"],
            'gain_vec': gains, 'detuning_vec_mhz': df_vec, 'drive_center_mhz': pi_freq,
            'ss_data': pop, 'best_gain': best_gain, 'best_detuning_mhz': best_df,
            'best_drive_freq_mhz': pi_freq + best_df,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[Rabi Chevron SS] max excited population at gain = {best_gain:.0f} DAC, "
              f"detuning = {best_df:+.3f} MHz (drive {pi_freq + best_df:.3f} MHz)")
        if self.save:
            self._plot(gains, df_vec, pop, plotDisp=plotDisp)
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, gains, df_vec, pop, plotDisp=False):
        fig = plt.figure(figsize=(6.5, 5))
        plt.pcolormesh(gains, df_vec, pop, shading='nearest')
        plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("Qubit detuning [MHz]")
        plt.minorticks_on(); plt.colorbar(label="Excited population")
        plt.suptitle(f"SS Rabi chevron {self.element} {self.pulse_type}, {self.num_pi} pulses, "
                     f"drive {self.data['drive_center_mhz']:.3f} MHz")
        plt.tight_layout()
        plt.savefig(self.iname, bbox_inches="tight")
        if plotDisp:
            plt.show(block=False); plt.pause(0.1)
        else:
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        super().save_data(data={'ss_data': self.data['ss_data'],
                                'gain_vec': self.data['gain_vec'],
                                'detuning_vec_mhz': self.data['detuning_vec_mhz']})
