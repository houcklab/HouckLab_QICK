from qick import *
# from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Pyro4 import Proxy
from qick import QickConfig

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF

# import qick
# print("Test", qick.__file__)

class CavitySpecFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch = self.cfg["res_ch"]))

        FF.FFDefinitions(self)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        cfg = self.cfg
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        # self.pulse(ch=self.cfg["res_ch"],t=0)
        #
        # self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
        #                          length=self.us2cycles(cfg["length"], gen_ch = self.cfg["res_ch"]))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]), gen_t0=self.gen_t0)

        #
        # self.synci(200) # give processor time to get ahead of the pulses
        # self.trigger(adcs=self.ro_chs, pins=[0],adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        # self.pulse(ch=self.cfg["res_ch"],t=0)
        #
        # # control should wait until the readout is over
        # self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"])+self.us2cycles(self.cfg["readout_length"]))
        # self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]))  # sync all channels

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    # ====================================================== #

class CavitySpecFFMUX(ExperimentClassPlus):
    """
    Transmission Experiment basic
    """

    # Config Template
    config_template = {'res_ch': 6, 'qubit_ch': 4, 'mixer_freq': 500, 'ro_chs': [0], 'reps': 20, 'nqz': 1, 'qubit_nqz': 2, 'relax_delay': 200, 'res_phase': 0, 'pulse_style': 'const', 'length': 20, 'pulse_gain': 11000, 'adc_trig_offset': 0.5, 'cavity_LO': 6800000000.0, 'cavity_winding_freq': 1.0903695, 'cavity_winding_offset': -15.77597, 'Additional_Delays': {'1': {'channel': 4, 'delay_time': 0}}, 'readout_length': 3, 'pulse_freq': -321.5, 'pulse_gains': [0.34375], 'pulse_freqs': [-321.5], 'TransSpan': 1.5, 'TransNumPoints': 61, 'cav_relax_delay': 30, 'qubit_pulse_style': 'const', 'qubit_gain': 100, 'qubit_freq': 4401.7, 'qubit_length': 100, 'SpecSpan': 20, 'SpecNumPoints': 51, 'step': 0.8, 'start': 4381.7, 'expts': 51, 'FF_Qubits': {'1': {'channel': 2, 'delay_time': 0.005, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}, '2': {'channel': 3, 'delay_time': 0.0, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}, '3': {'channel': 0, 'delay_time': 0.002, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}, '4': {'channel': 1, 'delay_time': 0.0, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0}}, 'Read_Indeces': [1], 'cavity_min': True, 'rounds': 20}

    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig]

    ### Plotting parameters
    cavity_LO = 0
    pulse_freqs = []

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg = hardware
        CavitySpecFFMUX.cavity_LO = self.cfg["cavity_LO"]
        CavitySpecFFMUX.pulse_freqs = self.cfg["pulse_freqs"]


    def acquire(self, progress=False):
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        print(results)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        CavitySpecFFMUX.cavity_LO = self.cfg["cavity_LO"]
        CavitySpecFFMUX.pulse_freqs = self.cfg["pulse_freqs"]

        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        # print(data)
        if 'data' in data:
            data = data['data']

        for i in range(len(data['results'][0])):
            avgi = data['results'][0][i][0]
            avgq = data['results'][0][i][1]
            x_pts = (data['fpts'] + CavitySpecFFMUX.cavity_LO / 1e6) / 1e3  #### put into units of frequency GHz
            print(CavitySpecFFMUX.pulse_freqs)
            x_pts += CavitySpecFFMUX.pulse_freqs[i] / 1e3
            sig = avgi + 1j * avgq

            avgamp0 = np.abs(sig)

            # Create structured data
            prepared_data = {
                "plots": [
                    {"x": x_pts, "y": avgi, "xlabel": "Cavity Frequency (GHz)", "ylabel": "a.u."},
                    {"x": x_pts, "y": avgq, "xlabel": "Cavity Frequency (GHz)", "ylabel": "a.u."},
                    {"x": x_pts, "y": avgamp0, "xlabel": "Cavity Frequency (GHz)", "ylabel": "a.u."},
                ]
            }

            p = plot_widget.addPlot(title="Cavity Transmission")
            p.addLegend()
            p.setLabel('bottom', "Cavity Frequency (GHz)")
            p.setLabel('left',  "a.u.")

            colors = ["r", 'g', 'b']
            for i, plot in enumerate(prepared_data["plots"]):
                p.plot(plot["x"], plot["y"], pen=colors[i], symbol='o', symbolSize=5, symbolBrush='b')
            plot_widget.nextRow()

            plots.append(p)

        return

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        for i in range(len(data['data']['results'][0])):
            avgi = data['data']['results'][0][i][0]
            avgq = data['data']['results'][0][i][1]
            x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"] / 1e6) / 1e3  #### put into units of frequency GHz
            x_pts += self.cfg['pulse_freqs'][i] / 1e3
            sig = avgi + 1j * avgq

            avgamp0 = np.abs(sig)

            plt.figure(figNum)
            plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
            plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
            plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
            plt.ylabel("a.u.")
            plt.xlabel("Cavity Frequency (GHz)")
            plt.title(self.titlename)
            plt.legend()

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=True)
                plt.pause(0.1)
            plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





