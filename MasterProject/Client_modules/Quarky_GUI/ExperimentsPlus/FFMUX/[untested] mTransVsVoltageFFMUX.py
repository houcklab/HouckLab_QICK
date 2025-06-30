"""
======================
mSpecVsVoltageFFMUX.py
======================
A Fast Flux Spec Multiplex vs Voltage experiment. Takes any voltageInterface of type Qblox or Yoko to perform voltage sweep.
Plots using matplotlib that the GUI intercepts.
Also a good example of using intermediate_data signal to emit data from within a set for more frequent data updates.

plotter (pyqtgraph): provided
display (matplotlib): provided
"""

from qick import *
import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
import pyqtgraph as pg
from qick.helpers import gauss
from tqdm.notebook import tqdm
from Pyro4 import Proxy
from qick import QickConfig
from PyQt5.QtCore import pyqtSignal

from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
import MasterProject.Client_modules.Quarky_GUI.ExperimentsPlus.FFMUX.FF_utils as FF

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
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
# ====================================================== #

class TransVsVoltage(ExperimentClassPlus):
    """
    Spec experiment that finds the qubit spectrum as a function of flux
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through voltage
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    ### The signal sent to the experiment thread if any intermediate data is sent
    intermediateData = pyqtSignal(object)  # argument is ip_address

    # TODO: trim the current config template. The below trim is not tested yet and may be missing some things
    ### define the template config
    config_template = {'res_ch': 6, 'qubit_ch': 4, 'mixer_freq': 500, 'ro_chs': [0], 'reps': 20, 'nqz': 1, 'qubit_nqz': 2,
         'relax_delay': 200, 'res_phase': 0, 'pulse_style': 'const', 'length': 20, 'pulse_gain': 5500,
         'adc_trig_offset': 0.5, 'cavity_LO': 6700000000.0, 'cavity_winding_freq': 1.0903695,
         'cavity_winding_offset': -15.77597, 'Additional_Delays': {'1': {'channel': 4, 'delay_time': 0}},
         'has_mixer': True, 'readout_length': 3, 'pulse_freq': -9.75, 'pulse_gains': [0.171875], 'pulse_freqs': [-9.75],
         'TransSpan': 1.5, 'TransNumPoints': 61, 'cav_relax_delay': 30, 'qubit_pulse_style': 'const',
         'qubit_gain': 1500, 'qubit_freq': 4608, 'qubit_length': 100, 'SpecSpan': 200, 'SpecNumPoints': 101,
         'step': 5.714285714285714, 'start': 4408, 'expts': 71,
         'FF_Qubits': {'1': {'channel': 2, 'delay_time': 0.005, 'Gain_Readout': 10000, 'Gain_Expt': 0, 'Gain_Pulse': 0},
                       '2': {'channel': 3, 'delay_time': 0.0, 'Gain_Readout': 0, 'Gain_Expt': 0, 'Gain_Pulse': 0},
                       '3': {'channel': 0, 'delay_time': 0.002, 'Gain_Readout': 10000, 'Gain_Expt': 0,
                             'Gain_Pulse': 10000},
                       '4': {'channel': 1, 'delay_time': 0.0, 'Gain_Readout': 10000, 'Gain_Expt': 0, 'Gain_Pulse': 0}},
         'Read_Indeces': [2], 'cavity_min': True, 'rounds': 5, 'VoltageNumPoints': 2, 'sleep_time': 0.1, 'DACs': [5],
         'VoltageStart': [-0.5], 'VoltageStop': [0], 'Gauss': False
    }

    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig, VoltageInterface]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.voltage_interface = hardware
        self.stop_flag = False

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):

        expt_cfg = {
            ### define the voltage parameters
            "VoltageStart": self.cfg["VoltageStart"],
            "VoltageStop": self.cfg["VoltageStop"],
            "VoltageNumPoints": self.cfg["VoltageNumPoints"],
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequency
            ### spec parameters
            "step": self.cfg["step"],
            "start": self.cfg["start"],
            "expts": self.cfg["expts"],
        }
        print(self.cfg["step"], self.cfg["start"], self.cfg["expts"])

        voltage_matrix = []
        # creates an n x VoltageNumPoints matrix where n should be the length of DACs
        # ie, voltageStart and VoltageStop should be n length arrays
        for n in range(len(expt_cfg["VoltageStart"])):
            voltage_matrix.append(np.linspace(expt_cfg["VoltageStart"][n],expt_cfg["VoltageStop"][n], expt_cfg["VoltageNumPoints"]))

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        self.trans_Imat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((expt_cfg["VoltageNumPoints"], expt_cfg["TransNumPoints"]))


        self.data= {
            'config': self.cfg,
            'data': {
                        'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                        'voltage_matrix': voltage_matrix
                     }
        }

        # loop over the voltageVec
        for i in range(expt_cfg["VoltageNumPoints"]):
            if self.stop_flag:
                break
            if i != 0:
                time.sleep(self.cfg['sleep_time'])

            # Setting voltages
            if 'DACs' in self.cfg:
                for m in range(len(self.cfg['DACs'])):
                    print("Setting channel " + str(self.cfg['DACs'][m]) + " to " + str(voltage_matrix[m][i]))
                    self.voltage_interface.set_voltage(voltage_matrix[m][i], [self.cfg['DACs'][m]])
            else:
                self.voltage_interface.set_voltage(voltage_matrix[0][i])
                self.cfg['DACs'] = [1]
            time.sleep(1)

            if i != expt_cfg["VoltageNumPoints"]:
                time.sleep(self.cfg['sleep_time'])

            ### take the transmission data
            data_I, data_Q = self._aquireTransData()
            self.data['data']['trans_Imat'][i,:] = data_I
            self.data['data']['trans_Qmat'][i,:] = data_Q

            # send out signal for updated data
            if i != expt_cfg["VoltageNumPoints"] - 1:
                self.intermediateData.emit(self.data)

        return self.data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        cfg = data['config']
        if 'data' in data:
            data = data['data']

        voltage_matrix = data['voltage_matrix']
        trans_fpts = np.linspace(cfg["trans_freq_start"], cfg["trans_freq_stop"], cfg["TransNumPoints"])

        X_trans = (trans_fpts + cfg["cavity_LO"]/1e6) /1e3
        X_trans_step = X_trans[1] - X_trans[0]
        Y = voltage_matrix[0]
        Y_step = Y[1] - Y[0]
        trans_Imat = data['trans_Imat']
        trans_Qmat = data['trans_Qmat']
        Z_trans = np.abs(trans_Imat + 1j * trans_Qmat)

        # Plotting
        if len(plots) == 0:  # If creating the plot for the very first time
            # Create the plot
            date_time_now = datetime.datetime.now()
            date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
            plot_title = "TransVsVoltage_" + date_time_string
            plot = plot_widget.addPlot(title=
                                       plot_title + ", Voltage Range: " + str(Y[0]) + " to" + str(
                                           Y[-1]) + ", NumPoints: " + str(len(Y)))
            plot.setLabel('left', "Voltage (V)")
            plot.setLabel('bottom', "Cavity Frequency (GHz)")

            # create the image
            image_item = pg.ImageItem()
            plot.addItem(image_item)
            image_item.setImage(np.flipud(Z_trans.T))
            image_item.setRect(
                pg.QtCore.QRectF(X_trans[0] - X_trans_step / 2, X_trans[-1] + X_trans_step / 2, Y[0] - Y_step / 2,
                                 Y[-1] + Y_step / 2)
            )

            # Create ColorBarItem
            color_map = pg.colormap.get("viridis")
            image_item.setLookupTable(color_map.getLookupTable())
            color_bar = pg.ColorBarItem(values=(np.nanmin(image_item.image), np.nanmax(image_item.image)), colorMap=color_map)
            color_bar.setImageItem(image_item, insert_in=plot)  # Add color bar to the plot
            plots.append(plot)

        else:  # Only need to update plot if already created
            plot = plots[0]
            image_item = plot.items[0]
            image_item.setImage(np.flipud(Z_trans.T), levels=image_item.levels)

        return

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    @classmethod
    def estimate_runtime(self, cfg):
        # using YOKO ramp step and interval since slower than qblox
        # total sleep + total voltage ramp time + total trans time
        ramp_step = 0.001
        ramp_interval = 0.01

        return (((cfg["VoltageNumPoints"] - 1) * 2 * cfg["sleep_time"]) +
                len(cfg["DACs"]) * (abs(cfg["VoltageStop"][0] - cfg["VoltageStart"][0])/ramp_step) * ramp_interval +
                cfg["VoltageNumPoints"] * (cfg["reps"] * cfg["TransNumPoints"] * (cfg["relax_delay"] + cfg["length"]) * 1e-6))  # [s]

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(8, 6), num=figNum)

        voltage_matrix = data['data']['voltage_matrix']
        X_trans = (self.trans_fpts + self.cfg["cavity_LO"] / 1e6) / 1e3
        X_trans_step = X_trans[1] - X_trans[0]
        Y = voltage_matrix[0]
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((self.cfg["VoltageNumPoints"], self.cfg["TransNumPoints"]), np.nan)

        for i in range(self.cfg["VoltageNumPoints"]):

            data_I = data['data']['trans_Imat'][i, :]
            data_Q = data['data']['trans_Qmat'][i, :]

            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig)
            Z_trans[i, :] = avgamp0
            if i == 1:
                ax_plot_0 = axs[0].imshow(
                    Z_trans,
                    aspect='auto',
                    extent=[np.min(X_trans)-X_trans_step/2,np.max(X_trans)+X_trans_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                    origin= 'lower',
                    interpolation= 'none',
                )
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                ax_plot_0.set_data(Z_trans)
                ax_plot_0.autoscale()
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)

        axs[0].set_ylabel("Voltage (V)")
        axs[0].set_xlabel("Cavity Frequency (GHz)")
        axs[0].set_title("Cavity Transmission")

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        plt.close(figNum)

    def _aquireTransData(self, progress=False):
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)

        return results[0][0][0], results['results'][0][0][1]

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

def Normalize_Qubit_Data(idata, qdata):
    idata_rotated = Amplitude_IQ_angle(idata, qdata)
    idata_rotated -= np.median(idata_rotated) #subtract the offset
    range_ = max(idata_rotated) - min(idata_rotated)
    if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
        idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
    idata_rotated -= min(idata_rotated)
    idata_rotated *= 1 / range_   #normalize data to have amplitude of 1

    return(idata_rotated)

def Amplitude_IQ_angle(I, Q, phase_num_points = 50):
    '''
    IQ data is inputted and it will multiply by a phase such that all of the
    information is in I
    :param I:
    :param Q:
    :param phase_num_points:
    :return: Array of data all in I quadrature
    '''
    complexarg = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complexarg * np.exp(1j * phase) for phase in phase_values]
    I_range = np.array([np.max(IQPhase.real) - np.min(IQPhase.real) for IQPhase in multiplied_phase])
    phase_index = np.argmax(I_range)
    angle = phase_values[phase_index]
    complexarg *= np.exp(1j * angle)
    return(complexarg.real)

