"""
STEP 5 of the TLS pipeline: single-shot readout calibration.

QUA analog: LabCode/Experiments/Readout_Cal/m_single_shot_1Q.py::SingleShot1Q
QICK model: escher mSingleShotProgram.LoopbackProgramSingleShot + Helpers/hist_analysis.hist_process.

Collect ground (no pulse) vs excited (pi pulse) single shots, find the optimal
rotation angle + threshold that separate the IQ blobs, report fidelity, and emit
``calib_params`` used downstream (step 6) to discriminate shots.

calib_params convention (this project)
--------------------------------------
hist_process rotates by theta = -atan2(ye-yg, xe-xg), which orients the g->e vector
along +real, so the excited blob sits at LARGER rotated-I than ground.  Thus:
    rotated_I = i*cos(theta) - q*sin(theta)
    state = 1 (excited) if rotated_I > threshold else 0
and ``scale_factor = +1`` always (the rotation already fixes the sign, so unlike the
QUA convention no explicit factor flip is needed).  We store both the QICK tuple
(fid, threshold, theta) and a QUA-style dict for parity.
"""

import numpy as np
from qick import RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.hist_analysis import hist_process


def rotate_and_threshold(i, q, calib_params):
    """Assign single shots to 0/1 using the project's discrimination convention."""
    theta = calib_params['theta']
    thr = calib_params['threshold']
    rotated_I = np.asarray(i) * np.cos(theta) - np.asarray(q) * np.sin(theta)
    return (rotated_I > thr).astype(int)


class SingleShotProgram(RAveragerProgram):
    """Two experiments: gain 0 (ground) then gain=qubit_gain (excited), reps=shots."""

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
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

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
        if self.cfg["qubit_gain"] != 0:
            self.pulse(ch=self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(self.cfg["relax_delay"]))

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
    """Single-shot readout calibration -> (fid, threshold, theta) + calib_params."""

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data',
                 suffix='SS_Cal', cfg=None, meta_dict=None, plot=True, save=True,
                 min_F=0.0, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=cfg, meta_dict=meta_dict, **kw)
        self.plot = plot
        self.save = save
        self.min_F = min_F
        self.calib_params = None
        self.max_F = None

    def acquire(self, progress=False, plotDisp=False):
        cfg = self.cfg
        cfg.setdefault("shots", cfg.get("ss_shots", 1000))
        prog = SingleShotProgram(self.soccfg, cfg)
        shots_i, shots_q = prog.acquire(self.soc, load_pulses=True, progress=progress)
        i_g, q_g = shots_i[0], shots_q[0]
        i_e, q_e = shots_i[1], shots_q[1]

        fid, threshold, theta = hist_process(data=[i_g, q_g, i_e, q_e],
                                             plot=self.plot, figNum=1,
                                             title=f"SS cal ({cfg.get('shots')} shots)")
        self.max_F = float(fid)
        self.calib_params = {
            'fid': float(fid), 'threshold': float(threshold), 'theta': float(theta),
            'scale_factor': 1, 'ground_threshold': float(threshold),
        }
        data = {'config': cfg,
                'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e,
                         'fid': fid, 'threshold': threshold, 'theta': theta}}
        self.data = data

        if self.plot:
            import matplotlib.pyplot as plt
            plt.savefig(self.iname)
            if plotDisp:
                plt.show(block=False); plt.pause(0.1)
            else:
                plt.close('all')
        if self.save:
            self.save_data(data)
            self.save_config()

        print(f"[5] Single-shot fidelity F = {self.max_F:.3f}")
        if self.max_F < self.min_F:
            raise RuntimeError(f"SS cal fidelity {self.max_F:.3f} < min_F {self.min_F}; "
                               "aborting before the T1 step.")
        return data

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
