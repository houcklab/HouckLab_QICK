from qick import *

import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.tProc_V2.Helpers_V2.FF_utils as FF

'''In order to use tProc v2'''
from qick.asm_v2 import AveragerProgramV2

# import qick
# print("Test", qick.__file__)

class CavitySpecFFProg(AveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg['res_ch'], ro_ch=cfg['ro_chs'][0], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg['pulse_freqs'],
                         mux_gains=cfg['pulse_gains'],
                         mux_phases=[0])#cfg['pulse_phases'])

        for ch, f in zip(cfg['ro_chs'], cfg['pulse_freqs']):
            self.declare_readout(ch=ch, length=cfg['readout_length']) #, freq=f, phase=0, gen_ch=res_ch)

        self.add_pulse(ch=cfg['res_ch'], name="readout_drive",
                       style="const",
                       length=cfg["length"],
                       mask=cfg['ro_chs']
                       )

        FF.FFDefinitions(self)

    def _body(self, cfg):
        self.delay_auto()
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.delay(0.5)  # delay trigger and pulse to 0.5 us after beginning of FF pulses
        self.trigger(ros=self.cfg["ro_chs"], pins=[0],
                     t=self.cfg["adc_trig_offset"], ddr4=False)
        self.pulse(self.cfg["res_ch"], name='readout_drive')
        self.delay_auto(0.025)  # us
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)



class CavitySpecFFMUX(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        fpts = np.linspace(self.cfg["mixer_freq"] - self.cfg["TransSpan"],
                           self.cfg["mixer_freq"] + self.cfg["TransSpan"],
                           self.cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["mixer_freq"] = f
            prog = CavitySpecFFProg(self.soccfg, cfg=self.cfg, final_delay=self.cfg['cav_relax_delay'],
                                    reps=self.cfg["reps"])
            results.append(prog.acquire(self.soc, soft_avgs=self.cfg["rounds"], load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        print(results)
        data = {'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        print(results.shape)
        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][1][0][0]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        for i in range(len(data['data']['results'][0])):
            avgi = data['data']['results'][0][i][0]
            avgq = data['data']['results'][1][i][0]
            x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"] / 1e6) / 1e3  #### put into units of frequency GHz
            x_pts += self.cfg['pulse_freqs'][i] / 1e3
            sig = avgi + 1j * avgq

            avgamp0 = np.abs(sig)

            plt.figure(figNum)
            plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
            plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
            plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
            plt.ylabel("a.u.")
            plt.xlabel("Cavity Frequency (GHz)")
            plt.title(self.titlename)
            plt.legend()

            plt.savefig(self.iname)

            if plotDisp:
                plt.show(block=True)
                plt.pause(0.1)
            plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





