###
# This file contains an NDAveragerProgram and ExperimentClass
# for ramping and then holding for some time and then ramping back down
# Parth, Sept 2025: create file.
###

import sys
from tqdm import tqdm
import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import PulseFunctions
import time

class mFFnTransmission(NDAveragerProgram):
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

        # Check if neg_offset is not too big
        if "neg_offset" in self.cfg.keys():
            if self.cfg["ff_hold"] + self.cfg["neg_offset"] < 0 :
                raise ValueError("Ramp hold negative. Increase the negative offset")
            else:
                print(f"Ramp Hold for {self.cfg['ff_hold'] + (self.cfg['neg_offset'])} us")
        else:
            self.cfg["neg_offset"] = 0



        self.adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])  # Do NOT include channel, it's wrong!
        # Give tprocessor time to execute all initialisation instructions before we expect any pulses to happen
        self.sync_all(self.us2cycles(1))

    def body(self):

        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel = 'last',
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"], t = 'auto')

        self.sync_all(self.us2cycles(self.cfg["ff_hold"]))

        # play reversed fast flux ramp, return to original spot
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"], t ='auto')

        if self.cfg['negative_pulse'] :
            self.sync_all(self.us2cycles(1))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')
            self.sync_all(self.us2cycles((self.cfg["ff_hold"]/2) - self.cfg['neg_offset']))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')

        # Sync to make sure ramping is done before starting second measurement.
        self.sync_all(self.us2cycles(self.cfg['pre_meas_delay']))

        # trigger measurement, play measurement pulse, wait for relax_delay_2. Once per experiment.
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=self.adc_trig_offset_cycles,
                     wait = True,
                     syncdelay=self.us2cycles(0))

        if self.cfg['negative_pulse'] :
            self.sync_all(self.us2cycles(1))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')
            self.sync_all(self.us2cycles((self.cfg["ff_hold"]/2) + self.cfg['neg_offset']))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')

        self.sync_all(self.us2cycles(self.cfg["relax_delay_2"]))

    # Override acquire such that we can collect the single-shot data


class FFHoldTransmission(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        if 'pre_meas_delay' not in self.cfg.keys():
            self.cfg['pre_meas_delay'] = 1
        else:
            print(f"Pre Meas Delay = {self.cfg['pre_meas_delay']}")

        if 'negative_pulse' in self.cfg.keys():
            if self.cfg['negative_pulse']:
                print(f"Playing negative pulses for integration to be zero")
            else:
                print("Not playing negative pulses")
        else:
            self.cfg['negative_pulse'] = False
            print("Not playing negative pulses")


        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"]-1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts):
            self.cfg["read_pulse_freq"] = f
            prog = mFFnTransmission(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True,progress=False))
            # time.sleep(0.01) # Added to wait for the RFSOC to send all data
        if debug:
            print(f'Time: {time.time() - start}')
        # results = np.transpose(results)
        #
        # prog = LoopbackProgram(self.soccfg, self.cfg)
        # self.soc.reset_gens()  # clear any DC or periodic values on generators
        # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)


        #### find the frequency corresponding to the peak
        avgi = np.array([elem[1] for elem in results])[:,0,0]
        avgq = np.array([elem[2] for elem in results])[:,0,0]
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq = fpts[peak_loc]

        data={'config': self.cfg, 'data': {'fpts':fpts, 'peak_freq':self.peakFreq,
                                           'amp0':avgamp0, 'avgi': avgi, 'avgq': avgq}}
        self.data=data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        avgamp0 = data['data']['amp0']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        plt.plot(x_pts, avgi,label="I")
        plt.plot(x_pts, avgq,label="Q")
        plt.plot(x_pts, avgamp0, label="Magnitude")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.legend()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show()

        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        # print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



