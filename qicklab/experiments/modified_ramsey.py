import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram

from qicklab.core.active_reset import ActiveResetMixin
from qicklab.core.experiment import ExperimentClass
from qicklab.core.readout import cover_readout_window
from qicklab.core.schedule import RepPeriodMixin

# h5 code of cfg["mr_control_type"]; expected signatures in docs/experiments/modified_ramsey.md.
MR_CONTROL_TYPE_CODES = {
    "parity": 0,
    "flip_final_pi2": 1,
    "echo_null": 2,
    "tau_offset": 3,
    "drive_detuned": 4,
    "drive_off": 5,
}


def plan_parity_mapping(
    df_mhz,
    sigma_us,
    use_pi_pulse=False,
    symmetric_ramsey=False,
    flip_final_pi2=False,
    max_bandwidth_ratio=1.0,
    tau_us=None,
    drive_freq_offset_mhz=None,
):
    """Hardware-free timing/bandwidth feasibility of the parity -> state mapping with
    nominal 4*sigma envelopes; returns feasible, errors, warnings and the derived
    numbers (docs/experiments/modified_ramsey.md)."""
    errors, warnings = [], []
    if df_mhz <= 0:
        raise ValueError("df_mhz must be positive")
    if sigma_us <= 0:
        raise ValueError("sigma_us must be positive")

    tau_us = 1.0 / (2.0 * df_mhz) if tau_us is None else float(tau_us)
    pulse_us = 4.0 * sigma_us
    n_gaps = 2 if use_pi_pulse else 1
    gap_us = (tau_us - n_gaps * pulse_us) / n_gaps
    df_max_mhz = 1.0 / (2.0 * n_gaps * pulse_us)
    if gap_us <= 0:
        errors.append(
            f"df={df_mhz} MHz needs tau={tau_us:.4f} us but the "
            f"{3 if use_pi_pulse else 2} pulses span "
            f"{n_gaps * pulse_us:.4f} us; need df < {df_max_mhz:.4f} MHz at "
            f"sigma={sigma_us} us (or shorter sigma)"
        )

    rabi_pi2_mhz = 0.0997 / sigma_us
    if drive_freq_offset_mhz is None:
        drive_freq_offset_mhz = -df_mhz / 2.0 if symmetric_ramsey else 0.0
    branch_detuning_mhz = max(
        abs(float(drive_freq_offset_mhz)), abs(float(drive_freq_offset_mhz) + df_mhz)
    )
    bandwidth_ratio = branch_detuning_mhz / rabi_pi2_mhz
    recommend_symmetric = (not symmetric_ramsey) and bandwidth_ratio > 0.2
    if bandwidth_ratio > max_bandwidth_ratio:
        errors.append(
            f"branch detuning {branch_detuning_mhz:.4f} MHz is "
            f"{bandwidth_ratio:.2f}x the pi/2 Rabi rate "
            f"({rabi_pi2_mhz:.4f} MHz): the off-resonant branch cannot be "
            "rotated; shorten sigma" + ("" if symmetric_ramsey else " or set symmetric_ramsey=True")
        )
    elif bandwidth_ratio > 0.2:
        warnings.append(
            f"branch detuning is {bandwidth_ratio:.2f}x the pi/2 Rabi rate; "
            "the off-resonant branch will be under-rotated"
            + (" -- symmetric_ramsey=True would halve the detuning" if recommend_symmetric else "")
        )
    if use_pi_pulse:
        warnings.append(
            "use_pi_pulse=True is a Hahn-echo NULL control: it refocuses the "
            "static parity detuning and should suppress the parity signal"
        )

    base = 90 if symmetric_ramsey else 180
    final_phase = (base + (180 if flip_final_pi2 else 0)) % 360
    return {
        "feasible": not errors,
        "errors": errors,
        "warnings": warnings,
        "tau_us": tau_us,
        "pulse_us": pulse_us,
        "n_gaps": n_gaps,
        "gap_us": gap_us,
        "df_max_mhz": df_max_mhz,
        "rabi_pi2_mhz": rabi_pi2_mhz,
        "branch_detuning_mhz": branch_detuning_mhz,
        "bandwidth_ratio": bandwidth_ratio,
        "recommend_symmetric": recommend_symmetric,
        "drive_freq_offset_mhz": float(drive_freq_offset_mhz),
        "final_pi2_phase_deg": final_phase,
    }


def build_control_variants(
    base_cfg,
    include=("parity", "flip_final_pi2", "echo_null", "tau_offset", "drive_detuned", "drive_off"),
    tau_offset_frac=0.25,
    detuning_mhz=None,
):
    """Copies of base_cfg for the parity run and each control in `include`, each
    pre-checked with plan_parity_mapping; infeasible ones get cfg=None and a
    skip_reason instead of raising (docs/experiments/modified_ramsey.md#analysis)."""
    out = []
    for name in include:
        if name not in MR_CONTROL_TYPE_CODES:
            raise ValueError(f"unknown control type {name!r}")
        cfg = dict(base_cfg)
        cfg["mr_control_type"] = name
        expected = ""
        if name == "parity":
            expected = "telegraph parity signal at tau = 1/(2 df)"
        elif name == "flip_final_pi2":
            cfg["flip_final_pi2"] = not bool(base_cfg.get("flip_final_pi2", False))
            expected = "parity->state mapping inverted; same rates/amplitude"
        elif name == "echo_null":
            cfg["use_pi_pulse"] = True
            expected = "parity contrast suppressed (echo refocuses df)"
        elif name == "tau_offset":
            cfg["ramsey_tau_us"] = (
                1.0 / (2.0 * float(base_cfg["df"])) * (1.0 + float(tau_offset_frac))
            )
            cfg["mr_control_tau_offset_frac"] = float(tau_offset_frac)
            expected = (
                f"tau deliberately {tau_offset_frac:+.0%} off the pi "
                "condition; contrast reduced/rotated"
            )
        elif name == "drive_detuned":
            det = float(detuning_mhz) if detuning_mhz is not None else float(base_cfg["df"])
            base_drive = (
                float(base_cfg["f_ge"]) - float(base_cfg["df"]) / 2.0
                if base_cfg.get("symmetric_ramsey", False)
                else float(base_cfg["f_ge"])
            )
            cfg["ramsey_drive_freq_mhz"] = base_drive + det
            cfg["max_drive_bandwidth_ratio"] = 1e12
            cfg["mr_control_detuning_mhz"] = det
            expected = f"drive detuned {det:+.4f} MHz; mapping degraded"
        elif name == "drive_off":
            cfg["pi2_gain"] = 0
            expected = "no Ramsey drive; readout baseline only"

        plan = plan_parity_mapping(
            cfg["df"],
            cfg["sigma"],
            use_pi_pulse=cfg.get("use_pi_pulse", False),
            symmetric_ramsey=cfg.get("symmetric_ramsey", False),
            flip_final_pi2=cfg.get("flip_final_pi2", False),
            tau_us=cfg.get("ramsey_tau_us"),
            drive_freq_offset_mhz=(
                cfg.get("ramsey_drive_freq_mhz") - cfg["f_ge"]
                if cfg.get("ramsey_drive_freq_mhz") is not None
                else None
            ),
            max_bandwidth_ratio=cfg.get("max_drive_bandwidth_ratio", 1.0),
        )
        skip = None
        if not plan["feasible"]:
            skip = "; ".join(plan["errors"])
            cfg = None
        out.append(
            {
                "label": name,
                "control_type": name,
                "cfg": cfg,
                "skip_reason": skip,
                "expected": expected,
                "plan": plan,
            }
        )
    return out


class ModifiedRamseyProgram(ActiveResetMixin, RepPeriodMixin, AveragerProgram):
    """Fixed-tau Ramsey for charge parity: [active reset] -> pi/2 -> tau -> pi/2(final
    phase) -> readout; echo: pi/2 -> tau/2 -> pi -> tau/2 -> pi/2. tau is the total
    centre-to-centre interval; cfg reference in docs/experiments/modified_ramsey.md."""

    def initialize(self):
        cfg = self.cfg

        if cfg["df"] <= 0:
            raise ValueError("cfg['df'] must be positive")
        if cfg["sigma"] <= 0:
            raise ValueError("cfg['sigma'] must be positive")
        if cfg["readout_length"] <= 0:
            raise ValueError("cfg['readout_length'] must be positive")
        for delay_key in ("adc_trig_offset", "mr_relax_delay"):
            if cfg.get(delay_key, 0.0) < 0:
                raise ValueError(f"cfg['{delay_key}'] must be non-negative")
        if int(cfg.get("rounds", 1)) != 1:
            raise ValueError(
                f"cfg['rounds']={cfg.get('rounds')} is not supported: the "
                "shot buffer keeps only the final round, so earlier rounds "
                "would be silently dropped from the parity record. Use "
                "rounds=1 and increase cfg['reps']."
            )
        if cfg.get("flattop_length") is not None:
            raise ValueError(
                "ModifiedRamseyProgram plays gaussian 'arb' qubit pulses only, "
                "but cfg['flattop_length'] is set "
                f"({cfg['flattop_length']}). The pi/pi2 gains for a flat_top "
                "pulse do not transfer to a gaussian. Set flattop_length=None "
                "and supply arb-calibrated gains."
            )

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3

        self.configure_active_reset()

        self.tau_us = float(cfg.get("ramsey_tau_us", 1.0 / (2.0 * cfg["df"])))
        self.use_pi_pulse = cfg.get("use_pi_pulse", False)
        if self.use_pi_pulse:
            print(
                "[ModifiedRamsey] WARNING: use_pi_pulse=True inserts a Hahn "
                "echo, which refocuses the static parity detuning df. This is "
                "a NULL/CONTROL sequence -- expect zero parity contrast. Do "
                "not interpret its output as a parity trace."
            )

        # f_ge is the UPPER branch; symmetric drives the midpoint f_ge - df/2.
        self.symmetric_ramsey = cfg.get("symmetric_ramsey", False)
        default_drive = cfg["f_ge"] - cfg["df"] / 2.0 if self.symmetric_ramsey else cfg["f_ge"]
        self.drive_freq_mhz = float(cfg.get("ramsey_drive_freq_mhz", default_drive))

        base_pi2_phase_deg = 90 if self.symmetric_ramsey else 180
        flip_offset_deg = 180 if cfg.get("flip_final_pi2", False) else 0
        self.final_pi2_phase_deg = (base_pi2_phase_deg + flip_offset_deg) % 360

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        cover_readout_window(self, cfg)

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        # Every qubit pulse, the reset pi included, plays at the drive frequency.
        self.f_ge_reg = self.freq2reg(self.drive_freq_mhz, gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.pulse_us = float(self.cycles2us(self.pulse_qubit_length, gen_ch=cfg["qubit_ch"]))

        # Waits run between pulse edges, tau is centre-to-centre (docs/experiments/modified_ramsey.md).
        n_gaps = 2 if self.use_pi_pulse else 1
        total_pulse_span_us = n_gaps * self.pulse_us
        wait_us = (self.tau_us - total_pulse_span_us) / n_gaps
        if wait_us <= 0:
            df_max = 1.0 / (2.0 * n_gaps * self.pulse_us)
            raise ValueError(
                f"programmed tau={self.tau_us:.4f} us (physical "
                f"df={cfg['df']} MHz), but "
                f"the {'three' if self.use_pi_pulse else 'two'} qubit pulses "
                f"already span {total_pulse_span_us:.4f} us "
                f"(4*sigma = {self.pulse_us:.4f} us each). The parity phase "
                f"condition is unreachable. At sigma={cfg['sigma']} us the "
                f"largest usable peak separation is df < {df_max:.4f} MHz; "
                f"either shorten cfg['sigma'] (df_max scales as 1/(8*sigma)) or "
                "cap the accepted doublet separation via "
                "ModifiedRamsey_params['max_sep_MHz']."
            )
        self.wait_us = wait_us
        self.wait_cycles = self.us2cycles(wait_us)
        self.effective_tau_us = float(n_gaps * (self.cycles2us(self.wait_cycles) + self.pulse_us))
        self.regwi(self.q_rp, self.r_wait, self.wait_cycles)

        # Drive-bandwidth gate: docs/experiments/modified_ramsey.md (Drive bandwidth).
        rabi_pi2_mhz = 0.0997 / cfg["sigma"]
        branch_upper = float(cfg["f_ge"])
        branch_lower = branch_upper - float(cfg["df"])
        branch_detuning_mhz = max(
            abs(self.drive_freq_mhz - branch_upper), abs(self.drive_freq_mhz - branch_lower)
        )
        self.drive_bandwidth_ratio = float(branch_detuning_mhz / rabi_pi2_mhz)
        max_bw_ratio = float(cfg.get("max_drive_bandwidth_ratio", 1.0))
        if self.drive_bandwidth_ratio > max_bw_ratio:
            raise ValueError(
                f"branch detuning {branch_detuning_mhz:.4f} MHz is "
                f"{self.drive_bandwidth_ratio:.2f}x the pi/2 Rabi rate "
                f"({rabi_pi2_mhz:.4f} MHz at sigma={cfg['sigma']} us), above "
                f"the max_drive_bandwidth_ratio={max_bw_ratio:g} limit: the "
                "off-resonant parity branch cannot be rotated and the "
                "parity -> state mapping is unrealizable. Shorten sigma"
                + (
                    ""
                    if self.symmetric_ramsey
                    else ", set symmetric_ramsey=True (halves the detuning),"
                )
                + " or raise cfg['max_drive_bandwidth_ratio'] deliberately."
            )
        if self.drive_bandwidth_ratio > 0.2:
            print(
                f"[ModifiedRamsey] WARNING: branch detuning "
                f"{branch_detuning_mhz:.4f} MHz is {self.drive_bandwidth_ratio:.2f}x "
                f"the pi/2 Rabi rate ({rabi_pi2_mhz:.4f} MHz at sigma="
                f"{cfg['sigma']} us). The off-resonant branch will be "
                "under-rotated. Shorten sigma or set symmetric_ramsey=True."
            )

        # One envelope shared by pi and pi/2: two copies can overflow the 65536-sample
        # envelope memory (docs/architecture.md#generators-and-registers).
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        self.load_reset_threshold()

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        cfg = self.cfg

        if self.use_active_reset:
            self.active_reset_to_g()

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=0,
            gain=cfg["pi2_gain"],
            waveform="qubit",
        )
        self.pulse(ch=cfg["qubit_ch"])

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.use_pi_pulse:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge_reg,
                phase=0,
                gain=cfg["pi_gain"],
                waveform="qubit",
            )
            self.pulse(ch=cfg["qubit_ch"])

            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=self.f_ge_reg,
            phase=self.deg2reg(self.final_pi2_phase_deg, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_gain"],
            waveform="qubit",
        )
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # mr_relax_delay, not the shared relax_delay (docs/experiments/modified_ramsey.md).
        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(cfg.get("mr_relax_delay", 0.0)),
        )

    def acquire(
        self,
        soc,
        threshold=None,
        angle=None,
        load_pulses=True,
        readouts_per_experiment=None,
        save_experiments=None,
        start_src="internal",
        progress=False,
    ):
        self.reads_per_rep = self.reset_cycles + 1
        if readouts_per_experiment is not None and readouts_per_experiment != self.reads_per_rep:
            raise ValueError(
                "readouts_per_experiment must equal reset_cycles + 1 "
                f"({self.reads_per_rep}) for ModifiedRamseyProgram"
            )
        super().acquire(
            soc,
            readouts_per_experiment=self.reads_per_rep,
            load_pulses=load_pulses,
            start_src=start_src,
            progress=progress,
            threshold=threshold,
            angle=angle,
            save_experiments=save_experiments,
        )
        return self.collect_shots()

    def collect_shots(self):
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", 1)
        # Read ii of each rep is di_buf[ch][ii::reads_per_rep]; the Ramsey read is last.
        final = reads_per_rep - 1
        shots_i = self.di_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        shots_q = self.dq_buf[0][final::reads_per_rep].reshape((1, self.cfg["reps"])) / norm
        return shots_i, shots_q

    def collect_reset_shots(self):
        """Reset readouts as (reset_cycles, reps) I and Q in collect_shots() units; row k
        precedes flip k (docs/experiments/active_reset.md#reset-readout-k-is-taken-before-flip-k)."""
        n_cycles = self.reset_cycles
        reps = self.cfg["reps"]
        if not n_cycles:
            return (np.zeros((0, reps)), np.zeros((0, reps)))
        ro_ch = self.cfg["ro_chs"][0]
        norm = self.us2cycles(self.cfg["readout_length"], ro_ch=ro_ch)
        reads_per_rep = getattr(self, "reads_per_rep", n_cycles + 1)
        reset_i = np.stack(
            [self.di_buf[0][k::reads_per_rep][:reps] / norm for k in range(n_cycles)]
        )
        reset_q = np.stack(
            [self.dq_buf[0][k::reads_per_rep][:reps] / norm for k in range(n_cycles)]
        )
        return reset_i, reset_q


class ModifiedRamsey(ExperimentClass):
    """Repeated fixed-tau Ramsey record for charge-parity switching time series."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, debug=False):
        prog = ModifiedRamseyProgram(self.soccfg, self.cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True, progress=progress)

        shots_i = np.asarray(shots_i).ravel()
        shots_q = np.asarray(shots_q).ravel()
        reset_i, reset_q = prog.collect_reset_shots()

        # Streamer stats include polling/transfer latency: diagnostics only.
        streamer_elapsed_s = np.nan
        streamer_average_rep_period_us = np.nan
        if prog.stats:
            last_elapsed_s, last_shots, _, _ = prog.stats[-1]
            streamer_elapsed_s = float(last_elapsed_s)
            if last_shots:
                streamer_average_rep_period_us = streamer_elapsed_s * 1e6 / float(last_shots)

        # The time base is the emitted schedule, active-reset overhead included.
        rep_period_us = float(prog.scheduled_rep_period_us())
        n_shots = shots_i.size
        shot_index = np.arange(n_shots)
        shot_time_us = shot_index * rep_period_us

        ro_ch = self.cfg["ro_chs"][0]
        readout_window_us = float(
            prog.readout_window_cycles[ro_ch] / float(self.soccfg["readouts"][ro_ch]["f_output"])
        )
        symmetric = self.cfg.get("symmetric_ramsey", False)
        use_reset = self.cfg.get("use_active_reset", False)
        control_type = self.cfg.get("mr_control_type", "parity")

        data = {
            "config": self.cfg,
            "data": {
                "shots_i": shots_i,
                "shots_q": shots_q,
                "shot_index": shot_index,
                "shot_time_us": shot_time_us,
                "scheduled_rep_period_us": rep_period_us,
                "gap_indices": np.zeros(0, dtype=int),
                "tau_us": float(prog.tau_us),
                "effective_tau_us": float(prog.effective_tau_us),
                "wait_us": float(prog.wait_us),
                "qubit_pulse_us": float(prog.pulse_us),
                "sigma_us": float(self.cfg["sigma"]),
                "drive_bandwidth_ratio": float(prog.drive_bandwidth_ratio),
                "f_ge": self.cfg["f_ge"],
                "f_branch_upper": self.cfg["f_ge"],
                "f_branch_lower": self.cfg["f_ge"] - self.cfg["df"],
                "df": self.cfg["df"],
                "drive_freq": float(prog.drive_freq_mhz),
                "pi2_gain": self.cfg["pi2_gain"],
                "pi_gain": self.cfg.get("pi_gain", np.nan),
                "first_pi2_phase_deg": 0.0,
                "final_pi2_phase_deg": float(prog.final_pi2_phase_deg),
                "use_pi_pulse": self.cfg.get("use_pi_pulse", False),
                "flip_final_pi2": self.cfg.get("flip_final_pi2", False),
                "symmetric_ramsey": symmetric,
                "mr_control_type_code": MR_CONTROL_TYPE_CODES.get(control_type, -1),
                "read_pulse_freq": self.cfg["pulse_freq"],
                "read_pulse_gain": self.cfg["pulse_gain"],
                "res_phase": self.cfg["res_phase"],
                "readout_length_us": self.cfg["readout_length"],
                "readout_window_us": readout_window_us,
                "adc_trig_offset_us": self.cfg["adc_trig_offset"],
                "mr_relax_delay_us": self.cfg.get("mr_relax_delay", 0.0),
                "use_active_reset": use_reset,
                "reset_cycles": (int(self.cfg.get("reset_cycles", 1)) if use_reset else 0),
                "reset_shots_i": reset_i,
                "reset_shots_q": reset_q,
                "readout_threshold": self.cfg.get("readout_threshold", np.nan)
                if use_reset
                else np.nan,
                "reset_ground_below_threshold": self.cfg.get("reset_ground_below_threshold", True),
                "reset_readout_relax_delay_us": self.cfg.get("reset_readout_relax_delay", 1.0)
                if use_reset
                else 0.0,
                "post_reset_wait_us": self.cfg.get("post_reset_wait", 0.0) if use_reset else 0.0,
                "streamer_elapsed_s": streamer_elapsed_s,
                "streamer_average_rep_period_us": streamer_average_rep_period_us,
            },
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        shots_i = np.asarray(data["data"]["shots_i"])
        shots_q = np.asarray(data["data"]["shots_q"])
        tau_us = data["data"]["tau_us"]
        eff_tau_us = data["data"].get("effective_tau_us", tau_us)
        wait_us = data["data"]["wait_us"]
        df = data["data"]["df"]
        use_pi_pulse = data["data"].get("use_pi_pulse", False)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        seq_label = "echo pi" if use_pi_pulse else "no pi"

        fig = plt.figure(figNum)
        plt.plot(shots_i, shots_q, ".", alpha=0.4, markersize=3)
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis("equal")
        plt.title(
            self.titlename
            + f"\n{seq_label}, tau={tau_us:.4f} us (realized {eff_tau_us:.4f} us),"
            + f" gap={wait_us:.4f} us, df={df:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "_IQ.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


def modified_ramsey_timing(soccfg, cfg):
    """Model of ModifiedRamseyProgram's per-rep schedule (excludes initialize(), tProc
    latency, transfer and Python overhead); docs/experiments/modified_ramsey.md#timing-ledger."""
    res_ch = cfg["res_ch"]
    qubit_ch = cfg["qubit_ch"]
    ro_chs = cfg["ro_chs"]

    if not ro_chs:
        raise ValueError("cfg['ro_chs'] must contain at least one readout channel")
    if cfg["df"] <= 0:
        raise ValueError("cfg['df'] must be positive")
    if cfg["sigma"] <= 0:
        raise ValueError("cfg['sigma'] must be positive")
    if cfg["readout_length"] <= 0:
        raise ValueError("cfg['readout_length'] must be positive")
    delay_keys = ["adc_trig_offset", "mr_relax_delay"]
    if cfg.get("use_active_reset", False):
        delay_keys.extend(["reset_readout_relax_delay", "post_reset_wait"])
    for delay_key in delay_keys:
        if cfg.get(delay_key, 0.0) < 0:
            raise ValueError(f"cfg['{delay_key}'] must be non-negative")

    f_time = float(soccfg["tprocs"][0]["f_time"])
    res_f_fabric = float(soccfg["gens"][res_ch]["f_fabric"])
    qubit_f_fabric = float(soccfg["gens"][qubit_ch]["f_fabric"])

    # Native cycles -> tProc cycles, truncated by sync_all() (docs/architecture.md#timing).
    requested_tone_native_cycles = soccfg.us2cycles(cfg["length"], gen_ch=res_ch)
    adc_offset_tproc_cycles = soccfg.us2cycles(cfg["adc_trig_offset"])
    window_native_cycles_by_ch = {
        int(ch): soccfg.us2cycles(cfg["readout_length"], ro_ch=ch) for ch in ro_chs
    }
    adc_end_tproc_by_ch = {
        int(ch): (
            adc_offset_tproc_cycles
            + window_native_cycles_by_ch[int(ch)]
            * f_time
            / float(soccfg["readouts"][ch]["f_output"])
        )
        for ch in ro_chs
    }
    adc_window_end_tproc = max(adc_end_tproc_by_ch.values())
    required_tone_native_cycles = int(np.ceil(adc_window_end_tproc * res_f_fabric / f_time - 1e-12))
    tone_native_cycles = max(requested_tone_native_cycles, required_tone_native_cycles)
    tone_extension_native_cycles = tone_native_cycles - requested_tone_native_cycles
    tone_end_tproc = tone_native_cycles * f_time / res_f_fabric
    readout_slot_tproc_cycles = int(max(tone_end_tproc, adc_window_end_tproc))

    qubit_native_cycles = soccfg.us2cycles(cfg["sigma"] * 4, gen_ch=qubit_ch)
    qubit_end_tproc = qubit_native_cycles * f_time / qubit_f_fabric
    qubit_pulse_tproc_cycles = int(qubit_end_tproc)
    use_pi_pulse = bool(cfg.get("use_pi_pulse", False))
    ramsey_pulse_count = 3 if use_pi_pulse else 2
    # Centre-to-centre tau, edge-to-edge gap: gap = tau/n_gaps - 4*sigma.
    tau_us = float(cfg.get("ramsey_tau_us", 1.0 / (2.0 * cfg["df"])))
    qubit_pulse_us = float(qubit_native_cycles / qubit_f_fabric)
    wait_count = 2 if use_pi_pulse else 1
    wait_request_us = tau_us / wait_count - qubit_pulse_us
    if wait_request_us <= 0:
        raise ValueError(
            f"cfg['df']={cfg['df']} MHz needs tau={tau_us:.4f} us, but the "
            f"qubit pulses span {wait_count * qubit_pulse_us:.4f} us "
            f"(4*sigma = {qubit_pulse_us:.4f} us each). Shorten cfg['sigma'] "
            "or work at a smaller peak separation."
        )
    wait_cycles_each = soccfg.us2cycles(wait_request_us)
    wait_tproc_cycles = wait_count * wait_cycles_each
    effective_tau_us = float(wait_count * (wait_cycles_each / f_time + qubit_pulse_us))
    final_padding_tproc_cycles = soccfg.us2cycles(0.05)
    mr_relax_tproc_cycles = soccfg.us2cycles(cfg.get("mr_relax_delay", 0.0))

    reset_cycles = int(cfg.get("reset_cycles", 1)) if cfg.get("use_active_reset", False) else 0
    if reset_cycles < 0:
        raise ValueError("cfg['reset_cycles'] must be non-negative")
    reset_delay_tproc_cycles = (
        soccfg.us2cycles(cfg.get("reset_readout_relax_delay", 1.0)) if reset_cycles else 0
    )
    post_reset_wait_tproc_cycles = (
        soccfg.us2cycles(cfg.get("post_reset_wait", 0.0)) if reset_cycles else 0
    )

    ramsey_sequence_tproc_cycles = (
        ramsey_pulse_count * qubit_pulse_tproc_cycles
        + wait_tproc_cycles
        + final_padding_tproc_cycles
        + readout_slot_tproc_cycles
        + mr_relax_tproc_cycles
    )
    reset_block_tproc_cycles = (
        # The conditional pi is reserved on both branches (docs/experiments/active_reset.md).
        reset_cycles
        * (readout_slot_tproc_cycles + reset_delay_tproc_cycles + qubit_pulse_tproc_cycles)
        + post_reset_wait_tproc_cycles
    )
    scheduled_rep_period_tproc_cycles = ramsey_sequence_tproc_cycles + reset_block_tproc_cycles

    to_us = lambda cycles: float(cycles / f_time)
    tone_us = float(tone_end_tproc / f_time)
    adc_offset_us = to_us(adc_offset_tproc_cycles)
    window_us_by_ch = {
        int(ch): float(
            window_native_cycles_by_ch[int(ch)] / float(soccfg["readouts"][ch]["f_output"])
        )
        for ch in ro_chs
    }

    return {
        "scheduled_rep_period_us": to_us(scheduled_rep_period_tproc_cycles),
        "scheduled_rep_period_tproc_cycles": int(scheduled_rep_period_tproc_cycles),
        "ramsey_sequence_us": to_us(ramsey_sequence_tproc_cycles),
        "reset_block_us": to_us(reset_block_tproc_cycles),
        "readout_slot_us": to_us(readout_slot_tproc_cycles),
        "readout_slot_tproc_cycles": int(readout_slot_tproc_cycles),
        "resonator_tone_us": tone_us,
        "requested_resonator_tone_us": float(requested_tone_native_cycles / res_f_fabric),
        "tone_quantization_extension_cycles": int(tone_extension_native_cycles),
        "adc_offset_us": adc_offset_us,
        "max_readout_window_us": float(max(window_us_by_ch.values())),
        "tone_coverage_margin_us": float((tone_end_tproc - adc_window_end_tproc) / f_time),
        "qubit_pulse_us": to_us(qubit_pulse_tproc_cycles),
        "ramsey_qubit_pulse_count": int(ramsey_pulse_count),
        "ramsey_wait_us": to_us(wait_tproc_cycles),
        "requested_tau_us": float(tau_us),
        "effective_tau_us": effective_tau_us,
        "ramsey_gap_per_wait_us": float(wait_cycles_each / f_time),
        "final_padding_us": to_us(final_padding_tproc_cycles),
        "mr_relax_delay_us": to_us(mr_relax_tproc_cycles),
        "reset_cycles": int(reset_cycles),
        "reset_readout_relax_delay_us": to_us(reset_delay_tproc_cycles),
        "post_reset_wait_us": to_us(post_reset_wait_tproc_cycles),
        "f_time_mhz": f_time,
        "res_f_fabric_mhz": res_f_fabric,
        "qubit_f_fabric_mhz": qubit_f_fabric,
        "ro_f_output_mhz": {int(ch): float(soccfg["readouts"][ch]["f_output"]) for ch in ro_chs},
    }
