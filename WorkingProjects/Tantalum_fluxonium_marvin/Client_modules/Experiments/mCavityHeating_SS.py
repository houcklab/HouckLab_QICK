'''
Created on Mon Jan 20 2025:
@author: pjatakia
This code tries to measure how fast a cavity heats up using the number splitting of qubit tone due to photons in the cavity
'''

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import Transmission_Enhance
from tqdm.notebook import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time


def group_and_average(my_arr, k):
    # Initialize an empty list to store the averages
    result = []

    # Iterate through the array in steps of k
    for i in range(0, len(my_arr), k):
        # Slice the array to get the next k elements
        group = my_arr[i:i + k]

        # Calculate the average of the group
        avg = sum(group) / k

        # Append the average to the result list
        result.append(avg)

    return np.array(result)

class LoopbackProgramCavityHeating_SS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):

        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0]) # conver f_res to dac register value
        self.f_res = f_res
        self.f_start = self.freq2reg(self.cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

        #### define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
        elif self.cfg["qubit_pulse_style"] == "const":
            if self.cfg["mode_periodic"] == True:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"]), mode="periodic")
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"])
            else:
                self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                         length=self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"]))
                self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"],gen_ch=cfg["qubit_ch"])

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.f_start,
                                     phase=0, gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = (self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
                                      + self.us2cycles(self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"]))

        # Adding the resonator pulse
        if self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["cavity_pulse_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["res_ch"]), mode="periodic")
        elif not self.cfg['ro_periodic']:
            self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=f_res, phase=0,
                                     gain=cfg["cavity_pulse_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=cfg["res_ch"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(1))

    def body(self):

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Configure the cavity pulse for populating the cavity
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                 gain=self.cfg["cavity_pulse_gain"],
                                 length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["res_ch"]))

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        if self.cfg["qubit_gain"] != 0 and self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch

        self.pulse(ch=self.cfg["res_ch"])   # Play a cavity tone
        self.pulse(ch=self.cfg["qubit_ch"])  # Play a qubit tone
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Configure the cavity pulse for readout
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=self.f_res, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))

        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0])
        shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0])

        return shots_i0,shots_q0

class StarkShift(ExperimentClass):
    """
    to write
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, **kwargs):
        '''
        Code to measure the single shot data after populating the cavity and pumping the qubit
        '''

        expt_cfg = {
            ### spec parameters
            "qubit_freq": self.cfg["qubit_freq"],
        }
        self.cfg["reps"] = self.cfg["shots"]
        self.cfg["start"] = expt_cfg["qubit_freq"]
        self.cfg["step"] = 0
        self.cfg["expts"] = 1

        start = time.time()

        prog = LoopbackProgramCavityHeating_SS(self.soccfg, self.cfg)
        i_arr, q_arr = prog.acquire(self.soc, load_pulses=True)

        t_delta = time.time() - start
        t_arr = np.linspace(0, t_delta, self.cfg['avg'])

        i_arr_avg = group_and_average(i_arr, self.cfg['avg'])
        q_arr_avg = group_and_average(q_arr, self.cfg['avg'])

        self.data = {'config': self.cfg, 'data': {'t_arr': t_arr, 'i_arr_avg': i_arr_avg, 'q_arr_avg': q_arr_avg,
                                                  'i_arr': i_arr, 'q_arr': q_arr,}}

        return self.data

    def display(self, data= None, plotDisp=True, plotSave=True):
        if data is None:
            data = self.data

        t_arr = data["data"]["t_arr"]
        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        i_arr_avg = data['data']['i_arr_avg']
        q_arr_avg = data['data']['q_arr_avg']

        fig, axs = plt.subplots(2, 1, figsize=(10, 10))

        # Plot i_arr vs t_arr in the first subplot
        axs[0].plot(t_arr, i_arr_avg)
        axs[0].set_title('i_arr vs t_arr')
        axs[0].set_xlabel('Time (in s)')
        axs[0].set_ylabel('i_arr')

        # Plot q_arr vs t_arr in the second subplot
        axs[1].plot(t_arr, q_arr_avg)
        axs[1].set_title('q_arr vs t_arr')
        axs[1].set_xlabel('Time (in s)')
        axs[1].set_ylabel('q_arr')

        # Layout so plots do not overlap
        fig.tight_layout()


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])




