import datetime
import time

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.glitch import remeasure_glitched_rows
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import (
    n_drive_pulses, flux_hold_declare, flux_hold_build, flux_hold_us,
    rabi_flux_body)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
    acquire_pulse_sweep_iq,
)


class RabiSSProgram(RAveragerProgram):

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
        flux_hold_declare(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        drive_freq = self.freq2reg(cfg["rabi_drive_freq"], gen_ch=cfg["qubit_ch"])

        add_qubit_gaussian(self)
        if active_reset.uses_feedback(cfg):
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=drive_freq,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                 gain=cfg["start"], waveform="qubit")

        set_readout_pulse(self, read_freq)
        flux_hold_build(self)
        self.synci(200)

    def body(self):
        rabi_flux_body(self)

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        super().acquire(soc, load_pulses=load_pulses, readouts_per_experiment=1 + n_reset,
                        progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        reads = 1 + n_reset
        buf_i = self.di_buf[0].reshape((self.cfg["expts"], self.cfg["reps"], reads))
        buf_q = self.dq_buf[0].reshape((self.cfg["expts"], self.cfg["reps"], reads))
        shots_i = buf_i[:, :, n_reset] / length
        shots_q = buf_q[:, :, n_reset] / length
        return shots_i, shots_q


def sweep_gain_populations(experiment, cfg, gains, calib_params, progress=False):
    gains = np.asarray(gains, dtype=int).reshape(-1)
    if gains.size == 0:
        raise ValueError("Rabi gain sweep needs at least one gain")
    cfg["amp_start"] = int(gains[0])
    cfg["amp_step"] = int(round(
        (int(gains[-1]) - int(gains[0])) / max(gains.size - 1, 1)
    ))
    cfg["amp_expts"] = int(gains.size)
    if active_reset.uses_opx_unbounded(cfg):
        do_excursion = bool(cfg.get("ff_hold_gain", 0))
        shots_i, shots_q, _ = acquire_pulse_sweep_iq(
            experiment.soc,
            experiment.soccfg,
            cfg,
            gains=gains,
            pulses=int(cfg["n_pulses"]),
            frequency_mhz=cfg["rabi_drive_freq"],
            shots=int(cfg["shots"]),
            pulse_placement="excursion",
            do_excursion=do_excursion,
            excursion_gain=(cfg.get("ff_hold_gain") if do_excursion else None),
            flux_hold_us=flux_hold_us(
                cfg,
                cover_readout=not bool(cfg.get("readout_after_park", True)),
            ),
        )
    else:
        shots_i, shots_q = RabiSSProgram(experiment.soccfg, cfg).acquire(
            experiment.soc, load_pulses=True, progress=progress)
    pops = np.empty(len(gains), dtype=float)
    for j in range(len(gains)):
        pops[j] = discriminate_shots(shots_i[j], shots_q[j], calib_params).mean()
    return pops


class RabiChevronSS(ExperimentClass):

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
        gains = cfg["amp_start"] + cfg["amp_step"] * np.arange(int(cfg["amp_expts"]))
        df_vec = np.linspace(-cfg["freq_span"] / 2.0, cfg["freq_span"] / 2.0, int(cfg["freq_points"]))
        pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))

        n_f, n_a = len(df_vec), len(gains)
        pop = np.full((n_f, n_a), np.nan)
        reset_note = ("validated feedback reset" if active_reset.uses_feedback(cfg)
                      else f"passive relax {cfg['relax_delay']} us")
        print(f"[Rabi Chevron SS] {self.pulse_type} x{self.num_pi} pulses (error-amplified): "
              f"{n_f} detunings x {n_a} gains, {cfg['shots']} shots/pt; {reset_note}")

        def measure_row(i):
            cfg["rabi_drive_freq"] = pi_freq + float(df_vec[int(i)])
            pop[int(i), :] = sweep_gain_populations(self, cfg, gains, self.calib_params)

        start_time = time.time()
        for i in range(n_f):
            measure_row(i)
            if progress:
                progress_counter(i, n_f, start_time=start_time, label="Rabi chevron SS")

        nlow = max(1, min(int(cfg.get("baseline_ngains", 4)), max(1, n_a // 4)))
        if bool(cfg.get("remeasure_outliers", True)):
            remeasure_glitched_rows(
                lambda: np.median(pop[:, :nlow], axis=1), measure_row,
                sigma=float(cfg.get("outlier_sigma", 6.0)),
                passes=int(cfg.get("outlier_passes", 2)), label="Rabi Chevron SS",
                row_labels=[f"{df:+.1f} MHz" for df in df_vec])

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
