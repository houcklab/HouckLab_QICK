### This experiment just outputs a constant tone on a given chanel at a given frequency and gain.
# Note that the RFSOC will continue playing the tone after the experiment is complete, until THIS CHANNEL
# is told to play something else, e.g. if we play a tone on channel 1, then run this experiment for channel 0,
# both channel 1 AND channel 0 will continue playing their respective tones.

from qick import AveragerProgram
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass

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

        a, b = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass # No data to display

    def save_data(self, data=None):
        pass # No data collected