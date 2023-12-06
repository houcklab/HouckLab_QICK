from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy, soc, soccfg
import h5py
import os
import platform
from qick import *
# from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime


class ResSweepProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=2,
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=[0, 1, 2, 3])
        self.synci(200)  # give processor some time to configure pulses

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1, ro_ch=cfg["ro_chs"], mixer_freq=0.0)

        self.declare_readout(ch=cfg["ro_chs"], freq=cfg["pulse_freqsTMP"], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        # play for ring_time
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["ring_time_gen"], gain=cfg["pulse_gains"],
                                 freq=cfg["pulse_freqsTMP"], phase=0)
        self.synci(200)  # give processor some time to configure pulses
        self.pulse(ch=self.cfg["res_ch"], t=0)

        #reconfigure pulses for readout_length
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["readout_length_gen"]+cfg["adc_trig_offset_gen"],
                                 gain=cfg["pulse_gains"], freq=cfg["pulse_freqsTMP"], phase=0)

        #sync everything
        self.sync_all()

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

    def body(self):
        #play pulses. Trigger for a small wait time for the pulse to sync up a bit
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg['adc_trig_offset'])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"], t=0)

        # sync everything
        self.wait_all()
        self.sync_all()

# ====================================================== #

class ResSweep(ExperimentClass):
    """
    Loopback Experiment basic
    """

    def __init__(self, input = None, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

        self.soc = soc
        self.cfg = {"res_ch": 0,  # --Fixed
                    "ro_chs": 0,  # --Fixed
                    "pulse_style": "const",  # --Fixed
                    }

        self.LO_f = input['LO_f']
        self.mixerCenter_f = input['mixerCenter_f']
        self.span_f = input['span_f']
        self.res_f = input['res_f']

        self.n_expts = input['n_expts']
        self.n_rounds = input['n_rounds']
        self.n_reps = input['n_reps']

        self.ring_up_time = soc.us2cycles(input['ring_up_time'])
        self.ring_up_time_gen = soc.us2cycles(input['ring_up_time'], gen_ch=0)
        self.ring_between_time = soc.us2cycles(input['ring_between_time'])
        self.ring_between_time_gen = soc.us2cycles(input['ring_between_time'], gen_ch=0)
        self.cfg['readout_length'] = soc.us2cycles(input['readout_length'], ro_ch=0)
        self.cfg['readout_length_gen'] = soc.us2cycles(input['readout_length'], gen_ch=0)

        self.cfg['adc_trig_offset'] = soc.us2cycles(input['adc_trig_offset'])
        self.cfg['adc_trig_offset_gen'] = soc.us2cycles(input['adc_trig_offset'], gen_ch=0)

        self.basePower = input['basePower']
        self.attenList = input['attenList']
        self.attenSerial = input['attenSerial']
        self.cfg["pulse_gains"] = input['gain']

        self.mixerArray_f = np.linspace(self.mixerCenter_f - self.span_f / 2, self.mixerCenter_f + self.span_f / 2, self.n_expts)

        self.cfg['pulse_freqs'] = input['res_f'] - self.LO_f - self.mixerCenter_f #self.soc.roundfreq(input['res_f'] - self.LO_f - self.mixerCenter_f, dict1=self.soccfg['gens'][0],
        #dict2=self.soccfg['readouts'][self.cfg['ro_chs']])

        # create frequency axis for each resonator
        self.resArray_f = self.cfg['pulse_freqs'] + self.mixerArray_f + self.LO_f

        self.input = input

        self.filePrefix = prefix
        filenames = os.listdir(self.path)
        increment = 0
        for file in filenames:
            if self.filePrefix + '_' in file:
                if '.' in file:
                    dotInd = file.index('.')
                else:
                    dotInd = 0
            try:
                newIncrement = int(file[(dotInd - 3):dotInd])
                if newIncrement > increment:
                    increment = newIncrement
            except:
                pass
        increment += 1
        self.filename = self.filePrefix + '_{0:03}'.format(increment)

        print('Pulse frequencies are: {0} MHz'.format(self.cfg['pulse_freqs']))
        print('Frequencies out are: {0} MHz'.format(self.res_f - self.LO_f))

    def hangerFit(self, xData, freq0, QInt, Qc, asymm, offset):
        Q0 = 1 / ((1 / QInt) + (1 / Qc))
        return 20 * np.log10(np.abs(1 - ((Q0 / Qc) - 2j * Q0 * asymm / (2 * np.pi * freq0)) / (
                    1 + 2j * Q0 * (xData - freq0) / freq0))) + offset

    def acquire(self, progress=False, debug=False):
        diList = [[] for i in self.mixerArray_f]
        dqList = [[] for i in self.mixerArray_f]
        iqListRound = [[] for i in self.mixerArray_f]
        ampArrayTMP = np.asarray([0. for ii in self.mixerArray_f])
        ampArrayIQ_log = np.asarray([0. for ii in self.mixerArray_f])
        IArray = np.asarray([0. for ii in self.mixerArray_f])
        QArray = np.asarray([0. for ii in self.mixerArray_f])

        start = time.time()
        print("start round")
        for roundInd in range(self.n_rounds):
            roundStart = time.time()
            # ring up the resonator
            self.cfg['ring_time'] = self.ring_up_time
            self.cfg['ring_time_gen'] = self.ring_up_time_gen
            self.cfg['pulse_freqsTMP'] = int(self.cfg['pulse_freqs'] + self.mixerArray_f[0] + self.LO_f)
            self.cfg['reps'] = 2

            print("start ring-up")
            prog = ResSweepProgram(self.soccfg, self.cfg)
            dummy = prog.acquire(self.soc, load_pulses=True, debug=False)
            print("ring-up done")

            self.cfg['reps'] = self.n_reps
            self.cfg['ring_time'] = self.ring_between_time
            self.cfg['ring_time_gen'] = self.ring_between_time_gen
            for fInd, f in enumerate(tqdm(self.mixerArray_f)):
                self.cfg['pulse_freqsTMP'] = int(self.cfg['pulse_freqs'] + f + self.LO_f)
                if fInd % 50 == 0:
                    print('{0}: {1:0.2f} s'.format(fInd, time.time() - roundStart))
                # freqStart = time.time()
                prog = ResSweepProgram(self.soccfg, self.cfg)
                iqListRound[fInd] = prog.acquire(self.soc, load_pulses=True, debug=False)
                diList[fInd] = prog.di_buf
                dqList[fInd] = prog.dq_buf
                # print('Frequency {0}, time {1:0.3f} s'.format(fInd, time.time() - freqStart))

            # add the frequencies to older measurements
            for freqInd, iq in enumerate(iqListRound):
                ampArrayTMP[freqInd] += abs(np.asarray(iq[0]) + 1j * np.asarray(iq[1]))
                IArray[freqInd] += np.asarray(iq[0])
                QArray[freqInd] += np.asarray(iq[1])

            print('Round {0}, time {1:0.3f} s'.format(roundInd, time.time() - roundStart))

        print('Final time = {0:0.3f} s'.format(time.time() - start))

        # normalize measurements and find amplitudes
        ampArray = ampArrayTMP/self.n_rounds
        ampArray_log = 20*np.log10(ampArray)

        IArray = IArray/self.n_rounds
        QArray = QArray/ self.n_rounds
        ampArrayIQ_log = 20*np.log10(abs(IArray + 1j*QArray))

        data={'config': self.cfg,
              'input': self.input,
              'data': {
                  'ampArray': ampArray,
                  'ampArray_log': ampArray_log,
                  'IArray': IArray,
                  'QArray': QArray,
                  'ampArrayIQ_log': ampArrayIQ_log,
                  'f': self.resArray_f,
                  'power': self.basePower,
                  'diList': diList,
                  'dqList': dqList,
                  'endTime': time.time(),
                  'startTime': start
              }}
        self.data=data

        return data

    def acquire_decimated(self, soft_avgs=1, readout_length=100, progress=False, debug=False):

        self.cfg['mixer_freq'] = self.mixerCenter_f
        self.cfg['ring_time'] = self.ring_up_time
        self.cfg['soft_avgs'] = soft_avgs
        self.cfg['readout_length'] = readout_length
        self.cfg['reps'] = 1

        prog = ResSweepProgram(self.soccfg, self.cfg)
        print("start decimated")
        self.soc.reset_gens()  # clear any DC or periodic values on generators
        iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        print("decimated done")
        data={'config': self.cfg, 'data': {'iq_list': iq_list}}
        self.data=data
        return data

    def display_decimated(self, data=None, fit=True, **kwargs):
        if data is None:
            data = self.data

        hfig, hax = plt.subplots(4, 1, figsize = (10, 10), dpi = 150)
        plt.subplots_adjust(hspace = 0.4, wspace=0.4)
        for ii, iq in enumerate(data['data']['iq_list']):
            hax[ii].plot(iq[0], '.', label="I value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(iq[1], '.', label="Q value, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].plot(np.abs(iq[0] + 1j * iq[1]), '.', label="mag, ADC %d" % (data['config']['ro_chs'][ii]))
            hax[ii].set_ylabel("a.u.")
            hax[ii].set_xlabel("Clock ticks")
            hax[ii].legend(loc='best', bbox_to_anchor = (1,1))
        hax[0].set_title("Averages = " + str(data['config']["soft_avgs"]))
        plt.savefig(self.iname + '_decimated.png', bbox_inches='tight')

    def display(self, data=None, fit=True, **kwargs):
        data = data['data']

        pOpt = [[] for i in range(4)]
        pCov = [[] for i in range(4)]
        centerF = self.resArray_f[data['ampArray_log'].argmin()]
        pOpt, pCov = curve_fit(self.hangerFit, self.resArray_f * 10 ** 6, data['ampArray_log'],
                                     p0=[centerF * 10 ** 6, 1e7, 1e6, 0, 0], maxfev=100000)

        fig, axs = plt.subplots(1, 1, figsize=(4.5, 4.5), dpi=150)
        plt.subplots_adjust(wspace=0.5, hspace=0.5)

        axs.plot(self.resArray_f, data['ampArray_log'], '.', label='data', markersize=2)
        axs.plot(self.resArray_f, self.hangerFit((self.resArray_f) * 10 ** 6, *pOpt), label='fit')
        axs.set_ylabel('10log10(I^2 + Q^2)')
        axs.set_xlabel('Frequency [MHz]')
        axs.legend(loc='best')
        axs.set_title('f = {0:.0f} MHz, Q_int = {1:0.4e} , Q_c = {2:0.4e}'.format(self.res_f, pOpt[1], pOpt[2]))
        axs.grid()

        # plt.savefig(self.path+'/'+self.filename+'_sweep.png', bbox_inches='tight')
        plt.savefig(self.iname, bbox_inches='tight')

        fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        plt.subplots_adjust(wspace=0.5, hspace=0.5)

    def save_data(self, data=None):
        print(f'Saving {self.filename}')
        with open(self.path+'/'+self.filename+'.pickle', 'wb') as f:
            pickle.dump(self.data, f)
        # super().save_data(data=data['data'])
