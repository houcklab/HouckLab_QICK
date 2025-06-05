"""
==================
mSpecSliceFFMUX.py
==================
A Fast Flux Multiplex Spec slice experiment.
Plots using pyqtgraph (recommended) but also provides a matplotlib display function.

plotter (pyqtgraph): provided
display (matplotlib): provided
"""

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Pyro4 import Proxy
from qick import QickConfig
import datetime
from tqdm.notebook import tqdm
import time

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
import MasterProject.Client_modules.Quarky_GUI.ExperimentsPlus.FFMUX.FF_utils as FF

class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])


        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]
        print(cfg["qubit_length"], self.f_start, cfg['start'], cfg["qubit_gain"])
        # self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
        #                          length=self.us2cycles(cfg["length"]))
        print(self.FFPulse)
        print(cfg["mixer_freq"], cfg["pulse_freqs"], cfg["pulse_gains"], cfg["length"], self.cfg["adc_trig_offset"])

    def body(self):

        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, self.qubit_length_us + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        # self.FFPulses(self.FFPulse, self.cfg["length"])
        # self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class QubitSpecSliceFFMUX(ExperimentClassPlus):
    """
    Basic spec experiement that takes a single slice of data
    """

    ### Config template
    config_template =  {
        'qubit_pulse_style': 'const',
        'qubit_gain': 100,
        'qubit_length': 100,
        'pulse_gains': [0.9375],
        'pulse_freqs':  [-321.5],

        'SpecNumPoints': 71,
        'step': 0.8571428571428571,
        'start': 4395,
        'expts': 51,

        'readout_length': 3,
        'length': 20,
        'Gauss': False,
        'sets': 2,
        'reps': 20,
    }

    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg = hardware

    def acquire(self, progress=False):

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0]
        avgq = data['data']['avgq'][0]
        print(avgi)
        print(avgq)
        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq = x_pts[peak_loc]

        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        # clear plot widget and array
        plot_widget.ci.clear()
        plots = []

        # print(data)
        if 'data' in data:
            data = data['data']

        x_pts = data['x_pts']
        avgi = data['avgi']
        avgq = data['avgq']

        sig = np.array(avgi).squeeze() + 1j * np.array(avgq).squeeze()
        print(sig)
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)

        # Create structured data
        prepared_data = {
            "plots": [
                {"x": x_pts, "y": avgphase, "label": "Phase", "xlabel": "Qubit Frequency (GHz)", "ylabel": "Degree"},
                {"x": x_pts, "y": avgsig, "label": "Magnitude", "xlabel": "Qubit Frequency (GHz)", "ylabel": "a.u."},
                {"x": x_pts, "y": np.abs(avgi[0][0]), "label": "I - Data", "xlabel": "Qubit Frequency (GHz)",
                 "ylabel": "a.u."},
                {"x": x_pts, "y": np.abs(avgq[0][0]), "label": "Q - Data", "xlabel": "Qubit Frequency (GHz)",
                 "ylabel": "a.u."}
            ]
        }

        date_time_now = datetime.datetime.now()
        date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        plot_title = "SpecSlice_" + date_time_string
        plot_widget.addLabel(plot_title, row=0, col=0, colspan=2, size='12pt')
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

    @classmethod
    def estimate_runtime(self, cfg):
        return cfg["reps"] * cfg["SpecNumPoints"] * (cfg["relax_delay"] + cfg["length"]) * 1e-6  # [s]

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        else:
            print(data)

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.legend()

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.close(figNum)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


