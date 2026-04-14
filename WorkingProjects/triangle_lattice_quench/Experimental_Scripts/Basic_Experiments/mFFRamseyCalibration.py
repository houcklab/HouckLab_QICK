import datetime
import time
from locale import normalize

from matplotlib import pyplot as plt
from qick.asm_v2 import AsmV2

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepWaveformAveragerProgram import \
    SweepWaveformAveragerProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast, normalize_contrast
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *

from math import ceil

class RamseyFFCalProg(SweepWaveformAveragerProgram):
    def _initialize(self, cfg):
        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])

        FF.FFDefinitions(self)
        longest_length = self.cfg["start"] + self.cfg["expts"] * self.cfg["step"]
        # print(longest_length)
        # print(longest_length)

        # Qubit (Equal sigma for all)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])  # Qubit
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_1', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=0, gain=cfg["pi2_gain"])
        self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_2', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0],
                       phase=cfg["Second_Pulse_Angle"], gain=cfg["pi2_gain"])
        self.qubit_length_us = 4 * cfg["sigma"]
        # 1 cycle = 16 samples
        # cycle_counter: always 2+length of waveform in cycles
        self.add_reg(name='cycle_counter')
        # sample_counter: total samples Mod 16, but output (1...16) instead
        self.add_reg(name='sample_counter')
        # Set in before_reps of the "reps" loop (see self.__init__ above)

        # Increment the cycle and sample counter. Carry the one if sample_counter > 16.
        IncrementLength = AsmV2()
        IncrementLength.inc_reg(dst='cycle_counter', src=cfg["step"] // 16)
        IncrementLength.inc_reg(dst='sample_counter', src=cfg["step"] % 16)
        ############# If sample_counter > 16:
        IncrementLength.cond_jump("finish_inc", "sample_counter", "S", "-", 17)
        IncrementLength.inc_reg(dst='cycle_counter', src=+1)
        IncrementLength.inc_reg(dst='sample_counter', src=-16)
        IncrementLength.label("finish_inc")
        IncrementLength.nop()
        ##############
        # # Write into data memory for debugging
        # self.add_reg(name='data_counter')
        # self.write_reg(dst='data_counter', src=0)
        # IncrementLength.write_reg("temp", "w_length")
        # IncrementLength.inc_reg(addr='temp', src='sample_counter')
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "cycle_counter")
        # IncrementLength.inc_reg(dst='data_counter', src=+1)
        # IncrementLength.write_dmem("data_counter", "sample_counter")
        #############
        self.add_loop("expt_samples", int(self.cfg["expts"]), exec_before=IncrementLength)

        self.delay_auto(200)

    def _body(self, cfg):
        FF_QUBIT_DELAY = 0.085 # Time for FFPulses to asymptote
        # 1: FFPulses
        # self.delay_auto()
        # Length: 1 us to reach asymptotic value, qubit length for qubit, 0.1 us to account for relative qubit delay
        self.FFPulses(self.FFPulse, FF_QUBIT_DELAY + self.qubit_length_us)
        # first pi/2
        self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_1', t= FF_QUBIT_DELAY)
        self.delay(self.qubit_length_us + FF_QUBIT_DELAY)

        # 2: FFExpt
        # self.delay(self.cycles2us(max(3, ceil(self.cfg["expt_samples1"] / 16)) - 2))
        # self.delay_auto()
        self.FFLoad16Waveforms(self.FFExpts, self.FFPulse, cfg["IDataArray"])
        self.FFPulses_arb_length_and_delay(t_start=0)
        # self.delay(self.cycles2us(2))  # Placeholder correction
        # second pi/2
        self.FFPulses(self.FFPulse, FF_QUBIT_DELAY+self.qubit_length_us, t_start=0)
        self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_2', t=FF_QUBIT_DELAY)
        self.delay(self.qubit_length_us + FF_QUBIT_DELAY)
        # 3: FFReadouts
        self.FFPulses(self.FFReadouts, self.cfg["res_length"], t_start=0)
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive', t=0)
        self.wait(self.cfg["res_length"])
        self.delay(self.cfg["res_length"])  # us

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.delay(self.cfg["res_length"])
        self.FFInvert_arb_length_and_delay(t_start=0)
        self.FFPulses(-1 * self.FFPulse, 2*(self.qubit_length_us + FF_QUBIT_DELAY+0.1), t_start=0)
        self.delay(2*(self.qubit_length_us + FF_QUBIT_DELAY + 0.1))

    def loop_pts(self):
        return (self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts']) ,)

class FFRamseyCal(ExperimentClass):
    """
    RamseyCal
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        self.cfg.setdefault('pi_gain',  self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)
        self.cfg.setdefault('Y_meas_angle', 90)

        x_pts = self.cfg['start'] + self.cfg['step'] * np.arange(self.cfg['expts'])
        data = {'config': self.cfg,
                'data': {'expt_samples': x_pts, 'Y_meas_angle':self.cfg['Y_meas_angle']}}
        self.data = data
        # Measure in X basis
        start_time = time.time()
        self.cfg['Second_Pulse_Angle'] = 0
        prog = RamseyFFCalProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                            final_delay=self.cfg["relax_delay"], initial_delay=10.0)


        # pop_list = prog.acquire_populations(soc=self.soc, load_envelopes=True, rounds=self.cfg.get('rounds', 1),
        #                                     progress=progress)[0]
        # print(self.cfg['confusion_matrix'][0])
        # pop_list = correct_occ(pop_list, self.cfg['confusion_matrix'][0])
        # x_contrast = pop_to_expect(pop_list)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        self.data['data']['yi'] = avgi
        self.data['data']['yq'] = avgq
        x_contrast = normalize_contrast(avgi, avgq)

        self.data['data']['x_contrast'] = x_contrast
        self.soc.reset_gens()

        fig, axs = self.display(data, block=False, plotDisp=True)
        elapsed_time = time.time() - start_time
        print(f"Elapsed time (X measurement): {datetime.timedelta(seconds=int(elapsed_time))} (hh:mm:ss)")
        print("Expected finish:", datetime.datetime.fromtimestamp(time.time()+elapsed_time).strftime('%A %B %d, %I:%M:%S %p'))

        # Measure in Y basis
        self.cfg['Second_Pulse_Angle'] = self.cfg['Y_meas_angle']
        prog = RamseyFFCalProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                               final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        # pop_list = prog.acquire_populations(soc=self.soc, load_envelopes=True, rounds=self.cfg.get('rounds', 1),
        #                                     progress=progress)[0]
        # pop_list = correct_occ(pop_list, self.cfg['confusion_matrix'][0])
        # y_contrast = pop_to_expect(pop_list)
        #
        self.soc.reset_gens()
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        self.data['data']['yi'] = avgi
        self.data['data']['yq'] = avgq
        y_contrast = normalize_contrast(avgi, avgq)
        self.data['data']['y_contrast'] = y_contrast

        phi = np.arctan2(y_contrast, x_contrast)
        detunings = phi[1:] - phi[:-1]
        detunings[detunings > np.pi] -= 2 * np.pi
        detunings[detunings < -np.pi] += 2 * np.pi

        samples2us = self.soccfg.cycles2us(1) / 16
        detunings_MHz = detunings / (2 * np.pi) / samples2us
        self.data['data']['detunings_MHz'] = detunings_MHz

        print(f"Elapsed time (total): {datetime.timedelta(seconds=int(time.time() - start_time))} (hh:mm:ss)")

        self.save_data(data)

        plt.close(fig)

        return data


    def display(self, data=None, plotDisp = False, block=True, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        fig, (ax_trace, ax_detuning) = plt.subplots(2, 1, figsize=(12, 6))
        ax_trace.set_ylabel("a.u.")
        ax_trace.set_xlabel("Wait time (samples)")
        ax_detuning.set_ylabel("Detuning (MHz)")
        ax_detuning.set_xlabel("Wait time (samples)")

        expt_samples = data['data']['expt_samples']
        # xi, xq = data['data']['xi'], data['data']['xq']
        # x_contrast = normalize_contrast(xi, xq)
        ax_trace.plot(expt_samples, data['data']['x_contrast'], 'o-', color='blue', label=f'X')

        if 'y_contrast' in data['data']:
            # yi, yq = data['data']['yi'], data['data']['yq']
            # y_contrast = normalize_contrast(yi, yq)
            ax_trace.plot(expt_samples, data['data']['y_contrast'], 'o-', color='orange', label=f'Y')


            ax_detuning.plot(expt_samples[1:], data['data']['detunings_MHz'],'-o', color='red')

        ax_trace.legend()
        plt.suptitle(self.titlename)
        plt.savefig(self.iname[:-4] + '.png')

        if plotDisp:
            plt.show(block=block)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        return fig, (ax_trace, ax_detuning)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])