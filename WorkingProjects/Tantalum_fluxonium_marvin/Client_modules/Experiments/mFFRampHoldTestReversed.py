###
# This file contains an NDAveragerProgram and ExperimentClass
# for ramping and then holding for some time and then ramping back down
# Parth, Sept 2025: create file.
###

import sys

import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions


class FFRampHoldTestReversed(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux
        if self.cfg["qubit_pulse"]:  # Optional qubit pulse
            self.declare_gen(ch=self.cfg["qubit_ch"], nqz=self.cfg["qubit_nqz"])
            PulseFunctions.create_qubit_pulse(self, self.cfg["qubit_freq"])

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))

        # Define the fast flux ramp. For now, just linear ramp is supported
        if self.cfg["ff_ramp_style"] == "linear":
            PulseFunctions.create_ff_ramp(self, reversed = False)
            PulseFunctions.create_ff_ramp(self, reversed = True)
        else:
            print("Need an ff_ramp_style! only \"linear\" supported at the moment.")

        self.adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])  # Do NOT include channel, it's wrong!

        self.pulse_gap = self.cfg.get('pulse_gap', 0.5)
        self.pulse_gap_cycles = self.us2cycles(self.pulse_gap)

        self.sync_all(self.us2cycles(1))

    def body(self):

        # Play the first ff pulse and prepare the qubit and measure it underneath the ff pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                 gain=self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch=self.cfg["ff_ch"], t='auto')
        self.sync_all(self.pulse_gap_cycles)
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.pulse_gap_cycles)
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=self.adc_trig_offset_cycles,
                     wait=True, syncdelay=self.us2cycles(0))
        self.sync_all(self.pulse_gap_cycles)
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                 gain=self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch=self.cfg["ff_ch"], t='auto')

        # Now wait for relaxation
        self.sync_all(self.us2cycles(self.cfg["ff_hold"]))

        # Play the second ff pulse and measure it underneath the ff pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                 gain=self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch=self.cfg["ff_ch"], t='auto')
        self.sync_all(self.pulse_gap_cycles)
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=self.adc_trig_offset_cycles,
                     wait=True, syncdelay=self.us2cycles(0))
        self.sync_all(self.pulse_gap_cycles)
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                 gain=self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch=self.cfg["ff_ch"], t='auto')

    # Override acquire such that we can collect the single-shot data
    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=None, save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress) # qick update, debug=debug)

        length = self.us2cycles(self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        data = self.get_raw()
        shots_i0 = np.array(data)[0, :, 0, 0]/ length
        shots_q0 = np.array(data)[0, :, 0, 1]/ length
        shots_i1 = np.array(data)[0, :, 1, 0]/ length
        shots_q1 = np.array(data)[0, :, 1, 1]/ length
        i_0 = shots_i0
        i_1 = shots_i1
        q_0 = shots_q0
        q_1 = shots_q1

        return i_0, i_1, q_0, q_1



if __name__ == '__main__':
    from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
    print("Running the Ramp - Hold - DeRamp Test")
    soc, soccfg = makeProxy()
    soc.reset_gens()

    SwitchConfig = {
        "trig_buffer_start": 0.05,  # 0.035, # in us
        "trig_buffer_end": 0.04,  # 0.024, # in us
        "trig_delay": 0.07,  # in us
    }

    BaseConfig = BaseConfig | SwitchConfig

    outerFolder = r"Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

    UpdateConfig = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 20,  # [us]
        "read_pulse_gain": 30000, #5600,  # [DAC units]
        "read_pulse_freq": 6671.71,  # [MHz]

        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": -32000, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_hold": 50, # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
        "ff_ramp_length": 2,  # [us] Half-length of ramp to use when sweeping gain

        # Optional qubit pulse before measurement, intende0 as pi/2 to populate both blobs
        "qubit_pulse": True,  # [bool] Whether to apply the optional qubit pulse at the beginning
        "qubit_freq": 512,  # [MHz] Frequency of qubit pulse
        "qubit_pulse_style": "const",  # one of ["const", "flat_top", "arb"]
        "sigma": 0.50,  # [us], used with "arb" and "flat_top"
        "qubit_length": 0.5,  # [us], used with "const"
        "flat_top_length": 1,  # [us], used with "flat_top"
        "qubit_gain": 1000,  # [DAC units]

        # Ramp sweep parameters
        "yokoVoltage": -0.115,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 0.1, # - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10 - BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout

        # General parameters
        "reps": 100,
    }

    config = BaseConfig | UpdateConfig

    prog = FFRampHoldTest(soccfg, config)

    try :
        a,b,c,d = prog.acquire(soc, threshold=None, angle=None, load_pulses=True, save_experiments=None, start_src="internal", progress=True)
    except Exception:
        print("Pyro traceback:")
        print("".join(Pyro4.util.getPyroTraceback()))

    print(a.shape)