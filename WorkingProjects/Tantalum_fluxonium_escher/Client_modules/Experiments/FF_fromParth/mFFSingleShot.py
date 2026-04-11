from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFRampHoldTest import FFRampHoldTest
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.Shot_Analysis.shot_analysis import SingleShotAnalysis
import scipy.optimize as opt

'''
@author: Parth Jatakia
'''

class FFSingleShotSSE(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None, fast_analysis=False, disp_image = True):
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
        self.progress = progress

    def acquire(self):
        # pull the data from the single shots
        prog = FFRampHoldTest(self.soccfg, self.cfg)
        i_0,  shots_i, q_0, shots_q = prog.acquire(self.soc, load_pulses=True, progress=self.progress)
        data = {'config': self.cfg, 'data': {'i_arr': shots_i, 'q_arr': shots_q, "i_0": i_0, "q_0": q_0}}
        self.data = data
        return data

    def process(self, data=None, cen_num = None, centers = None):
        # print("Processing data")
        # Get the data
        if data is None:
            data = self.data

        if cen_num is None:
            cen_num = self.cfg["cen_num"]

        i_arr = data['data']['i_arr']
        q_arr = data['data']['q_arr']
        i_0 = data['data']['i_0']
        q_0 = data['data']['q_0']

        if cen_num == 2 :
            qubit_freq_mat = np.array([[0,self.cfg['qubit_ge_freq']],[self.cfg['qubit_ge_freq'],0]])
        else:
            qubit_freq_mat = None

        self.analysis = SingleShotAnalysis(i_arr, q_arr, cen_num=cen_num, outerFolder=self.path_only,
                                           name = self.datetimestring + "final", fast = self.fast_analysis,
                                           disp_image = self.disp_image, qubit_freq_mat= qubit_freq_mat, centers=centers, i_0_arr=i_0, q_0_arr=q_0)
        self.data["data"] = self.data["data"] | self.analysis.estimate_populations()

        # self.analysis_init = SingleShotAnalysis(i_0, q_0, cen_num=cen_num, outerFolder=self.path_only,
        #                                    name=self.datetimestring + "init", num_bins=151, fast=True,
        #                                    disp_image=self.disp_image, qubit_freq_mat=qubit_freq_mat)
        # self.analysis_init.estimate_populations()

        if 'keys' in self.cfg.keys():
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
            plt.xlabel(self.keys[0])
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
