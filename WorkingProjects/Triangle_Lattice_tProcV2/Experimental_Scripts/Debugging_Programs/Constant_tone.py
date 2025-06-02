### This experiment just outputs a constant tone on a given chanel at a given frequency and gain.
# Note that the RFSOC will continue playing the tone after the experiment is complete, until THIS CHANNEL
# is told to play something else, e.g. if we play a tone on channel 1, then run this experiment for channel 0,
# both channel 1 AND channel 0 will continue playing their respective tones.

from qick import AveragerProgram
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import Pyro4.util

# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q_2QGates import *
import time
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.SQ_RB_Helpers import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import soc, soccfg
# soc, soccfg = makeProxy_RFSOC_11()

#TODO UPDATE FOR TPROC_V2

class ConstantTone(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        # for ch in cfg["ro_chs"]:
        #     self.declare_readout(ch=ch, length=self.us2cycles(1),
        #                          freq=cfg["freq"], gen_ch=cfg["channel"])

        freq = self.freq2reg(self.cfg["freq"], gen_ch=self.cfg["channel"])#, ro_ch=self.cfg["ro_chs"][0])  # convert to dac register value
        # self.declare_gen(ch=self.cfg["channel"], nqz=self.cfg["nqz"])
        self.declare_gen(ch=cfg["channel"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=[cfg["freq"]],
                         mux_gains=[cfg["gain"] /32766 ],
                         ro_ch=0)
        self.set_pulse_registers(ch=cfg["channel"], style="const", mask=[0],
                                 length=self.us2cycles(600000))#, mode="periodic")
        # self.set_pulse_registers(ch=self.cfg["channel"], style="const", freq=freq, phase=0, gain=self.cfg["gain"],
        #                          length=self.us2cycles(1), mode="periodic")
        #self.sync_all(self.us2cycles(0.5)) # TODO unnecessary, probably
        self.synci(200)
    def body(self):
        self.pulse(ch=self.cfg["channel"])  # play probe pulse
        # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

    def update(self):
        pass # Nothing to update

    ## define the template config
    ################################# code for outputting a single cw tone
    config_template = {
        ###### cavity
        "read_pulse_style": "const",  # --Fixed
        "gain": 30000, # [DAC units]
        "freq": 7392, # [MHz]
        "channel": 0, # TODO default value
        "nqz": 2,     # TODO default value
    }

# ====================================================== #

class ConstantTone_Experiment(ExperimentClass):
    """
    This experiment just sets the RFSOC to output a constant tone on a given chanel at a given frequency and gain.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ConstantTone(self.soccfg, self.cfg)

        # a, b = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False)#, debug=False)
        #a = prog.acquire(self.soc) #, load_pulses=True)
        prog.run_rounds(self.soc) # Necessary instead of acquire, since we are not collecting any results
    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass # No data to display

    def save_data(self, data=None):
        pass # No data collected


LO_FREQ = 6800
MIXER_FREQ = 500
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 0,  # [DAC units]
    "reps": 1,
    "rounds":1,
    "mixer_freq": MIXER_FREQ,
    "freq": 7555.8 - MIXER_FREQ - LO_FREQ,#3713,  # [MHz]

    "channel": 6, #0,  # TODO default value # 0 is resonator, 1 is qubit
    "nqz": 1, #2,#1,  # TODO default value
}
print("Freq:", UpdateConfig["freq"])

config = UpdateConfig
outerFolder = ''

ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
try:
    ConstantTone_Experiment.acquire(ConstantTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
ConstantTone_Experiment.save_data(ConstantTone_Instance)
ConstantTone_Experiment.save_config(ConstantTone_Instance)