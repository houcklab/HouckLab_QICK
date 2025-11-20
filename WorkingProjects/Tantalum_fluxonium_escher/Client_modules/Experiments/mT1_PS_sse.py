from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import GammaFit as gf


'''
@author: Parth Jatakia
'''


def expFit(x, a, T1, c):
    return a * np.exp(-1 * x / T1) + c


class LoopbackProgramT1_PS_sse(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ### set up the experiment updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        ### Configure Resonator Tone
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"],
                         ro_ch=cfg["ro_chs"][0])  # Declare the resonator channel
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch,
                                  ro_ch=cfg["ro_chs"][0])  # Convert to clock ticks
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), )  # define the pulse

        ### Configure the Qubit Tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        qubit_ch = cfg["qubit_ch"]  # Get the qubit channel
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])  # Declare the qubit channel
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # Convert qubit length to clock ticks
        # Define the qubit pulse
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        else:
            print("define pi or flat top pulse")

        ### Declare ADC Readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"], ro_ch = self.cfg["res_ch"]), gen_ch=cfg["res_ch"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.cfg["qubit_pulseLength"] #self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        ### initial pulse
        self.sync_all(self.us2cycles(0.01))  # align channels and wait

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.01))  # align channels and wait

        #### post selection
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False)

        self.sync_all(self.us2cycles(0.01))  # align channels and wait

        ### Wait
        self.sync_all(self.us2cycles(self.cfg["wait_length"]))

        ### Final measure
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2,
                save_experiments=[0, 1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress,  # qick update - debug=debug,
                        readouts_per_experiment=2, save_experiments=[0, 1])

        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        shots_i0 = np.array(self.get_raw())[0, :, :, 0, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q0 = np.array(self.get_raw())[0, :, :, 0, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_i1 = np.array(self.get_raw())[0, :, :, 1, 0].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        shots_q1 = np.array(self.get_raw())[0, :, :, 1, 1].reshape((self.cfg["expts"], self.cfg["reps"])) / length
        i_0 = shots_i0[0]
        i_1 = shots_i1[0]
        q_0 = shots_q0[0]
        q_1 = shots_q1[0]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class T1_PS_sse(ExperimentClass):
    """
    Use post selection at a thermal state (significant thermal population) to find T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self):

        ### Define the wait vector
        if self.cfg['wait_type'] == 'linear':
            wait_vec = np.linspace(self.cfg["wait_start"], self.cfg["wait_stop"], self.cfg["wait_num"])
        if self.cfg['wait_type'] == 'log':
            wait_vec = np.logspace(self.cfg["wait_start"], np.log10(self.cfg["wait_stop"]), self.cfg["wait_num"],
                                   base=10) - 1

        ##### create arrays to store all the raw data
        i_0_arr = np.full((self.cfg["wait_num"], int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((self.cfg["wait_num"], int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((self.cfg["wait_num"], int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((self.cfg["wait_num"], int(self.cfg["shots"])), np.nan)

        ### loop over all wait times and collect raw data
        for idx_wait in range(self.cfg["wait_num"]):
            self.cfg["wait_length"] = wait_vec[idx_wait]

            #### pull the data from the single shots for the first run
            prog = LoopbackProgramT1_PS_sse(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                              save_experiments=[0, 1])

            #### save all the data to arrays
            i_0_arr[idx_wait, :] = i_0
            q_0_arr[idx_wait, :] = q_0
            i_1_arr[idx_wait, :] = i_1
            q_1_arr[idx_wait, :] = q_1

        ### save the data
        data = {'config': self.cfg, 'data': {
            "wait_vec": wait_vec,
            'i_0': i_0_arr, 'q_0': q_0_arr,
            'i_1': i_1_arr, 'q_1': q_1_arr,
        }
                }

        self.data = data
        return data

    def process_data(self, data=None, **kwargs):
        '''
        kwargs :
        1. cen_num : number of centers
        2. save_all : save intermediate processed data
        '''
        if data is None:
            data = self.data

        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]
        wait_vec = data["data"]["wait_vec"]

        data_to_process = [i_0, i_1, q_0, q_1, wait_vec]

        gammafit = gf.GammaFit(data_to_process, freq_01 = data['config']["qubit_freq"]*1e6)
        pop = gammafit.pops_vec
        pop_err = gammafit.pops_err_vec
        centers_list = gammafit.centers
        g01 = gammafit.result.params['g01'].value
        err01 = gammafit.result.params['g01'].stderr
        g10 = gammafit.result.params['g10'].value
        err10 = gammafit.result.params['g10'].stderr
        T1 = gammafit.T1
        T1_err = gammafit.T1_err
        temp_rate = gammafit.temp
        temp_std_rate = gammafit.temp_err
        data_fitted = gammafit.data_fitted
        T1_guess = gammafit.T1_guess

        # saving the processed data
        update_data = {"data": {"population": pop, "population_std": pop_err, "centers": centers_list,
                                "g01": g01, "err01": err01, "g10": g10, "err10": err10, "T1": T1, "T1_err": T1_err,
                                "temp_rate": temp_rate, "temp_std_rate": temp_std_rate, "data_fitted": data_fitted,
                                "T1_guess": T1_guess}}


        data["data"] = data["data"] | update_data["data"]
        self.data = data


        return data

    def display(self, data=None, plotDisp=False, saveFig = True, figNum=1, ran=None, **kwargs):

        if data is None:
            data = self.data

        if "cen_num" in kwargs:
            cen_num = kwargs["cen_num"]
        else:
            cen_num = 2

        # Extracting data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        wait_vec = data["data"]["wait_vec"]
        pop = data["data"]["population"]
        pop_err = data["data"]["population_std"]
        centers = data["data"]["centers"][0]
        # popt_list = data["data"]["popt_list"]
        # perr_list = data["data"]["perr_list"]

        data_fitted = data["data"]["data_fitted"]
        T1 = data["data"]["T1"]
        T1_err = data["data"]["T1_err"]

        # Create histogram
        iq_data = np.stack((i_0[0],q_0[0]), axis = 0)
        hist2d = sse2.createHistogram(iq_data, bin_size = 51)
        xedges = hist2d[1]
        yedges = hist2d[2]
        x_points = (xedges[1:] + xedges[:-1]) / 2
        y_points = (yedges[1:] + yedges[:-1]) / 2

        # Choice of color
        colorlist = [
            'firebrick',
            'midnightblue',
            'coral',
            'darkolivegreen'
        ]

        ### Plotting the T1 vs wait_vec data and the fitted exponential.
        ### The fit of exponential is only valid for cen_num = 2.
        # Create 2x2 subplots
        gs = gridspec.GridSpec(cen_num, 2, width_ratios=[1, 2])
        fig = plt.figure(figsize=[12, 5 * cen_num])
        # Plot the blob distribution
        subplot_left = plt.subplot(gs[0, 0])
        subplot_left.scatter(np.ravel(i_0), np.ravel(q_0), s=0.1)
        subplot_left.scatter(centers[:, 0], centers[:, 1], s=10, c='r')
        subplot_left.set_xlabel("I")
        subplot_left.set_ylabel("Q")

        subplot_left_bottom = plt.subplot(gs[1, 0])
        im = subplot_left_bottom.imshow(np.transpose(hist2d[0]), extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]],
               origin = 'lower', aspect = 'auto')
        fig.colorbar(im, ax = subplot_left_bottom)
        subplot_left_bottom.scatter(centers[:, 0], centers[:, 1], s=10, c='r')
        subplot_left_bottom.set_xlabel("I")
        subplot_left_bottom.set_ylabel("Q")


        # Plot the population vs time
        subplot_right = []
        for idx_start in range(cen_num):
            subplot_right.append(plt.subplot(gs[idx_start, 1]))
            for idx_end in range(cen_num):
                pop_curr = pop[idx_start, idx_end, :]
                pop_curr_std = pop_err[idx_start, idx_end, :]

                subplot_right[idx_start].errorbar(wait_vec, pop_curr, pop_curr_std, fmt='o',
                                                  label="Blob " + str(idx_end),
                                                  c=colorlist[idx_end])
                # Plot the fit if decay is exponential
                # TODO: extend it to cen_num > 2
                if cen_num == 2:
                    # subplot_right[idx_start].plot(wait_vec, expFit(wait_vec,*popt_list[idx_start][idx_end]),
                    #                               c=colorlist[idx_end], linestyle="--")
                    subplot_right[idx_start].plot(wait_vec, data_fitted[idx_start][:, idx_end],
                                                  c=colorlist[idx_end], linestyle="--")
            if cen_num == 2:
                T1_str = "T1 = " + str(T1.round(3)) + " +/- " + str(T1_err.round(3)) + " us"
            subplot_right[idx_start].set_xlabel("time (n us)")
            subplot_right[idx_start].set_ylabel("Population in Blob")
            subplot_right[idx_start].set_title("Start Blob = " + str(idx_start) + "\n" + T1_str)
            subplot_right[idx_start].legend()


        data_information = ("Fridge Temperature = " + str(self.cfg["fridge_temp"]) + "mK, Yoko_Volt = "
                            + str(self.cfg["yokoVoltage_freqPoint"]) + "V, relax_delay = " + str(
                    self.cfg["relax_delay"])
                            + "us." + " Qubit Frequency = " + str(self.cfg["qubit_freq"])
                            + " MHz")
        plt.suptitle(self.outerFolder + '\n' + self.path_wDate + '\n' + data_information)
        plt.tight_layout()
        if saveFig:
            plt.savefig(self.iname, dpi=400)

        if plotDisp:
            plt.show()
        plt.close()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
