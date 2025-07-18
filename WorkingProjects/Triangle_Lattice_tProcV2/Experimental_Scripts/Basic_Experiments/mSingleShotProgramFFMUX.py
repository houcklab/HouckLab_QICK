
from qick import helpers
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Qt5agg")
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import Compensated_Pulse
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
        # print(cfg["res_freqs"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
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
        print(cfg["readout_lengths"])
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
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + FF_Delay_time)

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
        print(np.array(d_buf).shape)
        for i in range(len(d_buf)):
            shots_i0 = d_buf[i][..., -1, 0] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
            shots_q0 = d_buf[i][..., -1, 1] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
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
        if "readout_length" in self.cfg:
            print(f"Setting readout length to {self.cfg["readout_length"]} us.")
            self.cfg["readout_lengths"][0] = self.cfg["readout_length"]
        #### pull the data from the single shots
        # self.cfg["IDataArray"] = [None, None, None, None, None, None, None, None]
        # for Q in range(len(self.cfg["IDataArray"])):
        #     self.cfg["IDataArray"][Q] = Compensated_Pulse(self.cfg['FF_Qubits'][str(Q+1)]['Gain_Pulse'], 0, Q)

        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ig,shots_qg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ie,shots_qe = prog.acquire(self.soc, load_pulses=True)
        print(self.cfg)
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

        for j, read_index in enumerate(display_indices):

            i_g = data["data"]["i_g" + str(read_index)]
            q_g = data["data"]["q_g" + str(read_index)]
            i_e = data["data"]["i_e" + str(read_index)]
            q_e = data["data"]["q_e" + str(read_index)]

            #### plotting is handled by the helper histogram
            title = 'Read Length: ' + str(self.cfg["readout_lengths"][j]) + "us" + ", Read: " + str(read_index)
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


class SingleShot_2QFFMUX(ExperimentClass):
    """
    2Q Single shot characterization for generating a 2 qubit confusion matrix
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

        self.data = None
        self.fid = []

        self.threshold = []
        self.angle = []
        self.ne_contrast = []
        self.ng_contrast = []
        self.data_in_hist = []

    def acquire(self, progress=False):
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1
        if "readout_length" in self.cfg:
            print(f"Setting readout length to {self.cfg["readout_length"]} us.")
            self.cfg["readout_lengths"][0] = self.cfg["readout_length"]
        #### pull the data from the single shots
        # self.cfg["IDataArray"] = [None, None, None, None, None, None, None, None]
        # for Q in range(len(self.cfg["IDataArray"])):
        #     self.cfg["IDataArray"][Q] = Compensated_Pulse(self.cfg['FF_Qubits'][str(Q+1)]['Gain_Pulse'], 0, Q)

        qubits_freqs = self.cfg['qubit_freqs']
        qubit_gains = self.cfg['qubit_gains']


        if len(self.cfg["Qubit_Readout_List"]) != 2:
            raise ValueError("Must have 2 readout qubits")

        if len(qubits_freqs) != 2 or len(qubit_gains) != 2:
            raise ValueError("Must have 2 pulse qubits")

        # in the future might have different sigmas for each qubit
        sigma = self.cfg['sigma']

        ## 00 state
        self.cfg["Pulse"] = False
        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_igg,shots_qgg = prog.acquire(self.soc, load_pulses=True)

        self.cfg["Pulse"] = True

        ## 10 state
        self.cfg['qubit_freqs'] = [qubits_freqs[0]]
        self.cfg['qubit_gains'] = [qubit_gains[0]]

        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ieg,shots_qeg = prog.acquire(self.soc, load_pulses=True)


        ## 01 state
        self.cfg['qubit_freqs'] = [qubits_freqs[1]]
        self.cfg['qubit_gains'] = [qubit_gains[1]]

        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_ige, shots_qge = prog.acquire(self.soc, load_pulses=True)


        ## 11 state
        self.cfg['qubit_freqs'] = qubits_freqs
        self.cfg['qubit_gains'] = qubit_gains

        print('before')
        print(self.cfg['qubit_freqs'])
        print(self.cfg['qubit_gains'])

        # if second qubit parameters are provided and not none, replace the freq and gain in config
        # this is used when pi pulsing the first qubit shifts the frequency of the second qubit
        if 'second_qubit_freq' in self.cfg:
            second_qubit_freq = self.cfg['second_qubit_freq']
            if second_qubit_freq is not None:
                self.cfg['qubit_freqs'][1] = second_qubit_freq

        if 'second_qubit_gain' in self.cfg:
            second_qubit_gain = self.cfg['second_qubit_gain']
            if second_qubit_gain is not None:
                self.cfg['qubit_gains'][1] = second_qubit_gain/32766.

        print('after')
        print(self.cfg['qubit_freqs'])
        print(self.cfg['qubit_gains'])

        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        shots_iee, shots_qee = prog.acquire(self.soc, load_pulses=True)



        print(self.cfg)
        data = {'config': self.cfg, 'data': {}}
                # {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}

        self.data = data

        population_shots = np.zeros((2, 4, self.cfg["Shots"]), dtype=np.int64) # 2 qubits, 4 initial states, shots


        for i, read_index in enumerate(self.cfg["Qubit_Readout_List"]):
            i_gg = shots_igg[i]
            q_gg = shots_qgg[i]

            i_ge = shots_ige[i]
            q_ge = shots_qge[i]

            i_eg = shots_ieg[i]
            q_eg = shots_qeg[i]

            i_ee = shots_iee[i]
            q_ee = shots_qee[i]


            self.data['data']['i_gg' + str(read_index)] = i_gg
            self.data['data']['q_gg' + str(read_index)] = q_gg

            self.data['data']['i_ge' + str(read_index)] = i_ge
            self.data['data']['q_ge' + str(read_index)] = q_ge

            self.data['data']['i_eg' + str(read_index)] = i_eg
            self.data['data']['q_eg' + str(read_index)] = q_eg

            self.data['data']['i_ee' + str(read_index)] = i_ee
            self.data['data']['q_ee' + str(read_index)] = q_ee

            # process the first qubit

            if i == 0:
                # trace out second qubit
                i_g = np.concatenate((i_gg, i_ge))
                q_g = np.concatenate((q_gg, q_ge))

                i_e = np.concatenate((i_eg, i_ee))
                q_e = np.concatenate((q_eg, q_ee))

            else:
                # trace out first qubit
                i_g = np.concatenate((i_gg, i_eg))
                q_g = np.concatenate((q_gg, q_eg))

                i_e = np.concatenate((i_ge, i_ee))
                q_e = np.concatenate((q_ge, q_ee))

            self.data['data']['i_g' + str(read_index)] = i_g
            self.data['data']['q_g' + str(read_index)] = q_g

            self.data['data']['i_e' + str(read_index)] = i_e
            self.data['data']['q_e' + str(read_index)] = q_e



            fid, threshold, angle, ne_contrast, ng_contrast = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, return_errors=True) ### arbitrary ran, change later
            self.data_in_hist.append([i_g, q_g, i_e, q_e])
            self.fid.append(fid)
            self.threshold.append(threshold)
            self.angle.append(angle)
            self.ne_contrast.append(ne_contrast)
            self.ng_contrast.append(ng_contrast)

            # build confusion matrix
            # rotate IQ points according to angle

            i_gg_new = i_gg * np.cos(angle) - q_gg * np.sin(angle)
            q_gg_new = i_gg * np.sin(angle) + q_gg * np.cos(angle)
            i_ge_new = i_ge * np.cos(angle) - q_ge * np.sin(angle)
            q_ge_new = i_ge * np.sin(angle) + q_ge * np.cos(angle)
            i_eg_new = i_eg * np.cos(angle) - q_eg * np.sin(angle)
            q_eg_new = i_eg * np.sin(angle) + q_eg * np.cos(angle)
            i_ee_new = i_ee * np.cos(angle) - q_ee * np.sin(angle)
            q_ee_new = i_ee * np.sin(angle) + q_ee * np.cos(angle)

            p_gg = (i_gg_new > threshold).astype(int)
            p_ge = (i_ge_new > threshold).astype(int)
            p_eg = (i_eg_new > threshold).astype(int)
            p_ee = (i_ee_new > threshold).astype(int)

            population_shots[i, 0] = p_gg
            population_shots[i, 1] = p_ge
            population_shots[i, 2] = p_eg
            population_shots[i, 3] = p_ee


        # convert outcomes (00, 01, 10, 11) to (0, 1, 2, 3)

        measurement_outcomes =  2 * population_shots[0,:,:] + population_shots[1,:,:]

        confusion_matrix = np.zeros((4, 4))

        for i in range(confusion_matrix.shape[0]):
            confusion_matrix[:,i] = np.bincount(measurement_outcomes[i], minlength=4) / self.cfg["Shots"]

        print(confusion_matrix)



        self.data['data']['threshold'] = self.threshold
        self.data['data']['angle'] = self.angle
        self.data['data']['ne_contrast'] = self.ne_contrast
        self.data['data']['ng_contrast'] = self.ng_contrast
        self.data['data']['fid'] = self.fid

        self.data['data']['confusion_matrix'] = confusion_matrix

        return self.data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, block=True, **kwargs):
        if data is None:
            data = self.data




        #### plotting is handled by the helper histogram
        title = 'Read Length: ' + str(self.cfg["readout_lengths"]) + "us" + ", Read: " + str(self.cfg["Qubit_Readout_List"])
        hist_process_2Q(data=data, print_fidelities=False, ran=None, title = title)

        plt.suptitle(self.titlename + " , Read: " + str(self.cfg["Qubit_Readout_List"]))

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])