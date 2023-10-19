from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from tqdm.notebook import tqdm
import time

class LoopbackProgramSingleShotgef(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # This is a two stage process. Hence, the expts = 2
        # In stage 1, the ground state is measured.
        # In stage 2, a g-e pi pulse and e-f pi pulse is applied to measure the f state.

        cfg["start"] = 0                      # start represent the gain of the g-e and e-f pulse in stage 1
        cfg["step"] = cfg["qubit_ge_gain"]    # TODO : Remove the variable and check
        cfg["reps"] = cfg["shots"]            # Represents the averages
        cfg["expts"] = 2                      # The number of stages


        # ### Reverse the experiment order
        # cfg["start"]=cfg["qubit_gain"]
        # cfg["step"]= -cfg["qubit_gain"]
        # cfg["reps"]=cfg["shots"]
        # cfg["expts"]=2

        # Declare the qubit pages and register
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])             # Get register page for qubit_ch
        self.qreg_gain = self.sreg(cfg["qubit_ch"], "gain")   # Get g-e gain register for qubit_ch
        self.qreg_gain_ef = 4                                      # New register used for e-f gain
        self.qreg_freq = self.sreg(cfg["qubit_ch"],"freq")   # Get freq register for qubit_ch

        # Declare the channel for readout
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], ro_ch=cfg["ro_chs"][0])

        # Declare the channel for qubit
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        # Convert frequency to dac frequency
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        self.qubit_ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])
        self.qubit_ef_freq = self.freq2reg(self.cfg["qubit_ef_freq"], gen_ch=self.cfg["qubit_ch"])

        # Declare the pulses
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=self.qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.qubit_ge_freq, phase=0,
                                     gain=cfg["start"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     mode="periodic")

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 ) # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):

        #wait 10ns
        self.sync_all(self.us2cycles(0.01))

        # Apply g-e pi pulse
        self.safe_regwi(self.q_rp, self.qreg_freq, self.qubit_ge_freq ) # Hack to set the g-e pulse frequency
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        # Apply e-f pi pulse
        self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=self.qubit_ef_freq,
                                 phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["start"],
                                 waveform="qubit")
        self.mathi(self.q_rp, self.qreg_gain, self.qreg_gain_ef, "+", 0)
        self.pulse(ch=self.cfg['qubit_ch'])  # play ef probe pulse

        self.sync_all(self.us2cycles(0.01))  # wait 10ns after pulse ends

        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.qreg_gain, self.qreg_gain, '+', self.cfg["step"]) # update frequency list index
        self.mathi(self.q_rp, self.qreg_gain_ef, self.qreg_gain_ef, '+', self.cfg["qubit_ef_gain"])

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0].reshape((self.cfg["expts"],self.cfg["reps"]))/self.us2cycles(self.cfg['read_length'], ro_ch = 0)

        return shots_i0,shots_q0



# ====================================================== #

class SingleShotProgram_g_e_f(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramSingleShotgef(self.soccfg, self.cfg)
        shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)

        i_g = shots_i0[0]
        q_g = shots_q0[0]
        i_e = shots_i0[1]
        q_e = shots_q0[1]

        data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
        self.data = data

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=20) ### arbitrary ran, change later

        # stop = 100
        # plt.figure(101)
        # plt.plot(i_g[0:stop], q_g[0:stop], 'o')
        # plt.plot(i_e[0:stop], q_e[0:stop], 'o')
        # plt.show()


        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, save_fig = True, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_g = data["data"]["i_g"]
        q_g = data["data"]["q_g"]
        i_e = data["data"]["i_e"]
        q_e = data["data"]["q_e"]

        #### plotting is handled by the helper histogram
        title = ('Read Length: ' + str(self.cfg["read_length"]) + "us, freq: " + str(self.cfg["read_pulse_freq"])
                    + "MHz, gain: " + str(self.cfg["read_pulse_gain"]) )
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=plotDisp, ran=ran, title = title)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        if plotDisp:
            plt.show(block = False)
            plt.pause(0.1)

        if save_fig:
            plt.savefig(self.iname)


        # else:
            # fig.clf(True)
            # plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


