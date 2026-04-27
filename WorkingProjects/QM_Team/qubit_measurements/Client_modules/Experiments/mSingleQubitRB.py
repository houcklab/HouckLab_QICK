from qick import *
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


# ============================================================
# Clifford library
# We represent each Clifford by:
#   - a short pulse decomposition in terms of X/Y pi and pi/2 pulses
#   - a 2x2 unitary used only in software to compute the recovery gate
# ============================================================

I2 = np.eye(2, dtype=complex)

sx = np.array([[0, 1], [1, 0]], dtype=complex)
sy = np.array([[0, -1j], [1j, 0]], dtype=complex)
sz = np.array([[1, 0], [0, -1]], dtype=complex)


def rot(axis, theta):
    """Single-qubit rotation exp(-i theta/2 sigma_axis)."""
    if axis == "X":
        s = sx
    elif axis == "Y":
        s = sy
    elif axis == "Z":
        s = sz
    else:
        raise ValueError(f"Unknown axis {axis}")
    return np.cos(theta / 2) * I2 - 1j * np.sin(theta / 2) * s


# primitive pulse names that the QICK program will understand
# X90, Xm90, X180, Y90, Ym90, Y180
CLIFFORDS = [
    {"name": "I",          "pulses": [],                    "U": I2},
    {"name": "X90",        "pulses": ["X90"],              "U": rot("X", np.pi/2)},
    {"name": "Xm90",       "pulses": ["Xm90"],             "U": rot("X", -np.pi/2)},

    {"name": "X180",       "pulses": ["X180"],             "U": rot("X", np.pi)},
    {"name": "Y90",        "pulses": ["Y90"],              "U": rot("Y", np.pi/2)},
    {"name": "Ym90",       "pulses": ["Ym90"],             "U": rot("Y", -np.pi/2)},
    {"name": "Y180",       "pulses": ["Y180"],             "U": rot("Y", np.pi)},

    {"name": "X90_Y90",    "pulses": ["X90", "Y90"],       "U": rot("Y", np.pi/2) @ rot("X", np.pi/2)},
    {"name": "X90_Ym90",   "pulses": ["X90", "Ym90"],      "U": rot("Y", -np.pi/2) @ rot("X", np.pi/2)},
    {"name": "Xm90_Y90",   "pulses": ["Xm90", "Y90"],      "U": rot("Y", np.pi/2) @ rot("X", -np.pi/2)},
    {"name": "Xm90_Ym90",  "pulses": ["Xm90", "Ym90"],     "U": rot("Y", -np.pi/2) @ rot("X", -np.pi/2)},

    {"name": "Y90_X90",    "pulses": ["Y90", "X90"],       "U": rot("X", np.pi/2) @ rot("Y", np.pi/2)},
    {"name": "Y90_Xm90",   "pulses": ["Y90", "Xm90"],      "U": rot("X", -np.pi/2) @ rot("Y", np.pi/2)},
    {"name": "Ym90_X90",   "pulses": ["Ym90", "X90"],      "U": rot("X", np.pi/2) @ rot("Y", -np.pi/2)},
    {"name": "Ym90_Xm90",  "pulses": ["Ym90", "Xm90"],     "U": rot("X", -np.pi/2) @ rot("Y", -np.pi/2)},

    {"name": "X180_Y90",   "pulses": ["X180", "Y90"],      "U": rot("Y", np.pi/2) @ rot("X", np.pi)},
    {"name": "X180_Ym90",  "pulses": ["X180", "Ym90"],     "U": rot("Y", -np.pi/2) @ rot("X", np.pi)},
    {"name": "Y180_X90",   "pulses": ["Y180", "X90"],      "U": rot("X", np.pi/2) @ rot("Y", np.pi)},
    {"name": "Y180_Xm90",  "pulses": ["Y180", "Xm90"],     "U": rot("X", -np.pi/2) @ rot("Y", np.pi)},

    {"name": "X90_Y180", "pulses": ["X90", "Y180"], "U": rot("Y", np.pi) @ rot("X", np.pi / 2)},
    {"name": "Xm90_Y180", "pulses": ["Xm90", "Y180"], "U": rot("Y", np.pi) @ rot("X", -np.pi / 2)},
    {"name": "Y90_X180", "pulses": ["Y90", "X180"], "U": rot("X", np.pi) @ rot("Y", np.pi / 2)},
    {"name": "Ym90_X180", "pulses": ["Ym90", "X180"], "U": rot("X", np.pi) @ rot("Y", -np.pi / 2)},
    {"name": "X180_Y180", "pulses": ["X180", "Y180"], "U": rot("Y", np.pi) @ rot("X", np.pi)},
]

# keep exactly 24
assert len(CLIFFORDS) == 24


def unitary_equal_up_to_phase(U, V, atol=1e-8):
    """Check U == exp(i phi) V."""
    a = U.flatten()
    b = V.flatten()
    idx = np.argmax(np.abs(b))
    if np.abs(b[idx]) < atol:
        return False
    phase = a[idx] / b[idx]
    return np.allclose(U, phase * V, atol=atol)


def find_recovery_clifford(U_total):
    """Find Clifford C such that C @ U_total = I up to global phase."""
    U_target = np.linalg.inv(U_total)
    for k, cliff in enumerate(CLIFFORDS):
        if unitary_equal_up_to_phase(cliff["U"], U_target):
            return k
    raise RuntimeError("Could not find recovery Clifford in 24-element library.")


def generate_rb_sequence(m, rng):
    """Generate m random Cliffords + recovery."""
    seq = rng.integers(0, len(CLIFFORDS), size=m).tolist()

    U_total = I2.copy()
    for idx in seq:
        U_total = CLIFFORDS[idx]["U"] @ U_total

    rec_idx = find_recovery_clifford(U_total)
    return seq + [rec_idx]


# ============================================================
# QICK program
# ============================================================

class SingleQubitRBProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        self.f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        # readout pulse
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"])
        )

        # qubit waveform
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4
        if cfg["flattop_length"] is not None:
            trig_length += cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.2))

    def play_primitive(self, gate_name):
        cfg = self.cfg

        phase_deg = {
            "X90": 0,
            "Xm90": 180,
            "X180": 0,
            "Y90": 90,
            "Ym90": -90,
            "Y180": 90,
        }[gate_name]

        gain = {
            "X90": cfg["pi2_gain"],
            "Xm90": cfg["pi2_gain"],
            "Y90": cfg["pi2_gain"],
            "Ym90": cfg["pi2_gain"],
            "X180": cfg["pi_gain"],
            "Y180": cfg["pi_gain"],
        }[gate_name]

        self.trigger(
            pins=[0],
            t=self.us2cycles(0.01 + cfg["trig_delay"] - cfg["trig_buffer_start"]),
            width=self.trig_length
        )

        if cfg["flattop_length"] is not None:
            flattop_length = self.us2cycles(cfg["flattop_length"], gen_ch=cfg["qubit_ch"])
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style='flat_top',
                freq=self.f_ge,
                phase=self.deg2reg(phase_deg, gen_ch=cfg["qubit_ch"]),
                gain=gain,
                waveform="qubit",
                length=flattop_length,
                t=self.us2cycles(0.01)
            )
        else:
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_ge,
                phase=self.deg2reg(phase_deg, gen_ch=cfg["qubit_ch"]),
                gain=gain,
                waveform="qubit",
                t=self.us2cycles(0.01)
            )

        self.sync_all(self.us2cycles(0.02))

    def body(self):
        # sequence is passed in cfg["rb_pulses"] as a flat list of primitive pulse names
        for gate_name in self.cfg["rb_pulses"]:
            self.play_primitive(gate_name)

        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"])
        )


# ============================================================
# Experiment wrapper
# ============================================================

class SingleQubitRB(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        cfg = self.cfg

        lengths = np.asarray(cfg["rb_lengths"], dtype=int)
        nseeds = int(cfg["rb_nseeds"])
        seed0 = int(cfg.get("rb_seed", 0))

        avgi_mat = np.zeros((nseeds, len(lengths)))
        avgq_mat = np.zeros((nseeds, len(lengths)))

        for i_seed in range(nseeds):
            rng = np.random.default_rng(seed0 + i_seed)

            for i_m, m in enumerate(lengths):
                clifford_seq = generate_rb_sequence(m, rng)

                # flatten Clifford list into primitive pulse names
                rb_pulses = []
                for idx in clifford_seq:
                    rb_pulses.extend(CLIFFORDS[idx]["pulses"])

                run_cfg = dict(cfg)
                run_cfg["rb_pulses"] = rb_pulses

                prog = SingleQubitRBProgram(self.soccfg, run_cfg)
                avg_di, avg_dq = prog.acquire(
                    self.soc,
                    threshold=None,
                    angle=None,
                    load_pulses=True,
                    readouts_per_experiment=1,
                    save_experiments=None,
                    start_src="internal",
                    progress=False
                )

                avgi_mat[i_seed, i_m] = avg_di[0][0]
                avgq_mat[i_seed, i_m] = avg_dq[0][0]

        avgi = np.mean(avgi_mat, axis=0)
        avgq = np.mean(avgq_mat, axis=0)

        data = {
            "config": cfg,
            "data": {
                "lengths": lengths,
                "avgi_seeds": avgi_mat,
                "avgq_seeds": avgq_mat,
                "avgi": avgi,
                "avgq": avgq,
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        m = np.asarray(data["data"]["lengths"])
        avgi = np.asarray(data["data"]["avgi"])
        avgq = np.asarray(data["data"]["avgq"])

        # crude survival metric: rotate IQ so signal is mostly in I, then normalize
        z = avgi + 1j * avgq
        phases = np.linspace(0, np.pi, 200)
        z_rot = np.array([z * np.exp(1j * ph) for ph in phases])
        best_idx = np.argmin(np.ptp(z_rot.imag, axis=1))
        s = z_rot[best_idx].real

        def rb_fit(x, A, p, B):
            return A * (p ** x) + B

        A0 = s[0] - s[-1]
        B0 = s[-1]
        p0 = 0.99
        popt, _ = curve_fit(rb_fit, m, s, p0=[A0, p0, B0], maxfev=20000)
        fit_y = rb_fit(m, *popt)

        A_fit, p_fit, B_fit = popt
        r_cliff = (1 - p_fit) / 2

        while plt.fignum_exists(figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(m, s, 'o', label="RB data")
        plt.plot(m, fit_y, '-', label=f"fit: p={p_fit:.6f}, r_C={r_cliff:.3e}")
        plt.xlabel("Number of Cliffords")
        plt.ylabel("Survival signal (rotated I)")
        plt.title(self.titlename)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname)

        print(f"RB fit p = {p_fit:.6f}")
        print(f"Estimated Clifford error r_C = {(1 - p_fit)/2:.3e}")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])