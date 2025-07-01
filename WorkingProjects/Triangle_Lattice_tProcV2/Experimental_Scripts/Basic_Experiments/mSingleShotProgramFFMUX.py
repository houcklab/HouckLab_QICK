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

# ====================================================== #
class SingleShotProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],
                                 length=self.us2cycles(cfg["readout_length"] + cfg["adc_trig_offset"] + 1, gen_ch=self.cfg["res_ch"]))

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=90, gain=cfg["qubit_gains"][0])
        self.qubit_length_us = cfg["sigma"] * 4


        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.cfg['number_of_pulses'] * len(self.cfg["qubit_gains"]) * self.cfg['sigma'] * 4 + FF_Delay_time)
        if self.cfg["Pulse"]:
            for i in range(len(self.cfg["qubit_gains"])):
                gain_ = self.cfg["qubit_gains"][i]
                freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])

                for pulse_num in range(self.cfg["number_of_pulses"]):
                    if i == 0 and pulse_num == 0:
                        time = self.us2cycles(FF_Delay_time)
                    else:
                        time = 'auto'
                    self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                     gain=gain_,
                                     waveform="qubit", t=time)

        self.sync_all(gen_t0=self.gen_t0)

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False):
        start = time.time()
        super().acquire(soc, load_pulses=load_pulses, progress=progress)
        end = time.time()

        return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []

        for i in range(len(self.di_buf)):
            shots_i0=self.di_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
            shots_q0=self.dq_buf[i].reshape((1,self.cfg["reps"])) /self.us2cycles(self.cfg['readout_length'], ro_ch = 0)
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
        self.cfg["reps"] = self.cfg["Shots"]
        self.cfg["rounds"] = 1
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1

        #### pull the data from the single shots
        self.cfg["IDataArray"] = [None, None, None, None]
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Pulse'], 0, 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Pulse'], 0, 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Pulse'], 0, 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Pulse'], 0, 4)

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, self.cfg)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)

        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}
        self.data = data
        self.fid = []
        for i, read_index in enumerate(self.cfg["Qubit_Readout_List"]):
            i_g = shots_ig[i][0]
            q_g = shots_qg[i][0]
            i_e = shots_ie[i][0]
            q_e = shots_qe[i][0]
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