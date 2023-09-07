from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.PythonDrivers.YOKOGS200 import *
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
import datetime

##########################################################################################################
### define functions to be used later for analysis
#### define a rotation function
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot

def SelectShots(shots_1_i, shots_1_q, shots_0_igRot, gCen, eCen):
    ### shots_1 refers to second measurement, shots_0_iRot is rotated i quad of first measurement
    ### gCen and eCen are centers of the respective blobs from the ground state expirement
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])
    if gCen < eCen:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] < gCen:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
    else:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] > gCen:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

    return shots_1_iSel, shots_1_qSel

def SelectAllShots(shots_1_i, shots_1_q, shots_0_igRot, Cen1, Cen2):
    ### selects out shots and defines based on left being 1 and right being 2
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])
    shots_2_iSel = np.array([])
    shots_2_qSel = np.array([])
    if Cen1 < Cen2:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] < Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] > Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_1_iSel, shots_1_qSel, shots_2_iSel, shots_2_qSel

    else:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] > Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] < Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_2_iSel, shots_2_qSel, shots_1_iSel, shots_1_qSel



####################################################################################################################

class LoopbackProgramFFPulse_WTF_sweep(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the expirement updates, only runs it once
        cfg["start"]= 0
        cfg["step"]= 0
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_read_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        ##### define a fast flux pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                 gain=self.cfg["ff_gain"],
                                 length=self.us2cycles(self.cfg["ff_length"]))
        self.cfg["ff_length_total"] = self.us2cycles(self.cfg["ff_length"])

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.010))

        #### measure beginning thermal state
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait = False)

        self.sync_all(self.us2cycles(0.010))

        # ##### run the fast flux pulse 10 times
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse

        #### wait until everything is finished reading
        self.synci(self.us2cycles(0.20))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class FFPulse_WTF_Sweep(ExperimentClass):
    """
    running the WTF experiment at multiple yoko points and running sweep multiple times to build up statistics
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, calibData = None):

        expt_cfg = {
            ### define the yoko parameters
            "yokoVoltageStart": self.cfg["yokoVoltageStart"],
            "yokoVoltageStop": self.cfg["yokoVoltageStop"],
            "yokoVoltageNumPoints": self.cfg["yokoVoltageNumPoints"],
            ###
            "WTF_avgs": self.cfg["WTF_avgs"],
            ### store a copy of the base ff gain
            "ff_gain_start": self.cfg["ff_gain"]
        }

        ### define the yoko vector for the voltages, note this assumes that yoko1 already exists
        yoko1 = YOKOGS200(VISAaddress='GPIB0::5::INSTR', rm=visa.ResourceManager())

        voltVec = np.linspace(expt_cfg["yokoVoltageStart"], expt_cfg["yokoVoltageStop"],
                              expt_cfg["yokoVoltageNumPoints"])
        yoko1.SetVoltage(expt_cfg["yokoVoltageStart"])

        voltVec_step = voltVec[1] - voltVec[0]
        voltVec_plotSpan = [voltVec[0] - voltVec_step/2, voltVec[-1] + voltVec_step/2]

        ### set up plot
        figNum = 1
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 2, figsize=(10, 6), num=figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ##### create arrays to store all the raw data
        i_0_arr = np.full((expt_cfg["yokoVoltageNumPoints"],expt_cfg["WTF_avgs"], int(self.cfg["shots"]) ), np.nan)
        q_0_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)

        ##### create arrays to store all the processed data
        i_0_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        q_0_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        i_1_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        q_1_1_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        i_0_2_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        q_0_2_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        i_1_2_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)
        q_1_2_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], int(self.cfg["shots"])), np.nan)

        #### pull out calibration data
        i_g = calibData["data"]["i_g"]
        q_g = calibData["data"]["q_g"]
        i_e = calibData["data"]["i_e"]
        q_e = calibData["data"]["q_e"]

        self.fid, self.threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=122)

        ##### create arrays to store the popultaions
        pop_arr = np.full((expt_cfg["yokoVoltageNumPoints"], expt_cfg["WTF_avgs"], 4), np.nan)

        #### loop over the yoko vector
        for idx_volt in range(expt_cfg["yokoVoltageNumPoints"]):
            ### set the yoko voltage for the specific run
            yoko1.SetVoltage(voltVec[idx_volt])
            #### need to add code to adjust the ff gain when changing the yoko
            self.cfg["ff_gain"] = int(expt_cfg["ff_gain_start"] - 33500*(voltVec[idx_volt] - self.cfg["yokoVoltage"]) )
            print(self.cfg["ff_gain"])

            for idx_avg in range(expt_cfg["WTF_avgs"]):

                #### pull the data from the single shots
                prog = LoopbackProgramFFPulse_WTF_sweep(self.soccfg, self.cfg)
                i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

                i_0_arr[idx_volt, idx_avg, :] = i_0
                q_0_arr[idx_volt, idx_avg, :] = q_0
                i_1_arr[idx_volt, idx_avg, :] = i_1
                q_1_arr[idx_volt, idx_avg, :] = q_1

                #### sort into mixed states
                mixed_0 = MixedShots(i_0, q_0, numbins=25)

                #### rotate the full arrays
                theta = mixed_0.theta

                i_0_rot, q_0_rot = rotateBlob(i_0, q_0, theta)

                cen1 = mixed_0.cen1_rot[0]
                cen2 = mixed_0.cen2_rot[0]

                ### select out data that started in the ground state
                ### convention here is i_[EXPIREMENT NUMBER]_[BLOB NUMBER]

                i_0_1, q_0_1, i_0_2, q_0_2 = SelectAllShots(i_0, q_0, i_0_rot, cen1, cen2)
                i_1_1, q_1_1, i_1_2, q_1_2 = SelectAllShots(i_1, q_1, i_0_rot, cen1, cen2)

                #### intset above data into arrays for storage
                i_0_1_arr[idx_volt, idx_avg, 0:len(i_0_1)] = i_0_1
                q_0_1_arr[idx_volt, idx_avg, 0:len(q_0_1)] = q_0_1
                i_0_2_arr[idx_volt, idx_avg, 0:len(i_0_2)] = i_0_2
                q_0_2_arr[idx_volt, idx_avg, 0:len(q_0_2)] = q_0_2
                i_1_1_arr[idx_volt, idx_avg, 0:len(i_1_1)] = i_1_1
                q_1_1_arr[idx_volt, idx_avg, 0:len(q_1_1)] = q_1_1
                i_1_2_arr[idx_volt, idx_avg, 0:len(i_1_2)] = i_1_2
                q_1_2_arr[idx_volt, idx_avg, 0:len(q_1_2)] = q_1_2

                ### rename data for simplicity or processing
                i_fast_1 = i_1_1
                q_fast_1 = q_1_1
                i_fast_2 = i_1_2
                q_fast_2 = q_1_2

                i_fast_1_rot, q_fast_1_rot = rotateBlob(i_fast_1, q_fast_1, angle)
                i_fast_2_rot, q_fast_2_rot = rotateBlob(i_fast_2, q_fast_2, angle)

                #### calculate the amounts of blob 1 and blob 2 in the ground and excited states
                populations = np.zeros(4)
                for i in range(len(i_fast_1_rot)):
                    if i_fast_1_rot[i] < self.threshold:
                        populations[0] += 1 ### blob1_g
                    else:
                        populations[1] += 1 ### blob1_e

                for i in range(len(i_fast_2_rot)):
                    if i_fast_2_rot[i] < self.threshold:
                        populations[2] += 1 ### blob2_g
                    else:
                        populations[3] += 1 ### blob2_e

                populations[0] = populations[0] / len(i_fast_1_rot) * 1.0
                populations[1] = populations[1] / len(i_fast_1_rot) * 1.0

                populations[2] = populations[2] / len(i_fast_2_rot) * 1.0
                populations[3] = populations[3] / len(i_fast_2_rot) * 1.0

                pop_arr[idx_volt, idx_avg, :] = populations

                #### save the data
                data = {'config': self.cfg, 'data': {"voltVec": voltVec, 'fidelity': self.fid,
                                                     "i_g": i_g, "q_g": q_g, "i_e": i_e, "q_e": q_e,
                                                     'i_0_arr': i_0_arr, 'q_0_arr': q_0_arr,
                                                     'i_1_arr': i_1_arr, 'q_1_arr': q_1_arr,
                                                     'i_0_1_arr': i_0_1_arr, 'q_0_1_arr': q_0_1_arr,
                                                     'i_0_2_arr': i_0_2_arr, 'q_0_2_arr': q_0_2_arr,
                                                     'i_1_1_arr': i_1_1_arr, 'q_1_1_arr': q_1_1_arr,
                                                     'i_1_2_arr': i_1_2_arr, 'q_1_2_arr': q_1_2_arr,
                                                     'pop_arr': pop_arr
                                                     }
                        }
                self.data = data

                if idx_volt ==0 and idx_avg == 0: ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start ### time for single full row in seconds
                    timeEst = t_delta*expt_cfg["yokoVoltageNumPoints"]*expt_cfg["WTF_avgs"] ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

            #### plot out the data so far

            axs[0].plot(voltVec, np.nanmean(pop_arr[:, :, 0], axis=1), 'o-',
                        color = 'g' )
            axs[0].errorbar(voltVec, np.nanmean(pop_arr[:, :, 0], axis=1),
                        yerr = np.nanstd(pop_arr[:, :, 0], axis=1),
                        color = 'g'
                        )

            axs[0].plot(voltVec, np.nanmean(pop_arr[:, :, 2], axis=1), 'o-',
                        color = 'm')
            axs[0].errorbar(voltVec, np.nanmean(pop_arr[:, :, 2], axis=1),
                        yerr=np.nanstd(pop_arr[:, :, 2], axis=1),
                        color='m'
                        )

            axs[0].set_ylim([-0.05, 1.05])
            axs[0].set_xlim(voltVec_plotSpan)
            axs[0].set_xlabel('Starting Flux (yoko V)')
            axs[0].set_ylabel('g population (%)')
            axs[0].set_title('g pop after FF pulse')

            #### plot the excited state populations
            axs[1].plot(voltVec, np.nanmean(pop_arr[:, :, 1], axis=1), 'o-',
                        color = 'g' )
            axs[1].errorbar(voltVec, np.nanmean(pop_arr[:, :, 1], axis=1),
                        yerr = np.nanstd(pop_arr[:, :, 1], axis=1),
                        color = 'g'
                        )

            axs[1].plot(voltVec, np.nanmean(pop_arr[:, :, 3], axis=1), 'o-',
                        color = 'm')
            axs[1].errorbar(voltVec, np.nanmean(pop_arr[:, :, 3], axis=1),
                        yerr=np.nanstd(pop_arr[:, :, 3], axis=1),
                        color='m'
                        )
            axs[1].set_ylim([-0.05, 1.05])
            axs[1].set_xlim(voltVec_plotSpan)
            axs[1].set_xlabel('Starting Flux (yoko V)')
            axs[1].set_ylabel('e population (%)')
            axs[1].set_title('e pop after FF pulse')

            plt.show(block=False)
            plt.pause(0.1)

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        return data



    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data


        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])