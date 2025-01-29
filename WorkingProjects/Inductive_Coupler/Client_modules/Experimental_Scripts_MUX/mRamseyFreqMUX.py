from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF
from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox


class T2RProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase=self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, cfg["start"])
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi2_gain"],
                                 waveform="qubit")

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)

        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update the time between two π/2 pulses


# ====================================================== #


class RamseyFreqCal(ExperimentClass):
    """
    Spec experiment that performs multiple Ramseys, plotted as a function of qubit frequency
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None, qblox = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, qblox = qblox)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):
        expt_cfg = {
            ### define the frequency sweep parameters
            "freqStart": self.cfg["freqStart"],
            "freqStop": self.cfg["freqStop"],
            "freqNumPoints": self.cfg["freqNumPoints"],

            ### spec parameters
            "step": self.cfg["step"],
            "start": self.cfg["start"],
            "expts": self.cfg["expts"],
        }
        print(self.cfg["step"], self.cfg["start"], self.cfg["expts"])

        freq_data = np.linspace(expt_cfg["freqStart"], expt_cfg["freqStop"], expt_cfg["freqNumPoints"])
        print(freq_data)
        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        # fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        fig, axs = plt.subplots(1,1, figsize = (8,6), num = figNum)

        # fig.suptitle(str(self.identifier), fontsize=16)
        ### create the time array
        self.time_pts = expt_cfg["start"] + np.arange(expt_cfg["expts"]) * expt_cfg["step"]

        X_time = self.time_pts
        X_time_step = X_time[1] - X_time[0]
        Y = freq_data
        Y_step = Y[1] - Y[0]
        Z_spec = np.full((expt_cfg["freqNumPoints"], expt_cfg["expts"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.spec_Imat = np.zeros((expt_cfg["freqNumPoints"], expt_cfg["expts"]))
        self.spec_Qmat = np.zeros((expt_cfg["freqNumPoints"], expt_cfg["expts"]))
        self.data= {
            'config': self.cfg,
            'data': {'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.time_pts,
                     'freq_data': freq_data}
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()


        #### loop over the qblox vector
        for i in range(expt_cfg["freqNumPoints"]):
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()
            ### set the pulse frequency for the specific run
            self.cfg["f_ge"] = freq_data[i]
            time.sleep(1)


            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            data_I = data_I[0]
            data_Q = data_Q[0]

            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q

            avgamp0 = np.abs(sig)
            if smart_normalize:
                # avgamp0 = Normalize_Qubit_Data(data_I[0], data_Q[0])
                avgamp0 = Amplitude_IQ_angle(data_I[0], data_Q[0])
            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            if i == 0:
                ax_plot_1 = axs.imshow(
                    Z_spec,
                    aspect='auto',
                    extent=[X_time[0]-X_time_step/2,X_time[-1]+X_time_step/2,Y[0]-Y_step/2,Y[-1]+Y_step/2],
                    origin='lower',
                    interpolation = 'none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_spec)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs.set_ylabel("Pulse Frequency (MHz)")
            axs.set_xlabel("Time delay (us)")
            axs.set_title(f"{self.titlename}, "
                             f"Cav Freq: {np.round(self.cfg['pulse_freqs'][0] + self.cfg['mixer_freq'] + self.cfg['cavity_LO'] / 1e6, 3)}")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start ### time for single full row in seconds
                timeEst = (t_delta )*expt_cfg["freqNumPoints"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname) #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)
        else:
            plt.show(block=True)

        return self.data


    def _aquireSpecData(self, progress=False):
        prog = T2RProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        return avgi, avgq

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# def Normalize_Qubit_Data(idata, qdata):
#     idata_rotated = Amplitude_IQ_angle(idata, qdata)
#     idata_rotated -= np.median(idata_rotated) #subtract the offset
#     range_ = max(idata_rotated) - min(idata_rotated)
#     idata_rotated *= 1 / range_   #normalize data to have amplitude of 1
#     if np.abs(max(idata_rotated)) < np.abs(min(idata_rotated)):
#         idata_rotated *= -1 #ensures that the spec has a peak rather than a dip
#     return(idata_rotated)

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

