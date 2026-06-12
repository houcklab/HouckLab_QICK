from qick import *
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import numpy as np
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.FF_fromParth.mFFRampHoldPopTest_wPulsePreDist import FFRampHoldPopTest
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.Shot_Analysis.shot_analysis import SingleShotAnalysis
import scipy.optimize as opt

'''
@author: Parth Jatakia
'''

class FFPopulateProbe(ExperimentClass):

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

    def acquire(self, plot_predist=False):
        # pull the data from the single shots
        prog = FFRampHoldPopTest(self.soccfg, self.cfg, save_loc=self.path_wDate + "_ff_predist.png", plot_debug=plot_predist)
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

        # self.analysis = SingleShotAnalysis(i_0, q_0, cen_num=cen_num, outerFolder=self.path_only,
        #                                    name=self.datetimestring + "inital", fast=True,
        #                                    disp_image=self.disp_image, qubit_freq_mat=qubit_freq_mat, centers=centers)
        # self.data["data"] = self.data["data"] | self.analysis.estimate_populations()

        self.analysis = SingleShotAnalysis(i_arr, q_arr, cen_num=cen_num, outerFolder=self.path_only,
                                           name=self.datetimestring + "final", fast=self.fast_analysis,
                                           disp_image=self.disp_image, qubit_freq_mat=qubit_freq_mat, centers=centers,
                                           i_0_arr = i_0, q_0_arr = q_0)

        self.data["data"] = self.data["data"] | self.analysis.estimate_populations()


        if 'keys' in self.cfg.keys():
            # Calculating the distinctness of cluster
            self.distinctness = {}
            # keys = ["mahalanobis", "bhattacharyya", "kl", "hellinger"]
            for key in self.cfg['keys']:
                self.distinctness[key] = self.analysis.calculate_distinctness(method = key)


            # Update data
            self.data["data"] = self.data["data"] | self.distinctness


        return self.data

    def process_v2(self, data=None, cen_num=None, centers=None, confidence=0.95, bin_size=101):
        """
        Post-selected version of process().

        Uses the pre-measurement shots (i_0, q_0) to cluster the qubit state via
        Gaussian fitting, then selects only the main-measurement shots (i_arr, q_arr)
        whose pre-measurement reading falls above a probability confidence threshold
        for each cluster. Populations are then estimated from those selected shots.

        Adapted from SpecSlice_PS_sse.process_data() in mSpecSlice_PS_sse.py.

        Parameters
        ----------
        data       : data dict (defaults to self.data)
        cen_num    : number of clusters / qubit states
        centers    : optional initial cluster centers
        confidence : minimum PDF value used as a post-selection threshold (default 0.8)
        bin_size   : number of histogram bins along each axis (default 101)

        Returns
        -------
        self.data  : updated with 'pop', 'centers', and per-state population arrays
        """
        from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2

        if data is None:
            data = self.data

        if cen_num is None:
            cen_num = self.cfg.get("cen_num", 2)

        i_0   = data['data']['i_0']    # pre-measurement shots, shape (n_shots,)
        q_0   = data['data']['q_0']
        i_arr = data['data']['i_arr']  # main measurement shots, shape (n_shots,)
        q_arr = data['data']['q_arr']

        # Stack into (2, n_shots) arrays expected by sse2 helpers
        iq_data_0 = np.stack((i_0, q_0), axis=0)    # pre-measurement
        iq_data_1 = np.stack((i_arr, q_arr), axis=0) # main measurement

        # ----- Fit Gaussians to the pre-measurement distribution -----
        if centers is None:
            centers = sse2.getCenters(iq_data_0, cen_num)
        print("Centers are ", centers)

        hist2d = sse2.createHistogram(iq_data_0, bin_size)
        no_of_params = 4
        gaussians_0, popt, x_points_0, y_points_0 = sse2.findGaussians(hist2d, centers, cen_num)

        # Build tight bounds around the fit so the second-pass fits stay anchored
        bound = [popt - 1e-5, popt + 1e-5]
        for idx_bound in range(cen_num):
            bound[0][0 + int(idx_bound * no_of_params)] = 0
            bound[1][0 + int(idx_bound * no_of_params)] = np.inf

        pdf_0 = sse2.calcPDF(gaussians_0)

        # ----- Calculate per-shot probability of belonging to each cluster -----
        n_shots = iq_data_0.shape[1]
        probability = np.zeros((cen_num, n_shots))
        for i in range(cen_num):
            for j in range(n_shots):
                indx_i = np.argmin(np.abs(x_points_0 - iq_data_0[0, j]))
                indx_q = np.argmin(np.abs(y_points_0 - iq_data_0[1, j]))
                probability[i, j] = pdf_0[i][indx_i, indx_q]

        # ----- Sort shots by descending probability for each cluster -----
        sorted_prob   = np.zeros((cen_num, n_shots))
        sorted_data_0 = np.zeros((cen_num,) + iq_data_0.shape)
        sorted_data_1 = np.zeros((cen_num,) + iq_data_1.shape)

        for i in range(cen_num):
            sorted_indx = np.argsort(-probability[i, :])
            sorted_prob[i, :]    = probability[i, sorted_indx]
            sorted_data_0[i, :, :] = iq_data_0[:, sorted_indx]
            sorted_data_1[i, :, :] = iq_data_1[:, sorted_indx]

        # ----- Post-select and estimate populations for each starting state -----
        # pop[i, j] = probability of ending in state j given pre-measurement said state i
        pop = np.zeros((cen_num, cen_num))
        std = np.zeros((cen_num, cen_num))

        for i in range(cen_num):
            indx_confidence = np.argmin(np.abs(sorted_prob[i, :] - confidence))
            selected_data_1 = sorted_data_1[i, :, 0:indx_confidence + 1]

            hist2d_1 = sse2.createHistogram(selected_data_1, bin_size)
            gaussians_1, popt_1, x_points_1, y_points_1 = sse2.findGaussians(
                hist2d_1, centers, cen_num, input_bounds=bound, p_guess=popt
            )

            pdf_1 = sse2.calcPDF(gaussians_1)
            num_samples_1 = sse2.calcNumSamplesInGaussian(hist2d_1, pdf_1, cen_num)
            prob_1, std_1 = sse2.calcProbability(num_samples_1, cen_num)
            pop[i, :] = prob_1
            std[i, :] = std_1

        #Plot the data and save the figure
        fig, axs = plt.subplots(1, 2, figsize=(12, 5))
        # Pre-measurement distribution
        sse2.plotFitAndData(pdf_0, gaussians_0, x_points_0, y_points_0, centers, iq_data_0, fig, axs[0], cen_num = 2)
        axs[0].set_title("Pre-measurement Distribution with Gaussian Fits")
        # Post-measurement distribution (using shots above confidence threshold for first cluster as example)
        sse2.plotFitAndData(pdf_1, gaussians_1, x_points_1, y_points_1, centers, selected_data_1, fig, axs[1], cen_num = 2)
        axs[1].set_title(f"Post-measurement Distribution (Confidence = {confidence})")
        plt.tight_layout()
        import os
        save_path = os.path.abspath(self.path_only + "\\data_dist.png")
        if not save_path.startswith("\\\\?\\"):
            save_path = "\\\\?\\" + save_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=200)
        plt.close(fig)


        # ----- Store results -----
        update = {
            "mean_pop":   pop,
            "std_pop":    std,
            "centers":   centers,
            "pdf_0":     pdf_0,
            "gaussians_0": gaussians_0,
            "x_points_0":  x_points_0,
            "y_points_0":  y_points_0,
        }
        self.data["data"] = self.data["data"] | update
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
