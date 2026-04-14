import time
import datetime

from itertools import product


import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import RampCurrentCalibration1D
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCorrelationExperiments import generate_counts, display_counts

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment1D_plots import SweepExperiment1D_plots

class BB1(FFAveragerProgramV2):
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

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])

        phase_1 = cfg['phase_1']
        phase_2 = cfg['phase_2']

        if not 'qubit_gains_2' in cfg or cfg['qubit_gains_2'] is None:
            cfg['qubit_gains_2'] = cfg['qubit_gains']

        if not 'qubit_gains_3' in cfg or cfg['qubit_gains_3'] is None:
            cfg['qubit_gains_3'] = [2*gain for gain in cfg['qubit_gains_2']]

        if not 'qubit_gains_4' in cfg or cfg['qubit_gains_4'] is None:
            cfg['qubit_gains_4'] = cfg['qubit_gains_2']

        for i in range(len(self.cfg["qubit_gains"])):

            # print(f'adding naive with gain: {self.cfg["qubit_gains"][i]}')
            # print(f'adding pulse 2 with gain: {self.cfg["qubit_gains_2"][i]}')
            # print(f'adding pulse 3 with gain: {self.cfg["qubit_gains_3"][i]}')
            # print(f'adding pulse 4 with gain: {self.cfg["qubit_gains_4"][i]}')
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}_naive', style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][i],
                       phase=90, gain=cfg["qubit_gains"][i])

            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}_2', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i],
                           phase=90 + phase_1, gain=cfg["qubit_gains_2"][i])

            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}_3', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i],
                           phase=90 + phase_2, gain=cfg["qubit_gains_3"][i])

            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive{i}_4', style="arb", envelope="qubit",
                           freq=cfg["qubit_freqs"][i],
                           phase=90 + phase_1, gain=cfg["qubit_gains_4"][i])

        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        # print(cfg["readout_lengths"])
        FF_Delay_time = 10
        self.FFPulses(self.FFPulse, 4 * len(self.cfg["qubit_gains"]) * self.cfg['sigma'] * 4 + FF_Delay_time)
        for i in range(len(self.cfg["qubit_gains"])):
            if i == 0:
                time = FF_Delay_time
            else:
                time = 'auto'

            if self.cfg["qubit_gains"][i] != 0:
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}_naive', t=time)
            if self.cfg["qubit_gains_2"][i] != 0:
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}_2', t='auto')
            if self.cfg["qubit_gains_3"][i] != 0:
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}_3', t='auto')
            if self.cfg["qubit_gains_4"][i] != 0:
                self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_drive{i}_4', t='auto')

        self.delay_auto()

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + FF_Delay_time)

        self.delay_auto()


    # def acquire(self, soc, threshold=None, angle=None, load_envelopes=True, readouts_per_experiment=1, save_experiments=None,
    #             start_src="internal", progress=False):
    #     start = time.time()
    #     super().acquire(soc, load_envelopes=load_envelopes, progress=progress)
    #     end = time.time()
    #
    #     return self.collect_shots()

    def collect_shots(self):
        all_i = []
        all_q = []

        d_buf = self.get_raw() # [(*self.loop_dims, nreads, 2) for ro in ros]
        # print(np.array(d_buf).shape)
        for i in range(len(d_buf)):
            shots_i0 = d_buf[i][..., -1, 0] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
            shots_q0 = d_buf[i][..., -1, 1] / self.us2cycles(self.cfg['readout_lengths'][i], ro_ch=self.cfg['ro_chs'][i])
            all_i.append(shots_i0)
            all_q.append(shots_q0)
        return all_i,all_q


### Simple Singleshot experiment, but uses a separately calibrated angle and threshold to pick 0 or 1
class BB1_Base(ExperimentClass):
    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):

        readout_list = self.cfg["Qubit_Readout_List"]
        self.num_qubits = len(readout_list)

        self.cfg['number_of_pulses'] = self.cfg.get('number_of_pulses', 1)
        self.cfg['Pulse'] = self.cfg.get('Pulse', True)

        num_shots = self.cfg['reps'] * self.cfg.get('rounds', 1)

        Z_mat = [np.full(num_shots, np.nan) for _ in readout_list]

        # raw i and q data
        self.I_mat = [np.full(num_shots, np.nan) for _ in readout_list]
        self.Q_mat = [np.full(num_shots, np.nan) for _ in readout_list]


        self.data = {
            'config': self.cfg,
            'data': {'population_shots': Z_mat,
                     "I": self.I_mat,
                     "Q": self.Q_mat,
                     'readout_list': readout_list,
                     'angle': self.cfg['angle'],
                     'threshold': self.cfg['threshold'],
                     'confusion_matrix': self.cfg['confusion_matrix'],
                     'Qubit_Readout_List': self.cfg["Qubit_Readout_List"]},

        }

        self.last_saved_time = time.time()

        '''iterating through itertools.product is equivalent to a nested for loop such as
        for i, y_pt in enumerate(self.y_points):
            for j, x_pt in enumerate(self.x_points):'''

        prog = BB1(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                final_delay=self.cfg["relax_delay"], initial_delay=10.0)



        excited_populations, (self.I_mat, self.Q_mat) = prog.acquire_population_shots(soc=self.soc, return_shots=True,
                                                            load_envelopes=True,
                                                            progress=progress, rounds=1)

        excited_populations = np.array(excited_populations)

        for ro_index in range(len(readout_list)):
            Z_mat[ro_index] = excited_populations[ro_index]

        counts = generate_counts(excited_populations, num_qubits=self.num_qubits)
        self.data['data']['counts'] = counts

        self.save_data(data=self.data)
        return self.data

    def display(self, data=None, **kwargs):

        if data is None:
            data = self.data

        counts = data['data']['counts']

        display_counts(counts, self.titlename, num_qubits=self.num_qubits)


        # also display points on IQ plane
        fig, axs = plt.subplots((self.num_qubits+1)//2,2, figsize=(8, 6*self.num_qubits//2), constrained_layout=True)

        for i in range(self.num_qubits):

            ax = axs[i]

            angle = self.cfg['angle'][i]
            threshold = self.cfg['threshold'][i]

            I = self.I_mat[i]
            Q = self.Q_mat[i]


            new_I = I * np.cos(angle) - Q * np.sin(angle)
            new_Q = I * np.sin(angle) + Q * np.cos(angle)

            ax.scatter(new_I, new_Q, s=2, alpha=0.5)

            ax.axvline(threshold, linestyle='--', color='black', label=f'Threshold: {threshold}')

            ax.set_xlabel('I (a.u.)')
            ax.set_ylabel('Q (a.u.)')

            ax.set_title(f'Q{self.cfg["Qubit_Readout_List"][i]}')

        if self.num_qubits % 2 == 1:
            axs[-1].axis('off')

        plt.tight_layout()
        plt.suptitle(self.titlename)
        plt.show()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


class BB1_SweepGain(SweepExperiment1D_plots):
    def init_sweep_vars(self):
        self.Program = BB1

        swept_gain_index = self.cfg['swept_gain_index'] # 1 is second pulse
        if not swept_gain_index in [0,1,2,3]:
            raise ValueError(f'Invalid swept_gain_index: {swept_gain_index}')

        swept_index = self.cfg['swept_qubit'] - 1

        if swept_gain_index == 0:
            self.x_key = ("qubit_gains", swept_index)
        else:
            self.x_key = (f"qubit_gains_{swept_gain_index+1}", swept_index)

        self.x_points = np.linspace(self.cfg['gainStart'], self.cfg['gainStop'], self.cfg['gainNumPoints'], dtype=int) / 32766
        self.z_value = 'population'  # contrast or population
        self.xlabel = f'Gain 2 (x32766)'  # for plotting
        self.ylabel = f'Population'  # for plotting


        self.cfg['qubit_gains_2'][swept_index] =  self.cfg['swept_qubit_gain_2']
        self.cfg['qubit_gains_3'][swept_index] =  self.cfg['swept_qubit_gain_3']
        self.cfg['qubit_gains_4'][swept_index] =  self.cfg['swept_qubit_gain_4']

        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))


