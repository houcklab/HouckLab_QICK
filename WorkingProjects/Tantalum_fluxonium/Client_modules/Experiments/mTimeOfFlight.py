from qick import *
from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np
from STFU.Client_modules.Calib_escher.initialize import *


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

hw_cfg={#"jpa_ch":6,
        "res_ch":0,
        "qubit_ch":1,
        #"storage_ch":0
       }
readout_cfg={
    "readout_length":soccfg.us2cycles(10.0, gen_ch=0), # [Clock ticks] # gen ch was 5
    "f_res": 5988.3, # [MHz]
    "res_phase": 0,
    "adc_trig_offset":0, # [Clock ticks]
    "res_gain":8000
    }
qubit_cfg={
    "sigma":0.5, # [us]
    "pi_gain": 12500,
    "pi2_gain":11500//2, # // is floor division
    "f_ge":4743.041802067813,
    "relax_delay":500
}


class LoopbackProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        #         self.declare_gen(ch=cfg["jpa_ch"], nqz=1) #JPA
        self.declare_gen(ch=cfg["res_ch"], nqz=2)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=1) #Qubit
        #         self.declare_gen(ch=cfg["storage_ch"], nqz=2) #Storage

        for ch in [0]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["frequency"], gen_ch=cfg["res_ch"])

        freq = self.freq2reg(cfg["frequency"], gen_ch=cfg["res_ch"],
                             ro_ch=0)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                 length=cfg["pulse_length"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"]),
                       length=self.us2cycles(self.cfg["sigma"]) * 4)
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=self.cfg["pi_gain"],
                                 waveform="qubit")

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        cfg = self.cfg
        if cfg["do_pulse"]:
            self.pulse(ch=self.cfg["qubit_ch"])  # play qubit pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        self.measure(pulse_ch=cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=cfg["adc_trig_offset"],
                     t=0,
                     wait=True,
                     syncdelay=self.us2cycles(cfg["relax_delay"]))



expt_config = {
    "reps": 1,  # --Fixed
    "pulse_length": 800,  # [Clock ticks]
    "readout_length": 1000,  # [Clock ticks]
    "pulse_gain": 11000,  # [DAC units]
    "frequency": 5988.21,  # [MHz]
    "adc_trig_offset": 200,  # [Clock ticks]
    "soft_avgs": 1000,
    "qubit_freq": 1715.6, # [MHz]
}


config = {**hw_cfg, **readout_cfg, **qubit_cfg, **expt_config}
config_nopulse = {"do_pulse": False, **config}
config_pulse = {"do_pulse": True, **config}

prog_nopulse = LoopbackProgram(soccfg, config_nopulse)
adc1_nopulse = prog_nopulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
# avgi_np, avgq_np = prog_nopulse.acquire(soc, threshold=None, angle=None, load_pulses=True,
#                                  readouts_per_experiment=1, save_experiments=None,
                                 # start_src="internal", progress=True, debug=False)

# print(avgi_np)
# print(avgq_np)

prog_pulse = LoopbackProgram(soccfg, config_pulse)
adc1_pulse = prog_pulse.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
# avgi_p, avgq_p = prog_pulse.acquire(soc, threshold=None, angle=None, load_pulses=True,
#                                  readouts_per_experiment=1, save_experiments=None,
#                                  start_src="internal", progress=True, debug=False)
#
# print(avgi_p)
# print(avgq_p)

# Plot results.
plt.figure()
plt.subplot(2, 2, 1, title=f"Averages = {config['soft_avgs']}", xlabel="Clock ticks", ylabel="Transmission (adc levels)")
plt.plot(adc1_nopulse[0, 0], label="I value; no pulse")
plt.plot(adc1_nopulse[0, 1], label="Q value; no pulse")
plt.plot(np.sqrt(np.square(adc1_nopulse[0, 1]) + np.square(adc1_nopulse[0, 1])), label="abs; no pulse")
#plt.plt.plt.plot(adc2[0], label="I value; ADC 1")
#plt.plot(adc2[1], label="Q value; ADC 1")
plt.legend()
# plt.axvline(readout_cfg["adc_trig_offset"])

plt.subplot(2, 2, 3, xlabel="Clock ticks", ylabel="Transmission (adc levels)")
plt.plot(adc1_pulse[0, 0], label="I value; pulse")
plt.plot(adc1_pulse[0, 1], label="Q value; pulse")
plt.plot(np.sqrt(np.square(adc1_pulse[0, 1]) + np.square(adc1_pulse[0, 1])), label="abs; pulse")
plt.legend()


plt.subplot(2, 2, 2, xlabel="I", ylabel="Q")
plt.plot(adc1_nopulse[0, 0], adc1_nopulse[0, 1], label ='No pulse')
plt.plot(adc1_pulse[0, 0], adc1_nopulse[0, 1], label ='Pulse')
plt.legend()

plt.figure()
plt.plot(adc1_pulse[0, 0] - adc1_nopulse[0, 0], label="I pulse - I no_pulse")
plt.plot(adc1_pulse[0, 1] - adc1_nopulse[0, 1], label="Q pulse - Q no_pulse")
plt.legend()

plt.show()

print('No pulse I:' + str(np.average(adc1_nopulse[0 ,0])))
print('No pulse Q:' + str(np.average(adc1_nopulse[0 ,1])))

print('Pulse I:' + str(np.average(adc1_pulse[0 ,0])))
print('Pulse Q:' + str(np.average(adc1_pulse[0 ,1])))