
"""
@author: Jocelyn Liu

This experiment does single shot with an intermediate populating pulse at the readout frequency.
Building block for MIST experiments
"""
import numpy as np
from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis.shot_analysis import SingleShotAnalysis
import scipy.optimize as opt


class SingleShotMISTExperiment(RAveragerProgram):
    """
    Class representing a single shot experiment
    """
    def __init__(self, soccfg, cfg):
        """
        Initialize the object
        """
        super().__init__(soccfg, cfg)

    def initialize(self):
        """
        Initialize the experiment on RFSOC
        """

        # Copy the self.cfg for the RFSOC
        cfg = self.cfg

        # There is only one experiments repeated by number of shots
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

        # Configure the Resonator Tone
        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                     gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(self.cfg["read_length"], gen_ch=res_ch))

        # Configure the readout
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                                 gen_ch=cfg["res_ch"])

        # Configure the qubit tone
        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch (used for flat top)
        self.qreg_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.qreg_freq = self.sreg(self.cfg["qubit_ch"], "freq")  # frequency register on qubit channel
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        cfg["qubit_ge_freq"]=0
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) #+ self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):

        #### wait 10ns
        self.sync_all(self.us2cycles(0.05))

        # First play populating pulse at the readout frequency
        read_freq = self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"], ro_ch=self.cfg["ro_chs"][0])
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=self.cfg["pop_pulse_gain"],
                                 length=self.us2cycles(self.cfg["pop_pulse_length"], gen_ch=self.cfg["res_ch"]))
        self.pulse(ch=self.cfg["res_ch"])  # play pulse
        self.sync_all(self.us2cycles(0.01))

        # Pause to empty the cavity
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["res_ch"]))
        self.sync_all(self.us2cycles(self.cfg["depop_delay"]))  # delay

        # Readout
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"], ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # Updates gain of the gaussian
        self.mathi(self.q_rp, self.r_gain2, self.r_gain2, '+', int(self.cfg["step"] / 2))  # update gain of the flat part

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0]/ self.us2cycles(
            self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])
        shots_q0 = self.dq_buf[0] / self.us2cycles(
            self.cfg['read_length'], ro_ch=self.cfg["ro_chs"][0])

        return shots_i0, shots_q0


# Measure cluster fidelity
class SingleShotMISTMeasure(ExperimentClass):
    """
    Measure the fidelity of identifying each shot correctly for a qubit with cen_num levels populated

    Methods
    -------
    acquire()
        Acquire the data from the experiment
    process()
        Process the data and calculate the fidelity of the clustering
    optimize()
        Takes in paramater dictionary over which it will calculate the bounds
    display()
        Creates and saves a plot. The plot can be displayed on the screen
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None, centers=None, fast_analysis=False, disp_image = True):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)
        self.fast_analysis = fast_analysis
        self.disp_image = disp_image
        self.params = []
        self.quants = []
        self.tolerance = []
        self.base_factor = {}
        self.keys = []
        self.index = 0
        self.total_size = 1
        self.mesh_grid = 0
        print("Initialized centers are \n", centers)
        self.centers = centers
    def acquire(self, progress=False, debug=False):
        # Perform the experiment
        # print("Acquiring data")
        prog = SingleShotMISTExperiment(self.soccfg, self.cfg)
        i_arr, q_arr = prog.acquire(self.soc, load_pulses=True)

        # Save the data
        data = {'config': self.cfg, 'data': {'i_arr' : i_arr, 'q_arr' : q_arr}}
        self.data = data
        return data

    def process(self, data=None, cen_num = None, debug=False ):
        # print("Processing data")
        # Get the data
        if data is None:
            data = self.data

        if cen_num is None:
            cen_num = self.cfg["cen_num"]

        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        self.analysis = SingleShotAnalysis(i_arr, q_arr, cen_num=cen_num, outerFolder=self.path_only,
                                           name = self.datetimestring, num_bins = 151, centers = self.centers, fast = self.fast_analysis,
                                           disp_image = self.disp_image)

        # Find the centers if they are not previously passed in
        if self.centers is None:
            print("Finding centers")
            self.centers = self.analysis.get_Centers(i_arr, q_arr)

        self.data["data"] = self.data["data"] | self.analysis.estimate_populations()



        # Calculating the distinctness of cluster
        self.distinctness = {}
        # keys = ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
        for key in self.cfg['keys']:
            self.distinctness[key] = self.analysis.calculate_distinctness(method = key)

        # Update data
        self.data["data"] = self.data["data"] | self.distinctness


        return self.data

    def calculate_distinctness(self, read_param):
        for i in range(len(self.keys)):
            self.cfg[self.keys[i]] = read_param[i]*self.base_factor[self.keys[i]]
        self.cfg["read_pulse_gain"] = int(self.cfg["read_pulse_gain"])
        self.index += 1

        # Get data and process
        data = self.acquire()
        data = self.process(data = data)

        # Get the distinctness
        val = 0
        for key in self.cfg['keys']:
            val += data['data'][key]

        val = -val

        # Store the data
        temp_param = []
        for i in range(len(self.keys)):
            temp_param.append([read_param[i]*self.base_factor[self.keys[i]]])
        self.params.append(temp_param)
        self.quants.append(val)
        print("New Params :", read_param , " Values :", self.quants[-1],
              " | Finished = ", self.index*100/self.total_size, " %")
        return val

    def callback(self, xk):
        if len(self.params) > 0:
            previous_x = self.params[-2]
            current_x  = self.params[-1]
            diffs = np.abs(np.array(current_x)-np.array(previous_x))
            if np.all(diffs < self.tolerance):
                raise StopIteration("TOLERANCE CRITERIA MET FOR ALL PARAMETERS")

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])