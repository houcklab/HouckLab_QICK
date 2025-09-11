from qick import *

from WorkingProjects.Triangle_Lattice_tProcV1.Basic_Experiments_Programs.AveragerProgramFF import RAveragerProgramFF
from WorkingProjects.Triangle_Lattice_tProcV1.Helpers.Compensated_Pulse_Jero import Compensated_Pulse
from WorkingProjects.Triangle_Lattice_tProcV1.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV1.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV1.Helpers.FF_utils_NEW as FF

'''Variation on ThreePartRProgramOneFF. Performs the time-domain spectroscopy experiment of Figure 1 in 
Roushan et al. 2017, "Spectral signatures of many-body localization with interacting photons",
https://arxiv.org/pdf/1709.07108.'''


# get waveforms of less than 3 clock cycles by padding the first 3 cycles of the arbitrary pulse
# with FFPulses.
THREE = 3
# I declare this as a variable so that someone reading the code knows the purpose of the 3.


class TimeDomainSpecProgram(RAveragerProgramFF):
    def initialize(self):
        cfg = self.cfg
        if cfg["start"] + cfg["step"] * cfg["expts"] >= 4096 - THREE:
            raise ValueError("Not enough waveform memory, must be less than 4096 - 3 cycles")

        FF.FFDefinitions(self)
        # Pages and "mode" registers for each fast flux generator
        self.ff_rps = [self.ch_page(ch) for ch in self.FFChannels]
        self.r_mode = [self.sreg(ch, "mode") for ch in self.FFChannels]

        # Register to store waveform length
        self.r_length = 3
        for page in self.ff_rps:
            self.regwi(page, self.r_length, cfg["start"] + THREE)

        # Qubit (Equal sigma for all)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and down-conversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],
                                 length=self.us2cycles(cfg["res_length"]))

        self.sync_all(200)

    def body(self):
        # 1: FFPulses
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])
            time_ = self.us2cycles(1) if i == 0 else 'auto'

            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_, waveform="qubit", t=time_)
        # 2: FFExpt
        self.sync_all(gen_t0=self.gen_t0)

        # To get wait times of < 3 clock cycles
        padded_IDataArray = [np.pad(arr, (THREE * 16, 0), constant_values=prev_gain) for arr, prev_gain in
                             zip(self.cfg["IDataArray"], self.FFPulse)]
        FF.FFPulses_directSET_REGS(self, self.FFExpts,
                                   16 * (THREE + self.cfg["start"] + self.cfg["step"] * self.cfg["expts"]),
                                   self.FFPulse,
                                   IQPulseArray=padded_IDataArray)
        # Update pulse length, which is stored in the last 16 bits of the generator's "mode" register
        for ff_page, mode_reg in zip(self.ff_rps, self.r_mode):
            # self.bitwi(ff_page, mode_reg, mode_reg, '&', 0b111_1111_1111_1111_0000_0000_0000_0000)
            self.bitwi(ff_page, mode_reg, mode_reg, '|', 0b0_1111_1111_1111_1111)
            self.bitwi(ff_page, mode_reg, mode_reg, '^', 0b0_1111_1111_1111_1111)
            self.mathi(ff_page, mode_reg, mode_reg, '+', self.r_length)

        FF.FFPulses_directPULSE(self)

        self.sync(self.ff_rps[0], self.r_length)

        # Pre-measurement Pi/2 pulse to measure in either X or Y basis
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])
            time_ = self.us2cycles(1) if i == 0 else 'auto'

            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=self.cfg['second_qubit_phase'],
                                 gain=gain_, waveform="qubit", t=time_)

        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 2.32515/1e3*3) # Overshoot to freeze dynamics
        FF.FFPulses(self, self.FFReadouts, self.cfg["res_length"], t_start=0)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 2.32515/1e3*3)
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        inverted_IDataArray = [-1 * np.flip(arr) for arr in padded_IDataArray]
        FF.FFPulses_directSET_REGS(self, self.FFExpts,
                                   16 * (THREE + self.cfg["start"] + self.cfg["step"] * self.cfg["expts"]),
                                   self.FFPulse,
                                   IQPulseArray=inverted_IDataArray)
        for ff_page, mode_reg in zip(self.ff_rps, self.r_mode):
            # self.bitwi(ff_page, mode_reg, mode_reg, '&', 0b111_1111_1111_1111_0000_0000_0000_0000)
            self.bitwi(ff_page, mode_reg, mode_reg, '|', 0b0_1111_1111_1111_1111)
            self.bitwi(ff_page, mode_reg, mode_reg, '^', 0b0_1111_1111_1111_1111)
            self.mathi(ff_page, mode_reg, mode_reg, '+', self.r_length)
        FF.FFPulses_directPULSE(self)
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def update(self):
        for ff_page in set(self.ff_rps):  # set() to avoid double adding for generators sharing a page
            self.mathi(ff_page, self.r_length, self.r_length, '+', self.cfg["step"])


class TimeDomainSpec(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        self.cfg["IDataArray"] = [None] * 4
        self.cfg["IDataArray"][0] = Compensated_Pulse(self.cfg['FF_Qubits']['1']['Gain_Expt'], self.cfg['FF_Qubits'][
            '1']['Gain_Pulse'], 1)
        self.cfg["IDataArray"][1] = Compensated_Pulse(self.cfg['FF_Qubits']['2']['Gain_Expt'], self.cfg['FF_Qubits'][
            '2']['Gain_Pulse'], 2)
        self.cfg["IDataArray"][2] = Compensated_Pulse(self.cfg['FF_Qubits']['3']['Gain_Expt'], self.cfg['FF_Qubits'][
            '3']['Gain_Pulse'], 3)
        self.cfg["IDataArray"][3] = Compensated_Pulse(self.cfg['FF_Qubits']['4']['Gain_Expt'], self.cfg['FF_Qubits'][
            '4']['Gain_Pulse'], 4)

        # Relative to defining qubit drive as +sigma_y type.
        # Measure <sigma X>
        # Phase of second drive is 180, such that
        self.cfg['second_qubit_phase'] = self.soccfg.deg2reg(180, gen_ch=self.cfg['qubit_ch'])
        prog = TimeDomainSpecProgram(self.soccfg, self.cfg)
        avg_pop = prog.acquire_populations(soc=self.soc, load_pulses=True)
        avg_x = 1 - 2 * np.asarray(avg_pop)  # Convert from avg of 0,1 shots to avg of +1,-1 shots

        # Measure <sigma Y>
        self.cfg['second_qubit_phase'] = self.soccfg.deg2reg(270, gen_ch=self.cfg['qubit_ch'])
        prog = TimeDomainSpecProgram(self.soccfg, self.cfg)
        avg_pop = prog.acquire_populations(soc=self.soc, load_pulses=True)
        avg_y = 1 - 2 * np.asarray(avg_pop)  # Convert from avg of 0,1 shots to avg of +1,-1 shots

        t_pts = self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts'])

        data = {'config': self.cfg, 'data': {'t_pts': t_pts, 'avg_x': avg_x, 'avg_y': avg_y}}
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data
        t_pts = data['data']['t_pts']
        avg_x = data['data']['avg_x'][0]
        avg_y = data['data']['avg_y'][0]

        plt.figure(figNum)
        plt.plot(t_pts, avg_x, '.-', color='Maroon', label=r"$\langle\sigma_X\rangle$")
        plt.plot(t_pts, avg_y, '.-', color='Aqua',  label=r"$\langle\sigma_Y\rangle$")
        plt.ylabel("Expectation")
        plt.xlabel("Elapsed time (2.34 ns)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname[:-4] + '.png')
        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.close(figNum)