"""
STEP 5: single-shot readout calibration -- QUA-identical behavior.

Port of Houck-Lab-Qua m_single_shot_1Q.py::SingleShot1Q.  The analyze() algorithm
is the EXACT QUA one (theta from blob MEDIANS via ss_helpers.find_blob_median,
the verbatim 100-threshold find_threshold sweep, thresh_0 = leftmost F >
confidence_threshold crossing, the ground<thresh sign-flip rule with
scale_factor = +/-1, the 2x2 confusion matrix, read_theta accumulation), the
calib_params dict has the QUA keys {scale_factor, threshold, read_theta,
ground_threshold}, both QUA PNGs are reproduced panel-for-panel, and the '###'
console block prints verbatim.  analyze() returns max_F.
"""

import datetime

import numpy as np
import matplotlib.pyplot as plt
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (
    find_blob_median, find_threshold,
)


def discriminate_shots(i, q, calib_params):
    """QUA job_to_shots_1q convention: IQ = factor * Re(e^{-i theta} (I+iQ));
    state = 1 where IQ > threshold."""
    theta = calib_params["read_theta"]
    factor = calib_params["scale_factor"]
    thresh = calib_params["threshold"]
    IQ = factor * np.real(np.exp(-1j * theta) * (np.asarray(i) + 1j * np.asarray(q)))
    return (IQ > thresh).astype(int)


class SingleShotProgram(RAveragerProgram):
    """Two experiments: gain 0 (ground) then gain=qubit_gain (excited), reps=shots.
    The excited prep plays the pi pulse ``repeats`` times (QUA parity knob)."""

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        cfg["start"] = 0
        cfg["step"] = cfg["qubit_gain"]
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 2

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        # the excited-blob preparation is a pi pulse -> use the calibrated pi freq
        qubit_freq = self.freq2reg(cfg.get("qubit_pi_freq", cfg["qubit_freq"]),
                                   gen_ch=cfg["qubit_ch"])

        style = cfg.get("qubit_pulse_style", "arb")
        if style == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]),
                           length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                                     gain=cfg["start"], waveform="qubit")
        elif style == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(cfg["sigma"]),
                           length=self.us2cycles(cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="flat_top", freq=qubit_freq,
                                     phase=0, gain=cfg["start"], waveform="qubit",
                                     length=self.us2cycles(cfg["flat_top_length"]))
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq,
                                     phase=0, gain=cfg["start"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg.get("read_pulse_style", "const"),
                                 freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)

    def body(self):
        cfg = self.cfg
        if cfg["qubit_gain"] != 0:
            for _ in range(int(cfg.get("repeats", 1))):   # QUA: X180 x repeats
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.010))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"] / 2))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        raw = np.array(self.get_raw())
        shots_i = raw[0, :, :, 0, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q = raw[0, :, :, 0, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        return shots_i, shots_q


class SingleShot1Q(ExperimentClass):
    """Single-shot readout calibration; analyze() is the QUA algorithm verbatim."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='SS_Cal', cfg=None, meta_dict=None, plot=True, save=True,
                 repeats=1, confidence_threshold=6e-1, min_F=0.0, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.plot = plot
        self.save = save
        self.repeats = int(repeats)
        self.confidence_threshold = float(confidence_threshold)
        self.min_F = min_F
        self.calib_params = None
        self.max_F = None
        self.element = str(path)

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg.setdefault("shots", cfg.get("ss_shots", 1000))
        cfg["repeats"] = self.repeats
        self.shots = int(cfg["shots"])
        prog = SingleShotProgram(self.soccfg, cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True, progress=progress)
        self.I_0, self.Q_0 = shots_i[0], shots_q[0]
        self.I_1, self.Q_1 = shots_i[1], shots_q[1]

        self.data = {'meta_dict': dict(cfg), 'shots': self.shots, 'repeats': self.repeats}
        self.max_F = self.analyze(plotDisp=plotDisp)
        self.data.update({'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        if self.save:
            self.pickle_data()
        if self.max_F < self.min_F:
            raise RuntimeError(f"SS cal fidelity {self.max_F:.3f} < {self.min_F}; "
                               "aborting before the T1 step.")
        return {'config': cfg, 'data': self.data}

    def analyze(self, plotDisp=False):
        """VERBATIM QUA SingleShot1Q.analyze (blob medians, find_threshold sweep,
        thresh_0, sign-flip, confusion, both PNGs, '###' print block)."""
        cfg = self.cfg
        c_0 = self.I_0 + 1j * self.Q_0
        c_1 = self.I_1 + 1j * self.Q_1
        self.data.update({'cs': np.array([c_0, c_1])})
        num_shots = self.shots

        c_theta = np.angle(find_blob_median(c_1) - find_blob_median(c_0))
        c_0_rot = np.exp(-1j * c_theta) * c_0
        c_1_rot = np.exp(-1j * c_theta) * c_1

        c_thresh, c_F = find_threshold(c_0_rot, c_1_rot)
        thresh = c_thresh[np.argmax(c_F)]
        try:
            thresh_0 = c_thresh[np.where(c_F > self.confidence_threshold)[0][0]]
        except Exception:
            thresh_0 = c_thresh[np.where(c_F > 0)[0][0]]

        c_0_mean = np.mean(np.real(c_0_rot))
        c_factor = 1
        if c_0_mean > thresh:
            c_0_rot = -1 * c_0_rot
            c_1_rot = -1 * c_1_rot
            thresh = -1 * thresh
            c_factor = -1

        confusion = np.zeros([2, 2])
        for i in range(num_shots):
            c_0_point = np.real(c_0_rot[i])
            if c_0_point < thresh:
                confusion[0][0] += 1 / num_shots
            else:
                confusion[1][0] += 1 / num_shots
            c_1_point = np.real(c_1_rot[i])
            if c_1_point < thresh:
                confusion[0][1] += 1 / num_shots
            else:
                confusion[1][1] += 1 / num_shots

        self.thresh = thresh
        self.c_factor = c_factor
        # measured rotation ADDED to any pre-existing demod rotation (QUA behavior)
        self.c_theta = c_theta + cfg.get("read_theta", 0.0)
        self.confusion = confusion

        self.calib_params = {
            "scale_factor": self.c_factor,
            "threshold": self.thresh,
            "read_theta": self.c_theta,
            "ground_threshold": thresh_0,
        }
        self.data.update({'calib_params': self.calib_params, 'confusion': confusion})

        if self.plot:
            fig, ax = plt.subplots(2, 1, constrained_layout=True)
            nbins = int(np.sqrt(num_shots))
            ax[0].hist(np.real(c_0_rot), bins=nbins, density=True, histtype='step',
                       color='red', label='0')
            ax[0].hist(np.real(c_1_rot), bins=nbins, density=True, histtype='step',
                       color='black', label='1')
            ax[0].axvline(x=thresh_0, color='blue', linestyle='--')
            ax[0].axvline(x=self.thresh, color='blue', linestyle='-.')
            ax[0].legend()
            ax[0].set_title('Cavity ' + self.element[1:] + f', F = {round(np.max(c_F), 12)}'
                            + f', amp = {cfg["read_pulse_gain"]}, len = {cfg["read_length"]} us')
            ax[1].plot(c_thresh, c_F)
            ax[1].set_ylabel('Readout infidelity')
            ax[1].set_xlabel('Threshold')
            plt.savefig(self.iname[:-4], bbox_inches='tight')
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            else:
                plt.close(fig)

            fig, ax = plt.subplots(2, figsize=(5, 10))
            ax[0].scatter(np.real(c_0_rot), np.imag(c_0_rot), color='red', alpha=1, label='0')
            ax[0].scatter(np.real(c_1_rot), np.imag(c_1_rot), color='black', alpha=0.1, label='1')
            ax[0].set_title("Rotated Data")
            ax[0].legend()
            ax[1].scatter(self.I_0, self.Q_0, color='red', label='0')
            ax[1].scatter(self.I_1, self.Q_1, color='black', alpha=0.1, label='1')
            m1 = find_blob_median(c_1)
            m0 = find_blob_median(c_0)
            ax[1].scatter(np.real(m1), np.imag(m1), color='cyan', marker='x', s=100, linewidths=2)
            ax[1].scatter(np.real(m0), np.imag(m0), color='cyan', marker='x', s=100, linewidths=2)
            ax[1].set_title("Original Data")
            ax[1].legend()
            plt.ylabel('Q')
            plt.xlabel('I')
            plt.suptitle(f"SS CAL, readout repeated {self.repeats} times.")
            plt.tight_layout()
            plt.savefig(self.iname[:-4] + "_blob", bbox_inches='tight')
            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)
            else:
                plt.close(fig)

        print("###################################################")
        print(f"Threshold: {self.thresh}")
        print(f"Scale Factor: {self.c_factor}")
        print(f"Theta: {self.c_theta}")
        print(f"Ground Confidence Threshold: {thresh_0}")
        print(f"Fidelity: {np.max(c_F)}")
        print(f"Confusion Matrix: [{self.confusion[0]}")
        print(f"           {self.confusion[1]}]")
        print("###################################################")

        return np.max(c_F)

    def save_data(self, data=None):
        if data is None:
            data = {'data': self.data}
        print(f'Saving {self.fname}')
        arr = {'I_0': self.I_0, 'Q_0': self.Q_0, 'I_1': self.I_1, 'Q_1': self.Q_1,
               'confusion': self.confusion}
        super().save_data(data=arr)
