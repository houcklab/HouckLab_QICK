### This experiment just outputs a constant tone on a given chanel at a given frequency and gain.
# Note that the RFSOC will continue playing the tone after the experiment is complete, until THIS CHANNEL
# is told to play something else, e.g. if we play a tone on channel 1, then run this experiment for channel 0,
# both channel 1 AND channel 0 will continue playing their respective tones.

from qick import AveragerProgram
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.Init.initialize import BaseConfig
import Pyro4.util
import numpy as np

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
        "reps": 1,
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

        # default values for ZCU216 I think
        dac_max = 16383  # 14-bit DAC
        v_full_scale = 1.0  # 1.0 Vpp (differential)
        resistance = 50  # Standard RF load

        gain = self.cfg["gain"]
        freq = self.cfg["freq"]

        # 1. Period in microseconds seconds
        period = 1 / freq
        # 2. Peak Voltage from DAC gain
        v_peak = (gain / dac_max) * (v_full_scale / 2)
        # 3. RMS Voltage
        v_rms = v_peak / np.sqrt(2)
        # 4. Power in Watts
        power_watts = (v_rms ** 2) / resistance
        # 5. Power in dBm
        power_dbm = 10 * np.log10(power_watts * 1000)

        print(f"Period: {period * 1e9:.2f} μs")
        print(f"Power: {power_dbm:.2f} dBm")
        print(f"Peak Voltage: {v_peak:.3f} V")

        # 7. Plot Voltage vs Time
        t = np.linspace(0, 3 * period, 1000)
        v_t = v_peak * np.sin(2 * np.pi * freq * t)

        data = {'config': self.cfg, 'data': {'x_pts': t, 'v_t': v_t},}

        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        gain = 0
        freq = 0
        if "config" in data:
            gain = data["config"]["gain"]
            freq = data["config"]["freq"]

        if 'data' in data:
            data = data['data']

        x_pts = data['x_pts']
        v_t = data['v_t']

        # Create structured data
        prepared_data = {
            "plots": [
                {"x": x_pts, "y": v_t, "label": "Expected Voltage vs Time (μs)", "xlabel": "Time (μs)",
                 "ylabel": "Voltage (V)"},
            ]
        }

        dac_max = 16383  # 14-bit DAC
        v_full_scale = 1.0  # 1.0 Vpp (differential)
        resistance = 50  # Standard RF load

        period = 1 / freq
        v_peak = (gain / dac_max) * (v_full_scale / 2)
        v_rms = v_peak / np.sqrt(2)
        power_watts = (v_rms ** 2) / resistance
        power_dbm = 10 * np.log10(power_watts * 1000)

        period_label = f" Period: {period*1000:.3f} ns, "
        power_label = f" Power: {power_dbm:.4f} dBm, "
        peakVoltage_label = f" Peak Voltage: {v_peak:.3f} V, "

        plot_title = ("[Gain: " + str(gain) + " dBm, Freq: " + str(freq) + " Hz] Expected: " + period_label +
                      power_label + peakVoltage_label)
        plot_widget.addLabel(plot_title, row=0, col=0, colspan=2, size='8pt')

        plot_widget.nextRow()

        for i, plot in enumerate(prepared_data["plots"]):
            p = plot_widget.addPlot(title=plot["label"])
            p.addLegend()
            p.plot(plot["x"], plot["y"], pen='b', symbol='o', symbolSize=5, symbolBrush='b')
            p.setLabel('bottom', plot["xlabel"])
            p.setLabel('left', plot["ylabel"])
            plots.append(p)
            plot_widget.nextRow()

        return

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        pass # No data to display

    def save_data(self, data=None):
        pass # No data collected




#%%
# TITLE: Constant Tone Experiment
# exp_cfg = {
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "gain": 10000, # [DAC units]
#     "freq": 500, # [MHz]
#     "channel": 6, # TODO default value
#     "nqz": 1,     # TODO default value
#     "sets": 1,
# }
# config = BaseConfig | exp_cfg
# outerFolder = r"C:\Users\newforce\Desktop\HouckLab_QICK\MasterProject\Client_modules\Quarky_GUI\data\ConstantTone\data"
# soc, soccfg = makeProxy("192.168.1.137")
# ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# try:
#     ConstantTone_Experiment.acquire(ConstantTone_Instance)
# except Exception:
#     print("Pyro traceback:")
#     print("".join(Pyro4.util.getPyroTraceback()))
# ConstantTone_Experiment.save_data(ConstantTone_Instance)
# ConstantTone_Experiment.save_config(ConstantTone_Instance)

# using the 10MHz-1GHz balun
# f_center = 10e9 #Hz
# settings = set_filter(f_center)
# print(settings)