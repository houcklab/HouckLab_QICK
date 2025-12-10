'''
Single Shot Analysis
1. Calculate the population of each state
2. Calculate the error in the population using the confidence intervals, assuming Poisson statistics
3. Creates plots of the fit and residuals
4. Calculates temperature matrix and the error in the temperature matrix

Created by: Parth Jatakia
Date: 07/22/2024
'''

import numpy as np
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture as GMM
from lmfit import Model
import os
import logging
from tqdm import tqdm
import sklearn.metrics as metrics
from lmfit import Model, Parameters, Minimizer, report_fit, conf_interval
from lmfit.model import save_modelresult
from lmfit.models import Gaussian2dModel
import matplotlib.pyplot as plt
plt.rc('font', family='sans-serif')
plt.rc('text', usetex=False)
from matplotlib.colors import LogNorm

# Import custom modules
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import constants
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import utils
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import distinctness as dt



class SingleShotAnalysis:


    def __init__(self, i_arr, q_arr, cen_num = 2, cluster_method = 'gmm', fast = False, disp_image = True, i_0_arr = None, q_0_arr = None,
                centers = None, outerFolder = None, name = None, num_bins = None, qubit_freq_mat = None):

        """
        Initialize the class. 

        Attributes
        ----------
        i_arr : ndarray
            The I values of the single shot data
        q_arr : ndarray
            The Q values of the single shot data
        cen_num : int
            The number of centers to cluster the data
        cluster_method : str
            The method to cluster the data. Options are 'gmm' and 'kmeans'
        fast: bool
            If to skip all error calculation which takes most of the time
        disp_image: bool
            If to display the image, only used if fast is True
        i_0_arr : ndarray
            The I values of training data to initialize the centers
        q_0_arr : ndarray
            The Q values of training data to initialize the centers
        centers : ndarray
            The centers to use for clustering the data
        outerFolder : str
            The outer folder to save the data
        num_bins : int
            The number of bins to use for the histogram
        logger : logging.Logger
            The logger to log the data
        path : str
            The path to save the data
        name :  str
            The suffix to the name of the folder under which to save all data
        initialized : bool
            Whether the initialized state is provided or not
        qubit_freq_mat : 2d array or None
            The array of transition frequencies between each states

        Methods
        -------
        estimate_populations()
            Estimate the populations of the centers
        get_Centers()
            Get the centers from data
        fit_gaussians()
            Fit gaussians to the data
        create_model()
            Create the lmfit multi gaussian model
        calculate_populations()
            Calculate the populations of the centers

        """

        # Set the attributes
        self.i_arr = i_arr
        self.q_arr = q_arr
        self.cen_num = cen_num
        self.cluster_method = cluster_method
        self.i_0_arr = i_0_arr
        self.q_0_arr = q_0_arr
        self.centers = centers
        self.outerFolder = outerFolder
        self.num_bins = num_bins
        self.fast = fast
        self.disp_image = disp_image
        self.qubit_freq_mat = qubit_freq_mat


        # Set the path
        if self.outerFolder is not None:
            self.path = os.path.join(outerFolder, 'SingleShotAnalysis_' + name)
        else:
            self.path = os.path.join(os.getcwd(), 'SingleShotAnalysis')

        # Create the folder
        os.makedirs(self.path, exist_ok = True)

        # Configure the logging
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[
                                logging.FileHandler(os.path.join(self.path, 'singleshotanalysis.log'), mode='w'),
                            ])
        self.logger = logging.getLogger(__name__)
        self.logger.info('SingleShotAnalysis class initialized')

        # Check if the initialized state is provided
        if self.i_0_arr is not None and self.q_0_arr is not None:
            self.initialized = True
            self.logger.info('Initialized state provided')
        else:
            self.initialized = False
            self.logger.info('Initialized state not provided')
        
        
    # Estimate populations from the data
    def estimate_populations(self,i_arr=[], q_arr=[]):
        """
        Estimate the populations from the data

        Returns
        -------
        population_dict : dict
            A dictionary containing the populations of the centers
        """
        if self.initialized == True:
            # Step 1 : Get the centers from the initial data
            if self.centers is not None:
                print("Centers passed in:\n", self.centers)
                self.get_Centers(self.i_0_arr, self.q_0_arr)
                self.logger.info('Centers found')
                self.logger.info(self.centers)
            else:
                # print("Centers is none")
                self.get_Centers(self.i_0_arr, self.q_0_arr)
                self.logger.info('Centers found')
                self.logger.info(self.centers)

            # Step 2 : Fit gaussians to the initial data to get fit parameters
            self.inital_fit_results = self.fit_gaussians(self.i_0_arr, self.q_0_arr, self.centers)

            # Print the results
            self.logger.info('Initial fitting completed')
            self.logger.info(self.inital_fit_results['result'].fit_report())

            if self.fast is False or self.disp_image:
                self.book_keeping(self.inital_fit_results, 'Initial')

            initial_params = self.inital_fit_results['result'].params

        else:
            initial_params = None
            if self.centers is not None:
                print("Centers passed in:\n", self.centers)
            else:
                # print("centers is none")
                self.get_Centers(self.i_arr, self.q_arr)

        # Step 3 : Fit gaussians to the final data to get fit parameters

        # if no IQ arrays are passed, it will use the arrays that belong to the object at instantiation
        if not ( np.any(i_arr) or np.any(q_arr) ):
           self.final_results = self.fit_gaussians(self.i_arr, self.q_arr, self.centers, initial_params = initial_params)

        #use (truncated) arrays that are passed in as keyword arguments (see post_selection_SSA)
        else:
            self.final_results = self.fit_gaussians(i_arr, q_arr, self.centers, initial_params=initial_params)

        # Log the results
        self.logger.info('Fitting completed')
        self.logger.info((self.final_results['result'].fit_report()))

        # Bookkeeping

        if self.fast is False or self.disp_image:
            self.book_keeping(self.final_results, 'Final')

        # Step 4 : Estimate the populations
        self.population_dict = self.calculate_populations(self.final_results)

        return self.population_dict

    # Get the centers
    def get_Centers(self, i_arr, q_arr):
        """
        Get the centers from data

        Parameters
        ----------
        i_arr : ndarray
            The I values of the data
        q_arr : ndarray
            The Q values of the data

        Returns
        -------
        centers : ndarray
            The centers of the data
        """

        if self.cluster_method == 'gmm':
            self.centers = utils.get_GMM_centers(i_arr, q_arr, self.cen_num, self.centers)
        elif self.cluster_method == 'kmeans':
            self.centers = utils.get_kmeans_centers(i_arr, q_arr, self.cen_num, self.centers)
        else:
            self.logger.error('Invalid cluster method')
            raise ValueError('Invalid cluster method')

        # print("Returning \n",self.centers)
        return self.centers
        

    # Fit gaussians to the data
    def fit_gaussians(self, i_arr, q_arr, centers, initial_params = None):
        """
        Fit gaussians to the data
        """
        # Stack the data
        iq_data = np.vstack((i_arr, q_arr))

        # Create a histogram of the data
        hist2d = self.createHistogram(iq_data, bin_size = self.num_bins)

        # find the grid points
        x_points = (hist2d[1][1:] + hist2d[1][:-1])/2
        y_points = (hist2d[2][1:] + hist2d[2][:-1])/2
        Y, X = np.meshgrid(y_points, x_points)

        # Create the parameters
        self._create_model()
        params = self.full_model.make_params()

        # Define all the gaussians to have the same sigma
        params.add('sigma',value = (x_points[-1] - x_points[0])/32, min = 0, max = np.inf)
        for i in range(self.cen_num):
            prefix = 'g' + str(i) + '_'
            params.add(prefix + 'sigmax', expr = 'sigma')
            params.add(prefix + 'sigmay', expr = 'sigma')

        #TODO : Add in calculations for finding centers in the case there is no initialization data

        # Add in the guess for the centers 
        # Add the bounds for the centers
        # Add the bounds for the amplitudes
        cen_buff = 0.5
        for idx in range(self.cen_num):
            prefix = 'g' + str(idx) + '_'
            params[prefix + 'centerx'].set(
                value = self.centers[idx, 0],
                min = self.centers[idx, 0] - cen_buff,
                max = self.centers[idx, 0] + cen_buff,
                vary = True
                )
            params[prefix + 'centery'].set(
                value = self.centers[idx, 0],
                min = self.centers[idx, 1] - cen_buff,
                max = self.centers[idx, 1] + cen_buff,
                vary = True)
            params[prefix+'amplitude'].set(
                value = i_arr.size/self.cen_num,
                min = 0.0,
                max = np.inf,
                vary = True,
                )
            
        # If initial parameters are provided, use them to fix the sigma and center
        if initial_params is not None:
            params['sigma'].set(
                value = initial_params['sigma'].value,
                vary = False
                )
            for i in range(self.cen_num):
                prefix = 'g' + str(i) + '_'
                params[prefix + 'sigmax'].set(
                    value = initial_params[prefix + 'sigmax'].value,
                    vary = False
                    )
                params[prefix + 'sigmay'].set(
                    value = initial_params[prefix + 'sigmay'].value,
                    vary = False
                    )
                params[prefix + 'centerx'].set(
                    value = initial_params[prefix + 'centerx'].value,
                    vary = False
                    )
                params[prefix + 'centery'].set(
                    value = initial_params[prefix + 'centery'].value,
                    vary = False
                    )
                
        
        # Using Poisson statistics define the weights
        weights = 1 / np.sqrt(hist2d[0] + 1)

        # fit the data
        result = self.full_model.fit(
            hist2d[0], 
            params, 
            x = X, 
            y = Y,
            weights = weights, 
            method = 'least_squares',
            )
        
        # Create a dictionary of the components of the fit
        fit_results = {
            'result': result,
            'X': X,
            'Y': Y,
            'hist2d': hist2d[0],
            'centers': centers,
        }
        return fit_results

    # Define the model
    def _create_model(self):
        """
        Create the model
        """
        # Define the submodels
        models = []
        for i in range(self.cen_num):
            prefix = 'g' + str(i) + '_'
            model = Gaussian2dModel(prefix=prefix)
            models.append(model)
        
        # Define the full model
        full_model = models[0]
        for i in range(1, self.cen_num):
            full_model += models[i]
        
        # Set the nan policy
        full_model.nan_policy = 'omit'

        # Set the model
        self.full_model = full_model


    # Book keeping
    def book_keeping(self, fit_result, name):
        """
        Book keeping
        """
        # Save the model result
        save_modelresult(fit_result["result"], os.path.join(self.path, name + '_result.sav'))

        # save the fit statisitics
        heading = name + 'fit'
        file_name = 'fit_stats'
        self.saveOutput(
            heading, fit_result["result"].fit_report(), file_name, append = True)
        
        # save the residual plot
        self.plot_Fit(fit_result["result"], fit_result["X"], fit_result["Y"],  fit_result["hist2d"], plot_disp = False,
                      plot_save = True, plot_title = name + ' Fit')

        heading = 'confidence intervals'
        self.logger.info('Calculating confidence intervals for book keeping')
        try :
            conf_int_report = fit_result["result"].ci_report(
                ndigits = 3,
                maxiter = 10000,
                verbose = False,
                )
            self.logger.info('Confidence intervals')
            self.logger.info(conf_int_report)
            self.saveOutput(heading, conf_int_report, file_name, append=True)
        except:
            self.logger.info("Failed to calculate confidence intervals for book keeping")


        
        
    # function to save output text
    def saveOutput(self, heading, output, file_name, append = False ):
        # check if writing a new file or appending an existing
        if file_name[-4:] != '.txt':
            file_name += '.txt'
        file_name = self.path + '/' + file_name

        if append: 
            with open(file_name, "a") as text_file:
                text_file.write('\n \n')
                text_file.write(heading + '\n')
                text_file.write('')
                text_file.write(output)
        else:
            with open(file_name, "w") as text_file:
                text_file.write(heading + '\n')
            with open(file_name, "a") as text_file:
                text_file.write(output)

    # function to plot the fit
    def plot_Fit(self, result, X, Y, Z, plot_disp = False, plot_save = True, plot_title = 'Fit Comparison'):
        """
        Plot the fit and residuals of the data and the fit

        Parameters
        ----------
        result : lmfit.model.ModelResult
            The result of the fit
        X : ndarray
            The X values of the data
        Y : ndarray
            The Y values of the data
        Z : ndarray
            The Z values of the data
        plot_disp : bool
            Whether to display the plot
        plot_save : bool
            Whether to save the plot
        plot_title : str
            The title of the plot
        """

        # Evaluate the fit
        fit = result.eval(
            x = X, 
            y = Y,
            )
        
        # Convert all elements in fit to integer
        int_fit = np.rint(fit)

        # Create the plot
        fig, axs = plt.subplots(2, 2, figsize=(7, 5))
        
        # Define colorscheme
        cmap = plt.get_cmap('nipy_spectral')
        
        # plot the data
        ax = axs[0, 0]
        art = ax.pcolor(X, Y, Z, norm=LogNorm(), shading='auto', cmap = cmap)
        ax.set_aspect('equal')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Data')
        
        # find the ranges of the initial plot
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        
        # plot the fit 
        ax = axs[0, 1]
        art = ax.pcolor(X, Y, int_fit , norm=LogNorm(), shading='auto', cmap = cmap)
        ax.set_aspect('equal')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Fit')
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        # plot the residual
        ax = axs[1, 1]
        art = ax.pcolor(X, Y, Z-int_fit, shading='auto',norm=LogNorm(), cmap = cmap)
        ax.set_aspect('equal')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Residuals')
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        for ax in axs.ravel():
            ax.set_xlabel('I (arb. units)')
            ax.set_ylabel('Q (arb. units)')
            ax.set_aspect('equal')
        
        plt.suptitle(plot_title)
        plt.tight_layout()

        if plot_save:
            # Save it in a vector format
            plot_save_loc_pdf = self.path + '/' + plot_title + '.pdf'
            plt.savefig(plot_save_loc_pdf)

            # Save it in a raster format
            plot_save_loc_png = self.path + '/' + plot_title + '.png'
            plt.savefig(plot_save_loc_png, dpi = 500)

        if plot_disp:
            plt.show()

        plt.close()

    # Calculate the populations
    def calculate_populations(self, fit_results, max_iter = 1000, num_trials = 50000):
        """
        Calculate the populations
        """
        if self.fast is False :
            # Get the keys for the amplitudes
            keys = ['g' + str(idx) + '_amplitude' for idx in range(self.cen_num)]

            # define and array of the percentages to calculate
            percentages = np.linspace(0.01, 0.99, 101)

            # Get the confidence intervals
            self.logger.info('Calculating confidence intervals for calculating populations')
            conf_inter = fit_results["result"].conf_interval(maxiter = max_iter, sigmas = percentages)

            # store the confidence intervales in list
            values = [np.transpose(conf_inter[key])[1] for key in keys]
            for val in values:
                val[val == -np.inf] = 0

            # calculate the populations
            self.logger.info('Calculating populations')
            estimates = []
            temperatures = []
            for idx_trial in tqdm(range(num_trials)):
                amps = []
                # find random indexes to try
                for idx in range(self.cen_num):
                    rand_index = np.random.randint(0, len(values[idx]) - 1)

                    # pick number in range near index
                    try:
                        amp_val = np.random.uniform(
                            values[idx][rand_index], (values[idx][rand_index + 1])
                        )
                    except:
                        amp_val = np.nan

                    amps.append(amp_val)

                # append the estimates with the current population
                estimates.append(self.Pop_calc(amps))

                # Calculate the temperature
                if self.qubit_freq_mat is not None:
                    temperatures.append(utils.calc_tempr_mat(estimates[-1],self.qubit_freq_mat))

            # transpose for ease of use
            temperatures = np.array(temperatures)
            mean_temperature = np.mean(temperatures, axis = 0)
            std_temperatures = np.std(temperatures, axis = 0)
            estimates = np.transpose(estimates)
            mean_estimate = np.mean(estimates, axis=1)
            std_estimate = np.std(estimates, axis=1)

            # Get the centers of the gaussians
            keys_x = ['g' + str(idx) + '_centerx' for idx in range(self.cen_num)]
            keys_y = ['g' + str(idx) + '_centery' for idx in range(self.cen_num)]
            centers = []
            for i in range(self.cen_num):
                centers.append((
                    fit_results['result'].best_values[keys_x[i]],
                    fit_results['result'].best_values[keys_y[i]]
                ))
            centers = np.array(centers)


            population_dict = {
                'mean_pop': mean_estimate,
                'std_pop': std_estimate,
                'estimates': estimates,
                'num_trials': num_trials,
                'mean_temp': mean_temperature,
                'std_temp': std_temperatures,
                'temperatures': temperatures,
                'centers': centers,
            }
        else:
            keys = ['g' + str(idx) + '_amplitude' for idx in range(self.cen_num)]
            amps = []
            for i in range(self.cen_num):
                amps.append(fit_results['result'].best_values[keys[i]])

            mean_estimate = self.Pop_calc(amps)
            population_dict = {
                'mean': mean_estimate
            }

        return population_dict
    
    # define a function for calculating the populations
    def Pop_calc(self, amps):
        pop_list = []
        for idx in range(len(amps)):
            pop_list.append(amps[idx]/np.sum(amps))
            
        return pop_list
    
    # Create a histogram
    def createHistogram(self, iq_data, bin_size = None):
        """
        Create a histogram
        """
        if bin_size == None :
            norm = np.sqrt(iq_data[0,:]**2 + iq_data[1,:]**2)
            bin_size = np.histogram_bin_edges(norm, bins='fd').size

        # Create the histogram
        hist2d = np.histogram2d(iq_data[0,:], iq_data[1,:], bins = bin_size)

        return hist2d

    # Calculate the distinctness of a fit
    def calculate_distinctness(self, cen_num = None, new_fit = None, method = "mahalanobis"):
        """
        Calculates how well seperated the clusters are
        """
        if cen_num == None:
            cen_num = self.cen_num

        if new_fit == None:
            fit = self.final_results
        else:
            fit = new_fit

        # create quantifier
        quant = np.zeros((cen_num, cen_num))

        # Create a matrix of means, amplitudes and sigmas
        means = np.zeros((cen_num, 2))              # (cen_num, dim)
        sigmas = np.zeros((cen_num, 2, 2))          # (cen_num, dim, dim)
        amps = np.zeros((cen_num))                  # (cen_num)
        params = fit['result'].best_values
        for i in range(cen_num):
            key = "g"+str(i)+"_"
            means[i,:] = [params[key+"centerx"], params[key+"centery"]]
            sigmas[i,0,0] = sigmas[i,1,1] = params[key+'sigmax']
            amps[i] = params[key+'amplitude']
        # print(amps)
        if method == "mahalanobis":
            # Calculate the malalanabois distance
            for i in range(cen_num):
                for j in range(cen_num):
                    quant[i,j] = dt.mahalanobis_distance(means[i], sigmas[i], means[j], sigmas[j])

        elif method == "bhattacharyya":
            # Calculate the bhattacharyya distance
            for i in range(cen_num):
                for j in range(cen_num):
                    quant[i, j] = dt.bhattacharyya_distance(means[i], sigmas[i], means[j], sigmas[j])

        elif method == "kl":
            # Calculate the kl divergence
            for i in range(cen_num):
                for j in range(cen_num):
                    quant[i, j] = dt.kl_divergence(means[i], sigmas[i], means[j], sigmas[j])

        elif method == "hellinger":
            # Calculate the hellinger distance
            for i in range(cen_num):
                for j in range(cen_num):
                    quant[i, j] = dt.hellinger_distance(means[i], sigmas[i], means[j], sigmas[j])

        elif method == "brute":
            print("Under work")

        else:
            # Throw error
            raise Exception("Method Not Implemented")

        # Sum of all non-diagonal element
        quant = np.sum(quant) - np.trace(quant)

        # Check if the amps have a sane value if not then quant is zero
        total_amp = np.sum(amps)
        percentage = amps/total_amp
        # if any percentage less than 10 % we set to zero
        if np.min(percentage) < 0.1:
            quant = 0


        return quant
