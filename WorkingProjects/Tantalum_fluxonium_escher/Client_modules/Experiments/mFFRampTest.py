###
# This file contains an NDAveragerProgram and ExperimentClass for testing the ramp speed of a fast flux pulse.
# The qubit is measured at some flux point, then, the flux is moved with a variable-time (linear) ramp to a different point.
# The qubit is then moved back to the original point and measured again.
# For the fluxonium experiment, the speed conditions are:
# * slower than any crossings (adiabatic), as well as the energy spliting between g and e. (speed compares to these squared)
# * faster than any decoherence channels
# Lev, June 2025: create file.
###
from qick import NDAveragerProgram

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions

class FFRampTest(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux
        # There is no qubit pulse

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        # 'periodic' would not make sense for this experiment
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]), mode="oneshot")

        # Define the fast flux ramp. For now, just linear ramp is supported
        if self.cfg["ff_ramp_style"] == "linear":
            PulseFunctions.create_ff_ramp(self, reversed = False)
            PulseFunctions.create_ff_ramp(self, reversed = True)
        else:
            print("Need an ff_ramp_style! only \"linear\" supported at the moment.")

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        """
        Measures at original flux spot, plays ff ramp to second flux spot, waits, plays reversed ff ramp, measures.
        :return:
        """
        #TODO this doesn't really make sense as written, it would only really work for starting ramp from 0
        adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0])

        # play fast flux ramp
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"])

        self.sync_all(self.us2cycles(0.01)) # Wait for a few ns to align channels

        # trigger measurement, play measurement pulse, wait for relax_delay_1
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t = 0, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay_1"]))

        self.sync_all(self.us2cycles(self.cfg["ff_delay"])) # Wait for some time at the new flux spot

        # play reversed fast flux ramp, return to original spot
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"])

        self.sync_all(self.us2cycles(0.01)) # Wait for a few ns to align channels

        # trigger measurement, play measurement pulse, wait for relax_delay_2
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                     t = 0, wait = True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay_2"]))


    # Override acquire such that we can collect the single-shot data
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)

        # self.get_raw() has data in format (#channels, #reps, #measurements/expt, 2)
        # self.di/q_buf[0] have (rep1_meas1, rep1_meas2, ... rep1_measN, rep1_meas1, ...)
        # reshape to have [[rep1_meas1, rep1_meas2], [rep2_meas1, rep2_meas2], ...]
        return self.di_buf[0].reshape(-1, 2), self.dq_buf[0].reshape(-1, 2)

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "linear",  # --Fixed
        "read_length": 5,  # [us]
        "read_pulse_gain": 8000,  # [DAC units]
        "read_pulse_freq": 7392.25,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "const",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": 100, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 10, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive

        # Sweep parameters
        "ff_ramp_length_start": 1,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 5,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_expts": 10, # [int] Number of points in the ff ramp length sweep

        "yokoVoltage": 0,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 10,  # [us] Relax delay after first readout
        "relax_delay_2": 10, # [us] Relax delay after second readout
        "reps": 1000,
        "sets": 5,
    }



class FFRampTest_Experiment(ExperimentClass):
    """

    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

    def acquire(self, progress=False, debug=False):
        ramp_lengths = np.linspace(self.cfg["ff_ramp_length_start"], self.cfg["ff_ramp_length_stop"],
                                  num = self.cfg["ff_ramp_expts"])
        i_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))
        q_arr = np.zeros((self.cfg["ff_ramp_expts"], self.cfg["reps"], 2))

        for idx, length in enumerate(ramp_lengths):
            prog = FFRampTest(self.soccfg, self.cfg | {"ff_ramp_length": length})

            # Collect the data
            i_arr[idx], q_arr[idx] = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             save_experiments=None, #readouts_per_experiment=2,
                                             start_src="internal", progress=progress)

        data = {'config': self.cfg, 'data': {'ramp_lengths': self.ramp_lengths, 'i_arr': i_arr, 'q_arr': q_arr}}
        self.data = data

        return data

    def display(self, data=None, plot_disp = False, fig_num = 1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi[0][0] + 1j * avgq[0][0]
        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)
        while plt.fignum_exists(num=fig_num): ###account for if figure with number already exists
            fig_num += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=fig_num)

        ax0 = axs[0].plot(x_pts, avgphase, 'o-', label="phase")
        axs[0].set_ylabel("deg")
        axs[0].set_xlabel("Qubit Frequency (GHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="magnitude")
        axs[1].set_ylabel("ADC units")
        axs[1].set_xlabel("Qubit Frequency (GHz)")
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.abs(avgi[0][0]), 'o-', label="I - Data")
        axs[2].set_ylabel("ADC units")
        axs[2].set_xlabel("Qubit Frequency (GHz)")
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.abs(avgq[0][0]), 'o-', label="Q - Data")
        axs[3].set_ylabel("ADC units")
        axs[3].set_xlabel("Qubit Frequency (GHz)")
        axs[3].legend()

        plt.tight_layout()
        fig.subplots_adjust(top=0.95)
        plt.suptitle(self.fname + '\nYoko voltage %f V, FF amplitude %d DAC.' % (self.cfg['yokoVoltage'], self.cfg['ff_gain']))

        plt.savefig(self.iname)

        if plot_disp:
            plt.show(block=False)
            plt.pause(2)

        else:
            fig.clf(True)
            plt.close(fig)




    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

    # Used in the GUI, returns estimated runtime in seconds
    def estimate_runtime(self):
        return self.cfg["reps"] * self.cfg["qubit_freq_expts"] * (self.cfg["relax_delay"] + self.cfg["ff_length"]) * 1e-6  # [s]
