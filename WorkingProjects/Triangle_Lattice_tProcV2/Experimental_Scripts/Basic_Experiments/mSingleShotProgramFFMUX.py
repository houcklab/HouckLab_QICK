from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Jero import Compensated_Pulse
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.AveragerProgramFF import FFAveragerProgramV2


# ====================================================== #
class SingleShotProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])

        for i in range(len(self.cfg["qubit_gains"])):
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][i],
                       phase=90, gain=cfg["qubit_gains"][i])
        self.qubit_length_us = cfg["sigma"] * 4


    def _body(self, cfg):
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.cfg['number_of_pulses'] * len(self.cfg["qubit_gains"]) * self.cfg['sigma'] * 4 + FF_Delay_time)
        if self.cfg["Pulse"]:
            for i in range(len(self.cfg["qubit_gains"])):
                for pulse_num in range(self.cfg["number_of_pulses"]):
                    if i == 0 and pulse_num == 0:
                        time = FF_Delay_time
                    else:
                        time = 'auto'
                    self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}', t=time)

        self.delay_auto()

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        self.trigger(ros=cfg["ro_chs"], pins=[0],
                     t=cfg["adc_trig_delay"])
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1)

        self.delay_auto()


    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        end = time.time()

        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []

        d_buf = self.get_raw() # [(*self.loop_dims, nreads, 2) for ro in ros]
        for i in range(len(d_buf)):
            shots_i0 = d_buf[i][..., -1, 0] / self.us2cycles(self.cfg['readout_length'], ro_ch=self.cfg['ro_chs'][i])
            shots_q0 = d_buf[i][..., -1, 1] / self.us2cycles(self.cfg['readout_length'], ro_ch=self.cfg['ro_chs'][i])
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


class SingleShotFFMUX(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.threshold = []
        self.angle = []
        self.ne_contrast = []
        self.ng_contrast = []

    def acquire(self, progress=False):
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1

        #### pull the data from the single shots
        self.cfg["IDataArray"] = [None, None, None, None]
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], 0, 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], 0, 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], 0, 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], 0, 4)

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"])
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"])
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        for i, read_index in enumerate(self.cfg["Qubit_Readout_List"]):
            i_g = shots_ig[i]
            q_g = shots_qg[i]
            i_e = shots_ie[i]
            q_e = shots_qe[i]
            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g
            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e

            fid, threshold, angle, ne_contrast, ng_contrast = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, return_errors=True) ### arbitrary ran, change later
            self.data_in_hist = [i_g, q_g, i_e, q_e]
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)
            self.ne_contrast.append(ne_contrast)
            self.ng_contrast.append(ng_contrast)


        self.data['data']['threshold'] = self.threshold
        self.data['data']['angle'] = self.angle
        self.data['data']['ne_contrast'] = self.ne_contrast
        self.data['data']['ng_contrast'] = self.ng_contrast
        self.data['data']['fid'] = self.fid

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, display_indices=None, block=True, **kwargs):
        if data is None:
            data = self.data
        if display_indices is None:
            display_indices = self.cfg["Qubit_Readout_List"]

        for read_index in display_indices:

            i_g = data["data"]["i_g" + str(read_index)]
            q_g = data["data"]["q_g" + str(read_index)]
            i_e = data["data"]["i_e" + str(read_index)]
            q_e = data["data"]["q_e" + str(read_index)]

            #### plotting is handled by the helper histogram
            title = 'Read Length: ' + str(self.cfg["readout_length"]) + "us" + ", Read: " + str(read_index)
            hist_process(data=[i_g, q_g, i_e, q_e], plot=True, print_fidelities=False, ran=None, title = title)

            plt.suptitle(self.titlename + " , Read: " + str(read_index))

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=block)
                plt.pause(0.1)
        # else:
        #     plt.clf()
        #     plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])