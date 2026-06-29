import math
import warnings

import numpy as np
from matplotlib import pyplot as plt

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF


class QuenchProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        # print(cfg["res_freqs"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])

        FF.FFDefinitions(self)

        # qubit init pulses (one Gaussian envelope per pulse)
        for i in range(len(self.cfg["qubit_gains"])):
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=0,
                           gain=self.cfg["qubit_gains"][i])

        # qubit quench pulse (uses first pulse's sigma envelope)
        quench_freq = cfg["quench_freq"]
        quench_gain = cfg["quench_gain"]
        quench_phase = cfg["quench_phase"]

        self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_quench', style="arb", envelope=f"qubit0",
                       freq=quench_freq,
                       phase=quench_phase,
                       gain=quench_gain)

        self.qubit_total_length_us = 4 * sum(cfg["sigma"])


    def _body(self, cfg):

        ### Init Pulse
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        if self.cfg['init_pulse']:
            for i in range(len(self.cfg["qubit_gains"])):
                time_ = FF_Delay_time if i == 0 else 'auto'
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_{i}', t=time_)

        self.delay_auto()

        ### Ramp
        if self.cfg["expt_samples_ramp"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_ramp"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_ramp"], waveform_label='FFRamp')
            self.delay_auto()

        ### Quench
        if self.cfg["expt_samples_quench"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_quench"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_quench"], waveform_label='FFQuench')
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_quench', t='auto')
            self.delay_auto()

        ### Dynamics
        # print(f'dynamics')
        # print(self.cfg["IQArray_dynamics"])
        if self.cfg["expt_samples_dynamics"] >= 1:
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples_dynamics"],
                                 self.FFPulse, IQPulseArray=self.cfg["IQArray_dynamics"], waveform_label='FFDynamics')
            self.delay_auto()

        ### Readout

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        self.delay_auto()


class RampQuenchBase(SweepExperiment1D_lines):
    def init_sweep_vars(self):

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = None
        self.x_points = None
        self.xlabel = None

        self.cfg['init_pulse'] = self.cfg.get('init_pulse', True)


    def set_up_instance(self):

        ### round samples to nearest integer
        self.cfg['expt_samples_ramp'] = round(self.cfg['expt_samples_ramp'])
        self.cfg['expt_samples_quench'] = round(self.cfg['expt_samples_quench'])
        self.cfg['expt_samples_dynamics'] = round(self.cfg['expt_samples_dynamics'])


        ### option to offset step pulses
        t_offset = self.cfg.get('t_offset',0)
        if isinstance(t_offset, int):
            # this won't do anything because we are offsetting every channel relative to the channel with the least offset
            t_offset = np.array([t_offset] * len(self.cfg['fast_flux_chs']))
        elif isinstance(t_offset, (list, np.ndarray, tuple)):
            np.array(t_offset, dtype=int)
        else:
            raise TypeError('t_offset must be an int or array like of ints')


        t_offset -= np.min(t_offset)
        # print("Actual offsets:", t_offset)

        assert ((t_offset >= 0).all())
        ff_ro_pad = math.ceil(np.max(t_offset) / 16) * 16

        ### Ramp
        IQArray_ramp = FFEnvelope_Helpers.CompensatedRampArrays(self.cfg, 'Gain_Pulse', 'Gain_RampInit',
                                                                           'Gain_Expt', self.cfg['expt_samples_ramp'])

        self.cfg["IQArray_ramp"] = IQArray_ramp

        ### Quench
        # TODO for now reuse the Gain_BS label, might want to change in future
        gain_ramp = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Expt')
        gain_quench = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_BS')
        gain_dynamics = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Dynamics')
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, 'Gain_Readout')
        warnings.warn("gain_quench and gain_dynamics are currently identical! josh's build_config sets Gain_BS"
                      "and Gain_Dynamics equal to each other, and Gain_BS is propagated to gain_quench.")

        # print(f'gain_ramp: {gain_ramp}')
        # print(f'gain_quench: {gain_quench}')
        # print(f'gain_readout: {gain_readout}')

        IQArray_quench = []
        for j in range(len(gain_ramp)):
            ramp = gain_ramp[j]
            quench = gain_quench[j]

            arr = np.concatenate([np.full(t_offset[j], ramp),
                                  np.full(self.cfg['expt_samples_quench'], quench)])
            arr = Compensate(arr - ramp, ramp, j + 1)
            IQArray_quench.append(arr)

        ### Dynamics
        IQArray_dynamics = []
        for j in range(len(gain_quench)):
            ramp = gain_ramp[j]
            quench = gain_quench[j]


            arr = np.concatenate([np.full(t_offset[j], quench),
                                  np.full(self.cfg['expt_samples_dynamics'], ramp)])
            arr = Compensate(arr - quench, quench, j + 1)
            IQArray_dynamics.append(arr)

        ### Readout
        IQArray_readout = []
        for j in range(len(gain_ramp)):
            ramp = gain_ramp[j]
            readout = gain_readout[j]

            arr = np.concatenate([np.full(t_offset[j], ramp),
                                  np.full(ff_ro_pad - t_offset[j], readout)])
            arr = Compensate(arr - ramp, ramp, j + 1)
            IQArray_readout.append(arr)

        self.cfg["IQArray_quench"] = IQArray_quench
        self.cfg["IQArray_dynamics"] = IQArray_dynamics
        self.cfg["IQArray_readout"] = IQArray_readout

        # print(f'expt_samples_ramp: {self.cfg["expt_samples_ramp"]}')
        # print(f'expt_samples_quench: {self.cfg["expt_samples_quench"]}')
        # print(f'expt_samples_dynamics: {self.cfg["expt_samples_dynamics"]}')

        # total_IQArray = [np.concatenate([IQArray_ramp[i], IQArray_quench[i], IQArray_dynamics[i], IQArray_readout[i]]) for i in range(len(IQArray_quench))]
        #
        # if False and self.cfg['expt_samples_dynamics'] > 150:
        #     plt.figure()
        #     for i in range(len(total_IQArray)):
        #         print(f'Q{i+1}: {total_IQArray[i]}')
        #         plt.plot(total_IQArray[i], label=f'Q{i+1}')
        #     plt.axvline(self.cfg['expt_samples_ramp'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'], color='purple', linestyle='--')
        #     plt.axvline(self.cfg['expt_samples_ramp'] + self.cfg['expt_samples_quench'] + self.cfg['expt_samples_dynamics'], color='purple', linestyle='--')
        #     plt.legend()
        #     plt.show()



class RampQuenchDynamics(RampQuenchBase):
    def init_sweep_vars(self):

        super().init_sweep_vars()

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_dynamics'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting



class RampQuenchFreq(RampQuenchBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = 'quench_freq'
        self.x_points = np.linspace(self.cfg['freq_start'], self.cfg['freq_end'],
                                    self.cfg['freq_num_points'])
        self.xlabel = 'Frequency (MHz)'  # for plotting


class RampQuenchSweepRampTime(RampQuenchBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_ramp'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting

class RampQuenchSweepQuenchTime(RampQuenchBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples_quench'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting



class RampQuenchRabi(RampQuenchBase):
    def init_sweep_vars(self):
        super().init_sweep_vars()

        self.Program = QuenchProgram
        self.z_value = 'population_corrected'

        self.x_key = 'quench_gain'
        self.x_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'],
                                    self.cfg['gain_num_points'])

        self.xlabel = 'gain (a.u.)'  # for plotting

