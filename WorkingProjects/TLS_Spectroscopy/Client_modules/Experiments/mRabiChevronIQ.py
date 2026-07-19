"""
Rabi chevron, averaged-IQ readout -- QICK port of Houck-Lab-Qua
LabCode/Experiments/Rabi/m_Rabi_Chevron_IQ.py::RabiChevronIQ.

QUA parity (only units translate: Volts->DAC gain, IF Hz->absolute MHz, ns->us):
  * 2D sweep, qubit-drive frequency detuning (df) x pulse amplitude (gain).
  * Each point plays num_pi X180 pulses (or 2*num_pi X90 pulses -- 2 X90 == 1 X180)
    at the swept gain, then reads out I/Q averaged over `shots` reps.
  * QUA already uses a passive wait(reset_time) between shots here (NO active reset),
    so this is a byte-faithful port -- relax_delay is the QUA reset_time.
  * analyze(): argmax(I^2 + Q^2) over the (df, gain) map -> the drive detuning and gain
    that maximize the excited-state signal (rough pi frequency + amplitude), and the
    QUA 2-panel I/Q chevron PNG (amplitude [DAC] x detuning [MHz]).

The amplitude axis is the ABSOLUTE qubit-drive DAC gain (QICK sets gain directly), so
there is no QUA pi_amp normalization: `amp_start/amp_stop` ARE gains.  The frequency axis
is the drive detuning around cfg['qubit_pi_freq'] (absolute MHz; q_LO = 0 in this port).
"""

import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse


# ---- optional fast-flux hold: tune the pi at an arbitrary DC offset (the sweet spot may
# ---- be at any flux).  cfg['ff_hold_gain'] == 0 -> no hold (native/park, QUA YOKO=0).
# ---- Non-zero -> ramp park->hold at ff_hold_gain across the drive (and the readout if
# ---- cfg['readout_after_park'] is False), then ramp back -- the step-3 flux-delivery
# ---- sequence.  When holding, set qubit_pi_freq to the qubit freq AT that flux (from a
# ---- spec there); readout stays at park by default (uses the park single-shot cal).
def flux_hold_us(cfg, cover_readout):
    hold = int(cfg["n_pulses"]) * (4.0 * float(cfg["sigma"]) + 0.010) + 0.05
    if cover_readout:
        hold += float(cfg["read_length"]) + float(cfg["adc_trig_offset"]) + 0.05
    return hold


def flux_hold_declare(prog):
    """Declare the FF gen if cfg['ff_hold_gain'] != 0; sets prog.do_flux_hold.  Call early."""
    prog.do_flux_hold = bool(prog.cfg.get("ff_hold_gain", 0))
    if prog.do_flux_hold:
        ff_pulse.declare_ff(prog)


def flux_hold_build(prog):
    """Build the ramp-hold-ramp (after the pulse registers) if flux-holding."""
    if getattr(prog, "do_flux_hold", False):
        cfg = prog.cfg
        prog.ff_segs = ff_pulse.build_ramp_hold_ramp(
            prog, hold_us=flux_hold_us(cfg, cover_readout=not bool(cfg.get("readout_after_park", True))),
            ff_gain=int(cfg["ff_hold_gain"]),
            dt_play_us=cfg.get("dt_pulseplay", 5.0), ramp_us=cfg.get("ff_ramp_length", 0.02),
            dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(prog))


def rabi_flux_body(prog):
    """Shared body: (optional) ramp park->hold at ff_hold_gain -> n_pulses gaussian drive ->
    readout (at park after ramp-down by default, or AT the held flux) -> ramp down.  Passive
    relax_delay after the measurement (the tProc-v1 substitute for QUA active reset)."""
    cfg = prog.cfg
    hold = getattr(prog, "do_flux_hold", False)
    if hold:
        ff_pulse.assert_park(prog, prog.ff_segs)
        prog.sync_all(prog.us2cycles(max(float(cfg.get("baseline_rearm_us", 0.5)), 0.05)))
        ff_pulse.play_ramp_up_hold(prog, prog.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        prog.sync_all(prog.us2cycles(0.01))
    for _ in range(int(cfg["n_pulses"])):        # QUA: num_pi X180 (or 2*num_pi X90)
        prog.pulse(ch=cfg["qubit_ch"])
        prog.sync_all(prog.us2cycles(0.010))
    read_at_park = (not hold) or bool(cfg.get("readout_after_park", True))
    if hold and read_at_park:
        ff_pulse.play_ramp_down(prog, prog.ff_segs)
        prog.sync_all(prog.us2cycles(cfg.get("pre_meas_delay", 0.1)))
    prog.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                 adc_trig_offset=prog.us2cycles(cfg["adc_trig_offset"]),
                 wait=True, syncdelay=prog.us2cycles(cfg["relax_delay"] if read_at_park else 0.01))
    if hold and not read_at_park:
        ff_pulse.play_ramp_down(prog, prog.ff_segs)
        prog.sync_all(prog.us2cycles(cfg["relax_delay"]))


class RabiChevronIQProgram(RAveragerProgram):
    """Hardware gain sweep at a FIXED drive frequency (cfg['rabi_drive_freq']); body
    plays cfg['n_pulses'] gaussian pulses at the swept gain, then measures averaged IQ."""

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

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(cfg["sigma"]),
                       length=self.us2cycles(cfg["sigma"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=drive_freq,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                 gain=cfg["start"], waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        flux_hold_build(self)
        self.synci(200)

    def body(self):
        rabi_flux_body(self)

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])


def n_drive_pulses(pulse_type, num_pi):
    """QUA pulse count: X180 -> num_pi pulses; X90 -> 2*num_pi (2 X90 == 1 X180)."""
    return int(num_pi) * (2 if str(pulse_type).upper() == "X90" else 1)


class RabiChevronIQ(ExperimentClass):
    """2D amp x detuning Rabi chevron (averaged IQ).  Reads sweep knobs from cfg:
    amp_start/amp_stop/amp_expts (DAC gain), freq_span/freq_points (MHz detuning),
    num_pi, pulse_type ('X180'|'X90'), shots.  Drive freq centered on qubit_pi_freq."""

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
        gains = cfg["amp_start"] + cfg["amp_step"] * np.arange(int(cfg["amp_expts"]))  # actual HW sweep
        df_vec = np.linspace(-cfg["freq_span"] / 2.0, cfg["freq_span"] / 2.0, int(cfg["freq_points"]))
        pi_freq = float(cfg.get("qubit_pi_freq", cfg["qubit_freq"]))

        n_f, n_a = len(df_vec), len(gains)
        I = np.full((n_f, n_a), np.nan)
        Q = np.full((n_f, n_a), np.nan)
        print(f"[Rabi Chevron IQ] {self.pulse_type} x{self.num_pi} pulses: "
              f"{n_f} detunings x {n_a} gains, {cfg['shots']} shots/pt; drive @ "
              f"{pi_freq:.3f} MHz +/- {cfg['freq_span']/2:.2f} MHz, gain {gains[0]:.0f}..{gains[-1]:.0f} DAC")

        for i, df in enumerate(df_vec):
            cfg["rabi_drive_freq"] = pi_freq + df
            prog = RabiChevronIQProgram(self.soccfg, cfg)
            _x, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=False)
            I[i, :] = np.asarray(avgi[0][0])
            Q[i, :] = np.asarray(avgq[0][0])

        idx = np.unravel_index(np.argmax(I ** 2 + Q ** 2), I.shape)
        best_df, best_gain = float(df_vec[idx[0]]), float(gains[idx[1]])
        self.data = {
            'config': dict(cfg), 'element': self.element, 'pulse_type': self.pulse_type,
            'number_pulses': self.num_pi, 'shots': cfg["shots"],
            'gain_vec': gains, 'detuning_vec_mhz': df_vec, 'drive_center_mhz': pi_freq,
            'I': I, 'Q': Q,
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
        plt.subplot(121)
        plt.pcolormesh(gains, df_vec, I, shading='nearest')
        plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("Qubit detuning [MHz]")
        plt.minorticks_on(); plt.colorbar(); plt.title("I")
        plt.subplot(122)
        plt.pcolormesh(gains, df_vec, Q, shading='nearest')
        plt.xlabel("Qubit pulse gain [DAC]"); plt.ylabel("Qubit detuning [MHz]")
        plt.minorticks_on(); plt.colorbar(); plt.title("Q")
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
