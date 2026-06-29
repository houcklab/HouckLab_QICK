import math
import warnings

import numpy as np
from matplotlib import pyplot as plt

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND
from WorkingProjects.triangle_lattice_quench.Helpers import FFEnvelope_Helpers
from WorkingProjects.triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensate
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF


class MottQuenchBasicProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        # print(cfg["res_freqs"])

        # Qubit Readout pulses
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
        for i in range(len(cfg["qubit_gains"])):
            gain = cfg["qubit_gains"][i]
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=0,
                           gain=gain)
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_pi2_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=0,
                           gain=gain / 2)
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_measurement_pi2_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=self.cfg["measurement_pi2_phase"],
                           gain=gain / 2)

        self.qubit_total_length_us = 4 * sum(cfg["sigma"])


    def _body(self, cfg):

        ### Init Pulse
        FF_Delay_time = 0.2
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + FF_Delay_time)

        for i in range(len(self.cfg["qubit_gains"])):
            time_ = FF_Delay_time if i == 0 else 'auto'
            if i == int(self.cfg['pi2_init_index']):
                print(f"Preparing Qubit_Pulse index {int(self.cfg['pi2_init_index'])} in a superposition state.")
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_pi2_{i}', t=time_)
            else:
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive_{i}', t=time_)

        self.delay_auto()


        ### Dynamics
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples"],
                             self.FFPulse, IQPulseArray=self.cfg["IQArray"], waveform_label='FFDynamics')
        self.delay_auto()

        ### Readout
        Second_FFPulse_delay = 0.100
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + Second_FFPulse_delay)
        for i in range(len(self.cfg["qubit_gains"])):
            time_ = Second_FFPulse_delay if i == 0 else 'auto'
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_measurement_pi2_{i}', t=time_)
        self.delay_auto()

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + Second_FFPulse_delay)
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples"],
                             -1 * self.FFPulse, IQPulseArray=[-arr for arr in self.cfg["IQArray"]], waveform_label='FFDynamicsInverse')

        self.delay_auto()


class MottQuenchBase(SweepExperimentND):
    def init_sweep_vars(self):

        self.Program = MottQuenchBasicProgram
        self.z_value = 'population_corrected'

        self.x_key = None
        self.x_points = None
        self.xlabel = None



    def set_up_instance(self):

        ### round samples to nearest integer
        self.cfg['expt_samples'] = round(self.cfg['expt_samples'])


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
        ff_ro_pad = 16+math.ceil(np.max(t_offset) / 16) * 16

        gain_pulse = FFEnvelope_Helpers.get_gains(self.cfg, "Gain_Pulse")
        gain_expt = FFEnvelope_Helpers.get_gains(self.cfg, "Gain_Expt")
        gain_readout = FFEnvelope_Helpers.get_gains(self.cfg, "Gain_Readout")


        IQArray_quench = []
        for j in range(len(t_offset)):
            arr = np.concatenate([np.full(t_offset[j], gain_pulse[j]),
                                  np.full(self.cfg['expt_samples'], gain_expt[j]),
                                  np.full(ff_ro_pad, gain_readout[j])])
            arr = Compensate(arr - gain_pulse[j], gain_pulse[j], Qubit=j + 1)
            IQArray_quench.append(arr)

        self.cfg['IQArray'] = IQArray_quench

        # William-Oliver common-frequency dwell: the seed pi/2 fires with the seed qubit
        # already AT Expt_FF (partner detuned). So the dwell steps FFSeed -> FFExpts, where
        # only the PARTNER moves idle(Gain_Pulse) -> Gain_Expt; the seed + spectators are
        # already at their Expt level and hold. Build the same compensated profile as IQArray
        # but with each channel's pad/start level = its FFSeed target (gain_expt, except the
        # partner channel = gain_pulse). Gated; only built when the W-O scheme is requested.
        if self.cfg.get('second_pulse_at_dynamics') and self.cfg.get('meas_pi2_freq') is not None:
            qp = self.cfg.get('Qubit_Pulse') or self.cfg.get('_Qubit_Pulse_list')
            partner_ff_idx = int(str(qp[int(self.cfg['swept_qubit'])])) - 1  # FF chans are chips 1..N
            IQArray_wo = []
            for j in range(len(t_offset)):
                start = gain_expt[j] if j != partner_ff_idx else gain_pulse[j]
                arr = np.concatenate([np.full(t_offset[j], start),
                                      np.full(self.cfg['expt_samples'], gain_expt[j]),
                                      np.full(ff_ro_pad, gain_readout[j])])
                arr = Compensate(arr - start, start, Qubit=j + 1)
                IQArray_wo.append(arr)
            self.cfg['IQArray_wo'] = IQArray_wo


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



class MottQuenchDynamics(MottQuenchBase, SweepExperiment1D_lines):
    def init_sweep_vars(self):

        super().init_sweep_vars()

        self.z_value = 'population_corrected'

        self.x_key = 'expt_samples'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting

    def analyze(self, data):
        data['data']['measurement_pi2_phase'] = self.cfg['measurement_pi2_phase']

# class RampQuenchFreq(RampQuenchBase):
#     def init_sweep_vars(self):
#         super().init_sweep_vars()
#
#         self.Program = QuenchProgram
#         self.z_value = 'population_corrected'
#
#         self.x_key = 'quench_freq'
#         self.x_points = np.linspace(self.cfg['freq_start'], self.cfg['freq_end'],
#                                     self.cfg['freq_num_points'])
#         self.xlabel = 'Frequency (MHz)'  # for plotting
#
#
# class RampQuenchSweepRampTime(RampQuenchBase):
#     def init_sweep_vars(self):
#         super().init_sweep_vars()
#
#         self.Program = QuenchProgram
#         self.z_value = 'population_corrected'
#
#         self.x_key = 'expt_samples_ramp'
#         self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
#                                     self.cfg['samples_num_points'])
#         self.xlabel = 'Samples (4.65/16 ns)'  # for plotting
#
# class RampQuenchSweepQuenchTime(RampQuenchBase):
#     def init_sweep_vars(self):
#         super().init_sweep_vars()
#
#         self.Program = QuenchProgram
#         self.z_value = 'population_corrected'
#
#         self.x_key = 'expt_samples_quench'
#         self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
#                                     self.cfg['samples_num_points'])
#         self.xlabel = 'Samples (4.65/16 ns)'  # for plotting
#
#
#
# class RampQuenchRabi(RampQuenchBase):
#     def init_sweep_vars(self):
#         super().init_sweep_vars()
#
#         self.Program = QuenchProgram
#         self.z_value = 'population_corrected'
#
#         self.x_key = 'quench_gain'
#         self.x_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'],
#                                     self.cfg['gain_num_points'])
#
#         self.xlabel = 'gain (a.u.)'  # for plotting

