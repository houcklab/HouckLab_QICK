### writing a simulation of thermal dynamics in an ideal system

##### making code to plot the data from the WTF expirments
import numpy as np
import matplotlib.pyplot as plt
import h5py
# from hist_analysis import *
import scipy as sp
from scipy.io import loadmat
from scipy.optimize import curve_fit
from scipy.integrate import odeint
#import scqubits as scq
from tqdm import tqdm
import os
import pathlib
import json

# from thermalAnalysis import *

from sklearn.cluster import KMeans
# from sklearn import mixture
from sklearn.mixture import GaussianMixture as GMM
import sklearn.metrics as metrics

from lmfit import Model, Parameters, Minimizer, report_fit, conf_interval
from lmfit.model import save_modelresult
from lmfit.models import Gaussian2dModel

#from scipy.io import savemat

### define some constants
hbar = sp.constants.hbar ###1.054e-34
kb = sp.constants.k
echarge = sp.constants.e
phi0 = sp.constants.h / (2*echarge)

def temp2freq(temp):
    #### takes temp in units of K and returns GHz
    freq = ((kb*temp) / hbar) * (1/(1e9 *2*np.pi))
    return freq

def freq2temp(freq):
    #### takes freq in units of GHz and returns K
    temp = (1e9*freq *2*np.pi*hbar) / kb
    
    return temp

def Pop2Temp(pop0, pop1, freq):
    #### assume freq in units of MHz
    temp = -1*hbar * freq*1e6 * 2 *np.pi / (kb * np.log(pop1 / pop0) )
    return temp


def calcPDF(gaussians):
    pdf = []
    total_gauss = 0
    for j in range(len(gaussians)):
        total_gauss += gaussians[j]
    for j in range(len(gaussians)):
        pdf.append(gaussians[j]/total_gauss)
    return pdf

class PS_Analysis:
    ### define the initialization
    def __init__(
        self, 
        data, 
        cen_num = 2,
        cluster_method = 'gmm',
        Centers = None,
        select_size = None,
        init_method = 'all',
        outerFolder = None,
        data_name = None,
        gauss_fit = False
    ):
        """
        data : 'h5' file containing all data
        cen_num:  int, number of clusters to use
        cluster_method: 'gmm', 'kmeans', or 'None'
        Centers: array, initial estimates of centers of clusters
        select_size: float, radius around center to use in selection
        init_method: 'all' or int. If the method is 'all' then merge all 
            of the I and Q data into a single set for clustering and 
            identifying the gaussians. Set to a specificl integer value
            if you want to cluster and set the gaussians on a 
            particular time step
        outerFolder: str, location to save plots and such. A sub folder
            indexed with the data name will be created within it. If
            set to None, a subfolder will be made in the current directory
        data_name: str, name of the data set, the stored files will 
            contain this name
        """

        ### define number of clusters used
        self.cen_num = cen_num

        self.Centers = Centers
        self.select_size = select_size
        self.cluster_method = cluster_method
        self.init_method = init_method
            

        #### create a subfolder for the figure and info storage
        if outerFolder is not None:
            ### check to see if the outerFolder exsits
            outerFolderBool = pathlib.Path(outerFolder).is_dir()
            if outerFolderBool == False:
                os.mkdir(outerFolder)

        if data_name is not None:
            ### check to see if subfolder for data_name exists
            subFolderBool = pathlib.Path(
                os.path.join(outerFolder, data_name)).is_dir()
            if subFolderBool == False:
                os.mkdir(
                    os.path.join(outerFolder, data_name) 
                    )
            ### store the path name
            self.path = os.path.join(outerFolder, data_name)
        else:
            ### store the path name
            self.path = outerFolder

        ### if no data name given, use a temp name
        ### if this is the case, the data will just be store in the 
        ### current folder
        if data_name == None:
            data_name = 'temp_name'

        self.data_name = data_name

        ### extract out the I and Q informaiton from data file
        ### naming i_[EXPERIMENT NUMBER]_arr]
        ### EXPERIMENT_NUMBER = 0: initial measurement
        ### EXPERIMENT_NUMBER = 1: final measurement after wait

        ### try out the different import file types
        try:
            ### data style for T1_PS code
            self.i_0_arr = data['i_0_arr'][:]
            self.q_0_arr = data['q_0_arr'][:]

            self.i_1_arr = data['i_1_arr'][:]
            self.q_1_arr = data['q_1_arr'][:]

            ### extract out the time vector
            self.t_arr = data['wait_vec'][:]

        except:

            try:
                self.i_0_arr = [data['i_0'][:]]
                self.q_0_arr = [data['q_0'][:]]
                #### try to import QND and except for Thermal
                try:
                    self.i_1_arr = [data['i_1'][:]]
                    self.q_1_arr = [data['q_1'][:]]
                except:
                    try:
                        self.i_1_arr = [data['i_arr'][:]]
                        self.q_1_arr = [data['q_arr'][:]]
                    except:
                        pass
            except:
                """
                if you hit this point then you are 
                probably inputing data with only a single 
                measurement. if this is case, set the 
                intial and final measurements to be the
                same and just use a confidence seleciton 
                of 0. This is super hacky, but i think 
                that it should work.
                """
                self.i_0_arr = [data['i_arr'][:]]
                self.q_0_arr = [data['q_arr'][:]]
                self.i_1_arr = [data['i_arr'][:]]
                self.q_1_arr = [data['q_arr'][:]]


            self.t_arr = np.array([0.0])
        
        ### store the number of shots in a given experiment
        self.num_shots = len(self.i_0_arr[0])

        ### create the kmeans clustering definition
        if self.init_method == 'all':
            ### create a list of all I and Q data
            I = np.array([])
            Q = np.array([])
            for idx in range(len(self.t_arr)):
                I=np.append(I, self.i_0_arr[idx][:]) 
                Q=np.append(Q, self.q_0_arr[idx][:])

            ### store a version of the full data set
            self.I_full = I
            self.Q_full = Q

        else:
            I = self.i_0_arr[self.init_method]   
            Q = self.q_0_arr[self.init_method]
            
        if cluster_method == 'kmeans':
            self._init_kmeans(I, Q)
        elif cluster_method == 'gmm':
            self._init_gmm(I, Q)

        if gauss_fit:
            self._init_gaussFit(I, Q )

    ### define function for creating initial kmeans definition
    def _init_kmeans(self, I, Q):

        ### create stack of data for kmeans cluster
        iqData = np.stack((I, Q), axis = 1)

        if self.Centers is not None:
            self.kmeans = KMeans(
                n_clusters = self.cen_num,
                n_init = 1,
                max_iter = 1000, 
                init = self.Centers
                ).fit(iqData)
            #### redefine centers
            self.Centers = self.kmeans.cluster_centers_
        else:
            ### if Centers was given, use as initial estimate, if not use normal
            self.kmeans = KMeans(
                n_clusters = self.cen_num,
                n_init = 10,
                max_iter = 1000, 
                ).fit(iqData)

            ### from kmeans extract out the centers and labels
            self.Centers = self.kmeans.cluster_centers_

        ### create a place holder for the centers
        Centers_hold = np.copy(self.Centers)
        #### find the size of each cluster
        labels = self.kmeans.labels_
        unique, counts = np.unique(labels, return_counts=True)
        sizes = np.zeros(len(unique))
        for idx in range(len(unique)):
            sizes[unique[idx]] = counts[idx]
        sizes_index = np.array(sizes).argsort().tolist()[::-1]
 
        ### reorganize the centers
        for idx_cen in range(self.cen_num):
            Centers_hold[idx_cen] = self.Centers[sizes_index[idx_cen]]

        ### recenter the data
        self.kmeans = KMeans(
            n_clusters = self.cen_num,
            n_init = 1,
            max_iter = 1000, 
            init = Centers_hold
            ).fit(iqData)
        #### redefine centers
        self.Centers = self.kmeans.cluster_centers_

        ### from kmeans, find the average size of each cluster
        dists = np.full([self.cen_num, len(I)], np.nan)
        blob_nums = self.kmeans.labels_
        for idx_shot in range(len(I)):
            for idx_cen in range(self.cen_num):
                if blob_nums[idx_shot] == idx_cen:
                    dists[idx_cen][idx_shot] = np.sqrt(
                        (self.Centers[idx_cen][0] - I[idx_shot])**2 + 
                        (self.Centers[idx_cen][1] - Q[idx_shot])**2
                    )

        ### store the average size of each cluster
        if self.select_size is None:
            cluster_size = np.full(self.cen_num, np.nan)
            for idx_cen in range(self.cen_num):
                cluster_size[idx_cen] = np.nanmean(dists[idx_cen])

            self.select_size = np.mean(cluster_size)*1.25
            
            
    ### define function for creating gaussian mixture model
    def _init_gmm(self, I, Q):

        ### create stack of data for kmeans cluster
        iqData = np.stack((I, Q), axis = 1)

        if self.Centers is not None:
            self.gmm = GMM(
                n_components=self.cen_num, 
                covariance_type = 'tied', 
                means_init = self.Centers
            ).fit(iqData)
            #### redefine centers
            self.Centers = self.gmm.means_
        else:
            self.gmm = GMM(
                n_components=self.cen_num, 
                covariance_type = 'tied', 
                n_init = 10,
            ).fit(iqData)
            #### redefine centers
            self.Centers = self.gmm.means_

        #### find which cluster is largest and recluster with ordered centers
        Centers_hold = np.copy(self.Centers)
        sizes = self.gmm.weights_ 
        sizes_index = np.array(sizes).argsort().tolist()[::-1]
        for idx_cen in range(self.cen_num):
            Centers_hold[idx_cen] = self.Centers[sizes_index[idx_cen]]

        self.gmm = GMM(
            n_components=self.cen_num, 
            covariance_type = 'tied', 
            means_init = Centers_hold,
        ).fit(iqData)
        #### redefine centers
        self.Centers = self.gmm.means_
       
        #### find the selection size
        if self.gmm.covariance_type == "full":
            covariances = self.gmm.covariances_[n][:2, :2]
        elif self.gmm.covariance_type == "tied":
            covariances = self.gmm.covariances_[:2, :2]
        elif self.gmm.covariance_type == "diag":
            covariances = np.diag(self.gmm.covariances_[n][:2])
        elif self.gmm.covariance_type == "spherical":
            covariances = np.eye(
                self.gmm.means_.shape[1]) * self.gmm.covariances_[n]
            
        v, w = np.linalg.eigh(covariances)
        u = w[0] / np.linalg.norm(w[0])
        angle = np.arctan2(u[1], u[0])
        angle = 180 * angle / np.pi  # convert to degrees
        v = 2.0 * np.sqrt(2.0) * np.sqrt(v)
        
        self.select_size = np.mean(v)
        
    #### initialize the gaussian fit
    def _init_gaussFit(self, I, Q ):

        #### create a histogram of the inialize data
        #### make normal IQ data
        iqData = np.stack((I, Q), axis = 0)

        ##### create histogram of the data
        hist2d = self.createHistogram(
            iqData,
            bin_size = None,
            lims = None,
            )
        
        #### find the grid points
        xedges = hist2d[1]
        yedges = hist2d[2]
        xedges_mid = (xedges[1:] + xedges[:-1])/2
        yedges_mid = (yedges[1:] + yedges[:-1])/2
        x_points = xedges_mid
        y_points = yedges_mid
        Y, X = np.meshgrid(yedges_mid, xedges_mid)

        #### set the hist lims for the future fits
        self.hist_lims = [[xedges[0], xedges[-1]], [yedges[0], yedges[-1]] ]

        norm_hist = np.copy(hist2d[0])

        #### create the parameters
        self._create_model()

        params = self.full_model.make_params()
        params.add('sigma', 
            value = (x_points[-1] - x_points[0])/32, min = 0, max = np.inf)
        for i in range(self.cen_num):
            prefix = 'g' + str(i) + '_'
            params.add(prefix + 'sigmax', expr = 'sigma')
            params.add(prefix + 'sigmay', expr = 'sigma')
        
        amplitude_last_gauss = '1'
        for i in range(self.cen_num-1):
            prefix = 'g' + str(i) + '_'
            amplitude_last_gauss += '-' + prefix + 'amplitude'
        
        # #### fix the final amplitude?
        # params.add('g' + str(cen_num-1) + '_amplitude', 
        #    expr = amplitude_last_gauss)

        #### add in the geusses
        cen_buff = 1.0
        for idx in range(self.cen_num):
            prefix = 'g' + str(idx) + '_'
            params[prefix + 'centerx'].set(
                value = self.Centers[idx, 0],
                min = self.Centers[idx, 0] - cen_buff,
                max = self.Centers[idx, 0] + cen_buff,
                vary = True
                )
            params[prefix + 'centery'].set(
                value = self.Centers[idx, 0],
                min = self.Centers[idx, 1] - cen_buff,
                max = self.Centers[idx, 1] + cen_buff,
                vary = True
                )
        #    if idx < self.cen_num - 1:
        #        params[prefix+'amplitude'].set(
        #        value = 0.5,
        #        min = 0.0,
        #        max = 1.0,
        #        vary = True,
        #        )
        
            params[prefix+'amplitude'].set(
                value = 0.5,
                min = 0.0,
                max = np.inf,
                vary = True,
                )

        ### create a verison of the data to fit, remove the 0 elements
        fit_hist = np.copy(norm_hist)
        fit_hist[fit_hist == 0] = np.nan
        weights = 1 / np.sqrt(fit_hist)
        
        ### fit the data
        result = self.full_model.fit(
            fit_hist, 
            params, 
            x = X, 
            y = Y,
            weights = weights, 
            method = 'least_squares',
            )
        self.init_result = result
        self.init_params = result.params

        ##### print the results
        report_fit(result)

        ##### save the model results
        file_path = self.path + '/init_modelResult.sav'
        save_modelresult(result, file_path)

        ###### save the fit statisitics
        heading = 'Inital fit'
        file_name = 'fit_stats'
        self.saveOutput(
            heading, result.fit_report(), file_name, append = False)

        heading = 'confidence intervals'
        conf_int_report = result.ci_report(
            ndigits = 6, 
            maxiter = 1000,
            verbose = True,
            )
        print(conf_int_report)
        self.saveOutput(
            heading, conf_int_report, file_name, append = True)

        #### save the residual plot
        self.plot_Fit(
            result, 
            X, 
            Y,  
            norm_hist, 
            plot_disp = False, 
            plot_save = True, 
            plot_title = 'Initialize Fit'
            )

        ##### store a copy of the individual gaussians
        ### create the gaussians
        gaussians = []
        for idx in range(self.cen_num):
            gaussians.append(
                result.eval_components(
                    x = X.ravel(), 
                    y = Y.ravel()
                    )['g' + str(idx) + '_'].reshape(norm_hist.shape))
        
        gaussian_full = np.copy(gaussians[0])
        for idx in range(1, self.cen_num):
            gaussian_full += gaussians[idx]

        self.gaussians = gaussians
        self.gaussian_full = gaussian_full

        self.pdf = calcPDF(gaussians)

        #### store a copy of the x and y points
        self.init_x_points = x_points
        self.init_y_points = y_points

        ########
        #### after gaussians created, fix the init params
        self.init_params['sigma'].set(vary = False)
        for idx in range(self.cen_num):
            prefix = 'g' + str(idx) + '_'
            self.init_params[prefix + 'centerx'].set(
                vary = False
                )
            self.init_params[prefix + 'centery'].set(
                vary = False
                )

    ### define function for sorting measurement into kmeans and gmm cluster
    def clusterMeasurement(self,  
                            wait_num = 0,
                            ):
        ### wait_num: index for t_arr ('wait_vec' from data file)

        ### grab the initial I and Q data 
        I = self.i_0_arr[wait_num]
        Q = self.q_0_arr[wait_num]

        ### grab the final measurement data
        I1 = self.i_1_arr[wait_num]
        Q1 = self.q_1_arr[wait_num]

        ### create the iqData for sorting into kmeans clusters
        iqData = np.stack((I, Q), axis = 1)
        
        #### cluster for kmeans 
        if self.cluster_method == 'kmeans':
            blob_distribution = self.kmeans.predict(iqData)
        elif self.cluster_method == 'gmm':
            blob_distribution = self.gmm.predict(iqData)
            
        blobNums = blob_distribution

        ### create array for storing the blobs and distance of points to center
        ### blobs arr is indexed as:
        ### blobs[starting cluster num][meas num][I or Q][shot num]
        blobs = np.full([self.cen_num, 2, 2, len(I)], np.nan)

        ### loop over all shots and sort IQ data into arrays
        for idx_shot in range(len(I)):
            for idx_cen in range(self.cen_num):
                if blobNums[idx_shot] == idx_cen:
                    ### fill blobs array with data
                    blobs[idx_cen][0][0][idx_shot] = I[idx_shot]
                    blobs[idx_cen][0][1][idx_shot] = Q[idx_shot]

                    blobs[idx_cen][1][0][idx_shot] = I1[idx_shot]
                    blobs[idx_cen][1][1][idx_shot] = Q1[idx_shot]

        return blobs


    def GaussFitData(self,
                    I0, 
                    Q0, 
                    I1, 
                    Q1, 
                    confidence_selection = 0.99,
                    bin_size = None,
                    plot_title = None
                    ):
        """
        using the input values for I and Q, use the internal
        full model to fit the data
        """

        sorted_shots = []
            
        for idx in range(self.cen_num):
            sorted_shots.append([])
        
            for idx_shot in range(len(I0)):
                print(I0.shape)
                i_val = I0[idx_shot]
                q_val = Q0[idx_shot]
            
                i_idx = np.argmin(np.abs(self.init_x_points - i_val))
                q_idx = np.argmin(np.abs(self.init_y_points - q_val))
            
                sorted_shots[idx].append(self.pdf[idx][i_idx, q_idx])
        
        #### create lists to store the shots
        i_int_shots = []
        q_int_shots = []
        
        i_fin_shots = []
        q_fin_shots = []
        
        #### sort out the shots
        for idx_cen in range(self.cen_num):
            i_int_shots.append([])
            q_int_shots.append([])
            
            i_fin_shots.append([])
            q_fin_shots.append([])
        
            for idx_shot in range(len(sorted_shots[idx_cen])):
            
                if sorted_shots[idx_cen][idx_shot] > confidence_selection:
            
                    i_int_shots[idx_cen].append(I0[idx_shot])
                    q_int_shots[idx_cen].append(Q0[idx_shot])
            
                    i_fin_shots[idx_cen].append(I1[idx_shot])
                    q_fin_shots[idx_cen].append(Q1[idx_shot])
        
        ##### create a list to store the result objects
        results_list = []
    
        ### loop through the starting centers
        for idx_cen in range(self.cen_num):
            ### create the initial gaussian
            #### create the initial data selections
            I_fin = i_fin_shots[idx_cen]
            Q_fin = q_fin_shots[idx_cen]
            iqData_fin = np.stack((I_fin, Q_fin), axis = 0)
            
            ##### create new histogram
            hist2d_fin = self.createHistogram(
                iqData_fin, 
                bin_size = bin_size, 
                lims = self.hist_lims
            )
            norm_hist_fin = np.copy(hist2d_fin[0])
            #### find the grid points
            xedges_fin = hist2d_fin[1]
            yedges_fin = hist2d_fin[2]
            xedges_mid_fin = (xedges_fin[1:] + xedges_fin[:-1])/2
            yedges_mid_fin = (yedges_fin[1:] + yedges_fin[:-1])/2
            Y_fin, X_fin = np.meshgrid(yedges_mid_fin, xedges_mid_fin)
            
            ### create a verison of the data to fit, remove the 0 elements
            fit_hist_fin = np.copy(norm_hist_fin)
            fit_hist_fin[fit_hist_fin == 0] = np.nan
            weights_fin = 1 / np.sqrt(fit_hist_fin)
            
            ### fit the data
            result_fin = self.full_model.fit(
                fit_hist_fin, 
                self.init_params, 
                x = X_fin, 
                y = Y_fin,
                weights = weights_fin, 
                method = 'least_squares',
                )

            if plot_title != None:
                self.plot_Fit(
                    result_fin, 
                    X_fin, 
                    Y_fin, 
                    norm_hist_fin,
                    plot_disp = False,
                    plot_save = True, 
                    plot_title = plot_title + '_starting_state_' + str(idx_cen)
                    )
            
            results_list.append(result_fin)

        return results_list
    
                     
    ### define function performing gaussian fit to sort the data
    def GaussFitMeasurement(self,  
                            wait_num = 0, 
                            confidence_selection = 0.99,
                            bin_size = None, 
                            plot_title = None,
                            save_estimates_name = None,
                            save_pop_results = False,
                            qubit_freq = None,
                            ):
        #### sort the shots and find the probabilies  

        ### grab the initial I and Q data 
        I0 = self.i_0_arr[wait_num]
        Q0 = self.q_0_arr[wait_num]

        ### grab the final measurement data
        I1 = self.i_1_arr[wait_num]
        Q1 = self.q_1_arr[wait_num]

        
        if plot_title != None:
            results_list = self.GaussFitData(
                        I0, Q0, 
                        I1, Q1, 
                        confidence_selection = confidence_selection,
                        bin_size = bin_size,
                        plot_title = plot_title + '_timeStep_' + str(wait_num),
                        )
        else:
            results_list = self.GaussFitData(
                        I0, Q0, 
                        I1, Q1, 
                        confidence_selection = confidence_selection,
                        bin_size = bin_size,
                        plot_title = plot_title,
                        )
 
        ### loop through the starting centers and find estiamtes
        estimates_full = {}
        for idx_cen in range(self.cen_num):
            ### extract the result
            result_fin = results_list[idx_cen]

            if save_estimates_name != None:
                ####### calcualted the estimates and save
                estimates = self.calcPopEstimates(
                    result_fin, 
                    save_name = (save_estimates_name + 
                                 'waitStep_' + str(wait_num) + 
                                 '_Starting_' + str(idx_cen)
                                ),
                    qubit_freq = qubit_freq
                )
            else:
                ####### calcualted the estimates without saving
                estimates = self.calcPopEstimates(
                    result_fin, 
                    save_name = None,
                    qubit_freq = qubit_freq
                )

            estimates_full['Starting_'+str(idx_cen)] = estimates

            #### append population estimates to result text
            heading = ('Final Population at time step '+str(wait_num)+
                       ', starting state ' + str(idx_cen) + '\n' + 
                      'confidence selection: '+ str(confidence_selection*100) +
                      '%')
            file_name = 'fit_stats'
            ### loop and add info to the string
            PopInfo = ''
            for idx in range(self.cen_num):
                prefix = 'PopState_'+str(idx)+'_'
                PopInfo += 'Population of state ' + str(idx) + '\n'
                PopInfo += 'mean: ' + str(estimates[prefix+'mean']) + '\n'
                PopInfo += 'std: ' + str(estimates[prefix+'std']) + '\n'
                conf_interval_low = estimates[prefix+'95_low']
                conf_interval_high = estimates[prefix+'95_high']
                PopInfo += ('95% confidence interval: [' + 
                           str(conf_interval_low) + ', ' + 
                           str(conf_interval_high) + '] \n')
                
            if save_pop_results:
                self.saveOutput(
                    heading, PopInfo, file_name, append = True)

        if self.cen_num ==2 and qubit_freq != None:
            #### append qubit temperature info
            heading = ('Qubit Temperature')
            file_name = 'fit_stats'
            TempInfo = 'Qubit frequency ' + str(qubit_freq) + 'MHz, '
            prefix = 'temp_'
            TempInfo += 'Qubit temperature \n'
            TempInfo += 'mean: ' + str(estimates[prefix+'mean']) + 'mK \n'
            TempInfo += 'std: ' + str(estimates[prefix+'std']) + 'mK \n'
            conf_interval_low = estimates[prefix+'95_low']
            conf_interval_high = estimates[prefix+'95_high']
            TempInfo += ('95% confidence interval: [' + 
                       str(conf_interval_low) + ', ' + 
                       str(conf_interval_high) + '] mK \n')

            if save_pop_results:
                self.saveOutput(
                    heading, PopInfo, file_name, append = True)

        #### return the population estimates
        return estimates_full

    ### create function to count final state populations for kmeans and none
    def popCount(self, 
                wait_num = 0,
                ):
        ### wait_num: int, index for t_arr time slice

        ### define array for storing the population info
        pops = np.full([self.cen_num, self.cen_num], 0.0)
        
        if self.cluster_method in ['kmeans', 'None']:

            for idx_shot in range(self.num_shots):
                ### pull out the initial I and Q value
                I_int = self.i_0_arr[wait_num][idx_shot]
                Q_int = self.q_0_arr[wait_num][idx_shot]

                ### pull out the final I and Q value
                I_fin = self.i_1_arr[wait_num][idx_shot]
                Q_fin = self.q_1_arr[wait_num][idx_shot]

                for idx_cen_int in range(self.cen_num):

                    ### determine initial distance
                    dist_int = np.sqrt( 
                        (self.Centers[idx_cen_int][0] - I_int)**2 +
                        (self.Centers[idx_cen_int][1] - Q_int)**2
                        )

                    if dist_int<= self.select_size:

                        for idx_cen_fin in range(self.cen_num):
                            dist_fin = np.sqrt( 
                                (self.Centers[idx_cen_fin][0] - I_fin)**2 +
                                (self.Centers[idx_cen_fin][1] - Q_fin)**2
                                )
                            if dist_fin <= self.select_size:
                                pops[idx_cen_int][idx_cen_fin] += 1.0


            for idx_cen in range(self.cen_num):
                pops[idx_cen] = pops[idx_cen] / np.sum(pops[idx_cen])

            return pops
        
        ##### calculate probabilites for gmm
        elif self.cluster_method == 'gmm':

            I_int = self.i_0_arr[wait_num]
            Q_int = self.q_0_arr[wait_num]
            iqData_int = np.stack((I_int, Q_int), axis = 1)

            I_fin = self.i_1_arr[wait_num]
            Q_fin = self.q_1_arr[wait_num]
            iqData_fin = np.stack((I_fin, Q_fin), axis = 1)

            #### cluster the initial experiment
            labels = self.gmm.predict(iqData_int)
            probs = self.gmm.predict_proba(iqData_int)

            ### find the locations where the probabilies are high
            prob_thresh = 0.999

            IQ_sorted_int = []
            IQ_sorted_fin = []

            ##### loop through the starting states and find the IQ distributions
            for idx_cen_int in range(self.cen_num):
                prob_locs = np.argwhere(probs[:,idx_cen_int] > prob_thresh)[:,0]

                IQ_int = iqData_int[prob_locs]
                IQ_fin = iqData_fin[prob_locs]

                IQ_sorted_int.append(IQ_int)
                IQ_sorted_fin.append(IQ_fin)

            ### find the probabilites
            for idx_cen_int in range(self.cen_num):
                #### recluster the data to find the new weights

                weights_new = GMM(
                    n_components=self.cen_num, 
                    covariance_type = 'tied', 
                    means_init = self.gmm.means_,
                    precisions_init = self.gmm.precisions_,
                    n_init = 1,
                ).fit(IQ_sorted_fin[idx_cen_int]).weights_

                pops[idx_cen_int] = weights_new

#                #### find probabilies for starting in state idx
#                probs = self.gmm.predict_proba(IQ_sorted_fin[idx_cen_int])
#                ### loop over final states
#                for idx_cen_fin in range(self.cen_num):
#                    pops[idx_cen_int][idx_cen_fin] = np.mean(
#                        probs[:,idx_cen_fin])
            
            return pops
        
    ### define function for finding the populations as a funciton of time
    def popVsTime(
        self,
        gaussFit = False,
        ):

        ### find the populations at each time point

        t_len = len(self.t_arr)

        pop_vec = np.full([self.cen_num, self.cen_num, t_len], np.nan)
        pop_err_vec = np.full([self.cen_num, self.cen_num, t_len], np.nan)

        ### loop over the times
        for idx_t in tqdm(range(t_len)):
            ### find the populations at each time step
            if gaussFit:
                pops, pops_err = self.GaussFitMeasurement(  
                            wait_num = idx_t, 
                            confidence_selection = 0.99,
                            bin_size = None, 
                            )

            else:
                pops = self.popCount(wait_num = idx_t)

            ### loop and fill in the populaiton vector
            for idx_cen_start in range(self.cen_num):
                for idx_cen_stop in range(self.cen_num):
                    pop_vec[idx_cen_start][idx_cen_stop][idx_t] = (
                        pops[idx_cen_start][idx_cen_stop])

                    if gaussFit:
                        pop_err_vec[idx_cen_start][idx_cen_stop][idx_t] = (
                            pops_err[idx_cen_start][idx_cen_stop])

        self.pop_vec = pop_vec
        self.pop_err_vec = pop_err_vec

        if gaussFit:
            return pop_vec, pop_err_vec
        else:
            return pop_vec

    ### function to save output text
    def saveOutput(self, 
                heading, 
                output, 
                file_name, 
                append = False
                ):
        ### check if writing a new file or appending an existing
        if file_name[-4:] != '.txt':
            file_name += '.txt'
        try:
            file_name = self.path + '/' + file_name
        except:
            pass

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

    ########## function for creating a histogram to the data
    def createHistogram(self,
                iq_data, 
                bin_size = None,
                lims = None,
                ):
        ### if no bin_size is given, find optimal size
        if bin_size == None:
            norm = np.sqrt(iq_data[0,:]**2 + iq_data[1,:]**2)
            bin_size = np.histogram_bin_edges(norm, bins='fd').size

        ### if lims are given use them, if not, try to use internal
        ### limits, if it is the first time, create them

        if lims == None:
            try:
                hist2d = np.histogram2d(
                    iq_data[0,:], 
                    iq_data[1,:], 
                    bins = bin_size, 
                    density=False,
                    range = self.hist_lims
                    )
            except:
                hist2d = np.histogram2d(
                    iq_data[0,:], 
                    iq_data[1,:], 
                    bins = bin_size, 
                    density=False,
                    )

        else:
            hist2d = np.histogram2d(
                iq_data[0,:], 
                iq_data[1,:], 
                bins = bin_size, 
                density=False,
                range = self.hist_lims
                )

        return hist2d

    ################ define the gaussain fit model
    def _create_model(self):
        ##### Define the model to fit
        models = []
        for i in range(self.cen_num):
            prefix = 'g' + str(i) + '_'
            model = Gaussian2dModel(prefix=prefix)
            models.append(model)
        
        full_model = models[0]
        for i in range(1, self.cen_num):
            full_model += models[i]
        
        full_model.nan_policy = 'omit'

        self.full_model = full_model

    ####### function to plot the residuals


    ##############################################################
    def plot_Fit(
                self, 
                result, 
                X, 
                Y, 
                Z,
                plot_disp = False,
                plot_save = True, 
                plot_title = 'Fit Comparision'
                ):
        ### plot_fit_comparision:
        fit = result.eval(
            x = X, 
            y = Y,
            )
        fig, axs = plt.subplots(2, 2, figsize=(7, 7))
        
        vmax = np.nanpercentile(Z, 99.9)
        
        ###### plot the data
        ax = axs[0, 0]
        art = ax.pcolor(X, Y, Z, vmin=0, vmax=vmax, shading='auto')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Data')
        
        ### find the ranges of the initial plot
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        
        ###### plot the fit 
        ax = axs[0, 1]
        art = ax.pcolor(X, Y, fit, vmin=0, vmax=vmax, shading='auto')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Fit')
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        #### plot the residual
        ax = axs[1, 1]
        ###art = ax.pcolor(X, Y, Z-fit, vmin=0, vmax=1, shading='auto')
        art = ax.pcolor(X, Y, Z-fit, shading='auto')
        plt.colorbar(art, ax=ax, label='z')
        ax.set_title('Residuals')
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        for ax in axs.ravel():
            ax.set_xlabel('I (arb. units)')
            ax.set_ylabel('I (arb. units)')
        
        plt.suptitle(plot_title)
        plt.tight_layout()

        if plot_save:
            plot_save_loc = self.path + '/' + plot_title + '.pdf'
            plt.savefig(plot_save_loc)

        if plot_disp:
            plt.show()

    ##############################################################
    def calcPopEstimates(self,
                         result,
                         save_name = None,
                         qubit_freq = None
    ):
        #### find estimate for the errors

        
        #### create a list of the amplitude keys
        keys = []
        for idx in range(self.cen_num):
            prefix = 'g' + str(idx) + '_'
            keys.append(prefix+'amplitude')

        
        #### define and array of the percentages to calculate
        percentages = np.linspace(0.01, 0.99, 101)

        ##### calcualte the confidence interval for all percentages
        conf_inter = result.conf_interval( 
            maxiter = 1000,
            sigmas = percentages
            )

        #### store the confidence intervales in list
        values = []
    
        for idx in range(self.cen_num):
            values.append(np.transpose(conf_inter[keys[idx]])[1])
            values[idx][values == -np.inf] = 0

        #### define a function for calculating the populations
        def Pop_calc(amps):
            pop_list = []
            for idx in range(len(amps)):
                pop_list.append(amps[idx]/np.sum(amps))
                
            return pop_list

        #### set the number of trials to run to calculate estimates
        num_trials = 10000

        estimates = []
        for idx_trial in range(num_trials):
            amps = []
            #### find random indexes to try
            for idx in range(self.cen_num):
                rand_index = np.random.randint(0, len(values[idx]) -1)

                #### pick number in range near index
                try:
                    amp_val = np.random.uniform(
                        values[idx][rand_index], (values[idx][rand_index+1])
                    )
                except:
                    amp_val = np.nan
                
                amps.append(amp_val)
                
            ### append the estimates with the current population
            estimates.append(Pop_calc(amps) )

        ### transpose for ease of use
        estimates = np.transpose(estimates)

        ### put the estimates, confidences, and average into dictionary
        dict = {}
        for idx_cen in range(self.cen_num):
            prefix = 'PopState_'+str(idx_cen)+'_'
            dict[prefix+'estimates'] =  estimates[idx_cen]
            dict[prefix+'mean'] = np.nanmean(estimates[idx_cen])
            dict[prefix+'std'] = np.nanstd(estimates[idx_cen])
            #### find the 95% confidence interval
            estimates_sorted = sorted(estimates[idx_cen])
            lower = int(len(estimates_sorted)*0.025)
            upper = int(len(estimates_sorted)*0.975)
            dict[prefix+'95_low'] = estimates_sorted[lower]
            dict[prefix+'95_high'] = estimates_sorted[upper]

        ### if the qubit frequency is passed as an argument, calculate temp
        ### only do if two levels, 3 level not well defined yet
        if self.cen_num ==2 and qubit_freq != None:
            pop0_arr = dict['PopState_0_estimates']
            pop1_arr = dict['PopState_1_estimates']
            
            #### set the number of trials to run to calculate estimates
            num_trials = 100000
            temps_list = []
            
            for idx_trial in range(num_trials):
                rand_index0 = np.random.randint(0, len(pop0_arr) )
                rand_index1 = np.random.randint(0, len(pop1_arr) )
                pop0 = pop0_arr[rand_index0]
                pop1 = pop1_arr[rand_index1]
                #### find temp with random values
                temp = Pop2Temp(pop0, pop1, qubit_freq)*1e3
                    
                ### append the estimates with the current population
                temps_list.append(temp)

            ### fill in dict with temp info
            prefix = 'temp_'
            dict[prefix+'estimates'] =  temps_list
            dict[prefix+'mean'] = np.nanmean(temps_list)
            dict[prefix+'std'] = np.nanstd(temps_list)
            #### find the 95% confidence interval
            temps_list_sorted = sorted(temps_list)
            lower = int(len(temps_list)*0.025)
            upper = int(len(temps_list)*0.975)
            dict[prefix+'95_low'] = temps_list[lower]
            dict[prefix+'95_high'] = temps_list[upper]
            dict['qubit_freq'] = qubit_freq

        #### if save_name give, save the data
        if save_name != None:
            try:
                file_name = self.path + '/' + save_name
            except:
                file_name = save_name
                
            file_name_h5 = file_name + '.h5'
            
            f = h5py.File(file_name_h5, 'w')
            for grp_name in dict:
                grp = f.create_group(grp_name)
                dset = grp.create_dataset(grp_name, data = dict[grp_name])
            f.close()

            #### save a histogram of the data
            for idx_cen in range(self.cen_num):
                prefix = 'PopState_'+str(idx_cen)+'_'
                estimates_curr = dict[prefix+'estimates']*100
                plt.figure(101)
                plt.hist(estimates_curr, 101)
                plt.xlabel('Populations State ' + str(idx_cen) +'(in %)')
                plot_name = file_name + '_PopState_'+str(idx_cen) + '.pdf'
                plt.savefig(plot_name)
                plt.clf()

            if self.cen_num ==2 and qubit_freq != None:
                prefix =  'temp_'
                estimates_curr = dict[prefix+'estimates']
                plt.figure(101)
                plt.hist(estimates_curr, 101)
                plt.xlabel('qubit temperature (mK)')
                plot_name = file_name + '_qubit_temperature.pdf'
                plt.title('qubit freq ' + str(qubit_freq) + 'MHz')
                plt.savefig(plot_name)
                plt.clf()
    
        return dict


    # ##############################################################
    # def calcTemp(self,
    #             result,
    #             save_dir,
    # ):
        
