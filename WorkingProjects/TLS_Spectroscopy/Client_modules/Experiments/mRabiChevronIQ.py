import datetime
import time

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import progress_counter
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.glitch import remeasure_glitched_rows
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)


def flux_hold_us(cfg, cover_readout):
    hold = int(cfg["n_pulses"]) * (4.0 * float(cfg["sigma"]) + 0.010) + 0.05
    if cover_readout:
        hold += float(cfg["read_length"]) + float(cfg["adc_trig_offset"]) + 0.05
    return hold


def flux_hold_declare(prog):
    prog.do_flux_hold = bool(prog.cfg.get("ff_hold_gain", 0))
    prog.do_static_ff_park = bool(ff_pulse.static_park_configured(prog.cfg))
    if prog.do_flux_hold or prog.do_static_ff_park:
        ff_pulse.declare_ff(prog)


def flux_hold_build(prog):
    if getattr(prog, "do_flux_hold", False):
        cfg = prog.cfg
        prog.ff_segs = ff_pulse.build_ramp_hold_ramp(
            prog, hold_us=flux_hold_us(cfg, cover_readout=not bool(cfg.get("readout_after_park", True))),
            ff_gain=int(cfg["ff_hold_gain"]),
            dt_play_us=cfg.get("dt_pulseplay", 5.0), ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
            dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(prog))


def _rabi_feedback_reset(prog):
    cfg = prog.cfg
    reset_read_freq = float(cfg.get(
        "reset_read_pulse_freq", cfg["read_pulse_freq"]))
    if not np.isclose(
            reset_read_freq, float(cfg["read_pulse_freq"]),
            rtol=0.0, atol=1e-9):
        raise ValueError(
            "feedback reset profile does not match this Rabi program's ADC/DDC "
            "frequency")
    page = prog.ch_page(cfg["qubit_ch"])
    r_gain = prog.sreg(cfg["qubit_ch"], "gain")
    reset_pi_freq = (
        cfg["reset_pi_freq"] if "reset_pi_freq" in cfg else
        cfg["qubit_pi_freq"] if "qubit_pi_freq" in cfg else
        cfg["qubit_freq"])
    set_readout_pulse(
        prog, gain=int(cfg.get(
            "reset_read_pulse_gain", cfg["read_pulse_gain"])))
    prog.mathi(page, 3, r_gain, "+", 0)
    prog.set_pulse_registers(
        ch=cfg["qubit_ch"], style="arb",
        freq=prog.freq2reg(float(reset_pi_freq),
            gen_ch=cfg["qubit_ch"]),
        phase=prog.deg2reg(0, gen_ch=cfg["qubit_ch"]),
        gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
        waveform="qubit_reset")
    active_reset.active_reset_block(
        prog, ro_ch=cfg["ro_chs"][0], threshold_raw=cfg["reset_threshold_raw"],
        oper=cfg.get("reset_oper", "lower"), ground_below=cfg.get("reset_ground_below", True),
        max_iters=int(cfg.get("reset_max_iters", 3)), page=page, reg_val=1, reg_thr=2)
    prog.set_pulse_registers(
        ch=cfg["qubit_ch"], style="arb",
        freq=prog.freq2reg(float(cfg["rabi_drive_freq"]),
                           gen_ch=cfg["qubit_ch"]),
        phase=prog.deg2reg(0, gen_ch=cfg["qubit_ch"]),
        gain=0, waveform="qubit")
    prog.mathi(page, r_gain, 3, "+", 0)
    set_readout_pulse(prog)


def rabi_flux_body(prog):
    cfg = prog.cfg
    feedback = active_reset.uses_feedback(cfg)
    if feedback:
        _rabi_feedback_reset(prog)
    hold = getattr(prog, "do_flux_hold", False)
    if hold:
        ff_pulse.assert_park(prog, prog.ff_segs, force=True)
        prog.sync_all(prog.us2cycles(max(float(cfg.get("baseline_rearm_us", 0.5)), 0.05)))
        ff_pulse.play_ramp_up_hold(prog, prog.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        prog.sync_all(prog.us2cycles(0.01))
    elif getattr(prog, "do_static_ff_park", False):
        ff_pulse.play_static_park(
            prog, settle_us=cfg.get("ff_park_settle_us", 0.05))
    for _ in range(int(cfg["n_pulses"])):
        prog.pulse(ch=cfg["qubit_ch"])
        prog.sync_all(prog.us2cycles(0.010))
    read_at_park = (not hold) or bool(cfg.get("readout_after_park", True))
    if hold and read_at_park:
        ff_pulse.play_ramp_down(prog, prog.ff_segs)
        prog.sync_all(prog.us2cycles(ff_pulse.flux_settle_us(cfg)))
    _reset_sync = 0.05 if feedback else (cfg["relax_delay"] if read_at_park else 0.01)
    prog.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                 adc_trig_offset=prog.us2cycles(cfg["adc_trig_offset"]),
                 wait=True, syncdelay=prog.us2cycles(_reset_sync))
    if hold and not read_at_park:
        ff_pulse.play_ramp_down(prog, prog.ff_segs)
        prog.sync_all(prog.us2cycles(0.05 if feedback else cfg["relax_delay"]))


class RabiChevronIQProgram(RAveragerProgram):

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


def n_drive_pulses(pulse_type, num_pi):
    return int(num_pi) * (2 if str(pulse_type).upper() == "X90" else 1)


class RabiChevronIQ(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='Rabi_Chevron_IQ', cfg=None, meta_dict=None, num_pi_pulses=1,
                 pulse_type="X180", live_plot=False, save=True, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
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
        cfg["shots"] = int(cfg.get("shots", cfg.get("reps", 100)))

        cfg["amp_start"] = int(round(cfg["amp_start"]))
        cfg["amp_step"] = int(round((cfg["amp_stop"] - cfg["amp_start"]) / max(int(cfg["amp_expts"]) - 1, 1)))
        gains = cfg["amp_start"] + cfg["amp_step"] * np.arange(int(cfg["amp_expts"]))
        df_vec = np.linspace(-cfg["freq_span"] / 2.0, cfg["freq_span"] / 2.0, int(cfg["freq_points"]))
        pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))

        n_f, n_a = len(df_vec), len(gains)
        I = np.full((n_f, n_a), np.nan)
        Q = np.full((n_f, n_a), np.nan)
        shuffle = bool(cfg.get("shuffle_detuning", True))
        order = (np.random.default_rng(int(cfg.get("shuffle_seed", 12345))).permutation(n_f)
                 if shuffle else np.arange(n_f))
        print(f"[Rabi Chevron IQ] {self.pulse_type} x{self.num_pi} pulses: "
              f"{n_f} detunings x {n_a} gains, {cfg['shots']} shots/pt; drive @ "
              f"{pi_freq:.3f} MHz +/- {cfg['freq_span']/2:.2f} MHz, gain {gains[0]:.0f}..{gains[-1]:.0f} DAC"
              + ("; randomized detuning order" if shuffle else ""))

        nlow = max(1, min(int(cfg.get("baseline_ngains", 4)), max(1, n_a // 4)))

        def measure_row(i):
            cfg["rabi_drive_freq"] = pi_freq + float(df_vec[int(i)])
            prog = RabiChevronIQProgram(self.soccfg, cfg)
            _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            I[int(i), :] = np.asarray(avgi[0][0])
            Q[int(i), :] = np.asarray(avgq[0][0])

        start_time = time.time()
        for step, i in enumerate(order):
            measure_row(int(i))
            if progress:
                progress_counter(step, n_f, start_time=start_time, label="Rabi chevron IQ")

        if bool(cfg.get("remeasure_outliers", True)):
            remeasure_glitched_rows(
                lambda: np.median(I[:, :nlow], axis=1) + 1j * np.median(Q[:, :nlow], axis=1),
                measure_row, sigma=float(cfg.get("outlier_sigma", 6.0)),
                passes=int(cfg.get("outlier_passes", 2)), label="Rabi Chevron IQ",
                row_labels=[f"{df:+.1f} MHz" for df in df_vec])

        Is = I - np.median(I[:, :nlow], axis=1, keepdims=True)
        Qs = Q - np.median(Q[:, :nlow], axis=1, keepdims=True)
        idx = np.unravel_index(np.nanargmax(Is ** 2 + Qs ** 2), Is.shape)
        best_df, best_gain = float(df_vec[idx[0]]), float(gains[idx[1]])
        self.data = {
            'config': dict(cfg), 'element': self.element, 'pulse_type': self.pulse_type,
            'number_pulses': self.num_pi, 'shots': cfg["shots"],
            'gain_vec': gains, 'detuning_vec_mhz': df_vec, 'drive_center_mhz': pi_freq,
            'I': I, 'Q': Q, 'measurement_order': np.asarray(order),
            'best_gain': best_gain, 'best_detuning_mhz': best_df,
            'best_drive_freq_mhz': pi_freq + best_df,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        print(f"[Rabi Chevron IQ] max |IQ| at gain = {best_gain:.0f} DAC, "
              f"detuning = {best_df:+.3f} MHz (drive {pi_freq + best_df:.3f} MHz)")
        if self.save:
            self._plot(gains, df_vec, I, Q, plotDisp=plotDisp)
            self.pickle_data()
        return {'config': cfg, 'data': self.data}

    def _plot(self, gains, df_vec, I, Q, plotDisp=False):
        fig = plt.figure(figsize=(11, 4.5))
        plt.suptitle(f"{self.element} {self.pulse_type} Rabi chevron, {self.num_pi} pulses, "
                     f"drive {self.data['drive_center_mhz']:.3f} MHz, sigma={self.cfg['sigma']} us")
        for k, (title, M) in enumerate([("I", I), ("Q", Q)]):
            plt.subplot(1, 2, k + 1)
            plt.pcolormesh(gains, df_vec, M, shading='nearest')
            plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("Qubit detuning [MHz]")
            plt.minorticks_on(); plt.colorbar(); plt.title(title)
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
        super().save_data(data={'I': self.data['I'], 'Q': self.data['Q'],
                                'gain_vec': self.data['gain_vec'],
                                'detuning_vec_mhz': self.data['detuning_vec_mhz']})
