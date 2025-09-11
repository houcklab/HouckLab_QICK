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
from qick.asm_v2 import AveragerProgramV2
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
# from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.SQ_RB_Helpers import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import soc, soccfg
# soc, soccfg = makeProxy_RFSOC_11()

#TODO UPDATE FOR TPROC_V2

class ConstantTone(AveragerProgramV2):

    def _initialize(self, cfg):
        # cfg = self.cfg
        # for ch in cfg["ro_chs"]:
        #     self.declare_readout(ch=ch, length=self.us2cycles(1),
        #                          freq=cfg["freq"], gen_ch=cfg["channel"])

        # freq = self.freq2reg(self.cfg["freq"], gen_ch=self.cfg["channel"])#, ro_ch=self.cfg["ro_chs"][0])  # convert to dac register value
        # self.declare_gen(ch=self.cfg["channel"], nqz=self.cfg["nqz"])
        self.declare_gen(ch=cfg["channel"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["freqs"],
                         mux_gains=[gain/32766 for gain in cfg["gains"]],
                         ro_ch=0)

        self.add_pulse(ch=cfg['channel'], name="res_pulse",
                       style="const",
                       length=600000,
                       mask=range(len(cfg["freqs"])),)
        # self.set_pulse_registers(ch=cfg["channel"], style="const", mask=[0],
        #                          length=self.us2cycles(600000))#, mode="periodic")
        # self.set_pulse_registers(ch=self.cfg["channel"], style="const", freq=freq, phase=0, gain=self.cfg["gain"],
        #                          length=self.us2cycles(1), mode="periodic")
        #self.sync_all(self.us2cycles(0.5)) # TODO unnecessary, probably

    def _body(self, cfg):
        self.pulse(self.cfg["channel"], name='res_pulse')  # play probe pulse
        # self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns


    ## define the template config
    ################################# code for outputting a single cw tone

# ====================================================== #

class ConstantTone_Experiment(ExperimentClass):
    """
    This experiment just sets the RFSOC to output a constant tone on a given chanel at a given frequency and gain.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        prog = ConstantTone(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"], final_delay=0)

        # a, b = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False)#, debug=False)
        #a = prog.acquire(self.soc) #, load_pulses=True)
        prog.run_rounds(self.soc) # Necessary instead of acquire, since we are not collecting any results
    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass # No data to display

    def save_data(self, data=None):
        pass # No data collected

    # config_template = {
    #     ###### cavity
    #     "read_pulse_style": "const",  # --Fixed
    #     "gain": 30000, # [DAC units]
    #     "freq": 7392, # [MHz]
    #     "channel": 0, # TODO default value
    #     "nqz": 1,     # TODO default value
    #     "ro_chs": [0]
    # }

LO_FREQ = 9000
MIXER_FREQ = -1750
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gains": [16000, 16000, 16000, 16000],  # [DAC units]
    "reps": 1000000,
    "rounds":1,
    "mixer_freq": MIXER_FREQ,
    "freqs": [freq-LO_FREQ for freq in [7122, 7078, 7511, 7568]], # [MHz]

    "channel": 8, #0,  # TODO default value # 8 is resonator, 9 is qubit
    "nqz": 1, #2,#1,  # TODO default value
}
print("Freq:", UpdateConfig["freqs"])

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