"""
=================
mAmplitudeRabi.py
=================
A Basic Amplitude Rabi experiment.
Plots using pyqtgraph (recommended) but also provides a matplotlib display function.
"""

import datetime
import pyqtgraph as pg
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
import numpy as np
import matplotlib.pyplot as plt
from Pyro4 import Proxy
from qick import QickConfig

from MasterProject.Client_modules.Helpers.Amplitude_IQ import Amplitude_IQ
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass # used to come from WTF, might cause problems
from tqdm.notebook import tqdm
import time

class LoopbackProgramAmplitudeRabi(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        #### set the start, step, and other parameters
        self.cfg["start"] = self.cfg["qubit_gain_start"]
        self.cfg["step"] = self.cfg["qubit_gain_step"]
        self.cfg["expts"] = self.cfg["qubit_gain_expts"]
        self.cfg["reps"] = self.cfg["reps"]

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch, this is the gaussian part
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get gain2 register for qubit_ch, this is the flat part

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], ro_ch = self.cfg["ro_chs"][0])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"] )

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq, phase=0, #freq=cfg["start"]
                                     gain=cfg["start"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]),
                                     )
                                     #mode="periodic")
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switc
        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        # self.sync_all(self.us2cycles(0.05)) # align channels and wait 50ns
        # If we're calibrating a pi/2 pulse:
        if self.cfg["two_pulses"]:
            self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update gain of the Gaussian part
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', self.cfg["step"] // 2) # update gain of the flat part
        # This needs to be half the normal update, because something about the "arb" gain is different from const
        # I think the reason is that arb is defined as the individual points vs. time, whereas the const is an envelope
        # over the carrier, so const gets an extra bit and so is twice as big.


# ====================================================== #

class AmplitudeRabi(ExperimentClassPlus):
    """
    Basic AmplitudeRabi
    """

    config_template = {
        ###### cavity
        "read_pulse_style": "const",  # --Fixed
        "read_length": 10,  # us
        "read_pulse_gain": 10000,  # [DAC units]
        "read_pulse_freq": 6425.3,
        ##### spec parameters for finding the qubit frequency
        "qubit_freq_start": 2869 - 10,
        "qubit_freq_stop": 2869 + 10,
        "qubit_freq_expts": 41,
        "qubit_pulse_style": "arb",
        "sigma": 0.300,  ### units us, define a 20ns sigma
        # "flat_top_length": 0.300, ### in us
        "relax_delay": 500,  ### turned into us inside the run function
        ##### amplitude rabi parameters
        "qubit_gain_start": 20000,
        "qubit_gain_stop": 30000,  ### stepping amount of the qubit gain
        "qubit_gain_expts": 3,  ### number of steps
        "reps": 50,  # number of averages for the experiment
        "sets": 1,  # number of interations to loop over experiment
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

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramAmplitudeRabi(self.soccfg, self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.remainder(np.angle(sig,deg=True)+360,360)
        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="Phase")
        axs[0].set_ylabel("Degrees")
        axs[0].set_xlabel("Qubit gain (DAC units)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="Magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Qubit gain (DAC units)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Qubit gain (DAC units)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q")
        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Qubit gain (DAC units)")
        axs[3].legend()

        fig.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)
            plt.close()
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        # clear plot widget and array
        plot_widget.ci.clear()
        plots = []

        if 'data' in data:
            data = data['data']

        expt_pts = data['x_pts']
        avg_di = data['avgi']
        avg_dq = data['avgq']
        avg_abs = data['avg_abs']
        avg_angle = data['avg_angle']

        # print(data)

        labels = ["I (a.u.)", "Q (a.u.)", "Amp (a.u.)", "Phase (deg.)"]

        prepared_data = {"plots": [], "images": []}

        if len(expt_pts) == 1:
            xlabel = data['sweeps']['xlabel']
            for i, (d, label) in enumerate(zip([avg_di, avg_dq, avg_abs, avg_angle], labels)):
                prepared_data["plots"].append({
                    "x": expt_pts[0].tolist(),
                    "y": d[0][0].tolist(),
                    "label": label,
                    "xlabel": xlabel,
                    "ylabel": label
                })
        else:
            xlabel = data['sweeps']['xlabel']
            ylabel = data['sweeps']['ylabel']
            for i, (d, label) in enumerate(zip([avg_di, avg_dq, avg_abs, avg_angle], labels)):
                prepared_data["images"].append({
                    "data": d[0][0].T.tolist(),  # Convert NumPy array to list
                    "x": expt_pts[0].tolist(),
                    "y": expt_pts[1].tolist(),
                    "label": label,
                    "xlabel": xlabel,
                    "ylabel": ylabel,
                    "colormap": "viridis"
                })

        # print(prepared_data)

        date_time_now = datetime.datetime.now()
        date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        plot_title = "RabiAmp_ND" + date_time_string
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

        for i, img in enumerate(prepared_data["images"]):
            p = plot_widget.addPlot(title=img["label"])
            p.setLabel("bottom", img["xlabel"])
            p.setLabel("left", img["ylabel"])
            p.showGrid(x=True, y=True)

            # Create ImageItem
            if i == 3:
                image_data = np.unwrap(np.array(img["data"]))
            else:
                image_data = np.array(img["data"])

            image_item = pg.ImageItem()
            image_item.setImage(np.flipud(image_data.T))

            p.addItem(image_item)
            color_map = pg.colormap.get(img["colormap"])  # e.g., 'viridis'
            image_item.setLookupTable(color_map.getLookupTable())

            # set axis
            x_data = np.array(img["x"])  # Use your actual x-axis data here
            y_data = np.array(img["y"])  # Use your actual y-axis data here
            image_item.setRect(pg.QtCore.QRectF(x_data[0], y_data[0], x_data[-1] - x_data[0], y_data[-1] - y_data[0]))

            # Create ColorBarItem
            color_bar = pg.ColorBarItem(values=(image_item.image.min(), image_item.image.max()),
                                        colorMap=color_map)
            color_bar.setImageItem(image_item, insert_in=p)  # Add color bar to the plot

            plots.append(p)
            if len(plots) % 2 == 0: plot_widget.nextRow()

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass