from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Experiment import ExperimentClass
import datetime
from qick import *
import time
from scipy.optimize import curve_fit

class ResSweepProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1, mixer_freq=cfg["mixer_freq"], mux_freqs=cfg["pulse_freqs"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=[0, 1, 2, 3])
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.synci(self.cfg["relax_delay"])  # sync all channels

# ====================================================== #

class ResSweep(ExperimentClass):
    """
    Loopback Experiment basic
    """

    def __init__(self, input = None, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
        self.LO_f = input['LO_f']
        self.mixerCenter_f = input['mixerCenter_f']
        self.span_f = input['span_f']
        self.res_f = input['res_f']

        self.n_expts = input['n_expts']
        self.n_rounds = input['n_rounds']
        self.n_reps = input['n_reps']

        self.ring_up_time = input['ring_up_time']
        self.ring_between_time = input['ring_between_time']
        self.readout_length = input['readout_length']
        self.cfg['relax_delay'] = input['relax_delay']

        self.basePower = input['basePower']
        self.attenList = input['attenList']
        self.attenSerial = input['attenSerial']

        self.mixerArray_f = np.linspace(self.mixerCenter_f - self.span_f / 2, self.mixerCenter_f + self.span_f / 2, self.n_expts)
        cfg['pulse_freqs'] = [i - self.LO_f - self.mixerCenter_f for i in self.res_f]

        # create frequency axis for each resonator
        self.resArray_f = [self.mixerArray_f + self.LO_f for i in self.cfg['pulse_freqs']]
        for i, f in enumerate(self.cfg['pulse_freqs']):
            self.resArray_f[i] += self.soc.reg2freq(self.soc.freq2reg(f, gen_ch=6),
                                         gen_ch=6)  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        freq = [[] for i in cfg['pulse_freqs']]
        for i, f in enumerate(cfg['pulse_freqs']):
            freq[i] = soc.freq2reg(f,
                                   gen_ch=6)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        print("generator freq:", [soc.reg2freq(f, gen_ch=6) for f in freq])

        print('Pulse frequencies are: {0} MHz'.format(cfg['pulse_freqs']))
        print('Frequencies out are: {0} MHz'.format([i - self.LO_f for i in self.res_f]))

    def hangerFit(self, xData, freq0, QInt, Qc, asymm, offset):
        Q0 = 1 / ((1 / QInt) + (1 / Qc))
        return 20 * np.log10(np.abs(1 - ((Q0 / Qc) - 2j * Q0 * asymm / (2 * np.pi * freq0)) / (
                    1 + 2j * Q0 * (xData - freq0) / freq0))) + offset

    def acquire(self, progress=False, debug=False):
        iqListRound = [[] for i in self.mixerArray_f]
        IArray = [[np.asarray([0. for ii in self.mixerArray_f]) for i in range(4)] for iii in range(self.n_rounds)]
        QArray = [[np.asarray([0. for ii in self.mixerArray_f]) for i in range(4)] for iii in range(self.n_rounds)]

        start = time.time()
        # for attenInd, atten in enumerate(attenList):
        for roundInd in range(self.n_rounds):
            roundStart = time.time()
            # ring up the resonator
            self.cfg['adc_trig_offset'] = self.ring_up_time
            self.cfg['reps'] = 2
            self.cfg['mixer_freq'] = self.mixerArray_f[0]

            prog = ResSweepProgram(self.soccfg, self.cfg)
            dummy = prog.acquire(self.soc, load_pulses=True, debug=False)

            # sweep across the frequency range
            self.cfg['adc_trig_offset'] = self.ring_between_time
            self.cfg['reps'] = self.n_reps
            for fInd, f in enumerate(self.mixerArray_f):
                self.cfg['mixer_freq'] = f
                prog = ResSweepProgram(self.soccfg, self.cfg)
                iqListRound[fInd] = prog.acquire(self.soc, load_pulses=True, debug=False)

            # add the frequencies to older measurements
            for IQInd in range(4):
                for freqInd, iq in enumerate(iqListRound):
                    IArray[roundInd][IQInd][freqInd] = np.asarray(iq[0][IQInd])
                    QArray[roundInd][IQInd][freqInd] = np.asarray(iq[1][IQInd])

            print('Round {0}, time {1:0.3f} s'.format(roundInd, time.time() - roundStart))

        print('Final time = {0:0.3f} s'.format(time.time() - start))

        # normalize measurements and find amplitudes
        # for i, dummy in enumerate(IArray):
        #     IArray[i] = IArray[i] / self.n_rounds
        #     QArray[i] = QArray[i] / self.n_rounds
        # ampArray = np.asarray([np.abs(IArray[i] + 1j * Q) for i, Q in enumerate(QArray)])
        # ampArray_log = np.asarray([10 * np.log10(amp) for amp in ampArray])

        data={'config': self.cfg,
              'data': {
                  # 'ampArray': ampArray,
                  # 'ampArray_log': ampArray_log,
                  'IArray': IArray,
                  'QArray': QArray,
                  'f': self.resArray_f
              }}
        self.data=data

        return data

    def acquire_decimated(self, soft_avgs=50, readout_length=100, progress=False, debug=False):

        self.cfg['mixer_freq'] = self.mixerCenter_f
        self.cfg['adc_trig_offset'] = self.ring_up_time
        self.cfg['soft_avgs'] = soft_avgs
        self.cfg['readout_length'] = readout_length
        self.cfg['reps'] = 1

        prog = ResSweepProgram(self.soccfg, self.cfg)
        self.soc.reset_gens()  # clear any DC or periodic values on generators
        iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'iq_list': iq_list}}
        self.data=data
        return data

    def display_decimated(self, data=None, fit=True, **kwargs):
        if data is None:
            data = self.data

        hfig, hax = plt.subplots(4, 1, figsize = (10, 10), dpi = 150)
        plt.subplots_adjust(hspace = 0.4, wspace=0.4)
        for ii, iq in enumerate(data['data']['iq_list']):
            hax[ii].plot(iq[0], label="I value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(iq[1], label="Q value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(np.abs(iq[0] + 1j * iq[1]), label="mag, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].set_ylabel("a.u.")
            hax[ii].set_xlabel("Clock ticks")
            hax[ii].legend(loc='best', bbox_to_anchor = (1,1))
        hax[0].set_title("Averages = " + str(data['config']["soft_avgs"]))
        plt.savefig(self.iname + '_decimated.png', bbox_inches='tight')

    def display(self, data=None, fit=True, **kwargs):
        data = data['data']

        # pOpt = [[] for i in range(4)]
        # pCov = [[] for i in range(4)]
        # for i in range(4):
        #     centerF = self.resArray_f[i][data['ampArray_log'][i].argmin()]
        #     pOpt[i], pCov[i] = curve_fit(self.hangerFit, (self.resArray_f[i]) * 10 ** 6, data['ampArray_log'][i],
        #                                  p0=[(centerF) * 10 ** 6, 5e5, 5e5, 0.5e3, 0], maxfev=100000)
        #
        # fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        # plt.subplots_adjust(wspace=0.5, hspace=0.5)
        #
        # for i in range(4):
        #     axs[i].plot(self.resArray_f[i], data['ampArray_log'][i], '.', label='data')
        #     axs[i].plot(self.resArray_f[i], self.hangerFit((self.resArray_f[i]) * 10 ** 6, *pOpt[i]), label='fit')
        #     axs[i].set_ylabel('20log10(I^2 + Q^2)')
        #     axs[i].set_xlabel('Frequency [MHz]')
        #     axs[i].legend(loc='best')
        #     axs[i].set_title('f = {0:.0f} MHz, Q_int = {1:0.4e} , Q_c = {2:0.4e}'.format(self.res_f[i], pOpt[i][1], pOpt[i][2]))
        #
        # plt.savefig(self.iname + '_sweep.png', bbox_inches='tight')
        #
        # fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        # plt.subplots_adjust(wspace=0.5, hspace=0.5)
        #
        # for i in range(4):
        #     axs[i].plot(self.resArray_f[i], data['IArray'][i], '.', label='I')
        #     axs[i].plot(self.resArray_f[i], data['QArray'][i], '.', label='Q')
        #     axs[i].set_ylabel('Signal [ADC units]')
        #     axs[i].set_xlabel('Frequency [MHz]')
        #     axs[i].legend(loc='best')
        #     axs[i].set_title('f = {0:.0f} MHz, Q_int = {1:0.4e} , Q_c = {2:0.4e}'.format(self.res_f[i], pOpt[i][1], pOpt[i][2]))
        #
        # plt.savefig(self.iname + '_IQ_vs_f.png', bbox_inches='tight')
        #
        # fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        # plt.subplots_adjust(wspace=0.5, hspace=0.5)
        #
        # for i in range(4):
        #     axs[i].plot(data['IArray'][i], data['QArray'][i], '.-')
        #     axs[i].set_ylabel('I [ADC units]')
        #     axs[i].set_xlabel('Q [ADC units]')
        #     axs[i].set_title('f = {0:.0f} MHz, Q_int = {1:0.4e} , Q_c = {2:0.4e}'.format(self.res_f[i], pOpt[i][1], pOpt[i][2]))
        #
        # plt.savefig(self.iname + '_I_vs_Q.png', bbox_inches='tight')

        fig, axs = plt.subplots(4, 2, figsize=(12, 20), dpi=150)
        plt.subplots_adjust(wspace=0.4, hspace=0.4)

        for roundInd in range(self.n_rounds):
            for i in range(4):
                axs[i][0].plot(self.resArray_f[i], data['IArray'][roundInd][i], '.-')
                axs[i][0].set_ylabel('I [ADC units]')
                axs[i][0].set_xlabel('Frequency [MHz]')

                axs[i][1].plot(self.resArray_f[i], data['QArray'][roundInd][i], '.-')
                axs[i][1].set_ylabel('Q [ADC units]')
                axs[i][1].set_xlabel('Frequency [MHz]')

        plt.savefig(self.iname + '_roundCompare.png', bbox_inches='tight')

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


