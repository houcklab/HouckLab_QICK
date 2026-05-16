from qick import *
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import (
    SingleShotProgramFFMUX,
)
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.rotate_SS_data import (
    count_percentage,
    rotate_data,
)


I2 = np.eye(2, dtype=complex)
SX = np.array([[0, 1], [1, 0]], dtype=complex)
SY = np.array([[0, -1j], [1j, 0]], dtype=complex)
SZ = np.array([[1, 0], [0, -1]], dtype=complex)


def _rotation(axis, theta):
    if axis == "X":
        sigma = SX
    elif axis == "Y":
        sigma = SY
    elif axis == "Z":
        sigma = SZ
    else:
        raise ValueError(f"Unknown axis {axis}.")
    return np.cos(theta / 2.0) * I2 - 1j * np.sin(theta / 2.0) * sigma


PRIMITIVE_UNITARIES = {
    "X90": _rotation("X", np.pi / 2.0),
    "Xm90": _rotation("X", -np.pi / 2.0),
    "Y90": _rotation("Y", np.pi / 2.0),
    "Ym90": _rotation("Y", -np.pi / 2.0),
}


CLIFFORD_LIBRARY = (
    {"name": "I", "pulses": ()},
    {"name": "X180", "pulses": ("X90", "X90")},
    {"name": "Y180", "pulses": ("Y90", "Y90")},
    {"name": "Y180_X180", "pulses": ("Y90", "Y90", "X90", "X90")},
    {"name": "X90_Y90", "pulses": ("X90", "Y90")},
    {"name": "X90_Ym90", "pulses": ("X90", "Ym90")},
    {"name": "Xm90_Y90", "pulses": ("Xm90", "Y90")},
    {"name": "Xm90_Ym90", "pulses": ("Xm90", "Ym90")},
    {"name": "Y90_X90", "pulses": ("Y90", "X90")},
    {"name": "Y90_Xm90", "pulses": ("Y90", "Xm90")},
    {"name": "Ym90_X90", "pulses": ("Ym90", "X90")},
    {"name": "Ym90_Xm90", "pulses": ("Ym90", "Xm90")},
    {"name": "X90", "pulses": ("X90",)},
    {"name": "Xm90", "pulses": ("Xm90",)},
    {"name": "Y90", "pulses": ("Y90",)},
    {"name": "Ym90", "pulses": ("Ym90",)},
    {"name": "Xm90_Y90_X90", "pulses": ("Xm90", "Y90", "X90")},
    {"name": "Xm90_Ym90_X90", "pulses": ("Xm90", "Ym90", "X90")},
    {"name": "X180_Y90", "pulses": ("X90", "X90", "Y90")},
    {"name": "X180_Ym90", "pulses": ("X90", "X90", "Ym90")},
    {"name": "Y180_X90", "pulses": ("Y90", "Y90", "X90")},
    {"name": "Y180_Xm90", "pulses": ("Y90", "Y90", "Xm90")},
    {"name": "X90_Y90_X90", "pulses": ("X90", "Y90", "X90")},
    {"name": "Xm90_Y90_Xm90", "pulses": ("Xm90", "Y90", "Xm90")},
)


def _compose_pulses(pulses):
    unitary = I2.copy()
    for pulse in pulses:
        unitary = PRIMITIVE_UNITARIES[pulse] @ unitary
    return unitary


for clifford in CLIFFORD_LIBRARY:
    clifford["U"] = _compose_pulses(clifford["pulses"])


def _equal_up_to_global_phase(lhs, rhs, atol=1e-8):
    lhs_flat = lhs.flatten()
    rhs_flat = rhs.flatten()
    idx = int(np.argmax(np.abs(rhs_flat)))
    if np.abs(rhs_flat[idx]) < atol:
        return False
    phase = lhs_flat[idx] / rhs_flat[idx]
    return np.allclose(lhs, phase * rhs, atol=atol)


def _build_clifford_tables():
    n_cliffords = len(CLIFFORD_LIBRARY)
    cayley = np.zeros((n_cliffords, n_cliffords), dtype=int)

    for current_idx, current_clifford in enumerate(CLIFFORD_LIBRARY):
        for step_idx, step_clifford in enumerate(CLIFFORD_LIBRARY):
            target_unitary = step_clifford["U"] @ current_clifford["U"]
            for out_idx, out_clifford in enumerate(CLIFFORD_LIBRARY):
                if _equal_up_to_global_phase(out_clifford["U"], target_unitary):
                    cayley[current_idx, step_idx] = out_idx
                    break
            else:
                raise RuntimeError(
                    f"Could not close the Clifford group for current={current_idx}, step={step_idx}."
                )

    inv_gates = np.zeros(n_cliffords, dtype=int)
    for current_idx in range(n_cliffords):
        zero_hits = np.where(cayley[current_idx, :] == 0)[0]
        if len(zero_hits) != 1:
            raise RuntimeError(f"Could not find a unique recovery gate for Clifford {current_idx}.")
        inv_gates[current_idx] = int(zero_hits[0])

    return cayley, inv_gates


CAYLEY_TABLE, INVERSE_GATES = _build_clifford_tables()
LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD = float(
    np.mean([len(clifford["pulses"]) for clifford in CLIFFORD_LIBRARY])
)


def generate_rb_prefix_sequence(lengths, rng):
    lengths = np.asarray(lengths, dtype=int)
    if np.any(lengths < 0):
        raise ValueError("RB lengths must be non-negative.")

    max_length = int(np.max(lengths)) if len(lengths) else 0
    random_steps = rng.integers(0, len(CLIFFORD_LIBRARY), size=max_length, dtype=int)

    prefix_inverse = np.zeros(max_length, dtype=int)
    current_state = 0
    for idx, step in enumerate(random_steps):
        current_state = int(CAYLEY_TABLE[current_state, int(step)])
        prefix_inverse[idx] = int(INVERSE_GATES[current_state])

    sequences = []
    for depth in lengths:
        if depth == 0:
            sequences.append(np.asarray([0], dtype=int))
        else:
            seq = np.empty(depth + 1, dtype=int)
            seq[:depth] = random_steps[:depth]
            seq[depth] = prefix_inverse[depth - 1]
            sequences.append(seq)
    return sequences


def clifford_sequence_to_pulses(clifford_sequence):
    rb_pulses = []
    for clifford_idx in clifford_sequence:
        rb_pulses.extend(CLIFFORD_LIBRARY[int(clifford_idx)]["pulses"])
    return rb_pulses


def rotate_iq_to_i(avgi, avgq, phase_num_points=400):
    signal = np.asarray(avgi, dtype=float) + 1j * np.asarray(avgq, dtype=float)
    phase_values = np.linspace(0.0, np.pi, phase_num_points)
    rotated = np.asarray([signal * np.exp(1j * phase) for phase in phase_values])
    q_span = np.ptp(rotated.imag, axis=1)
    phase_idx = int(np.argmin(q_span))
    rotation_angle = float(phase_values[phase_idx])
    return signal * np.exp(1j * rotation_angle), rotation_angle


def rb_fit_func(x, a, p, b):
    return a * (p ** x) + b


class SingleQubitRBProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg.get("mixer_freq", 0.0),
            ro_ch=cfg["ro_chs"][0],
        )
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=self.f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4.0, gen_ch=cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length,
        )

        self.flattop_cycles = None
        if cfg["flattop_length"] is not None:
            self.flattop_cycles = self.us2cycles(cfg["flattop_length"], gen_ch=cfg["qubit_ch"])

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4.0
        if cfg["flattop_length"] is not None:
            trig_length += cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)
        self.gate_spacing_cycles = self.us2cycles(cfg.get("rb_gate_spacing", 0.02))

        self.sync_all(self.us2cycles(0.2))

    def play_primitive(self, gate_name):
        cfg = self.cfg

        phase_deg = {
            "X90": 0.0,
            "Xm90": 180.0,
            "Y90": 90.0,
            "Ym90": -90.0,
        }[gate_name]

        gain = cfg["pi2_gain"]

        self.trigger(
            pins=[0],
            t=self.us2cycles(0.01 + cfg["trig_delay"] - cfg["trig_buffer_start"]),
            width=self.trig_length,
        )

        if self.flattop_cycles is not None:
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=self.f_ge,
                phase=self.deg2reg(phase_deg, gen_ch=cfg["qubit_ch"]),
                gain=gain,
                waveform="qubit",
                length=self.flattop_cycles,
                t=self.us2cycles(0.01),
            )
        else:
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge,
                phase=self.deg2reg(phase_deg, gen_ch=cfg["qubit_ch"]),
                gain=gain,
                waveform="qubit",
                t=self.us2cycles(0.01),
            )

        self.sync_all(self.gate_spacing_cycles)

    def body(self):
        self.sync_all()

        for gate_name in self.cfg["rb_pulses"]:
            self.play_primitive(gate_name)

        self.sync_all(self.us2cycles(self.cfg.get("rb_post_sequence_delay", 0.05)))
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def acquire_shots(
        self,
        soc,
        threshold=None,
        angle=None,
        load_pulses=True,
        readouts_per_experiment=1,
        save_experiments=None,
        start_src="internal",
        progress=False,
    ):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg["readout_length"], ro_ch=0
        )
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg["readout_length"], ro_ch=0
        )
        return shots_i0, shots_q0


class SingleQubitRB(ExperimentClass):
    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="RB",
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
        cfg = self.cfg

        lengths = np.asarray(cfg["rb_lengths"], dtype=int)
        nseeds = int(cfg.get("rb_nseeds", 1))
        seed0 = int(cfg.get("rb_seed", 0))
        nrounds = int(cfg.get("rb_rounds", cfg.get("rounds", 1)))
        reps = int(cfg.get("rb_reps", cfg.get("reps", 1)))
        ss_shots = int(cfg.get("rb_single_shot_shots", reps))

        def run_classified_sequence(rb_pulses, ss_angle, ss_threshold):
            round_survival = np.zeros(nrounds, dtype=float)
            round_i = np.zeros(nrounds, dtype=float)
            round_q = np.zeros(nrounds, dtype=float)

            for i_round in range(nrounds):
                run_cfg = dict(cfg)
                run_cfg["reps"] = reps
                run_cfg["rounds"] = 1
                run_cfg["rb_pulses"] = list(rb_pulses)

                prog = SingleQubitRBProgram(self.soccfg, run_cfg)
                shots_i, shots_q = prog.acquire_shots(
                    self.soc,
                    threshold=None,
                    angle=None,
                    load_pulses=True,
                    readouts_per_experiment=1,
                    save_experiments=None,
                    start_src="internal",
                    progress=False,
                )

                rotated_iq = rotate_data((shots_i, shots_q), theta=ss_angle)
                excited_probability = float(count_percentage(rotated_iq, threshold=ss_threshold))
                round_survival[i_round] = 1.0 - excited_probability
                round_i[i_round] = float(np.mean(shots_i))
                round_q[i_round] = float(np.mean(shots_q))

            return np.mean(round_survival), np.mean(round_i), np.mean(round_q)

        avgi_mat = np.zeros((nseeds, len(lengths)), dtype=float)
        avgq_mat = np.zeros((nseeds, len(lengths)), dtype=float)
        survival_mat = np.zeros((nseeds, len(lengths)), dtype=float)
        primitive_counts = np.zeros((nseeds, len(lengths)), dtype=int)

        max_sequence_len = int(np.max(lengths) + 1) if len(lengths) else 1
        clifford_sequences = -np.ones((nseeds, len(lengths), max_sequence_len), dtype=int)

        ss_cfg = dict(cfg)
        ss_cfg["shots"] = ss_shots
        ss_cfg["number_of_pulses"] = int(cfg.get("rb_single_shot_number_of_pulses", 1))
        ss_cfg["qubit_gain"] = int(cfg["pi_gain"])
        ss_cfg["f_ge"] = cfg["f_ge"]
        ss_cfg["Read_Indeces"] = cfg.get("Read_Indeces", 0)

        ss_inst = SingleShotProgramFFMUX(
            path="RBSingleShotCal",
            cfg=ss_cfg,
            soc=self.soc,
            soccfg=self.soccfg,
            outerFolder=self.outerFolder,
            prefix=self.prefix,
        )
        ss_data = SingleShotProgramFFMUX.acquire(ss_inst)
        ss_threshold = float(np.asarray(ss_data["data"]["threshold"]).ravel()[0])
        ss_angle = float(np.asarray(ss_data["data"]["angle"]).ravel()[0])
        ss_fidelity = float(np.asarray(ss_inst.fid).ravel()[0]) if len(np.asarray(ss_inst.fid).ravel()) else np.nan
        if not np.isfinite(ss_threshold) or not np.isfinite(ss_angle):
            raise RuntimeError(
                f"Single-shot RB calibration failed: threshold={ss_threshold}, angle={ss_angle}"
            )

        for i_seed in range(nseeds):
            rng = np.random.default_rng(seed0 + i_seed)
            seed_sequences = generate_rb_prefix_sequence(lengths, rng)

            for i_depth, clifford_sequence in enumerate(seed_sequences):
                clifford_sequences[i_seed, i_depth, : len(clifford_sequence)] = clifford_sequence
                rb_pulses = clifford_sequence_to_pulses(clifford_sequence)
                primitive_counts[i_seed, i_depth] = len(rb_pulses)

                (
                    survival_mat[i_seed, i_depth],
                    avgi_mat[i_seed, i_depth],
                    avgq_mat[i_seed, i_depth],
                ) = run_classified_sequence(rb_pulses, ss_angle, ss_threshold)

        avgi = np.mean(avgi_mat, axis=0) if len(lengths) else np.asarray([])
        avgq = np.mean(avgq_mat, axis=0) if len(lengths) else np.asarray([])
        survival = np.mean(survival_mat, axis=0) if len(lengths) else np.asarray([])

        fit_success = False
        fit_popt = np.asarray([np.nan, np.nan, np.nan], dtype=float)
        fit_pcov = np.full((3, 3), np.nan, dtype=float)
        fit_y = np.full_like(survival, np.nan, dtype=float)
        p_clifford = np.nan
        p_clifford_err = np.nan
        clifford_error = np.nan
        clifford_fidelity = np.nan
        gate_fidelity = np.nan
        gate_fidelity_err = np.nan

        if len(lengths) >= 3:
            try:
                a_guess = float(survival[0] - survival[-1])
                b_guess = float(survival[-1])
                p_guess = float(cfg.get("rb_fit_p0", 0.99))

                fit_popt, fit_pcov = curve_fit(
                    rb_fit_func,
                    lengths,
                    survival,
                    p0=[a_guess, p_guess, b_guess],
                    bounds=([-np.inf, 0.0, -np.inf], [np.inf, 1.0, np.inf]),
                    maxfev=50000,
                )
                fit_success = True
                fit_y = rb_fit_func(lengths, *fit_popt)
                p_clifford = float(fit_popt[1])
                p_clifford_err = float(np.sqrt(max(fit_pcov[1, 1], 0.0)))
                clifford_error = 0.5 * (1.0 - p_clifford)
                clifford_fidelity = 1.0 - clifford_error

                gate_fidelity_scale = float(
                    cfg.get(
                        "rb_gate_fidelity_primitives_per_clifford",
                        LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD,
                    )
                )
                gate_fidelity = 1.0 - clifford_error / gate_fidelity_scale
                gate_fidelity_err = 0.5 * p_clifford_err / gate_fidelity_scale
            except Exception as err:
                print(f"RB fit failed: {err}")

        data = {
            "config": cfg,
            "data": {
                "lengths": lengths,
                "clifford_sequences": clifford_sequences,
                "primitive_counts": primitive_counts,
                "avgi_seeds": avgi_mat,
                "avgq_seeds": avgq_mat,
                "survival_seeds": survival_mat,
                "avgi": avgi,
                "avgq": avgq,
                "single_shot_shots": np.asarray(ss_shots),
                "single_shot_threshold": np.asarray(ss_threshold),
                "single_shot_angle": np.asarray(ss_angle),
                "single_shot_fidelity": np.asarray(ss_fidelity),
                "single_shot_i_g": np.asarray(ss_data["data"].get("i_g0", [])),
                "single_shot_q_g": np.asarray(ss_data["data"].get("q_g0", [])),
                "single_shot_i_e": np.asarray(ss_data["data"].get("i_e0", [])),
                "single_shot_q_e": np.asarray(ss_data["data"].get("q_e0", [])),
                "survival": survival,
                "fit_success": np.asarray(int(fit_success)),
                "fit_popt": fit_popt,
                "fit_pcov": fit_pcov,
                "fit_y": fit_y,
                "p_clifford": np.asarray(p_clifford),
                "p_clifford_err": np.asarray(p_clifford_err),
                "clifford_error": np.asarray(clifford_error),
                "clifford_fidelity": np.asarray(clifford_fidelity),
                "gate_fidelity": np.asarray(gate_fidelity),
                "gate_fidelity_err": np.asarray(gate_fidelity_err),
                "library_avg_primitives_per_clifford": np.asarray(
                    LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD
                ),
                "fit_gate_fidelity_primitives_per_clifford": np.asarray(
                    cfg.get(
                        "rb_gate_fidelity_primitives_per_clifford",
                        LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD,
                    )
                ),
            },
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        lengths = np.asarray(data["data"]["lengths"], dtype=float)
        survival = np.asarray(data["data"]["survival"], dtype=float)
        fit_success = bool(int(np.asarray(data["data"]["fit_success"]).item()))
        fit_y = np.asarray(data["data"]["fit_y"], dtype=float)
        p_clifford = float(np.asarray(data["data"]["p_clifford"]).item())
        clifford_error = float(np.asarray(data["data"]["clifford_error"]).item())
        gate_fidelity = float(np.asarray(data["data"]["gate_fidelity"]).item())
        gate_fidelity_err = float(np.asarray(data["data"]["gate_fidelity_err"]).item())
        survival_seeds = np.asarray(data["data"]["survival_seeds"], dtype=float)

        while plt.fignum_exists(figNum):
            figNum += 1

        fig = plt.figure(figNum)

        for seed_idx in range(survival_seeds.shape[0]):
            plt.plot(lengths, survival_seeds[seed_idx], color="lightgray", alpha=0.5, linewidth=1.0)

        plt.plot(lengths, survival, "o", color="tab:blue", label="RB survival")

        if fit_success:
            plt.plot(
                lengths,
                fit_y,
                "-",
                color="black",
                label=(
                    f"fit: p={p_clifford:.6f}, r_C={clifford_error:.3e}, "
                    f"F_gate={gate_fidelity:.6f} +/- {gate_fidelity_err:.6f}"
                ),
            )
        else:
            plt.plot([], [], " ", label="fit failed")

        plt.xlabel("Number of Cliffords")
        plt.ylabel("Ground-state survival probability")

        title = self.titlename
        if "Qubit_number" in self.cfg:
            title = f"Qubit: {self.cfg['Qubit_number']} ; {title}"
        plt.title(title)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname)

        if fit_success:
            print(f"RB fit p = {p_clifford:.6f}")
            print(f"Estimated Clifford error r_C = {clifford_error:.3e}")
            print(f"Estimated gate fidelity = {gate_fidelity:.6f} +/- {gate_fidelity_err:.6f}")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data

        if "Qubit_number" in self.cfg:
            self.fname = self.fname[:-3] + f"_Q{self.cfg['Qubit_number']}.h5"
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


RB = SingleQubitRB
RB1Q = SingleQubitRB
