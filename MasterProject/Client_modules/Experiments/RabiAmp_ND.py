#### ND averager program

import datetime
import pyqtgraph as pg
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Helpers.Amplitude_IQ import Amplitude_IQ

import numpy as np
import matplotlib.pyplot as plt

class RabiAmp_ND(NDAveragerProgram):

    def initialize(self):

        #### state varibles for sweeping in order of assignment
        self.sweep_var = []

        ### declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])  # Qubit

        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        ### define initial freq and gain
        q_freq = self.freq2reg(self.cfg["qubit_freq_start"], gen_ch=self.cfg["qubit_ch"])
        q_gain = self.cfg["qubit_gain_start"]

        read_freq = self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"], ro_ch=self.cfg["ro_chs"][0])


        ### start with setting the readout tone
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        #### define the qubit pulse depending on the pulse type
        if self.cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=q_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=q_gain,
                                     waveform="qubit")

        elif self.cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=self.cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=self.cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=q_freq,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]), gain=q_gain,
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))

        elif self.cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=q_freq, phase=0,
                                     gain=q_gain,
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]), )
                                     #mode="periodic")
        else:
            print("define arb, const, or flat top pulse")

        #### add pulse gain and phase sweep, first added will be first swept

        #### add the sweeps if number of experiments is correct
        if self.cfg["qubit_gain_expts"] > 1:
            self.sweep_var.append("Qubit Gain (a.u.)")
            self.qubit_r_gain = self.get_gen_reg(self.cfg["qubit_ch"], "gain")
            self.qubit_r_gain_update = self.new_gen_reg(self.cfg["qubit_ch"], init_val=self.cfg["qubit_gain_start"],
                                                        name="gain_update", reg_type="gain")
            self.add_sweep(
                QickSweep(self, self.qubit_r_gain_update, self.cfg["qubit_gain_start"], self.cfg["qubit_gain_stop"],
                          self.cfg["qubit_gain_expts"]))

        if self.cfg["qubit_freq_expts"] > 1:
            self.sweep_var.append("Qubit Freq (MHz)")
            self.qubit_r_freq = self.get_gen_reg(self.cfg["qubit_ch"], "freq")
            self.qubit_r_freq_update = self.new_gen_reg(self.cfg["qubit_ch"], init_val=self.cfg["qubit_freq_start"],
                                                        name="freq_update", reg_type="freq")
            self.add_sweep(
                QickSweep(self, self.qubit_r_freq_update, self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                          self.cfg["qubit_freq_expts"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def body(self):

        if self.cfg["qubit_gain_expts"] > 1:
            self.qubit_r_gain.set_to(self.qubit_r_gain_update, "+", 0)
        if self.cfg["qubit_freq_expts"] > 1:
            self.qubit_r_freq.set_to(self.qubit_r_freq_update, "+", 0)

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    ### define the template config
    config_template = {
        ##### define attenuators
        "yokoVoltage": 0.25,
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
        "sets": 1, # number of interations to loop over experiment
    }


# ====================================================== #

class RabiAmp_ND_Experiment(ExperimentClass):
    """
    Basic amplitude rabi experiment that can sweep both amplitude and frequecny
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        ##### code to aquire just the qubit spec data
        prog = RabiAmp_ND(self.soccfg, self.cfg)

        ### in the following the data are arrays in the dimensionality of swept varibles
        x_pts, avgi, avgq = prog.acquire(self.soc, load_pulses=True, progress=True)

        # print(avgi)
        # print(avgi[0][0])

        self.avg_abs = Amplitude_IQ(np.array(avgi), np.array(avgq))
        self.avg_angle = np.angle(np.array(avgi) + 1j * np.array(avgq))

        data = {'config': self.cfg, 'data': {'sweeps': {}, 'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq,
                                             'avg_abs': self.avg_abs, 'avg_angle': self.avg_angle}}

        ### store the sweep axes
        if len(x_pts) == 1:
            self.xlabel = prog.sweep_var[0]
            data['data']['sweeps']['xlabel'] = self.xlabel
        else:
            self.xlabel = prog.sweep_var[1]
            self.ylabel = prog.sweep_var[0]
            data['data']['sweeps']['xlabel'] = self.xlabel
            data['data']['sweeps']['ylabel'] = self.ylabel

        self.data = data
        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        expt_pts = data['data']['x_pts']
        avg_di = data['data']['avgi']
        avg_dq = data['data']['avgq']
        avg_abs = data['data']['avg_abs']
        avg_angle = data['data']['avg_angle']

        print(data)

        labels = ["I (a.u.)", "Q (a.u.)", "Amp (a.u.)", "Phase (deg.)"]

        prepared_data = {"plots": [], "images": []}

        if len(expt_pts) == 1:
            xlabel = data['data']['sweeps']['xlabel']
            for i, (d, label) in enumerate(zip([avg_di, avg_dq, avg_abs, avg_angle], labels)):
                prepared_data["plots"].append({
                    "x": expt_pts[0].tolist(),
                    "y": d[0][0].tolist(),
                    "label": label,
                    "xlabel": xlabel,
                    "ylabel": label
                })
        else:
            xlabel = data['data']['sweeps']['xlabel']
            ylabel = data['data']['sweeps']['ylabel']
            for i, (d, label) in enumerate(zip([avg_di, avg_dq, avg_abs, avg_angle], labels)):
                prepared_data["images"].append({
                    "data": d[0][0].T.tolist(),  # Convert NumPy array to list
                    "x": expt_pts[0].tolist(),
                    "y": expt_pts[1].tolist(),
                    "label": label,
                    "xlabel": xlabel,
                    "ylabel": ylabel,
                    "colormap": "inferno"
                })

        print(prepared_data)

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
                image_item = pg.ImageItem(np.unwrap(np.array(img["data"])))
            else:
                image_item = pg.ImageItem(np.array(img["data"]))
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
        pass

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):

        if data is None:
            data = self.data

        expt_pts = data['data']['x_pts']
        avg_di = data['data']['avgi']
        avg_dq = data['data']['avgq']

        labels = ["I (a.u.)", "Q (a.u.)", "Amp (a.u.)", "Phase (deg.)"]

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1

        ### check if the sweep is 1D
        if len(expt_pts) == 1:
            fig, axes = plt.subplots(4, 1, figsize=(8,12), num=figNum)
            for i, d in enumerate([avg_di, avg_dq, self.avg_abs, self.avg_angle]):
                axes[i].plot(expt_pts[0], d[0][0])
                axes[i].set_xlabel(self.xlabel)
                axes[i].set_ylabel(labels[i])
                axes[i].set_title(labels[i])

        else:
            ### create figure for the 2D sweep
            fig, axes = plt.subplots(4, 1, figsize=(8, 12), num=figNum)
            for i, d in enumerate([avg_di, avg_dq, self.avg_abs, self.avg_angle]):
                pcm = axes[i].pcolormesh(expt_pts[1], expt_pts[0], d[0, 0].T, shading="Auto")
                axes[i].set_xlabel(self.xlabel)
                axes[i].set_ylabel(self.ylabel)
                axes[i].set_title(labels[i])
                plt.colorbar(pcm, ax=axes[i])

                if i == 3:
                    pcm = axes[i].pcolormesh(expt_pts[1], expt_pts[0], np.unwrap(d[0, 0].T),
                                             shading="Auto")

        plt.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(2)

        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

