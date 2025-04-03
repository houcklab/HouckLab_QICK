from socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from Experiment import ExperimentClass
import datetime
from qick import *
import time
import pickle
import Pyro4
from scipy.optimize import curve_fit
from tqdm.notebook import tqdm


# program to send a pulse, wait some time, then measure a pulse
class CavityRingDownProgram(AveragerProgram):
    def __init__(self, soccfg, cfg):
        AveragerProgram.__init__(self, soccfg, cfg)

    # commands that will run once
    def initialize(self):
        cfg=self.cfg

        # set the nyquist zone
        for i in cfg['res_ch']:
            self.declare_gen(ch=i, nqz=1)

        for i, ch in enumerate(cfg["ro_chs"]):
            freq = self.freq2reg(cfg["pulse_freqs"][i], gen_ch=cfg["res_ch"][i],
                                 ro_ch=ch)
            phase = self.deg2reg(cfg["res_phases"][i],
                                 gen_ch=cfg["res_ch"][i])
            self.declare_readout(ch=ch, length=self.cfg["readout_length"],
                                 freq=self.cfg["pulse_freqs"][i],
                                 gen_ch=cfg["res_ch"][i])
            self.default_pulse_registers(ch=cfg['res_ch'][i],
                                         freq=freq,
                                         phase=phase,
                                         gain=cfg["pulse_gains"][i],
                                         )

            self.set_pulse_registers(ch=cfg["res_ch"][i], style='const',
                                     length=cfg['pulseLength'])

    # commands that will run once per rep
    def body(self):
        # for i, res_ch in enumerate(self.cfg['res_ch']):
        self.trigger(adcs=self.ro_chs, pins=[0], adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        for i in range(self.cfg['numPulses']):
            self.pulse(ch=self.cfg["res_ch"],t=self.cfg["init_delay"]+i*(self.cfg['pulseLength']+1))  # play readout pulse
        self.wait_all(0)
        self.sync_all(t=self.cfg["relax_delay"])  # sync all channels


class ResRingDown(ExperimentClass):
    def __init__(self, inputDict=None, soc=None, soccfg=None, path='', prefix='data', cfg={}, config_file=None,
                 progress=None,temperatureLogPath='Z:/t1Team/logFiles/'):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

        self.inputDict = inputDict

        self.soc = soc
        if len(inputDict['res_f']) == 1:
            self.cfg = {"res_ch": [0],
                        "ro_chs": [0],
                        "res_phases": [0]
                        }
        elif len(inputDict['res_f']) == 2:
            self.cfg = {"res_ch": [0, 1],
                        "ro_chs": [0, 1],
                        "res_phases": [0, 0]
                        }
        else:
            print('Error: ony one or two res_fs can be specified')
            assert 1

        self.LO_f = inputDict['LO_f']
        self.span_f = inputDict['span_f']
        self.res_f = inputDict['res_f']

        self.n_rounds = inputDict['n_rounds']
        self.cfg['reps'] = inputDict['n_reps']

        self.cfg['relax_delay'] = soc.us2cycles(inputDict['relax_delay']) #, gen_ch=self.cfg["res_ch"])
        self.cfg['init_delay'] = soc.us2cycles(inputDict['init_delay']) #, gen_ch=self.cfg["res_ch"])
        self.cfg['length'] = soc.us2cycles(inputDict['ring_up_time'], gen_ch=0)
        self.cfg['numPulses'] = self.cfg['length'] // 65536 + 1
        self.cfg['pulseLength'] = self.cfg['length'] // self.cfg['numPulses']
        self.cfg['readout_length'] = soc.us2cycles(inputDict['readout_length'], ro_ch=0)
        self.t_delayArray = inputDict['t_delayArray']

        self.basePower = inputDict['basePower']
        self.cfg["pulse_gains"] = inputDict['gain']

        self.filePrefix = prefix

        self.cfg['pulse_freqs'] = np.zeros(len(self.cfg['ro_chs']))
        for i, f in enumerate(self.res_f):
            self.cfg['pulse_freqs'][i] = self.soc.roundfreq(f - self.LO_f,
                                                            dict1=self.soccfg['gens'][0],
                                                            dict2=self.soccfg['readouts'][self.cfg['ro_chs'][i]])

        datestr = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        self.filename = self.filePrefix + '-' + datestr
        # self.temperatureLogPath = temperatureLogPath
        # self.readTemp()  # initial read to raise a warning if the file is out of date

        print('Frequencies out are: {0} MHz'.format([res_f - self.LO_f for res_f in self.res_f]))


    def acquire(self, progress=False, debug=False):
        ampArray = [np.asarray([0. for ii in self.t_delayArray]) for i in self.res_f]
        IArray = [np.asarray([0. for ii in self.t_delayArray]) for i in self.res_f]
        QArray = [np.asarray([0. for ii in self.t_delayArray]) for i in self.res_f]

        start = time.time()
        for roundInd in range(self.n_rounds):

            for i in tqdm(range(len(self.t_delayArray))):
                t_delay = self.t_delayArray[i]
                self.cfg['adc_trig_offset'] = self.soc.us2cycles(t_delay) #, ro_ch=0)
                prog = CavityRingDownProgram(self.soccfg, self.cfg)

                success = False
                while not success:
                    try:
                        iqList = prog.acquire(self.soc, load_pulses=True, debug=False)
                        success = True
                    except Exception:
                        print("Pyro traceback:")
                        print("".join(Pyro4.util.getPyroTraceback()))

                for res in range(len(self.res_f)):
                    IArray[res][i] += iqList[0][res][0]
                    QArray[res][i] += iqList[1][res][0]

                ibuf = prog.di_buf
                qbuf = prog.dq_buf
                for resInd in range(len(self.res_f)):
                    ampArray[resInd][i] += np.mean(np.sqrt(ibuf[resInd]**2 + qbuf[resInd]**2))

        print('Time elapsed: {0:0.2f} s'.format(time.time()-start))

        # normalize measurements and find amplitudes
        for i in range(len(self.res_f)):
            IArray[i] = IArray[i] / self.n_rounds
            QArray[i] = QArray[i] / self.n_rounds
            ampArray[i] = ampArray[i] / self.n_rounds

        ampArrayCoherent = [np.abs(IArray[i] + 1j * QArray[i]) for i in range(len(self.res_f))]

        data={'config': self.cfg,
              'input': self.inputDict,
              'data': {
                  'ampArray': ampArray,
                  'ampArrayCoherent': ampArrayCoherent,
                  'IArray': IArray,
                  'QArray': QArray,
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

        if len(self.cfg['ro_chs']) == 1:
            fig, axs = plt.subplots(1, 1, figsize=(4.5, 4.5), dpi=75)
            plt.subplots_adjust(wspace=0.5, hspace=0.5)
            axs = [axs]
        elif len(self.cfg['ro_chs']) == 2:
            fig, axs = plt.subplots(1, 2, figsize=(10, 4.5), dpi=75)
            plt.subplots_adjust(wspace=0.5, hspace=0.5)
        elif len(self.cfg['ro_chs']) == 3:
            fig, axs = plt.subplots(2, 2, figsize=(10, 10), dpi=75)
            plt.subplots_adjust(wspace=0.5, hspace=0.5)
            axs[1][1].set_axis_off()
            axs[1][1].set_frame_on(False)
            axs = [axs[0][0], axs[0][1], axs[1][0]]
        elif len(self.cfg['ro_chs']) == 4:
            fig, axs = plt.subplots(2, 2, figsize=(10, 10), dpi=75)
            plt.subplots_adjust(wspace=0.5, hspace=0.5)
            axs = [axs[0][0], axs[0][1], axs[1][0], axs[1][1]]

        for i in range(len(self.cfg['ro_chs'])):
            axs[i].plot(self.t_delayArray, data['ampArray'][i], '.', label='Incoherent')
            axs2 = axs[i].twinx()
            axs2.plot(self.t_delayArray, data['ampArrayCoherent'][i], '.', label='Coherent', color='C1')
            axs[i].set_ylabel('Incoherently averaged power [ADC units]')
            axs2.set_ylabel('Coherently averaged power [ADC units]')
            axs[i].set_xlabel('t delay [us]')
            axs[i].legend(loc='best')
            axs[i].legend(loc='best')
            axs[i].set_title('f = {0:.0f} MHz, P = {1:0.0f} dBm'.format(self.res_f[i], self.basePower))
            axs[i].grid()

        # plt.savefig(self.path+'/'+self.filename+'_linear.png', dpi=150, bbox_inches='tight')
        #
        # fig, axs = plt.subplots(4, 1, figsize=(4.5, 20), dpi=150)
        # plt.subplots_adjust(wspace=0.5, hspace=0.5)
        #
        # for i in range(len(self.cfg['ro_chs'])):
        #     axs[i].plot(self.t_delayArray, np.log10(data['ampArray'][i]), '.', label='data')
        #     axs[i].set_ylabel('Received power [log. ADC units]')
        #     axs[i].set_xlabel('t delay [us]')
        #     axs[i].legend(loc='best')
        #     axs[i].set_title('f = {0:.0f} MHz, P = {1:0.0f} dBm'.format(self.res_f[i], self.basePower))
        #     axs[i].grid()
        #
        # plt.savefig(self.path+'/'+self.filename+'_log.png', dpi=150, bbox_inches='tight')

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
