# This file is meant to do everything in the noise spectroscopy experiment.
# It is partially based on mFFRampTest, but that file is meant for testing the properties of the ramp, and so has many
# different arguments but performs one basic experiment. This one will be more narrowly-taylored to the data we want to
# take for this project, but also perform more experiments (e.g., probably T1 at each flux point as well).
# This means that this file will include several program sub-files. These are not separate files because they will
# assume that we are performing several different experiments at a given FF point, and so will be slightly different
# from a general-purpose experiment file.
# OK actually I think I take that back, let's not write a 10000 line file and reduplicate a bunch of existing code.

import sys
from datetime import time

from qick import NDAveragerProgram, AveragerProgram
import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFRampTest import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFSpecSlice import FFSpecSlice
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFTransSlice import FFTransSlice_Experiment
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions

class FF_Noise_spectroscopy(ExperimentClass):
    """ This experiment loops ff_gain from ff_gain_start to ff_gain_stop, and runs the following things at each value:
    1) FFTransSlice: either regular, or going back to 0 to readout.
    2) FFSpecSlice: this always pings the qubit at ff_gain and reads out at 0, but no need to thermalise at ff_gain
    3) FFInitProg: moves to ff_gain, waits a long time (1 s) to make sure everything is stable.
    4) FFSingleShot: defined here. Thermalises at ff_gain, moves back to 0 to read out.
    5) FFRampTest: in cycle_number mode, using same parameters as above. Check error introduced by ramp.

    FFSingleShot does not collect a reference gaussian, since we can just the one from FFRampTest. Although maybe I
    should add it?
    """


    class FFInitProg(AveragerProgram):
        """
        Sets up the FF to the new point, waits some time to allow thermalisation, and keeps the fast flux at the new value
        It may be possible to put this in the initialise of the other experiment, but I'm not 100% sure of the timing
        of the execution of that, so let's just be explicit by having a separate program.
        """
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

            self.sync_all(self.us2cycles(self.cfg["init_time"]))  # Wait to allow flux to settle

    class FFSingleShot(NDAveragerProgram):
        """ This class is the single-shot program. Assumes we start at some FF point already; performs a single-shot
        measurement at 0 FF DAC (assuming that is the good readout point), performs reverse pulse to cancel flux
        accumulation. """
        def __init__(self, soccfg, cfg):
            super().__init__(soccfg, cfg)

        def initialize(self):
            # Declare channels
            self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
            self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux

            # Declare readout
            for ch in self.cfg["ro_chs"]:
                self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                     freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

            # Readout pulse
            # 'periodic' would not make sense for this experiment
            self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                     freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                        ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                     gain=self.cfg["read_pulse_gain"], #mode="oneshot",
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))

            # Define the fast flux ramp. For now, just linear ramp is supported
            if self.cfg["ff_ramp_style"] == "linear":
                PulseFunctions.create_ff_ramp(self, ramp_start = self.cfg["ff_gain"], ramp_stop = 0, pulse_name = 'ramp_down')
            else:
                print("Need an ff_ramp_style! only \"linear\" supported at the moment.")

            # Give tprocessor time to execute all initialisation instructions before we expect any pulses to happen
            self.sync_all(self.us2cycles(1))

        def body(self):
            """
            Ramps from ff_gain down to 0 DAC, measures.
            Jumps to 2*ff_gain as a 'reverse' pulse to cancel out flux drift due to reactive components in chain.
            Jumps back to ff_gain. Waits for a long time to thermalise.
            :return:
            """

            adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"]) # Do NOT include channel, it's wrong!

            # Ramp down from ff_gain to 0 DAC
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                     gain=self.soccfg['gens'][0]['maxv'], waveform="ramp_down", outsel="input")
            self.pulse(ch = self.cfg["ff_ch"], t = 0)
            self.syncall(self.us2cycles(0.05)) # Give enough time to align channels and make sure flux ramp is done

            # Measure. We do not need to wait for the cavity to relax, since we will be waiting to thermalise anyway
            self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=adc_trig_offset_cycles,
                         t = 0, wait = True, syncdelay=self.us2cycles(0.05))

            # 'Reverse' pulse
            self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0, gain=2 * self.cfg["ff_gain"],
                                     length=self.us2cycles(self.cfg['read_length'], gen_ch=self.cfg["ff_ch"]), stdysel = 'last')
            self.pulse(ch = self.cfg["ff_ch"])

            # Go back to ff_gain
            self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0, gain= self.cfg["ff_gain"],
                                     length=3, stdysel = 'last')
            self.pulse(ch = self.cfg["ff_ch"])

            # Thermalise
            self.syncall(self.cfg['therm_time'])



        # Override acquire such that we can collect the single-shot data
        def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
                    start_src="internal", progress=False, debug=False):

            super().acquire(soc, load_pulses=load_pulses, progress=progress)

            # Shape of get_raw: [# readout channels, # expts, # reps, # readouts, I/Q = 2]
            # If no sweeps, # expts dimension goes away (not just becomes 1)
            length = self.us2cycles(self.cfg['read_length'], ro_ch = self.cfg["ro_chs"][0])
            assert len(np.array(self.get_raw()).shape) == 4
            # The values are integrated, divide by length to get average value
            shots_i = np.array(self.get_raw())[0, :, :, 0].reshape((self.cfg["reps"], 2)) / length
            shots_q = np.array(self.get_raw())[0, :, :, 1].reshape((self.cfg["reps"], 2)) / length

            return shots_i, shots_q

        def estimate_runtime(self):
            return self.cfg['reps'] * (self.cfg['ff_ramp_length'] + self.cfg['read_length'] * 2 + self.cfg['therm_time'])

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='', cfg=None, config_file=None,
                 progress=None, short_directory_names = False):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, short_directory_names = short_directory_names)

        # ff points; these must be ints as they are DAC units
        self.ff_gains = np.rint(np.linspace(self.cfg["ff_gain_start"], self.cfg["ff_gain_stop"], num = self.cfg["ff_gain_steps"])).astype(int)

        # Declare arrays for storing data

        # Transmission
        self.trans_fpts = np.linspace(start = self.cfg['trans_start_freq'], stop = self.cfg['trans_stop_freq'],
                                      num = self.cfg['trans_num_freqs'])
        self.trans_avgi = np.zeros(self.cfg["ff_gain_steps"], self.cfg['trans_num_freqs'])
        self.trans_avgq = np.zeros(self.cfg["ff_gain_steps"], self.cfg['trans_num_freqs'])

        # Spectroscopy
        self.spec_fpts = np.linspace(start = self.cfg['spec_start_freq'], stop = self.cfg['spec_stop_freq'],
                                      num = self.cfg['qubit_freq_expts'])
        self.spec_avgi = np.zeros((self.cfg["ff_gain_steps"], self.cfg["qubit_freq_expts"]))
        self.spec_avgq = np.zeros((self.cfg["ff_gain_steps"], self.cfg["qubit_freq_expts"]))

        # Single-shot
        self.shots_i = np.zeros((self.cfg["ff_gain_steps"], self.cfg["shots"]))
        self.shots_q = np.zeros((self.cfg["ff_gain_steps"], self.cfg["shots"]))

        # Ramp number sweep. Last dimension is the two measurements: pre/post ramp
        self.ramp_test_cycle_pts = np.zeros((self.cfg["ff_gain_steps"], self.cfg["cycle_number_expts"]))
        self.ramp_test_i_arr = np.zeros((self.cfg["ff_gain_steps"], self.cfg["cycle_number_expts"],
                                        self.cfg["ramp_test_reps"], 2))
        self.ramp_test_q_arr = np.zeros((self.cfg["ff_gain_steps"], self.cfg["cycle_number_expts"],
                                         self.cfg["ramp_test_reps"], 2))

        # T1, tbd
        #TODO

        self.data = {}

        if (self.cfg["measure_at_0"] and self.cfg["reversed_pulse"] and
            (np.max([np.abs(self.cfg["ff_gain_stop"]), np.abs(self.cfg["ff_gain_start"])]) * 2 >
                    self.soc.get_maxv(self.cfg['ff_ch']))):
            raise ValueError('If playing reversed pulse and measuring at 0, ff_gain * 2 cannot exceed maximum value')


    def acquire(self, progress=False, debug=False):
        # Loop over different ff_gains
        for i, gain in enumerate(self.ff_gains):
            print('Gain:')
            print(gain)
            if i == 1:
                step = time()

            # Update ff_gain value in config; creates key on first iteration
            self.cfg["ff_gain"] = gain

            # 1) FFTransSlice
            trans_cfg = self.cfg | {'start_freq': self.cfg['trans_start_freq'], 'stop_freq': self.cfg['trans_stop_freq'],
                                   'num_freq': self.cfg['trans_num_freqs'], 'reps': self.cfg['trans_reps'],
                                   'ro_mode_periodic': self.cfg["trans_ro_mode_periodic"]}
            trans_expt = FFTransSlice_Experiment(path="FFTransVsFlux_Slice", cfg=trans_cfg, soc=self.soc, soccfg=self.soccfg,
                                                 outerFolder = self.outerFolder, short_directory_names = True)
            trans_dat = trans_expt.acquire(progress = True)

            self.trans_fpts[i, :] = trans_dat['data']['fpts']
            self.trans_avgi[i, :] = trans_dat['data']['avgi']
            self.trans_avgq[i, :] = trans_dat['data']['avgq']

            # 2) FFSpecSlice
            self.cfg = self.cfg | {'pre_ff_delay' : 0}  # No need for that in this usage
            spec_cfg = self.cfg | { 'ro_mode_periodic': self.cfg['spec_ro_mode_periodic'],
                                    'reverse_pulse': self.cfg["spec_reverse_pulse"],
                                    'relax_delay': self.cfg['spec_relax_delay'], 'reps': self.cfg['spec_reps']}
            spec_prog = FFSpecSlice(self.soccfg, self.cfg | spec_cfg)

            # Check that the arguments make sense. We need the program first, to know the correct qubit pulse length
            if self.cfg["qubit_spec_delay"] + spec_prog.qubit_pulse_length + self.cfg["read_length"] > self.cfg["ff_length"]:
                print("!!! WARNING: fast flux pulse turns off before readout is complete !!!")
            # print("Qubit pulse length: ", spec_prog.qubit_pulse_length)

            # Collect the data
            spec_x_pts, spec_avgi, spec_avgq = spec_prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=progress)


            self.spec_fpts[i, :] = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                           self.cfg["qubit_freq_expts"])
            self.spec_avgi[i, :] = spec_avgi
            self.spec_avgq[i, :] = spec_avgq

            # 3) FFInitProg
            init_prog = self.FFInitProg(self.soccfg, self.cfg)
            init_prog.run_rounds(self.soc)

            # 4) FFSingleShot
            single_shot_prog = self.FFSingleShot(self.soccfg, self.cfg)
            shots_i, shots_q = single_shot_prog.acquire(self.soc, progress = False)

            self.shots_i = shots_i
            self.shots_q = shots_q

            # 5) FFRampTest
            # We need to modify the config such that it goes from 0 to ff_gain
            ramp_test_cfg = {"sweep_type": 'cycle_number', "ff_ramp_gain": gain, "reps": self.cfg["ramp_test_reps"],
                             "reversed_pulse": True}
            ramp_test_prog = FFRampTest_Experiment(path="FFRampTest", cfg= self.cfg | ramp_test_cfg, soc=self.soc,
                                          soccfg=self.soccfg, outerFolder=self.outerFolder, short_directory_names=True)
            ramp_test_dat = ramp_test_prog.acquire(progress = progress)

            self.ramp_test_cycle_pts[i, :] = ramp_test_dat['data']['cycle_numbers']
            self.ramp_test_i_arr[i, :] = ramp_test_dat['data']['i_arr']
            self.ramp_test_q_arr[i, :] = ramp_test_dat['data']['q_arr']

            #TODO T1



        #####
        # Return fast flux to 0
        self.soc.reset_gens()

        self.data =  {
            'config': self.cfg,
            'data': {'ff_gains_vec': self.ff_gains,
                     'trans_fpts': self.trans_fpts, 'trans_Imat': self.trans_avgi, 'trans_Qmat': self.trans_avgq,
                     'spec_fpts': self.spec_fpts, 'spec_Imat': self.spec_avgi, 'spec_Qmat': self.spec_avgq,
                     'shots_i': self.shots_i, 'shots_q': self.shots_q,
                     'ramp_test_cycle_pts': self.ramp_test_cycle_pts,
                     'ramp_test_Imat': self.ramp_test_i_arr, 'ramp_test_Qmat': self.ramp_test_q_arr,
                     #TODO check dimensions of ramp test
                     #TODO T1
                     }
        }

        return self.data

    # Template config dictionary, used in GUI for initial values
    config_template = {
        # Readout section. The readout is the same for every experiment since it's at 0. spec may use periodic
        "read_pulse_style": "const",     # --Fixed
        "read_length": 5,                # [us]
        "read_pulse_gain": 8000,         # [DAC units]
        "read_pulse_freq": 7392.25,      # [MHz]

        # Fast flux pulse parameters. We use the same fast flux pulse in every experiment, except for const jumps
        "ff_ch": 6,                      # RFSOC output channel of fast flux drive
        "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive

        # ff_gain sweep parameters: DAC value of fast flux at which we take every measurement. Readout is at 0.
        "ff_gain_start": 0,              # [DAC] Initial value
        "ff_gain_stop": 2,               # [DAC] Final value
        "ff_gain_steps": 10,             # number of ff gain points to take

        ### FFTransSlice parameters
        "trans_start_freq": 5000,        # [MHz] Start frequency of sweep
        "trans_stop_freq": 6000,         # [MHz] Stop frequency of sweep
        "trans_num_freqs": 101,          # Number of frequency points to use
        "trans_ro_mode_periodic": False, # Bool: if True, keeps readout tone on always
        "init_time": 1,                  # [us] Thermalisation time after FF to new point before starting measurement
        "measure_at_0": True,            # [Bool] Do we go back to 0 DAC units on the FF to measure?
        "reversed_pulse": True,          # [Bool] Do we play a reversed pulse on the ff channel after measurement?
        "trans_reps": 500,               # Number of reps for the FFTransSlice experiment

        ### FFSpecSlice parameters
        # For this usage of spec slice, we want the flux pulse started before the qubit pulse begins.
        # pre-ff delay is probably 0, ff_length > qubit_spec_delay + pre_ff_delay
        "qubit_freq_start": 1001,              # [MHz]
        "qubit_freq_stop": 2000,               # [MHz]
        "qubit_freq_expts": 2000,              # number of points

        "ff_length": 50,                       # [us] Total length of positive fast flux pulse
        "ff_pulse_style": "const",             # one of ["const", "flat_top", "arb"], currently only "const" is supported
        "spec_reverse_pulse": True,            # [Bool] reverse fast flux pulse to cancel current in reactive components

        "qubit_mode_periodic": False,          # Bool: Applies only to "const" pulse style; if True, keeps qubit tone on always
        "qubit_spec_delay": 10,                # [us] Delay before qubit pulse

        # Same also used for FFRampTest
        "qubit_pulse_style": "flat_top",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.050,                   # [us], used with "arb" and "flat_top"
        "qubit_length": 1,                # [us], used with "const"
        "flat_top_length": 0.300,         # [us], used with "flat_top"
        "qubit_gain": 25000,              # [DAC units]

        "spec_ro_mode_periodic": False,        # Bool: if True, keeps readout tone on always
        "spec_relax_delay": 10,                # [us]
        'spec_reps': 2000,                     # Number of reps for FFSpecSlice experiment

        ### FFSingleShot parameters
        "therm_time": 10000,                   # [us] Time to thermalise at a flux point before measuring single shot
        "ff_ramp_style": 'linear',             # [str] one of ["linear"]
        "ff_ramp_length": 0.01,                # [us] Length of one direction of ff ramp

        ### FFRampTest parameters
        "ff_delay": 1,                                # [us] Delay between fast flux ramps (length of constant part)
        "ramp_test_qubit_pulse": False,               # [bool] Whether to apply the optional qubit pulse at the beginning
        "ramp_test_qubit_freq": 1000,                 # [MHz] Frequency of qubit pulse
        "ramp_test_qubit_pulse_style": "flat_top",    # one of ["const", "flat_top", "arb"]

        "relax_delay_1": 10,                          # [us] Relax delay after first readout
        "relax_delay_2": 10,                          # [us] Relax delay after second readout

        "qubit_pulse": False,                 # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 1000,                   # [MHz] Frequency of qubit pulse

        # Sweep settings
        "cycle_number_expts": 11,         # [int] How many values for number of cycles around to use in this experiment
        "max_cycle_number": 500,          # [int] What is the largest number of cycles to use in sweep? Start at 1
        "cycle_delay": 0.02,              # [us] How long to wait between cycles in one experiment?

        "ramp_test_reps": 1000,           # Number of reps for RampTest

        # Other parameters
        "yokoVoltage": 0,                # [V] Yoko voltage for DC component of fast flux
        "relax_delay": 10,               # [us]
        "reps": 1000,
        "sets": 5,
        "use_switch": False,
    }