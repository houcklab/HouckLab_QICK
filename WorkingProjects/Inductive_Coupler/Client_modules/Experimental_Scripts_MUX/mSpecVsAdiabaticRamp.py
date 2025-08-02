from qick import *

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.AdiabaticRamps import generate_ramp
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF


# ====================================================== #
class SpecVsAdiabaticRampProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=int(self.us2cycles(cfg["readout_length"])),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=int(self.us2cycles(cfg["length"])))

        self.q_rp = int(self.ch_page(self.cfg["qubit_ch"]))  # get register page for qubit_ch
        self.r_freq = int(self.sreg(cfg["qubit_ch"], "freq"))  # get frequency register for qubit_ch

        ### Start fast flux
        FF.FFDefinitions(self)
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = int(self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"]))  # get start/step frequencies
        self.f_step = int(self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"]))


        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = int(self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"]))
            self.pulse_qubit_lenth = int(self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"]))
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"], gen_ch=self.cfg["qubit_ch"]))
            self.qubit_length_us = cfg["qubit_length"]

    def body(self):
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses_direct(self.FFExpts, self.cfg['ramp_length'], [0, 0, 0, 0], IQPulseArray=self.cfg["IDataArray"])
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses([array[-1] for array in self.cfg["IDataArray"]], self.qubit_length_us * 1.2)
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse


        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        IQ_Array_Negative = [-1 * array for array in self.cfg["IDataArray"]]
        self.FFPulses_direct(-1 * self.FFPulse, 1, -1 * self.FFPulse,
                             IQPulseArray=IQ_Array_Negative,
                             waveform_label='FF2')
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index

    def FFPulses_direct(self, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None,
                        waveform_label = "FF"):
        FF.FFPulses_direct(self, list_of_gains, length_dt, previous_gains= previous_gains, t_start = t_start,
                           IQPulseArray=IQPulseArray, waveform_label = waveform_label)

# ====================================================== #


class SpecVsAdiabaticRamp(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum during adiabatic ramp
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through qblox
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None, qblox = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, qblox = qblox)

    #### during the acquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        # fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)
        fig, axs = plt.subplots(1,1, figsize = (8,6), num = figNum)

        self.spec_fpts = self.cfg["start"] + np.arange(self.cfg["expts"]) * self.cfg["step"]

        X_spec = self.spec_fpts/1e3
        X_spec_step = X_spec[1] - X_spec[0]
        if self.cfg['double_ramp']:
            Y = np.linspace(0, 2*self.cfg['ramp_duration'], self.cfg['ramp_num_points'])
        else:
            Y = np.linspace(0, self.cfg['ramp_duration'], self.cfg['ramp_num_points'])

        Y_step = Y[1] - Y[0]
        Z_spec = np.full((self.cfg["ramp_num_points"], self.cfg["expts"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.spec_Imat = np.zeros((self.cfg["ramp_num_points"], self.cfg["expts"]))
        self.spec_Qmat = np.zeros((self.cfg["ramp_num_points"], self.cfg["expts"]))
        self.data= {
            'config': self.cfg,
            'data': {
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'ramp_times': Y
                     }
        }


        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()


        #### loop over the qblox vector
        for i in range(self.cfg['ramp_num_points']):
            if i != 0:
                time.sleep(self.cfg['sleep_time'])
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()

            ### set ramp pulse
            if self.cfg['double_ramp']:
                # if double, ramp forwards and backwards
                cutoff_index = int(i/(self.cfg['ramp_num_points'] - 1) * 2 * self.cfg['ramp_duration'])
            else:
                cutoff_index = int(i/(self.cfg['ramp_num_points'] - 1) * self.cfg['ramp_duration'])

            print("cutoff index:", cutoff_index)
            print(self.cfg['double_ramp'])
            ramp_length = 0
            for j in range(4):

                ramp = generate_ramp(0, self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp'], self.cfg['ramp_duration'], ramp_shape=self.cfg['ramp_shape'])

                if self.cfg['double_ramp']:
                    # if double, add reverse ramp to forward ramp
                    reverse_ramp = generate_ramp(self.cfg['FF_Qubits'][str(j + 1)]['Gain_Ramp'], 0,
                                                 self.cfg['ramp_duration'], reverse=True, ramp_shape=self.cfg['ramp_shape'])
                    ramp = np.concatenate([ramp, reverse_ramp])

                if j == 2:
                    print(len(ramp))
                    print(f'ramp: {ramp}')

                    print(f'ramp value: {ramp[cutoff_index]}')

                self.cfg["IDataArray"][j] = ramp[:cutoff_index]

                if len(self.cfg["IDataArray"][j]) == 0:
                    self.cfg["IDataArray"][j] = np.array([0])

                if len(self.cfg['IDataArray'][j]) > ramp_length:
                    ramp_length = len(self.cfg['IDataArray'][j])


                print(f'updating FF channel {j+1} to:')
                print(self.cfg["IDataArray"][j])

            self.cfg['ramp_length'] = ramp_length

            print()

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
                avgamp0 = Normalize_Qubit_Data(data_I[0], data_Q[0])
            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            if i == 0:

                ax_plot_1 = axs.imshow(
                    Z_spec,
                    aspect='auto',
                    extent=[X_spec[0]-X_spec_step/2,X_spec[-1]+X_spec_step/2,Y[0]-Y_step/2,Y[-1]+Y_step/2],
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


            axs.set_ylabel("Ramp Index")
            axs.set_xlabel("Spec Frequency (GHz)")
            axs.set_title(f"{self.titlename}, "
                             f"Cav Freq: {np.round(self.cfg['pulse_freqs'][0] + self.cfg['mixer_freq'] + self.cfg['cavity_LO'] / 1e6, 3)}")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start + self.cfg["sleep_time"] * 2### time for single full row in seconds
                timeEst = (t_delta )*self.cfg["ramp_num_points"]  ### estimate for full scan
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

        prog = SpecVsAdiabaticRampProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)


        return avgi, avgq


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

