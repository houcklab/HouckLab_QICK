
# from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
# from tqdm.notebook import tqdm
import time
from tqdm import tqdm
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2


class CavitySpecFFProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg['res_ch'], ro_ch=cfg['ro_chs'][0], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg['res_freqs'],
                         mux_gains=cfg['res_gains'],
                         mux_phases=[0]*len(cfg['res_freqs']))
        for ch, f in zip(cfg['ro_chs'], cfg['res_freqs']):
            self.declare_readout(ch=ch, length=cfg['readout_length'], freq=f, phase=0, gen_ch=cfg['res_ch'])

        self.add_pulse(ch=cfg['res_ch'], name="res_pulse",
                       style="const",
                       length=cfg["res_length"],
                       mask=cfg["ro_chs"])

        FF.FFDefinitions(self)

    def _body(self, cfg):
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        self.delay(0.1)  # delay trigger and pulse to 0.5 us after beginning of FF pulses
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(self.cfg["res_ch"], name='res_pulse')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])


    # ====================================================== #

class CavitySpecFFMUX(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        cfg = self.cfg
        fpts = np.linspace(cfg["res_freqs"][0] - cfg["TransSpan"],
                           cfg["res_freqs"][0] + cfg["TransSpan"],
                           cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=False):
            cfg["res_freqs"][0] = f
            prog = CavitySpecFFProg(self.soccfg, reps=self.cfg['reps'],cfg=self.cfg, final_delay=self.cfg['cav_relax_delay'])
            results.append(prog.acquire(self.soc, rounds=self.cfg.get('rounds',1), load_envelopes=True, progress=progress))
        print(f'Time: {time.time() - start}')
        results = np.array(results)
        # shape of results: (fpts, ROs, 1 [loops], I/Q)
        # print(results.shape)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data


        #### find the frequency corresponding to the peak
        sig = data['data']['results'][:,0,0,0] + 1j * data['data']['results'][:,0,0,1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = True, figNum = 1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data
        # for i in range(len(data['data']['results'][0])):
        avgi = data['data']['results'][:,0,0,0]
        avgq = data['data']['results'][:,0,0,1]
        x_pts = (data['data']['fpts'] + self.cfg["res_LO"]) / 1e3  #### put into units of frequency GHz

        freq_min = (self.peakFreq_min + self.cfg["res_LO"])/1e3
        sig = avgi + 1j * avgq

        avgamp0 = np.abs(sig)

        if ax is None:
            plt.figure()
        else:
            plt.sca(ax)
        plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
        plt.axvline(freq_min, color='black', linestyle='--', label=f"{1e3*freq_min:.1f} MHz")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)
        # plt.close(figNum)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





