# This experiment cools the qubit by performing a two-tone conversion from |e, 0> to |g, 1>, relying on the large cavity
# kappa to then quickly dissipate the photon. Four wave mixing allows this process if w_q + w_1 = w_r + w_2.
# Since we do not want to directly drive the qubit or cavity, we detune both drives by a static detuning Delta.
# The rate of the final process is proportional to Delta^(-2), so we don't want to make it too large.
# To optimise the exact frequencies of the drives, we also add a delta to one of them, which we can sweep.

from qick import *
from qick.averager_program import QickSweep
from qick import helpers
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib.initialize import *
import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime

class QubitTwoTwoResonatorCoolProgram(NDAveragerProgram):
    '''
    Drives a two-tone parametric process between the qubit and the readout cavity.
    The two drives are f_1 = f_r + Delta, f_2 + w_q01 + Delta + delta, applied for a time T before readout.
    The Delta is a detuning necessary to prevent us from driving the qubit/readout on resonance; the rate of the parametric
    process scales roughly with Delta^(-2). The delta accounts for Stark shifts of the frequencies (and in practice, any
    miscalibrations).

    Configuration parameters:
    cavity_drive_gain: DAC units, gain of the parametric cavity drive, NOT the readout
    qubit_drive_gain: DAC units, gain of the parametric qubit drive
    read_pulse_gain: DAC units, gain of the readout pulse
    read_pulse_freq: MHz, frequency of the readout pulse
    qubit_freq: MHz, frequency of the qubit 0-1 transition, does NOT include Delta or delta
    Delta: MHz, frequency detuning of both parametric drives
    delta_start: MHz, start of additional detuning, to compensate for Stark shifts, etc.; applied to qubit parametric drive
    delta_stop: MHz, stop o additional detuning
    T: us, length of the parametric drive
    read_length: us, length of the readout pulse
    delta_steps: integer, number of steps to take in delta
    reps: integer, number of repetitions of the experiment at each point
    '''

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Declare generators and readout channel(s)
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout drive
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit drive
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        # self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        # self.q_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        # self.f_start = self.freq2reg(self.cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        # self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # Readout frequency
        self.f_res = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # convert f_res to dac register value, necessary for tprocv1
        # Parametric drive on cavity frequency
        self.f_1 = self.freq2reg(cfg["read_pulse_freq"] + cfg["Delta"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # convert f_res to dac register value, necessary for tprocv1
        # Set the readout pulse registers for the parametric  drive, not measurement
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=self.f_1, phase=0,
                                 gain=cfg["cavity_drive_gain"],
                                 length=self.us2cycles(cfg["T"], gen_ch=cfg["res_ch"]))

        # Initial parametric drive on qubit frequency
        self.f_2_start = self.freq2reg(cfg["qubit_freq"] + cfg["Delta"] + cfg["delta_start"], gen_ch=cfg["qubit_ch"],
                              ro_ch=cfg["ro_chs"][0])
        # Set the qubit pulse registers for the parametric drive to the initial value, just constant for now
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_2_start, phase=0, gain=cfg["qubit_drive_gain"],
                                 length=self.us2cycles(self.cfg["T"], gen_ch=cfg["qubit_ch"]))
        # Get the register page for the qubit parametric drive frequency
        self.qubit_freq_reg = self.get_gen_reg(cfg["qubit_ch"], "freq")


        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.us2cycles(self.cfg["T"], gen_ch=cfg["qubit_ch"])

        # Set up the sweep
        # Below not necessary, let's just directly update the qubit frequency
        # # Declare a new register in the qubit_ch register page that keeps track of the current delta value
        # self.delta_reg = self.new_gen_reg(cfg["qubit_ch"], init_val=cfg["delta_start"], name="delta", reg_type="freq")
        # QickRegister's, as new_gen_reg returns, are supposed to be smart enough to tell MHz from register units
        # self.add_sweep(QickSweep(self, self.delta_reg, cfg["delta_start"], cfg["delta_stop"], cfg["delta_steps"]))

        self.add_sweep(QickSweep(self, self.qubit_freq_reg, cfg["qubit_freq"] + cfg["Delta"] + cfg["delta_start"],
                                 cfg["qubit_freq"] + cfg["Delta"] + cfg["delta_stop"], cfg["delta_steps"]))

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # Set the pulse registers for the parametric drive
        # Cavity drive
        self.set_pulse_registers(ch=self.cfg["res_ch"], style="const", freq=self.f_1, phase=0,
                                 gain=self.cfg["cavity_drive_gain"],
                                 length=self.us2cycles(self.cfg["T"], gen_ch=self.cfg["res_ch"]))
        # Qubit drive -- no need to set pulse registers I'm already sweeping the qubit frequency
        # f_2 = self.freq2reg(self.cfg["qubit_freq"] + self.cfg["Delta"] + self.delta_reg.reg2val(self.cfg["qubit_ch"]),
        #                     gen_ch=self.cfg["qubit_ch"], ro_ch=self.cfg["ro_chs"][0])
        # self.set_pulse_registers(ch=self.cfg["qubit_ch"], style="const", freq=f_2, phase=0,
        #                          gain=self.cfg["qubit_drive_gain"],
        #                          length=self.us2cycles(self.cfg["T"], gen_ch=self.cfg["qubit_ch"]))
        # self.res_r_gain.set_to(self.res_r_gain_update)
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Play the parametric drives
        self.pulse(ch=self.cfg["res_ch"])   # Play a cavity tone
        self.pulse(ch=self.cfg["qubit_ch"])  # Play a qubit tone
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # Reset cavity drive back to the readout frequency
        self.set_pulse_registers(ch=self.cfg["res_ch"], style="const", freq=self.f_res, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))
        self.sync_all(self.us2cycles(0.01))  # align channels and wait 10ns

        # trigger measurement, play measurement pulse, wait for system to equilibrate
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # No update function with NDAverager

class QubitTwoToneResonatorCoolExperiment(ExperimentClass):
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)
        self.data = None

    def acquire(self, progress: bool=False, debug: bool=False, plotDisp: bool=True, plotSave: bool = True, figNum: int = 1) -> None:

        # Timer
        startTime = datetime.datetime.now()
        print('') # empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))

        # Estimate runtime
        estimated_runtime = datetime.timedelta(seconds = 1e-6 * (self.cfg['delta_steps'] * self.cfg['reps'] *
                (self.cfg['T'] + self.cfg['read_length'] + self.cfg['relax_delay'])))
        print('estimated runtime: ' + str(estimated_runtime))
        print('estimated end time:' + (datetime.datetime.now() + estimated_runtime).strftime("%Y/%m/%d %H:%M:%S"))

        # Take the data
        prog = QubitTwoTwoResonatorCoolProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal",
                                         progress=False)  # qick update deprecated ? , debug=False)
        # The returned x_pts variable is garbage, generate correct replacement
        x_pts_correct = np.linspace(self.cfg['delta_start'], self.cfg['delta_stop'], num = self.cfg['delta_steps'])
        self.data = {'config': self.cfg, 'data': {'x_pts': x_pts_correct, 'avgi': avgi, 'avgq': avgq}}

        # Save the data before we have a chance to crash
        self.save_data()

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

    def display(self, data: dict = None, **kwargs) -> None:
        """
        Plot self.data, unless a data dictionary is provided, then plot that instead. Don't do anything with **kwargs
        """
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        avg_mag = np.abs(avgi + 1j * avgq)
        avg_phase = np.unwrap(np.angle(avgi + 1j * avgq))

        plt.figure(figsize=(16, 14))
        plt.subplot(4, 1, 1)
        plt.plot(x_pts, avgi)
        #plt.xlabel('delta (MHz)')
        plt.ylabel('I')

        plt.subplot(4, 1, 2)
        plt.plot(x_pts, avgq)
        #plt.xlabel('delta (MHz)')
        plt.ylabel('Q')

        plt.subplot(4, 1, 3)
        plt.plot(x_pts, avg_mag)
        #plt.xlabel('delta (MHz)')
        plt.ylabel('mag')

        plt.subplot(4, 1, 4)
        plt.plot(x_pts, avg_phase)
        plt.xlabel('delta (MHz)')
        plt.ylabel('phase (rad)')

    def save_data(self, data=None) -> None:
        """
        Saves the data currently in self.data. Does nothing for the data argumet.
        """
        # Save the data to an .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=self.data['data'])
