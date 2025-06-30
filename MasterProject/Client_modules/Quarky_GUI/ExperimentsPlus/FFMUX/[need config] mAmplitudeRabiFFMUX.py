from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
import datetime
from tqdm.notebook import tqdm
import time

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
import MasterProject.Client_modules.Quarky_GUI.ExperimentsPlus.FFMUX.FF_utils as FF

class AmplitudeRabiFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["res_gain"],
                                 length=self.us2cycles(cfg["res_length"]))

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        FF.FFDefinitions(self)

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        print(self.pulse_sigma, self.pulse_qubit_lenth)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                 waveform="qubit")


        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        # self.pulse(ch=self.cfg['ff_ch'])
        self.FFPulses(self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.cfg["sigma"] * 4 + 1)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update gain of the Gaussian

class AmplitudeRabiFFMUX(ExperimentClassPlus):
    """
    Basic AmplitudeRabi
    """

    config_template = {"res_ch": 6, "qubit_ch": 4, "mixer_freq": 500, "ro_chs": [0], "reps": 50, "nqz": 1, "qubit_nqz": 2, "relax_delay": 150, "res_phase": 0, "pulse_style": "const", "read_length": 5, "pulse_gain": 11000, "pulse_freq": -321.5, "adc_trig_offset": 0.5, "cavity_LO": 6800000000.0, "length": 20, "cavity_winding_freq": 1.0903695, "cavity_winding_offset": -15.77597, "Additional_Delays": {"1": {"channel": 4, "delay_time": 0}}, "readout_length": 3, "pulse_gains": [0.34375], "pulse_freqs": [-321.5], "TransSpan": 1.5, "TransNumPoints": 61, "cav_relax_delay": 30, "qubit_pulse_style": "const", "qubit_gain": 100, "qubit_freq": 4401.7, "qubit_length": 100, "SpecSpan": 20, "SpecNumPoints": 51, "step": 1, "start": 0, "expts": 150, "FF_Qubits": {"1": {"channel": 2, "delay_time": 0.005, "Gain_Readout": 0, "Gain_Expt": 0, "Gain_Pulse": 0}, "2": {"channel": 3, "delay_time": 0.0, "Gain_Readout": 0, "Gain_Expt": 0, "Gain_Pulse": 0}, "3": {"channel": 0, "delay_time": 0.002, "Gain_Readout": 0, "Gain_Expt": 0, "Gain_Pulse": 0}, "4": {"channel": 1, "delay_time": 0.0, "Gain_Readout": 0, "Gain_Expt": 0, "Gain_Pulse": 0}}, "Read_Indeces": [1], "cavity_min": true, "rounds": 50, "sigma": 0.05, "f_ge": 4401.7, "pi_gain": 10000}

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
        # You would overwrite these in the config if you wanted to
        cfg_ARabi_defaults = {'start': 0, "expts": 31, "reps": 30, "rounds": 30,
                                "f_ge": self.cfg["qubit_freqs"][0]}
        self.cfg = cfg_ARabi_defaults  | self.cfg
        self.cfg['step'] = int(self.cfg["max_gain"] / self.cfg['expts'])


        prog = AmplitudeRabiFFProg(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data

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


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.plot(x_pts, avgq, label="q", color = 'blue')
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


