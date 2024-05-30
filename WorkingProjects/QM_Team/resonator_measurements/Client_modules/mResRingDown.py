from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Experiment import ExperimentClass
import datetime
from qick import *
import time
import pickle
from scipy.optimize import curve_fit
from tqdm.notebook import tqdm


# program to send a pulse, wait some time, then measure a pulse
class CavityRingDownProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        AveragerProgram.__init__(self, soccfg, cfg)

    # commands that will run once
    def initialize(self):
        cfg=self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=1, mixer_freq=cfg["mixer_freq"], mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"], ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, freq=cfg["pulse_freqs"][iCh], length=cfg["readout_length"],
                                 gen_ch=cfg["res_ch"])

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", length=cfg["length"], mask=[0, 1, 2, 3])
        self.synci(1000)  # give processor some time to configure pulses

    # commands that will run once per rep
    def body(self):
        self.trigger(adcs=self.ro_chs, pins=[0], adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"],t=self.cfg["init_delay"])  # play readout pulse
        self.wait_all(0)
        self.sync_all(self.cfg["relax_delay"])  # sync all channels


class ResRingDown(ExperimentClass):
    def __init__(self, input=None, soc=None, soccfg=None, path='', prefix='data', cfg={}, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

        self.input = input

        self.cfg["res_ch"] = 6  # --Fixed
        self.cfg["ro_chs"] = [0, 1, 2, 3]  # --Fixed
        self.cfg["pulse_style"] = "const"  # --Fixed

        self.LO_f = input['LO_f']
        self.cfg['mixer_freq'] = input['mixer_freq']
        self.res_f = input['res_f']

        self.n_rounds = input['n_rounds']
        self.cfg['reps'] = input['n_reps']

        self.cfg['relax_delay'] = soc.us2cycles(input['relax_delay']) #, gen_ch=self.cfg["res_ch"])
        self.cfg['init_delay'] = soc.us2cycles(input['init_delay']) #, gen_ch=self.cfg["res_ch"])
        self.cfg['length'] = soc.us2cycles(input['ring_up_time'], gen_ch=self.cfg["res_ch"])
        self.cfg['readout_length'] = soc.us2cycles(input['readout_length'], ro_ch=0)
        # self.cfg['relax_delay_adc'] = soc.us2cycles(input['relax_delay'], ro_ch=0)
        self.t_delayArray = input['t_delayArray']

        self.basePower = input['basePower']
        self.cfg["pulse_gains"] = input['gain']

        self.filePrefix = prefix

        self.cfg['pulse_freqs'] = np.zeros(4)
        for i, f in enumerate(self.res_f):
            self.cfg['pulse_freqs'][i] = self.soc.roundfreq(f - self.LO_f - self.cfg['mixer_freq'],
                                                            dict1=self.soccfg['gens'][6],
                                                            dict2=self.soccfg['readouts'][self.cfg['ro_chs'][i]])

        filenames = os.listdir(self.path)
        increment = 0
        for file in filenames:
            if self.filePrefix+'_' in file:
                if '.' in file:
                    dotInd = file.index('.')
                else:
                    dotInd = 0
            try:
                newIncrement = int(file[(dotInd-3):dotInd])
                if newIncrement > increment:
                    increment = newIncrement
            except:
                pass
        increment += 1
        self.filename = self.filePrefix+'_{0:03}'.format(increment)


    def acquire(self, progress=False, debug=False):
        ampArray = [np.asarray([0. for ii in self.t_delayArray]) for i in range(4)]
        ampArrayCoherent = [np.asarray([0. for ii in self.t_delayArray]) for i in range(4)]
        ampArrayRound = [[] for i in range(4)]
        for i in range(4):
            ampArrayRound[i] = [np.asarray([0. for ii in self.t_delayArray]) for j in range(self.n_rounds)]
        iqListRound = [[] for i in self.t_delayArray]
        for i in range(len(self.t_delayArray)):
            iqListRound[i] = [[] for j in range(self.n_rounds)]

        start = time.time()
        for roundInd in range(self.n_rounds):

            for i, t_delay in enumerate(self.t_delayArray):
                self.cfg['adc_trig_offset'] = self.soc.us2cycles(t_delay) #, ro_ch=0)
                prog = CavityRingDownProgram(self.soccfg, self.cfg)
                iqListRound[i][roundInd] = prog.acquire(self.soc, debug=False)
                ibuf = prog.di_buf
                qbuf = prog.dq_buf
                for resInd in range(4):
                    ampArrayRound[resInd][roundInd][i] = np.mean(np.sqrt(ibuf[resInd]**2 + qbuf[resInd]**2))
            print('Round {0}, time = {1:0.2f} s'.format(roundInd, time.time()-start))

        print('Time elapsed: {0:0.2f} s'.format(time.time()-start))

        # normalize measurements and find amplitudes
        for i in range(4):
            for tind in range(len(self.t_delayArray)):
                ampArray[i][tind] = np.mean([ampArrayRound[i][roundInd][tind] for roundInd in range(self.n_rounds)])
                for roundInd in range(self.n_rounds):
                    ampArrayCoherent[i][tind] += (abs(iqListRound[tind][roundInd][0][i]+1j*iqListRound[tind][roundInd][1][i]))
                ampArrayCoherent[i][tind] = ampArrayCoherent[i][tind]/self.n_rounds

        data={'config': self.cfg,
              'input': self.input,
              'data': {
                  'ampArray': ampArray,
                  'ampArrayCoherent': ampArrayCoherent,
                  # 'ampArrayRound': ampArrayRound,
                  'f': self.res_f,
                  'power': self.basePower,
                  't_delayArray': self.t_delayArray,
                  'endTime': time.time(),
                  'startTime': start
              }}
        self.data=data

        return data

    def save_data(self, data=None):
        print(f'Saving {self.filename}')
        with open(self.path+'/'+self.filename+'.pickle', 'wb') as f:
            pickle.dump(self.data, f)
        # super().save_data(data=data['data'])

    def T1expo(self, x, a, T1, c):
        return a * np.exp(-x / T1) + c

    def display(self, data=None, fit=True, **kwargs):
        data = data['data']

        fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        plt.subplots_adjust(wspace=0.5, hspace=0.5)

        for i in range(len(self.cfg['ro_chs'])):
            axs[i].plot(self.t_delayArray, data['ampArray'][i], '.', label='data')
            axs[i].set_ylabel('Received power [ADC units]')
            axs[i].set_xlabel('t delay [us]')
            axs[i].legend(loc='best')
            axs[i].set_title('f = {0:.0f} MHz, P = {1:0.0f} dBm'.format(self.res_f[i], self.basePower))
            axs[i].grid()

        plt.savefig(self.path+'/'+self.filename+'_linear.png', dpi=150, bbox_inches='tight')

        fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        plt.subplots_adjust(wspace=0.5, hspace=0.5)

        for i in range(len(self.cfg['ro_chs'])):
            axs[i].plot(self.t_delayArray, np.log10(data['ampArray'][i]), '.', label='data')
            axs[i].set_ylabel('Received power [log. ADC units]')
            axs[i].set_xlabel('t delay [us]')
            axs[i].legend(loc='best')
            axs[i].set_title('f = {0:.0f} MHz, P = {1:0.0f} dBm'.format(self.res_f[i], self.basePower))
            axs[i].grid()

        plt.savefig(self.path+'/'+self.filename+'_log.png', dpi=150, bbox_inches='tight')

    def acquire_decimated(self, soft_avgs=1, readout_length=100, adc_trig_offset=0, progress=False, debug=False):

        self.cfg['soft_avgs'] = soft_avgs
        self.cfg['readout_length'] = readout_length
        self.cfg['reps'] = 1
        self.cfg['adc_trig_offset'] = adc_trig_offset

        print(self.cfg)

        prog = CavityRingDownProgram(self.soccfg, self.cfg)
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
