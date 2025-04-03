from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


class RBSequenceProgram(AveragerProgram):
    # def __init__(self, cfg):
    #     AveragerProgram.__init__(self, cfg)

    def initialize(self):
        cfg = self.cfg
        self.gate_seq = cfg['gate_seq']
        self.gate_set = cfg['gate_set']

        print(self.gate_set, self.gate_seq)

        # r_freq = self.sreg(cfg["rr_ch"], "freq")  # Get frequency register for res_ch
        # f_res = self.freq2reg(
        #     self.adcfreq(cfg["rr_freq"]))  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        #
        # #         rr_freq = self.sreg(self.device_cfg["rr_ch"], self.device_cfg["rr_freq"])   #Get frequency register for res_ch
        # self.cfg["adc_lengths"] = [self.cfg["rr_length"]] * 2  # add length of adc acquisition to config
        # self.cfg["adc_freqs"] = [self.adcfreq(self.cfg["rr_freq"])] * 2  # add frequency of adc ddc to config

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        self.f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        """Add a sequence of fixed number of gates, analytically compute
            the inverse operation after the final gate to bring the qubit back
            to |g> state (minimizes errors due to readout) before reading out the state.
            Repeat this experiment several times with the fixed number of gates.
        """
        #         self.add_pulse(ch=self.cfg["qubit_ch"], name="qubit", style="arb", idata=gauss(mu=cfg["pi_sigma"]*16*5/2,si=cfg["pi_sigma"]*16, length=5*cfg["pi_sigma"]*16, maxv=32000))

        """This adds the different types of pulses to the pulse library which can be played on demand later"""
        # for name, ginfo in self.gate_set.items():
        #     self.add_pulse(ch=self.cfg["qubit_ch"], name=name,
        #                    idata=ginfo["idata"],
        #                    qdata=ginfo["qdata"],
        #                    # style=ginfo["style"]
        #                    )

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.pulse_sigma_pi2 = self.us2cycles(cfg["sigma_pi2"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth_pi2 = self.us2cycles(cfg["sigma_pi2"] * 4, gen_ch = self.cfg["qubit_ch"])
        # print(self.pulse_sigma, self.pulse_sigma_pi2)
        # print(self.pulse_qubit_lenth, self.pulse_qubit_lenth_pi2)

        # self.add_gauss(ch=cfg["qubit_ch"], name="qubitpi", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubitpi2", sigma= self.pulse_sigma_pi2, length= self.pulse_qubit_lenth_pi2)

        # self.add_pulse(ch=self.cfg["rr_ch"], name="measure",
        #                style="const",
        #                length=self.cfg["rr_length"]
        #                )  # add a constant pulse to the pulse library of res_ch

        # self.pulse(ch=self.cfg["rr_ch"], name="measure", freq=f_res,
        #            phase=self.cfg["rr_phase"], gain=self.cfg["rr_gain"],
        #            length=self.cfg['rr_length'], t=0, play=False)

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))  # , mode='periodic')
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubitpi2", sigma=self.pulse_sigma_pi2,
                       length=self.pulse_qubit_lenth_pi2)
        self.add_gauss(ch=self.cfg["qubit_ch"], name="qubitpi", sigma=self.pulse_sigma,
                       length=self.pulse_qubit_lenth)
        self.sync_all(1000)  # give processor some time to configure pulses
    def body(self):
        self.phase_ref = 0
        for g in self.gate_seq:
            ginfo = self.cfg["gate_set"][g]
            """For the Z gates (virtual rotation), we need to advance the phase of all the pulses which follows afterwards"""
            if g == "Z":
                self.phase_ref += 180
            elif g == "Z/2":
                self.phase_ref += 90
            elif g == "-Z/2":
                self.phase_ref += -90
            elif g == "I" or g == "I/2":
                continue
            else:
                phase = self.deg2reg(ginfo["phase"] + self.phase_ref, gen_ch=self.cfg["qubit_ch"])
                if g[-1] == '2':
                    waveform = 'qubitpi2'
                else:
                    waveform = 'qubitpi'
                self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge, phase=phase,
                                     gain=ginfo["gain"], waveform=waveform)
                print(self.pulse_sigma, self.pulse_qubit_lenth, ginfo["gain"],self.f_ge )
                print('FLATTOP')
            self.sync_all(self.us2cycles(0.05))

                # self.pulse(ch=self.cfg["qubit_ch"], name=g, phase=self.deg2reg(self.phase_ref + ginfo["phase"]),
                #            gain=ginfo["gain"], play=True)
                # self.add_pulse(ch=self.cfg["qubit_ch"], name=str(ind),
                #                idata=ginfo["idata"],
                #                qdata=ginfo["qdata"],
                #                # style=ginfo["style"]
                #                )
                # self.pulse(ch=self.cfg["qubit_ch"], phase=self.deg2reg(self.phase_ref + ginfo["phase"]),
                #            gain=ginfo["gain"], play=True)

        self.sync_all(self.us2cycles(0.10))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))



        # ync_all(self.us2cycles(0.01))  # align channels and wait 10ns
        # # self.trigger_adc(adc1=1, adc2=1, adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        # # self.pulse(ch=self.cfg["rr_ch"], length=self.cfg["rr_length"], play=True)  # play readout pulse
        # # self.s
# class RB(RAveragerProgram):
#
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
#         for ch in self.cfg['ro_chs']:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=self.us2cycles(cfg["length"], ro_ch = self.cfg["res_ch"]),
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#
#         ### Start fast flux
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#
#         self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
#         self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
#
#
#         # add qubit and readout pulses to respective channels
#         if cfg['Gauss']:
#             self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
#             self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
#             self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
#             self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
#                                      phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
#                                      waveform="qubit")
#             self.qubit_length_us = cfg["sigma"] * 4
#         else:
#             if 'qb_periodic' in self.cfg.keys():
#                 if self.cfg['qb_periodic']:
#                     print("Qubit tone is periodic")
#                     self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
#                                              length=self.us2cycles(cfg["qubit_length"]), mode='periodic')
#                     self.qubit_length_us = cfg["qubit_length"]
#                 else:
#                     self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
#                                              gain=cfg["qubit_gain"],
#                                              length=self.us2cycles(cfg["qubit_length"]))
#                     self.qubit_length_us = cfg["qubit_length"]
#             else:
#                 self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
#                                          gain=cfg["qubit_gain"],
#                                          length=self.us2cycles(cfg["qubit_length"]))
#                 self.qubit_length_us = cfg["qubit_length"]
#
#         if 'ro_periodic' in self.cfg.keys():
#             if self.cfg['ro_periodic']:
#                 print("Readout periodic")
#                 self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=0,
#                                          gain=cfg["pulse_gain"],
#                                          length=self.us2cycles(cfg["length"], gen_ch=cfg["res_ch"]) , mode='periodic')
#             else:
#                 self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                          gain=cfg["pulse_gain"],
#                                          length=self.us2cycles(cfg["length"]))  # , mode='periodic')
#         else:
#             self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                      gain=cfg["pulse_gain"],
#                                      length=self.us2cycles(cfg["length"]))#, mode='periodic')
#         self.sync_all(self.us2cycles(1))
#
#     def body(self):
#         self.sync_all(self.us2cycles(0.05))
#         # self.pulse(ch=self.cfg["res_ch"])
#         # self.sync_all(self.us2cycles(0.01))
#         self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
#         # trigger measurement, play measurement pulse, wait for qubit to relax
#         self.sync_all(self.us2cycles(0.05))
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0],
#                      adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
#                      wait=True,
#                      syncdelay=self.us2cycles(self.cfg["relax_delay"]))
#
#
#
#     def update(self):
#         self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #




class SingleQRB(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):


        results = []
        start = time.time()
        for f in tqdm(self.cfg['all_gate_sequences'], position=0, disable=True):
            self.cfg["gate_seq"] = f
            print('gate_sec')
            prog = RBSequenceProgram(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':list(range(len(self.cfg['all_gate_sequences'])))}}
        self.data=data

        return data



    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        avgi = data['data']['results'][0][0][0]
        avgq = data['data']['results'][0][0][1]
        x_pts = data['data']['fpts']  #### put into units of frequency GHz
        sig = avgi + 1j * avgq

        avgamp0 = np.abs(sig)

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.close(figNum)
    # def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
    #     if data is None:
    #         data = self.data
    #     x_pts = data['data']['x_pts']
    #     avgi = data['data']['avgi'][0][0]
    #     avgq = data['data']['avgq'][0][0]
    #
    #     #### find the frequency corresponding to the qubit dip
    #     sig = avgi + 1j * avgq
    #     avgamp0 = np.abs(sig)
    #     avgphase = np.unwrap(np.angle(sig))
    #
    #     # Create figure and set up subplots (2x2 grid)
    #     plt.figure(figNum, figsize=(10, 8))
    #
    #     # Plot I (Real part)
    #     plt.subplot(2, 2, 1)  # 2x2 grid, 1st subplot
    #     plt.plot(x_pts, avgi, '.-', color='Orange', label="I")
    #     plt.xlabel("Qubit Frequency (GHz)")
    #     plt.ylabel("a.u.")
    #     plt.title("I Component")
    #     plt.legend()
    #     plt.grid(True)
    #
    #     # Plot Q (Imaginary part)
    #     plt.subplot(2, 2, 2)  # 2x2 grid, 2nd subplot
    #     plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")
    #     plt.xlabel("Qubit Frequency (GHz)")
    #     plt.ylabel("a.u.")
    #     plt.title("Q Component")
    #     plt.legend()
    #     plt.grid(True)
    #
    #     # Plot Amplitude
    #     plt.subplot(2, 2, 3)  # 2x2 grid, 3rd subplot
    #     plt.plot(x_pts, avgamp0, '.-', color='Green', label="Amplitude")
    #     plt.xlabel("Qubit Frequency (GHz)")
    #     plt.ylabel("Amplitude (a.u.)")
    #     plt.title("Amplitude")
    #     plt.legend()
    #     plt.grid(True)
    #
    #     # Plot Phase
    #     plt.subplot(2, 2, 4)  # 2x2 grid, 4th subplot
    #     plt.plot(x_pts, avgphase, '.-', color='Red', label="Phase")
    #     plt.xlabel("Qubit Frequency (GHz)")
    #     plt.ylabel("Phase (radians)")
    #     plt.title("Phase")
    #     plt.legend()
    #     plt.grid(True)
    #
    #     # Adjust layout to prevent overlap
    #     plt.tight_layout()
    #
    #
    #     plt.savefig(self.iname[:-4] + '_IQ.png')
    #     if plotDisp:
    #         plt.show(block=True)
    #         plt.pause(0.1)
    #     plt.close(figNum)
    #
    #     # plt.figure(figNum)
    #     # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
    #     # plt.ylabel("a.u.")
    #     # plt.xlabel("Qubit Frequency (GHz)")
    #     # plt.title(self.titlename)
    #     #
    #     # plt.savefig(self.iname[:-4] + '_Amplitude.png')
    #     #
    #     # if plotDisp:
    #     #     plt.show(block=True)
    #     #     plt.pause(0.1)
    #     # plt.close(figNum)
    #

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


"""Writing the sequences in terms of Clifford group algebra
    The Clifford gate set forms a closed group => 
    1. Multiplication of any two gates results in a gate part of the group 
    2. Each gate has an inverse
    3. The inverse of a product of multiple Clifford gates is unique
"""


def generate_rbsequence(depth):
    """Single qubit RB program to generate a sequence of 'd' gates followed
        by an inverse gate to bring the qubit back in 'g' state
    """

    gate_symbol = ['I', 'Z', 'X', 'Y', 'Z/2', 'X/2', 'Y/2', '-Z/2', '-X/2', '-Y/2']
    inverse_gate_symbol = ['I', '-Y/2', 'X/2', 'X', 'Y/2', '-X/2']

    """Modeled the bloch sphere as 6-node graph, each rotation in the RB sequence is effectively
    exchanging the node label on the bloch sphere.
    For example: Z rotation is doing this: (+Z->+Z, -Z->-Z, +X->+Y, +Y->-X, -X->-Y, -Y->+X)
    """
    matrix_ref = {}
    """Matrix columns are [Z, X, Y, -Z, -X, -Y]"""

    matrix_ref['0'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['1'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0]])
    matrix_ref['2'] = np.matrix([[0, 0, 0, 1, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 1, 0, 0, 0]])
    matrix_ref['3'] = np.matrix([[0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['4'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0]])
    matrix_ref['5'] = np.matrix([[0, 0, 1, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0]])
    matrix_ref['6'] = np.matrix([[0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])
    matrix_ref['7'] = np.matrix([[1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0]])
    matrix_ref['8'] = np.matrix([[0, 0, 0, 0, 0, 1],
                                 [0, 1, 0, 0, 0, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [0, 0, 0, 1, 0, 0]])
    matrix_ref['9'] = np.matrix([[0, 1, 0, 0, 0, 0],
                                 [0, 0, 0, 1, 0, 0],
                                 [0, 0, 1, 0, 0, 0],
                                 [0, 0, 0, 0, 1, 0],
                                 [1, 0, 0, 0, 0, 0],
                                 [0, 0, 0, 0, 0, 1]])

    """Generate a random gate sequence of a certain depth 'd'"""
    gate_seq = []
    for ii in range(depth):
        gate_seq.append(np.random.randint(0, 9))
    """Initial node"""
    a0 = np.matrix([[1], [0], [0], [0], [0], [0]])
    anow = a0
    for i in gate_seq:
        anow = np.dot(matrix_ref[str(i)], anow)
    anow1 = np.matrix.tolist(anow.T)[0]
    """Returns the """
    max_index = anow1.index(max(anow1))
    symbol_seq = [gate_symbol[i] for i in gate_seq]
    symbol_seq.append(inverse_gate_symbol[max_index])
    return symbol_seq