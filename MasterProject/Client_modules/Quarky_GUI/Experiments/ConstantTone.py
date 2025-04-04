### This experiment just outputs a constant tone on a given chanel at a given frequency and gain.
# Note that the RFSOC will continue playing the tone after the experiment is complete, until THIS CHANNEL
# is told to play something else, e.g. if we play a tone on channel 1, then run this experiment for channel 0,
# both channel 1 AND channel 0 will continue playing their respective tones.

from qick import AveragerProgram
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.Init.initialize import BaseConfig
import Pyro4.util

class ConstantTone(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        freq = self.freq2reg(self.cfg["freq"], gen_ch=self.cfg["channel"], ro_ch=self.cfg["ro_chs"][0])  # convert to dac register value
        self.declare_gen(ch=self.cfg["channel"], nqz=self.cfg["nqz"])
        self.set_pulse_registers(ch=self.cfg["channel"], style="const", freq=freq, phase=0, gain=self.cfg["gain"],
                                 length=self.us2cycles(1), mode="periodic")
        self.sync_all(self.us2cycles(0.5)) # TODO unnecessary, probably

    def body(self):
        self.pulse(ch=self.cfg["channel"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

    def update(self):
        pass # Nothing to update

    ## define the template config
    ################################# code for outputting a single cw tone
    config_template = {
        ###### cavity
        "read_pulse_style": "const",  # --Fixed
        "gain": 1000, # [DAC units]
        "freq": 2000, # [MHz]
        "channel": 1, # TODO default value
        "nqz": 1,     # TODO default value
        "sets": 1,
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

        prog.run_rounds(self.soc)

        return {'data': {}}

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass # No data to display

    def save_data(self, data=None):
        pass # No data collected






#%%
# TITLE: Constant Tone Experiment
exp_cfg = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 10000, # [DAC units]
    "freq": 500, # [MHz]
    "channel": 6, # TODO default value
    "nqz": 1,     # TODO default value
    "sets": 1,
}
config = BaseConfig | exp_cfg
outerFolder = r"C:\Users\newforce\Desktop\HouckLab_QICK\MasterProject\Client_modules\Quarky_GUI"
soc, soccfg = makeProxy("192.168.1.137")
ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
try:
    ConstantTone_Experiment.acquire(ConstantTone_Instance)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
ConstantTone_Experiment.save_data(ConstantTone_Instance)
ConstantTone_Experiment.save_config(ConstantTone_Instance)

# using the 10MHz-1GHz balun
# f_center = 10e9 #Hz
# settings = set_filter(f_center)
# print(settings)