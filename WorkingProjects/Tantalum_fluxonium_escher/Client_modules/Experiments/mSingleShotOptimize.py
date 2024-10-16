"""
Created on 31st July 2024
@author: Parth Jatakia

This experiment optimizes the single shot cluster seperability (or Fidelity). Some changes are made to include low
frequency qubits like fluxonium where two levels are already populated and hence gates are not needed. This code can
incorporate at most two pulses g-e and e-f.

The pulses should try that at the beginning the qubit is inequal population of each state.
"""
import numpy as np
from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.Shot_Analysis.shot_analysis import SingleShotAnalysis
import scipy.optimize as opt


class SingleShotExperiment(RAveragerProgram):
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
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=res_ch), mode="periodic")

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
        qubit_ge_freq = self.freq2reg(cfg["qubit_ge_freq"], gen_ch=cfg["qubit_ch"])
        # Define qubit pulse: gaussian
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        # Define qubit pulse: flat top
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_ge_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_ge_gain"],
                                     waveform="qubit", length=self.us2cycles(self.cfg["flat_top_length"]))
        # Don't know what kind of pulse we want
        else:
            print("define gaussian or flat top pulse")

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        # Wait
        ge_freq = self.freq2reg(self.cfg["qubit_ge_freq"], gen_ch=self.cfg["qubit_ch"])
        ef_freq = self.freq2reg(self.cfg["qubit_ef_freq"], gen_ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Apply g-e pi pulse
        if self.cfg["apply_ge"]:
            if self.cfg["use_switch"]:
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                             width=self.cfg["trig_len"])  # trigger for switch
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ge_freq,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ge_gain"],
                                     waveform="qubit")
            self.pulse(ch=self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.005))

        # Apply e-f pi pulse
        if self.cfg["apply_ef"]:
            if self.cfg["use_switch"]:
                self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                             width=self.cfg["trig_len"])  # trigger for switch
            self.set_pulse_registers(ch=self.cfg["qubit_ch"], style=self.cfg["qubit_pulse_style"], freq=ef_freq,
                                     phase=self.deg2reg(0, gen_ch=self.cfg["qubit_ch"]), gain=self.cfg["qubit_ef_gain"],
                                     waveform="qubit")
            self.pulse(ch=self.cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.005))

        # Measure the qubit
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
class SingleShotMeasure(ExperimentClass):
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
                 progress=None, fast_analysis=False, max_iter = 50000, num_trials = 50000, pop_perc = 101):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)
        self.fast_analysis = fast_analysis
        self.params = []
        self.quants = []
        self.tolerance = []
        self.base_factor = {}
        self.keys = []
        self.index = 0
        self.total_size = 1
        self.mesh_grid = 0
        self.max_iter = max_iter
        self.num_trials = num_trials
        self.pop_perc = pop_perc

    def acquire(self, progress=False, debug=False):
        # Perform the experiment
        # print("Acquiring data")
        prog = SingleShotExperiment(self.soccfg, self.cfg)
        i_arr, q_arr = prog.acquire(self.soc, load_pulses=True)

        # Save the data
        data = {'config': self.cfg, 'data': {'i_arr' : i_arr, 'q_arr' : q_arr}}
        self.data = data
        return data

    def process(self, data=None, cen_num = None, debug=False, max_iter = 50000, num_trials = 50000, pop_perc = 101 ):
        # print("Processing data")
        # Get the data
        if data is None:
            data = self.data

        if cen_num is None:
            cen_num = self.cfg["cen_num"]

        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        print(self.path_only)
        self.analysis = SingleShotAnalysis(i_arr, q_arr, cen_num=cen_num, outerFolder=self.path_only,
                                           name = self.datetimestring, num_bins = 151, fast = self.fast_analysis)
        self.data["data"] = self.data["data"] | self.analysis.estimate_populations(max_iter = self.max_iter, num_trials = self.num_trials, pop_perc = self.pop_perc)

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
        self.new_file()
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


    def optimize(self, keys, param_bounds, init_params, tolerance, method = 'L-BFGS-B'):
        # Resetting
        self.index = 0
        self.total_size = 1

        # Keys
        self.keys = keys
        # keys = ["read_pulse_freq","read_length","read_pulse_gain"]

        # Create bounds amd x0
        bounds = []
        x0 = []
        for key in keys:
            # Check if it is a tuple
            if type(param_bounds[key]) is not tuple:
                raise Exception("Parameter bounds is not a dictionary of tuples")

            self.base_factor[key] = init_params[key]
            bounds.append(param_bounds[key])
            x0.append(init_params[key])
            self.tolerance.append(tolerance[key])

            # Scale all the values
            bounds[-1] = tuple(b_i/self.base_factor[key] for b_i in bounds[-1])
            x0[-1] = x0[-1]/self.base_factor[key]
            self.tolerance[-1] = self.tolerance[-1]/self.base_factor[key]


        # Define the options including tolerance
        options = {
            'disp': True,  # Display convergence messages
            'eps': np.array(self.tolerance)/2
        }

        # Pretty Print
        print("~~~~~~ Starting the Optimizer~~~~~~~")
        print("Base Factor : ", self.base_factor)
        print("Initial Guess : ", x0)
        print("Tolerance : ", self.tolerance)
        print("Bounds : ", bounds)
        print("Options : ", options)
        print("------------------------------------")

        # Run Scipy optimize
        try:
            result = opt.minimize(lambda x: self.calculate_distinctness(x), x0, method='L-BFGS-B',
                                  bounds=bounds,
                                  options = options, callback=self.callback)
        except StopIteration as e:
            print(e)

        print(">>>>>>>>>>>Optimization finished<<<<<<<<<<")
        print("Results : ", self.params[-1])

        # Run a normal single shot experiment and do a complete analysis
        self.cfg["read_pulse_freq"] = self.params[-1][0]
        self.cfg["read_length"] = self.params[-1][1]
        self.cfg["read_pulse_gain"] = self.params[-1][2]
        self.fast_analysis = False
        data = self.acquire()
        data = self.process(data=data)

        return result

    def smarter_brute_search(self, keys, param_bounds, step_size, tolerance_quant):
        """
        Smarter brute search
        The step size given by user can sometimes be coarse.
        This makes the search finer if that is the case
        Each finer search will have 20 points each
        """
        print("^^^^^^^ Beginning Smarter Search ^^^^^^^")
        # Create new dictionaries with keys
        param_bounds = {key: param_bounds[key] for key in keys}
        step_size = {key: step_size[key] for key in keys}

        # Creating new variables
        i_work = 0
        opt_param = None
        d_quant = np.inf
        pre_quant = np.inf
        while d_quant > tolerance_quant:
            # Keep doing brute search
            print("Iteration : ", i_work)
            if i_work < 1:
                print("Step size : ", step_size)
            else:
                # Update step size
                for i in range(len(keys)):
                    param_bounds[keys[i]] = (opt_param[0][i] - 5*step_size[keys[i]], opt_param[0][i] + 5*step_size[keys[i]])
                    step_size[keys[i]] = step_size[keys[i]]/2
                print("Step size : ", step_size)

            # Run brute search
            opt_param = self.brute_search(keys, param_bounds, step_size)

            if i_work == 0:
                pre_quant = opt_param[1]
            else :
                d_quant = np.abs(opt_param[1] - pre_quant)
                pre_quant = opt_param[1]

            print("Optimal Quantifier Value = ", opt_param[1])
            print("Optimal Parameter Value = ", opt_param[0])
            print("Delta Quantifer = ", d_quant)

            i_work += 1

        print("********* Optimization Over **********")
        return opt_param

    def brute_search(self, keys, param_bounds, tolerance):
        # Resetting
        self.params = []
        self.quants = []
        self.tolerance = []
        self.base_factor = {}
        self.index = 0
        self.total_size = 1

        # Set base factor to 1
        self.keys = keys

        # Create parameter grid
        param_grid = []
        for key in keys:
            # Check if it is a tuple
            if type(param_bounds[key]) is not tuple:
                raise Exception("Parameter bounds is not a dictionary of tuples")

            self.base_factor[key] = 1
            self.tolerance.append(tolerance[key])
            param_grid.append(np.arange(param_bounds[key][0], param_bounds[key][1] + tolerance[key], tolerance[key]))
            self.total_size *= len(param_grid[-1])

        # Generate all combinations of parameters
        self.mesh_grid = np.meshgrid(*param_grid)
        param_combinations = np.array(np.meshgrid(*param_grid)).T.reshape(-1, len(keys))

        # Pretty Print
        print("~~~~~~ Starting the Brute Force Optimizer~~~~~~~")
        print("Base Factor : ", self.base_factor)
        print("Ranges : ", param_bounds)
        print("------------------------------------")

        # Run brute force optimization
        best_params = None
        best_value = float('inf')
        for i, params in enumerate(param_combinations):
            value = self.calculate_distinctness(params)
            if value < best_value:
                best_value = value
                best_params = params

        return best_params, best_value

    def display_opt(self, data=None, plotDisp=False, figNum=1, save_fig=True, ran=None, **kwargs):
        if data is None:
            data = self.data

        if len(self.keys) == 1:
            param1_values = [param[0][0] for param in self.params]
            quants = self.quants
            # Create a 1D  plot
            plt.figure(figsize=(10, 8))
            scatter = plt.scatter(param1_values, quants)
            plt.xlabel('Resonator Pulse Frequency')
            plt.ylabel('KL Divergence')
            plt.title('Optimization')
            plt.tight_layout()
            plt.savefig(self.iname, dpi = 500)
            if plotDisp == True:
                plt.show()
        return

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
