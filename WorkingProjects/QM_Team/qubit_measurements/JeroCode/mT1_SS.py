from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.rotate_SS_data import *

class T1Program(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg['rounds'] = 1

        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout


        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.f_qubit01 = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])


        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_qubit01,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                 waveform="qubit")

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.pulse(ch=self.cfg["qubit_ch"])

        self.sync_all(self.us2cycles(self.cfg["variable_wait"]))


        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False):

        # start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        # print(time.time() - start)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)

        return shots_i0, shots_q0

class T1_SS(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, excited_pulse = 2, progress=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg['Excited_PulseT1'] = excited_pulse

        results = []
        rotated_iq_array = []
        for t in tqdm(tpts, position=0, disable=True):
            self.cfg["variable_wait"] = t
            print(t)
            start = time.time()
            prog = T1Program(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            print(time.time() - start)

            rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
            rotated_iq_array.append(rotated_iq)
            excited_percentage = count_percentage(rotated_iq, threshold=threshold)
            results.append(excited_percentage)


        results = np.transpose(results)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': results, 'RotatedIQ': rotated_iq_array, 'threshold':threshold,
                        'angle': angle, 'wait_times': tpts,
                     }
        }
        return self.data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        expectation_values = data['data']['Exp_values']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, expectation_values, 'o-', color = 'orange')
        plt.ylabel("Qubit Population")
        plt.xlabel("Wait time (us)")
        plt.title(self.titlename)
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

