from qick import *
from tqdm import tqdm
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass


# helper functions
def hist(data=None, plot=True, ran=1.0):
    ig = data[0]
    qg = data[1]
    ie = data[2]
    qe = data[3]

    numbins = 200

    xg, yg = np.median(ig), np.median(qg)
    xe, ye = np.median(ie), np.median(qe)

    if plot == True:
        fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(16, 4))
        fig.tight_layout()

        axs[0].scatter(ig, qg, label='g', color='b', marker='*')
        axs[0].scatter(ie, qe, label='e', color='r', marker='*')
        axs[0].scatter(xg, yg, color='k', marker='o')
        axs[0].scatter(xe, ye, color='k', marker='o')
        axs[0].set_xlabel('I (a.u.)')
        axs[0].set_ylabel('Q (a.u.)')
        axs[0].legend(loc='upper right')
        axs[0].set_title('Unrotated')
        axs[0].axis('equal')
    """Compute the rotation angle"""
    theta = -np.arctan2((ye - yg), (xe - xg))
    """Rotate the IQ data"""
    ig_new = ig * np.cos(theta) - qg * np.sin(theta)
    qg_new = ig * np.sin(theta) + qg * np.cos(theta)
    ie_new = ie * np.cos(theta) - qe * np.sin(theta)
    qe_new = ie * np.sin(theta) + qe * np.cos(theta)

    """New means of each blob"""
    xg, yg = np.median(ig_new), np.median(qg_new)
    xe, ye = np.median(ie_new), np.median(qe_new)

    # print(xg, xe)

    xlims = [xg - ran, xg + ran]
    ylims = [yg - ran, yg + ran]

    if plot == True:
        axs[1].scatter(ig_new, qg_new, label='g', color='b', marker='*')
        axs[1].scatter(ie_new, qe_new, label='e', color='r', marker='*')
        axs[1].scatter(xg, yg, color='k', marker='o')
        axs[1].scatter(xe, ye, color='k', marker='o')
        axs[1].set_xlabel('I (a.u.)')
        axs[1].legend(loc='lower right')
        axs[1].set_title('Rotated')
        axs[1].axis('equal')

        """X and Y ranges for histogram"""

        ng, binsg, pg = axs[2].hist(ig_new, bins=numbins, range=xlims, color='b', label='g', alpha=0.5)
        ne, binse, pe = axs[2].hist(ie_new, bins=numbins, range=xlims, color='r', label='e', alpha=0.5)
        axs[2].set_xlabel('I(a.u.)')

    else:
        ng, binsg = np.histogram(ig_new, bins=numbins, range=xlims)
        ne, binse = np.histogram(ie_new, bins=numbins, range=xlims)

    """Compute the fidelity using overlap of the histograms"""
    contrast = np.abs(((np.cumsum(ng) - np.cumsum(ne)) / (0.5 * ng.sum() + 0.5 * ne.sum())))
    tind = contrast.argmax()
    threshold = binsg[tind]
    fid = contrast[tind]
    axs[2].set_title(f"Fidelity = {fid * 100:.2f}%")

    return fid, threshold, theta

# Load bitstream with custom overlay
#soc = QickSoc()
# Since we're running locally on the QICK, we don't need a separate QickConfig object.
# If running remotely, you could generate a QickConfig from the QickSoc:
#     soccfg = QickConfig(soc.get_cfg())
# or save the config to file, and load it later:
#     with open("qick_config.json", "w") as f:
#         f.write(soc.dump_cfg())
#     soccfg = QickConfig("qick_config.json")
#soccfg = soc
soc, soccfg = makeProxy()

# hw_cfg={#"jpa_ch":6,
#         "res_ch":0,
#         "qubit_ch":1,
#         #"storage_ch":0
#        }
# readout_cfg={
#     "readout_length":soccfg.us2cycles(10.0, gen_ch=0), # [Clock ticks] # gen ch was 5
#     "f_res": 5988.3, # [MHz]
#     "res_phase": 0,
#     "adc_trig_offset":0, # [Clock ticks]
#     "res_gain":8000
#     }
# qubit_cfg={
#     "sigma":0.5, # [us]
#     "pi_gain": 12500,
#     "pi2_gain":11500//2, # // is floor division
#     "f_ge":4743.041802067813,
#     "relax_delay":500
# }


class StateTrajectory(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        #         self.declare_gen(ch=cfg["jpa_ch"], nqz=1) #JPA
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
                                 length=self.us2cycles(self.cfg["read_length"], ro_ch=cfg["ro_chs"][0]), gen_ch=cfg["res_ch"])

            """
            length=self.us2cycles(self.cfg["read_length"], ro_ch=cfg["ro_chs"][0])
            """

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        # self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
        #                          gain=cfg["read_pulse_gain"],
        #                          length=self.us2cycles(self.cfg["read_length"], gen_ch=qubit_ch),
        #                          )  # mode="periodic")

        # self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
        #                          gain=cfg["read_pulse_gain"],
        #                          length=self.us2cycles(30.0, gen_ch=qubit_ch),
        #                          )  # mode="periodic")
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length = self.us2cycles(self.cfg["read_length"], gen_ch=cfg["ro_chs"][0]),
                                 )  # mode="periodic")



        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        cfg = self.cfg
        if cfg["do_pulse"]:
            self.pulse(ch=self.cfg["qubit_ch"])  # play qubit pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        # self.measure(pulse_ch=cfg["res_ch"],
        #              adcs=[0],
        #              adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
        #              t=0,
        #              wait=True,
        #              syncdelay=self.us2cycles(cfg["relax_delay"]))

        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0])
                     )  # trigger the adc acquisition


class TimeOfFlight(ExperimentClass):
    """
    find the state trajecoty during the measurement
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### config = {**hw_cfg, **readout_cfg, **qubit_cfg, **expt_config}
        config_nopulse = {"do_pulse": False, **self.cfg}
        config_pulse = {"do_pulse": True, **self.cfg}

        prog_nopulse = StateTrajectory(self.soccfg, config_nopulse)
        adc1_nopulse = prog_nopulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)

        prog_pulse = StateTrajectory(self.soccfg, config_pulse)
        adc1_pulse = prog_pulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)

        ###### NOTE: clock tick is about 2.3ns
        ### extract out the I and Q trajectoires, 0 means no pulse, 1 means pulse
        I_0 = adc1_nopulse[0][0]
        Q_0 = adc1_nopulse[0][1]

        I_1 = adc1_pulse[0][0]
        Q_1 = adc1_pulse[0][1]

        #### loop and add together trajectoires
        loop_len = self.cfg["loop_num"]
        for idx in range(loop_len):
            self.cfg["adc_trig_offset"] += self.cfg["read_length"]

            config_nopulse = {"do_pulse": False, **self.cfg}
            config_pulse = {"do_pulse": True, **self.cfg}

            prog_nopulse = StateTrajectory(soccfg, config_nopulse)
            adc1_nopulse = prog_nopulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)

            prog_pulse = StateTrajectory(soccfg, config_pulse)
            adc1_pulse = prog_pulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)

            ###### NOTE: clock tick is about 2.3ns
            ### extract out the I and Q trajectoires, 0 means no pulse, 1 means pulse
            I_0 = np.append(I_0, adc1_nopulse[0][0])
            Q_0 = np.append(Q_0, adc1_nopulse[0][1])

            I_1 = np.append(I_1, adc1_pulse[0][0])
            Q_1 = np.append(Q_1, adc1_pulse[0][1])

        #### create time vector given the number of samples
        time_vec = np.linspace(0, config["read_length"] * (loop_len + 1), len(I_0))


        #### save the data
        data = {'config': self.cfg, 'data': {
            "time_vec": time_vec, 'I_0': I_0, 'Q_0': Q_0, 'I_1': I_1, 'Q_1': Q_1,
        }
                }

        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data

        I_0 = data["data"]["I_0"]
        Q_0 = data["data"]["Q_0"]

        I_1 = data["data"]["I_1"]
        Q_1 = data["data"]["Q_1"]

        time_vec = data["data"]["time_vec"]

        ##### plot
        figNum = 111
        alpha = 0.9
        fig = plt.figure(layout="constrained", figsize=(12, 8), num=figNum)
        gs = GridSpec(4, 4, figure=fig)
        ax1 = fig.add_subplot(gs[0:2, :2])
        # identical to ax1 = plt.subplot(gs.new_subplotspec((0, 0), colspan=3))
        ax2 = fig.add_subplot(gs[2:4, :2])
        ax3 = fig.add_subplot(gs[:, 2:])

        ax1.plot(time_vec, I_0, '-', alpha=alpha, label="no pulse")
        ax1.plot(time_vec, I_1, '-', alpha=alpha, label="with pulse")
        ax1.set_xlabel("readout time (us)")
        ax1.set_ylabel("I value (adc units)")

        ax2.plot(time_vec, Q_0, '-', alpha=alpha)
        ax2.plot(time_vec, Q_1, '-', alpha=alpha)
        ax2.set_xlabel("readout time (us)")
        ax2.set_ylabel("Q value (adc units)")

        ### plot the blobs
        ax3.plot(I_0, Q_0, alpha=alpha)
        ax3.plot(I_1, Q_1, alpha=alpha)
        ax3.set_xlabel("I value (adc units)")
        ax3.set_ylabel("Q value (adc units)")

        plt.tight_layout()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

        #######################################

# ####################################### code for looking at state trajecotry
UpdateConfig = {
    ##### set yoko
    "yokoVoltage": 0,
    ###### cavity
    "reps": 1,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "read_length": 2.3, # [Clock ticks]
    "read_pulse_gain": 4000, # [DAC units]
    "read_pulse_freq": 5753.5, # [MHz]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 15000,
    # "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.088,  ### units us
    # "flat_top_length": 0.300,  ### in us
    "qubit_freq": 4655.75,
    "relax_delay": 1000,  ### turned into us inside the run function
    # #### define shots
    # "shots": 2000, ### this gets turned into "reps"

    ######## misc
    "soft_avgs": 10000,
    "adc_trig_offset": 0.40 + 0.14 + 0.15, #0.475, #+ 1, #soc.us2cycles(0.468-0.02), # [Clock ticks]
    "loop_num": 0, ### number of readouts to perform
}
config = BaseConfig | UpdateConfig

#### update the qubit and cavity attenuation
# yoko1.SetVoltage(config["yokoVoltage"])

# ##### run actual experiment
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_09_BF2_cooldown_5\\TT1\\"

#### change gain instead of attenuation
Instance_TimeOfFlight = TimeOfFlight(path="dataTestTimeOfFlight", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TimeOfFlight = TimeOfFlight.acquire(Instance_TimeOfFlight)
TimeOfFlight.save_data(Instance_TimeOfFlight, data_TimeOfFlight)
TimeOfFlight.save_config(Instance_TimeOfFlight)
TimeOfFlight.display(Instance_TimeOfFlight, data_TimeOfFlight, plotDisp=True)

plt.show()
