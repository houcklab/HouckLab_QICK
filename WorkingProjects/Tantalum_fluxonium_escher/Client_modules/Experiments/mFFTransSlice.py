###
# This file performs a transmission slice at a particular FF point.
# This requires several helper experiment files due to the way the RFSOC qick works.
# Lev, September 2025: create file.
###

from qick.averager_program import AveragerProgram
from tqdm import tqdm

from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt


# ====================================================== #

class FFTransSlice_Experiment(ExperimentClass):
    """
    This experiment runs a slice of transmission vs. frequency at some fast flux value.
    Since you cannot sweep readout frequency inside an experiment, this is accomplished by creating two program
    classes, one of which sets the fast flux value with a const pulse and stdysel = 'last', while the other measures.
    """
    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section
        "read_pulse_style": "const",    # --Fixed
        "read_length": 5,               # [us]
        "read_pulse_gain": 8000,        # [DAC units]
        "ro_mode_periodic": False,      # Bool: if True, keeps readout tone on always

        # Fast flux pulse parameters
        "ff_gain": 1,                   # [DAC units] Gain for fast flux pulse
        "ff_ch": 6,                     # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                    # Nyquist zone to use for fast flux drive

        # Transmission Experiment. Parameter naming convention preserved from mTransmission_SaraTest below
        #"read_pulse_freq": 7000,        # [MHz] Centre frequency of transmission sweep
        #"TransSpan": 5,                 # [MHz] Span of transmission sweep
        #"TransNumPoints": 301,          # Number of poitns in transmission sweep

        # New format parameters for transmission experiment
        "start_freq": 5000,             # [MHz] Start frequency of sweep
        "stop_freq": 6000,              # [MHz] Stop frequency of sweep
        "num_freqs": 101,               # Number of frequency points to use
        "init_time": 1,                 # [us] Thermalisation time after FF to new point before starting measurement
        "therm_time": 1,                # [us] Thermalisation time after moving FF down to 0 for measurement, if measure_at_0
        "measure_at_0": False,          # [Bool] Do we go back to 0 DAC units on the FF to measure?

        "yokoVoltage": 0,               # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,              # [us] Delay after measurement before starting next measurement
        "reps": 1000,                   # Reps of measurements; init program is run only once
        "sets": 5,                      # Sets of whole measurement; used in GUI
    }

    # Create some internal program classes that will only ever be used inside of this ExperimentClass.

    # Sets up the FF to the new point, waits some time to allow thermalisation, and keeps the fast flux at the new value
    # It may be possible to put this in the initialise of the other experiment, but I'm not 100% sure of the timing
    # of the execution of that, so let's just be explicit by having a separate program.
    class FFInit_Prog(AveragerProgram):
        def initialize(self):
            # Declare channels
            self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux

            # Define the fast flux pulse. The length is very short, since we will keep it const through mode or stdysel
            # stdysel = 'last' keeps the generator on the last value used, which in this case is the const value
            # This persists even when the tproc is done running the program. Could also use mode = 'periodic'
            self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0, gain=self.cfg["ff_gain"],
                                     length=self.us2cycles(0.01, gen_ch=self.cfg["ff_ch"]), stdysel = 'last')

            # Give some time to run the commands on the tproc
            self.sync_all(self.us2cycles(0.05))

        def body(self):
            self.pulse(ch=self.cfg["ff_ch"], t = 0)  # play fast flux pulse

            self.sync_all(self.us2cycles(self.cfg["init_time"]))  # Wait to allow everything to thermalise at this flux

    class FFTransPoint_Prog(AveragerProgram):
        def initialize(self):
            # Declare channels
            self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout

            # Declare readout
            for ch in self.cfg["ro_chs"]:
                self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                     freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

            # Readout pulse
            mode_setting = "periodic" if self.cfg["ro_mode_periodic"] else "oneshot"
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                     freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                        ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                     gain=self.cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]),
                                     mode=mode_setting)

            self.sync_all(self.us2cycles(0.05))

        def body(self):
            # For convenience
            adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])

            # If measuring at 0 ff DAC units, send back to 0
            if self.cfg["measure_at_0"]:
                self.set_pulse_registers(ch=self.cfg['ff_ch'], style="const", mode="oneshot", freq=0, phase=0, gain=0, length=3)
                self.pulse(ch=self.cfg['ff_ch'], t=0)

            # trigger measurement, play measurement pulse, wait for qubit to relax
            self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                         wait=True, syncdelay=self.us2cycles(self.cfg["relax_delay"]))

            # If measuring at 0 ff DAC units, go back to high value and leave it there; wait for init time
            if self.cfg["measure_at_0"]:
                self.set_pulse_registers(ch=self.cfg['ff_ch'], style="const", mode="oneshot", freq=0, phase=0,
                                         gain=self.cfg["ff_gain"], length=3, stdysel = 'last')
                self.pulse(ch=self.cfg['ff_ch'], t=0)
                self.sync_all(self.us2cycles(self.cfg["therm_time"]))

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

        # Declare some arrays

        # This is the way consistent with mTransmission_SaraTest, which is bad because 1) TransSpan is half of span and
        # 2) it doesn't actually go to the correct endpoint, it's one step off. Uncomment the lines if you prefer this
        #self.fpts = (self.cfg['read_pulse_freq'] - self.cfg['TransSpan'] +
        #             2 * self.cfg['TransSpan'] / self.cfg['TransNumPoints'] * np.arange(self.cfg['TransNumPoints']))
        # self.avgi = np.zeros(self.cfg['TransNumPoints'])
        # self.avgq = np.zeros(self.cfg['TransNumPoints'])

        self.fpts = np.linspace(start = self.cfg['start_freq'], stop = self.cfg['stop_freq'], num = self.cfg['num_freqs'])
        self.avgi = np.zeros(self.cfg['num_freqs'])
        self.avgq = np.zeros(self.cfg['num_freqs'])

        self.data = {}

    def acquire(self, progress=False, debug=False):
        # First, run init program. Only one rep for this one!
        init_prog = self.FFInit_Prog(soccfg = self.soccfg, cfg = self.cfg | {'reps': 1})
        init_prog.run_rounds(self.soc, progress = False)  # No measure in this one

        # Now, loop over transmission frequencies -- we are not allowed to change frequency inside a program!
        for i, freq in enumerate(tqdm(self.fpts, disable = not progress)):
            trans_prog = self.FFTransPoint_Prog(soccfg = self.soccfg, cfg = self.cfg | {'read_pulse_freq': freq})

            # Collect the data
            outp = trans_prog.acquire(self.soc, angle=None, load_pulses=True,
                                                   readouts_per_experiment=1, start_src="internal", progress=False)
            self.avgi[i] = outp[0][0][0]
            self.avgq[i] = outp[1][0][0]

        self.data = {'config': self.cfg, 'data': {'fpts': self.fpts, 'avgi': self.avgi, 'avgq': self.avgq}}

        # Return fast flux to 0
        self.soc.reset_gens()

        return self.data

    def display(self, data=None, plot_disp = False, fig_num = 1, **kwargs):

        if data is None:
            data = self.data

        x_pts = data['data']['fpts']/1000  # Frequency in GHz
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig  = avgi + 1j * avgq

        # Correct for additional phase roll from rfsoc
        sig = sig * np.exp(-1j * x_pts * 2 * np.pi * self.cfg["RFSOC_delay"]) # This is an empirically-determined "electrical delay"
        # It is much larger than the real, physical electrical delay (which is more like 80 ns, while this one is around a us),
        # and is caused by the fact that the RFSOC has two different clocks for the output and input. We can safely just remove this phase.
        # Expect the effective electrical delay to change when the RFSOC is rebooted.

        avgsig = np.abs(sig)
        avgphase = np.angle(sig, deg=True)
        while plt.fignum_exists(num=fig_num): ###account for if figure with number already exists
            fig_num += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=fig_num)

        ax0 = axs[0].plot(x_pts, np.unwrap(avgphase, period = 360), 'o-', label="phase")
        axs[0].set_ylabel("deg")
        axs[0].set_xlabel("Frequency (GHz)")
        axs[0].legend()

        ax1 = axs[1].plot(x_pts, avgsig, 'o-', label="magnitude")
        axs[1].set_ylabel("Transmission ADC units")
        axs[1].set_xlabel('Frequency (GHz)')
        axs[1].legend()

        ax2 = axs[2].plot(x_pts, np.real(sig), 'o-', label="I - Data")
        axs[2].set_ylabel("Transmission ADC units")
        axs[2].set_xlabel('Frequency (GHz)')
        axs[2].legend()

        ax3 = axs[3].plot(x_pts, np.imag(sig), 'o-', label="Q - Data")
        axs[3].set_ylabel("Transmission ADC units")
        axs[3].set_xlabel('Frequency (GHz)')
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
        #return (self.cfg['init_time'] + self.cfg["reps"] * self.cfg["TransNumPoints"] *
        #                                (self.cfg["relax_delay"] + self.cfg["read_length"]) * 1e-6)  # [s]
        return (self.cfg['init_time'] + self.cfg["reps"] * self.cfg["num_freqs"] *
                                (self.cfg["relax_delay"] + self.cfg["read_length"]) * 1e-6)  # [s]