'''
Post Selected Single Shot Analysis


Created by: Jocelyn Liu
Date: 08/13/2024
'''

import numpy as np
import matplotlib.pyplot as plt

# Import custom modules
import sys

from matplotlib.backends.backend_pdf import pdfRepr

sys.path.append(r"C:\Users\jocel\Documents\HouckLab_QICK")
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import constants
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import utils
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import distinctness as dt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis.shot_analysis import SingleShotAnalysis

""" Inherit from SingleShotAnalysis class, which handles the centers/fitting/population calc
"""
class PostSelection(SingleShotAnalysis):
    def __init__(self, i_arr,q_arr, confidence=0.8,**kwargs):
        super().__init__(i_arr,q_arr,**kwargs)#self,i_arr,q_arr)
        self.confidence = confidence
        """
        Initialize the class (From SingleShotAnalysis). 
c
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
        confidence : float
            The confidence value for calculating the post-selected populations
        """

    # Run post selection process
    def do_post_select(self, data=None, **kwargs):
        """
        Takes the initial and final IQ data, post-select for a certain confidence interval
        """
        # Stack initial and final IQ arrays to pass around
        iq_data_init = np.stack((self.i_0_arr, self.q_0_arr), axis=0)
        iq_data_fin = np.stack((self.i_arr, self.q_arr), axis=0)

        # Get centers
        centers = SingleShotAnalysis.get_Centers(self, self.i_0_arr, self.q_0_arr)

        # Find Gaussians, returns a dict with relevant parameters
        fit_results = SingleShotAnalysis.fit_gaussians(self, self.i_0_arr, self.q_0_arr, centers, initial_params=None)

        # Calculate PMF of each Gaussian from the fitted parameters
        myparams = fit_results['result'].params  # for ease of indexing fit parameters
        gaussians = []
        gaussians.append(gaussian_2d((fit_results['X'], fit_results['Y']), myparams['g0_amplitude'].value,
                                     myparams['g0_centerx'].value, myparams['g0_centery'].value,
                                     myparams['g0_sigmax'].value))
        print("shape of gaussians is ",np.shape(gaussians))
        gaussians.append(gaussian_2d((fit_results['X'], fit_results['Y']), myparams['g1_amplitude'].value,
                                     myparams['g1_centerx'].value, myparams['g1_centery'].value,
                                     myparams['g1_sigmax'].value))
        pmf_init = self.get_pmf(gaussians)
        print("shape of gaussians is ", np.shape(gaussians))

        # Create probability array
        probability = self.calculate_probability(self, self.i_0_arr, self.q_0_arr, fit_results, pmf_init)

        # Sort IQ data by probability
        sorted_prob, sorted_data_init, sorted_data_fin = self.sort_by_prob(self, iq_data_init, iq_data_fin, probability)

        # Store the fitted centers of initial IQ in an array
        centers = [(myparams['g0_centerx'].value, myparams['g0_centery'].value),(myparams['g1_centerx'].value, myparams['g1_centery'].value)]

        # Calculate populations in each blob using the post-selected data; return the post-selected initial and final IQ points in case of other post-processing
        pop, selected_data_init_arr, selected_data_fin_arr = self.calculate_ps_pop(self, sorted_prob, sorted_data_init, sorted_data_fin,centers, initial_params=myparams)



        return 1

    # Display the post-select process
    def display_ps(self,fit_results_i, selected_data_init_arr, selected_data_fin_arr):

        #plt.figure()
        fig, (ax1,ax2,ax3) = plt.subplots(1,3)

        xedges_init = fit_results_i['X'][:, 0]
        yedges_init = fit_results_i['Y'][0, :]
        im1 = ax1.imshow(fit_results_i['hist2d'],extent=(xedges_init[0],xedges_init[-1],yedges_init[0],yedges_init[-1]))
        ax1.set_title("Raw (initial)")
        fig.colorbar(im1)
        print("Selected data 0 is ",np.shape(selected_data_init_arr[0]))
        print("Selected data 1 is ", np.shape(selected_data_init_arr[1]))
        ax2.scatter(selected_data_init_arr[0][0,:],selected_data_init_arr[0][1,:],marker='.')
        ax2.scatter(selected_data_init_arr[1][0, :], selected_data_init_arr[1][1, :],marker='.')
        ax2.set_title("My final scatter")

        combined_findata = np.hstack((selected_data_fin_arr[0],selected_data_fin_arr[1]))
        combined_initdata = np.hstack((selected_data_init_arr[0],selected_data_init_arr[1]))
        # Create a hist2d to compare the post selected vs initial IQ data
        hist2d, xedges, yedges = SingleShotAnalysis.createHistogram(self, combined_initdata,bin_size=None)
        #hist2d, xedges, yedges = np.histogram2d(combined_findata[0,:],combined_findata[1,:], bins = 45)#self.num_bins)
        im3 = ax3.imshow(hist2d,extent=(xedges[0],xedges[-1],yedges[0],yedges[-1]))
        ax3.set_title("Post-selected (initial)")
        fig.colorbar(im3)
        # Plot the initial and final points fitted to each Gaussian
        fig, axs = plt.subplots(1, self.cen_num)
        axs = axs.ravel()
        for i in range(self.cen_num):
            #axs[i].scatter(self.i_0_arr, self.q_0_arr, marker='.', label='initial no selection')
            axs[i].scatter(selected_data_init_arr[i][0, :], selected_data_init_arr[i][1, :], marker='.',label='Initial')
            axs[i].scatter(selected_data_fin_arr[i][0,:],selected_data_fin_arr[i][1,:],marker='.',label='Final')

            # print("length of final arr is",np.shape(selected_data_fin_arr[i][0,:]))
            # print("length of initial arr is", np.shape(selected_data_init_arr[i][0, :]))
            # print("length of initial arr no selection is", np.shape(self.i_0_arr))
            axs[i].set_xlim([xedges_init[0],xedges_init[-1]])
            axs[i].set_ylim([yedges_init[0], yedges_init[-1]])
            axs[i].legend()
            axs[i].set_xlabel("I (au)")
            axs[i].set_ylabel("Q (au)")
            axs[i].set_title(f"Gaussian {i}")
            axs[i].set_aspect('equal')
        plt.show()

    # Calculate the population of the state with post-selected data
    def calculate_ps_pop(self, sorted_prob, sorted_data_init, sorted_data_fin, centers, initial_params=None):
        """
        Input: sorted_prob_size, np array of cen_num x length(IQ) sorted from smallest to largest
               sorted_data_init, np array of cen_num x 2 x length(IQ), the first shot sorted from smallest to largest
               sorted_data_fin, np array of cen_num x 2 x length(IQ), the second shot sorted from smallest to largest

        Output: pop, np array of populations
                selected_data_init_arr,
                selected_data_fin_arr,
        """
        # Store the probability
        pop = np.zeros((self.cen_num, self.cen_num))

        #Store the selected points in the final and initial IQ points for plotting
        selected_data_init_arr = []
        selected_data_fin_arr = []

        for i in range(self.cen_num):
            print('-------- cen num is',i)
            # Calculate the index corresponding to desired confidence to a given gaussian
            idx_confidence = np.argmin(np.abs(sorted_prob[i, :] - self.confidence))
            print("Throw out points ", np.shape(sorted_data_init[i,:,:])[1] - idx_confidence)

            # Slice sorted_data up to the confidence index
            selected_data = sorted_data_fin[i, :, 0:idx_confidence + 1]
            selected_data_init = sorted_data_init[i, :, 0:idx_confidence+1]

            selected_data_init_arr.append(selected_data_init)
            selected_data_fin_arr.append(selected_data)
            #print("shape of i arr is", np.shape(selected_data_fin_arr))
            #print("shape of i arr is",np.shape(selected_data_fin_arr[0][0][:]))

            # get the populations using estimate_populations in parent shot_analysis class
            pop_holder = self.estimate_populations(i_arr=selected_data_fin_arr[0][0][:], q_arr=selected_data_fin_arr[0][1][:])
            pop[i,:] = pop_holder['mean']

        return pop, selected_data_init_arr, selected_data_fin_arr

    # Sort the IQ points by probability
    def sort_by_prob(self, iq_data_init, iq_data_fin, cen_num, probability, confidence):
        """
        Input: iq_data_init, np array of IQ data for the first shot
               iq_data_fin, np array of IQ data for the second shot
               cen_num, number of gaussians
               probability, np array of size cen_num x length(IQ) from calculate_probability()

        Output: sorted_prob_size, np array of cen_num x length(IQ) sorted from smallest to largest
                sorted_data_init, np array of cen_num x 2 x length(IQ), the first shot sorted from smallest to largest
                sorted_data_fin, np array of cen_num x 2 x length(IQ), the second shot sorted from smallest to largest
        """

        sorted_prob = np.zeros((cen_num, iq_data_init.shape[1]))
        sorted_data_init = np.zeros((cen_num,) + iq_data_init.shape)
        sorted_data_fin = np.zeros((cen_num,) + iq_data_fin.shape)

        for i in range(cen_num):
            sorted_idx = np.argsort(-probability[i, :])
            print(f"sorted idx {i} is",sorted_idx[0:10])
            sorted_prob[i, :] = probability[i, sorted_idx]
            sorted_data_init[i, :, :] = iq_data_init[:, sorted_idx]
            sorted_data_fin[i, :, :] = iq_data_fin[:, sorted_idx]

        return sorted_prob, sorted_data_init, sorted_data_fin

    # Calculate probability of I/Q points belonging to a given Gaussian
    def calculate_probability(self, i_arr, q_arr, cen_num, fit_results, pmf):
        """
        Input: i_arr, I data
               q_arr, Q data
               cen_num, number of centers
               fit_results, output dictionary from SingleShotAnalysis.fit_gaussians()
               pmf, list of nbins x nbins pmf for each gaussian in cen_num

        Output: probability, a cen_num x length(IQ data) array where each value corresponds to the nth IQ point
               belonging to each gaussian
        """
        iq_data = np.stack((i_arr, q_arr), axis=0)
        print("iq_data shape is",np.shape(iq_data))
        probability = np.zeros((cen_num, iq_data.shape[1]))
        print("probability shape is", np.shape(probability))

        # reduce dimension of the size of the histogram grid; break into axes since fit_results X and Y are nxn redundant
        x_points = fit_results['X'][:,0]
        y_points = fit_results['Y'][0,:]

        xedges_mid = (x_points[1:] + x_points[:-1]) / 2
        yedges_mid = (y_points[1:] + y_points[:-1]) / 2
        fx_points = xedges_mid
        fy_points = yedges_mid

        print('x y points shape is',np.shape(x_points))
        for i in range(cen_num):
            for j in range(iq_data.shape[1]):
                # find the x,y point closest to the i,q point
                idx_i = np.argmin(np.abs(fx_points - iq_data[0, j]))
                idx_q = np.argmin(np.abs(fy_points - iq_data[1, j]))
                # Calculate the probability of your IQ points belonging to a particular gaussian (rows)
                probability[i, j] = pmf[i][idx_i, idx_q]

        return probability

    # Calculate the probability mass function of a Gaussian, given a list of Gaussian arrays gaussians
    def get_pmf(self, gaussians): #what is the type of gaussians
        """
        Input: gaussians, a list of nbins x nbins Gaussian arrays

        Output: pmf, a list of nbins x nbins arrays containing the pmf of each gaussian
        """
        pmf = []
        total_gauss = 0
        for j in range(len(gaussians)):
            total_gauss += gaussians[j]
        for j in range(len(gaussians)):
            pmf.append(gaussians[j] / total_gauss)
        return pmf

# Define the 2D Gaussian function, returns  np array of size points x points
def gaussian_2d(points, A, x0, y0, sigma_x):
    x,y = points
    theta = 0
    sigma_y = sigma_x
    a = np.cos(theta)**2 / (2*sigma_x**2) + np.sin(theta)**2 / (2*sigma_y**2)
    b = -np.sin(2*theta) / (4*sigma_x**2) + np.sin(2*theta) / (4*sigma_y**2)
    c = np.sin(theta)**2 / (2*sigma_x**2) + np.cos(theta)**2 / (2*sigma_y**2)
    return A * np.exp(-(a*(x-x0)**2 + 2*b*(x-x0)*(y-y0) + c*(y-y0)**2))

##### EXTRANEOUS FUNCTIONALITY, SEE PARENT CLASS SHOT_ANALYSIS #####
# Returns the number of samples in a given gaussian and the std
# def calcNumSamplesInGaussian(hist2d, pmf, cen_num, x_points, y_points):
#     """
#     Input: hist2d, weights of a nbins x nbins 2d histogram
#            pmf,
#            cen_num
#            x_points, x-axis for bins of hist2d
#            y_points, y_axis for bins of hist2d
#
#     Output: num_samples_in_gaussian, cen_num x 1 array of number of samples in each distribution
#             num_samples_in_gaussian_std
#     """
#     num_samples_in_gaussian = np.zeros(cen_num)
#     num_samples_in_gaussian_std = np.zeros(cen_num)
#
#     # Create expected_dist to store the expected distribution of each gaussian
#     # The shape is (cen_num, hist2d[0].shape)
#     expected_dist = np.zeros((cen_num,) + hist2d.shape)
#     expected_dist_std = np.zeros((cen_num,) + hist2d.shape)
#     #print('pmf shape is ',np.shape(pmf))
#     print('hist2d shape is',np.shape(hist2d))
#     #print('expected dist shape is',np.shape(expected_dist))
#     for i in range(cen_num):
#         expected_dist[i] = pmf[i]*hist2d
#         expected_dist_std[i] = pmf[i] * (1 - pmf[i]) * hist2d
#
#         num_samples_in_gaussian[i] = np.sum(expected_dist[i])
#         num_samples_in_gaussian_std[i] = np.sqrt(np.sum(expected_dist_std[i]))
#
#     return num_samples_in_gaussian, num_samples_in_gaussian_std
#
# # Calc probability of belonging to one Gaussian
# def calcBelongstoGaussian(num_samples_in_gaussian, num_samples_in_gaussian_std, cen_num):
#     """
#     Input: num_samples_in_gaussian, array of cen_num x 1
#            num_samples_in_gaussian_std
#
#     Output: probability, array of cen_num x cen_num
#             std_probability
#     """
#     probability = np.zeros(cen_num)
#     std_probability = np.zeros(cen_num)
#     total_samples = np.sum(num_samples_in_gaussian)
#     print("total samples is",total_samples)
#     for i in range(cen_num):
#         probability[i] = num_samples_in_gaussian[i] / total_samples
#         std_probability[i] = num_samples_in_gaussian_std[i] / total_samples
#
#     return probability, std_probability