import numpy as np
import matplotlib.pyplot as plt
import h5py
from tqdm import tqdm
from scipy.optimize import curve_fit
# Set default font size
plt.rcParams.update({'font.size': 10})

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers import SingleShot_ErrorCalc_2 as sse2

# import SingleShot_ErrorCalc_2 as sse2

from scipy.integrate import odeint, solve_ivp, solve_bvp
from lmfit import minimize, Parameters, Parameter, report_fit
from scipy.integrate import odeint

############
### define basic constants
import scipy as sp
hbar = sp.constants.hbar ###1.054e-34
kb = sp.constants.k

##### define a class for fitting and storing the gamma matrix

class GammaFit:
    def __init__(self, data, freq_01 = 0.815e9, verbose = False):
        #### extract out the data
        self.i_0_arr = np.array(data[0])
        self.i_1_arr = np.array(data[1])
        self.q_0_arr = np.array(data[2])
        self.q_1_arr = np.array(data[3])
        self.wait_arr = np.array(data[4])
        self.freq_01 = freq_01
        #### write local arrays
        i_0_arr  = self.i_0_arr 
        i_1_arr  = self.i_1_arr 
        q_0_arr  = self.q_0_arr 
        q_1_arr  = self.q_1_arr 
        wait_arr = self.wait_arr

        self._sortShots()
        self._calcGammaMat()

    def _sortShots(self):
        
        ##### loop over the time steps
        state0_probs = []
        state0_probs_err = []
        state1_probs = []
        state1_probs_err = []
        self.centers = []
        
        for idx_t in tqdm(range(len(self.wait_arr))):

            #### define new arrays for each time slice
            i_arr = self.i_0_arr[idx_t]
            q_arr = self.q_0_arr[idx_t]
            # Changing the way data is stored for kmeans
            iq_data = np.stack((i_arr, q_arr), axis = 0)

            # Get centers of the data
            cen_num = 2
            if idx_t == 0:
                self.centers.append(sse2.getCenters(iq_data, cen_num))
            else:
                self.centers.append(sse2.getCenters(iq_data, cen_num, init_guess=self.centers[0]))

            #### bin into a histogram
            bin_size = 51
            hist2d = sse2.createHistogram(iq_data, bin_size)

            # Find the fit parameters for the double 2D Gaussian
            gaussians, popt, x_points, y_points, bounds = sse2.findGaussians(
                hist2d, self.centers[idx_t], cen_num, plot= False,
                return_bounds = True,
                fname = "Wait_Arr_0_0", loc = "plots/")

            #### extract the fit parameters
            self.popt = popt

            ##############################
            #### create bounds given current fit
            lower_bound = np.zeros(len(popt))
            upper_bound = np.zeros(len(popt))
            p_guess = popt

            for idx in range(len(popt)):

                lower_bound[idx] = popt[idx] - 0.000001
                upper_bound[idx] = popt[idx] + 0.000001

                if idx == 0:
                    lower_bound[idx] = 0
                    upper_bound[idx] = np.inf

                if idx == 4:
                    lower_bound[idx] = 0
                    upper_bound[idx] = np.inf

            bounds = [lower_bound, upper_bound]
            ##############################

            # Extract the sigma
            sigma = []
            for i in range(cen_num):
                sigma.append(popt[i*4+3])
            
            # Calculate the probability function
            pdf = sse2.calcPDF(gaussians)
            
            #### find the points where probabilites change
            sorted_shots_0 = []
            sorted_shots_1 = []
            
            for idx_shot in range(len(i_arr)):
                i_val = i_arr[idx_shot]
                q_val = q_arr[idx_shot]
                
                i_idx = np.argmin(np.abs(x_points - i_val))
                q_idx = np.argmin(np.abs(y_points - q_val))
            
                sorted_shots_0.append(pdf[0][i_idx, q_idx])
                sorted_shots_1.append(pdf[1][i_idx, q_idx])
            
            ####
            i0_shots = []
            q0_shots = []
            
            i1_shots = []
            q1_shots = []

            confidence = 0.95
            
            for idx in range(len(sorted_shots_0)):
                if sorted_shots_0[idx] > confidence:
                    i0_shots.append(self.i_1_arr[idx_t][idx])
                    q0_shots.append(self.q_1_arr[idx_t][idx])
                if sorted_shots_1[idx] > confidence:
                    i1_shots.append(self.i_1_arr[idx_t][idx])
                    q1_shots.append(self.q_1_arr[idx_t][idx])
           
            ##### use the sorted shots
            for idx_cen in range(2):
                if idx_cen == 0:
                    iq_data = np.stack((i0_shots, q0_shots), axis = 0)
                if idx_cen == 1:
                    iq_data = np.stack((i1_shots, q1_shots), axis = 0)
        
                hist2d = sse2.createHistogram(iq_data, bin_size)
                
                # Find the fit parameters for the double 2D Gaussian
                gaussians, popt, x_points, y_points = sse2.findGaussians(
                    hist2d, self.centers[idx_t], cen_num, plot= False,
                    input_bounds = bounds, p_guess = p_guess,
                    sigma = sigma,
                    fname = "Wait_Arr_0_0", loc = "plots/")
                
                # Extract the sigma 
                sigma = []
                for i in range(cen_num):
                    sigma.append(popt[i*4+3])
                
                # Calculate the probability function
                pdf = sse2.calcPDF(gaussians)
                
                # Calculate the extected probability
                num_samples_in_gaussian = sse2.calcNumSamplesInGaussian(
                    hist2d, pdf, cen_num, plot = False, 
                    fname = "Wait_Arr_0_1", loc = "plots/", 
                    x_points = x_points, y_points = y_points)
                
                num_samples_in_gaussian_std = sse2.calcNumSamplesInGaussianSTD(
                    hist2d, pdf, cen_num, plot = False, 
                    fname = "Wait_Arr_0_1",loc = "plots/", 
                    x_points = x_points, y_points = y_points)
                
                probability, std_probability = sse2.calcProbability(
                    num_samples_in_gaussian, num_samples_in_gaussian_std,cen_num)
            
                if idx_cen == 0:
                    state0_probs.append(probability[0])
                    state0_probs_err.append(std_probability[0])
                if idx_cen == 1:
                    state1_probs.append(probability[0])
                    state1_probs_err.append(std_probability[0])
         
        self.pops_vec = np.full([cen_num, cen_num, len(self.wait_arr)], np.nan)
        self.pops_err_vec = np.full([cen_num, cen_num, len(self.wait_arr)], np.nan)

        for idx_t in range(len(self.wait_arr)):
            for idx_cen in range(cen_num):
                self.pops_vec[0][0][idx_t] = state0_probs[idx_t]
                self.pops_vec[0][1][idx_t] = 1 - state0_probs[idx_t]
        
                self.pops_vec[1][0][idx_t] = state1_probs[idx_t]
                self.pops_vec[1][1][idx_t] = 1 - state1_probs[idx_t]
        
                #### fill in the errors
                self.pops_err_vec[0][0][idx_t] = state0_probs_err[idx_t]
                self.pops_err_vec[0][1][idx_t] = state0_probs_err[idx_t]
        
                self.pops_err_vec[1][0][idx_t] = state1_probs_err[idx_t]
                self.pops_err_vec[1][1][idx_t] = state1_probs_err[idx_t]

        ### if cen_num = 2 just use exponential fil to get an estimate of T1 which will be used in the AutoSweep
        if cen_num == 2:
            # check which has the higher contrast
            idx = np.argmax(np.array([np.ptp(self.pops_vec[0][0][:]), np.ptp(self.pops_vec[1][0][:])]))
            pop_curr = self.pops_vec[idx][0][:]
            # Fit to data
            a_guess = pop_curr[0] - pop_curr[-1]
            T1_guess = np.max(self.wait_arr) / 4.0
            c_guess = pop_curr[-1]
            guess = [a_guess, T1_guess, c_guess]

            def expFit(x, a, T1, c):
                return a * np.exp(-1 * x / T1) + c

            popt, pcov = curve_fit(expFit, self.wait_arr, pop_curr, p0=guess)
            self.T1_guess = popt[1]
    ##########
    def Pops_ode(self, pops, t, params):
        """
        define the system of ODEs
        """
        P0 = pops[0]
        P1 = pops[1]

        try:
            g01 = params['g01'].value
            g10 = params['g10'].value

        except KeyError:
            g01, g10 = params

        ### model equaitons
        dP0dt = -1 * (g01) * P0 + g10 * P1
        dP1dt = g01 * P0 + -1 * (g10) * P1

        return [dP0dt, dP1dt]

    ##########
    def g(self, t, pops_init, params):
        """
        solution to the ODE with initial condition P_i[0] = pops_init[i]
        """
        x = odeint(self.Pops_ode, pops_init, t, args=(params,))

        return x

    def _calcGammaMat(self):

        pops_arr = self.pops_vec
        pops_arr_err = self.pops_err_vec


        t_arr = self.wait_arr

        P0_0_data = pops_arr[0][0]
        P0_1_data = pops_arr[0][1]
        
        P1_0_data = pops_arr[1][0]
        P1_1_data = pops_arr[1][1]
        
        P0_0_data_err = pops_arr_err[0][0]
        P0_1_data_err = pops_arr_err[0][1]
        
        P1_0_data_err = pops_arr_err[1][0]
        P1_1_data_err = pops_arr_err[1][1]
        
        def residual(params, t, data, data_err):
            """
            compute the residual between data and fit
            """
        
            #### create models
            pops0_init = params['P0_0_init'].value, params['P0_1_init'].value
            pops1_init = params['P1_0_init'].value, params['P1_1_init'].value
        
            pops0_err = [P0_0_data_err, P0_1_data_err]
            pops1_err = [P1_0_data_err, P1_1_data_err]
        
            model0 = self.g(t, pops0_init, params)
            model1 = self.g(t, pops1_init, params)
        
            P0_0_model = np.array(model0[:,0])
            P0_1_model = np.array(model0[:,1])
        
            P1_0_model = np.array(model1[:,0])
            P1_1_model = np.array(model1[:,1])
        
            P0_0_resid = ((P0_0_model - P0_0_data)/P0_0_data_err).ravel()
            P0_1_resid = ((P0_1_model - P0_1_data)/P0_1_data_err).ravel()
        
            P1_0_resid = ((P1_0_model - P1_0_data)/P1_0_data_err).ravel()
            P1_1_resid = ((P1_1_model - P1_1_data)/P1_1_data_err).ravel()
         
            return P0_0_resid, P0_1_resid, P1_0_resid, P1_1_resid
        
        params = Parameters()
       
        params.add('g01', value = 1e-2, min = 1e-9, max = 0.1)
        params.add('g10', value = 1e-2, min = 1e-9, max = 0.1)
        
        params.add('P0_0_init',P0_0_data[0],vary = False)
        params.add('P0_1_init',P0_1_data[0],vary = False)
        
        params.add('P1_0_init',P1_0_data[0],vary = False)
        params.add('P1_1_init',P1_1_data[0],vary = False)
        
        P_init = [
            params['P0_0_init'].value, 
            params['P0_1_init'].value,
            params['P1_0_init'].value, 
            params['P1_1_init'].value
            ]
        
        data = [P0_0_data, P0_1_data, P1_0_data, P1_1_data]
        data_err = [P0_0_data_err, P0_1_data_err, P1_0_data_err, P1_1_data_err]
        
        result_shgo = minimize(residual, params, args = (t_arr, data, data_err), 
            method = 'ampgo')
        params_update = result_shgo.params
        
        result = minimize(residual, params_update, args = (t_arr, data, data_err), 
            method = 'leastsq')
       
        result.params.pretty_print(colwidth=11)

        
        #### find the temperature values
        #### hard coded for now, need to change
        temp_01 = self.gamma2temp(
            self.freq_01, result.params['g01'].value, result.params['g10'].value
            )
        
        self.T1 = (1 / (result.params['g01'].value + result.params['g10'].value))
        
        #### calculate the propgated error
        self.temp = temp_01
        g01 = result.params['g01'].value
        err01 = result.params['g01'].stderr
        g10 = result.params['g10'].value
        err10 = result.params['g10'].stderr
        
        self.temp_err = self.propTempErr(err01, err10, self.temp, g01, g10)
        self.T1_err = self.propT1Err(err01, err10, g01, g10)
        
        ###
        self.temp_str = ('Temperature estimate: ' + 
            str(np.round(temp_01*1e3, 1)) +' +/- ' +
            str(np.round(self.temp_err*1e3, 1))+ ' mK')
        self.T1_str = ('State lifetime: T1 = ' + 
            str(np.round(self.T1, 1)) + ' +/- ' +
            str(np.round(self.T1_err, 1))+ ' us')
        
        print(self.temp_str)
        print(self.T1_str)
        
        ##### create the fit
        P0_init = [
            params['P0_0_init'].value, 
            params['P0_1_init'].value,
            ]
        
        P1_init = [
            params['P1_0_init'].value, 
            params['P1_1_init'].value
        ]
        
        data0_fitted = self.g(t_arr, P0_init, result.params)
        data1_fitted = self.g(t_arr, P1_init, result.params)
        data_fitted = [data0_fitted, data1_fitted]
        
        data_plot = [
            [P0_0_data, P0_1_data], 
            [P1_0_data, P1_1_data]
        ]
        data_err_plot = [
            [P0_0_data_err, P0_1_data_err], 
            [P1_0_data_err, P1_1_data_err]
        ]

        ### save the imporant variables
        self.result = result
        self.data_fitted = data_fitted
        self.data_plot = [
            [P0_0_data, P0_1_data], 
            [P1_0_data, P1_1_data]
            ]
        self.data_err_plot = [
            [P0_0_data_err, P0_1_data_err], 
            [P1_0_data_err, P1_1_data_err]
            ]
        
    #########
    def plotBlobs(self):
        ### plot an example of the blobs with coresponding centers
        colors = ['b', 'r', 'm', 'c', 'g']
        cen_num = 2
        alpha_val = 0.1
        
        fig, axs = plt.subplots(1,1,figsize=(10, 8) )

        ### plot inital measurement
        axs.plot(self.i_arr_full, self.q_arr_full, 'm.', alpha = alpha_val)
       
        axs.set_title('Intial measurement')
        axs.set_xlabel('I (arb. units)')
        axs.set_ylabel('Q (arb. units)')
        
        xlim = axs.get_xlim()
        ylim = axs.get_ylim()

        gauss0 = self.popt[:4]
        gauss1 = self.popt[4:]
        
        for idx_sig in range(3):
            axs.add_patch(
                 plt.Circle((gauss0[1], gauss0[2]), gauss0[3]*idx_sig, 
                             color = 'k', fill=False, zorder=2, ls = '--')
                            )
            axs.add_patch(
                 plt.Circle((gauss1[1], gauss1[2]), gauss0[3]*idx_sig, 
                             color = 'k', fill=False, zorder=2, ls = '--')
                            )

    #########
    def plotlifetime(self):
        #### plot the data and fits
        colors = ['b', 'r', 'm', 'c', 'g']
        cen_num = 2
        
        fig, axs = plt.subplots(2,1,figsize=(10, 8) )
        
        for idx_plot in range(2):
            for idx_blob in range(cen_num):
                pops_list = self.data_plot[idx_plot][idx_blob]
                pops_list_err = self.data_err_plot[idx_plot][idx_blob]
        
            
                axs[idx_plot].errorbar(
                    self.wait_arr, pops_list, yerr = pops_list_err,
                    color = colors[idx_blob], ls = 'none', marker = 'o',
                    label = 'state '+str(idx_blob)) 
            
            for idx_fit in range(cen_num):
                axs[idx_plot].plot(
                    self.wait_arr, self.data_fitted[idx_plot][:, idx_fit], 
                    '-', color = 'k')
            
            axs[idx_plot].set_xlabel('time (us)')
            axs[idx_plot].set_ylabel('populaiton')
            axs[idx_plot].set_title('Starting state ' + str(idx_plot))
        
        fig.suptitle(self.temp_str + '\n' + self.T1_str)
        
        plt.legend()
        plt.tight_layout()

    ### define function to convert gamma values into temperature
    def gamma2temp(self, freq, gamma1, gamma2):
        temp = (hbar * freq)/(kb) * (1/(np.log(gamma2 / gamma1))) *2*np.pi
        return np.abs(temp)
    
    def propTempErr(self, err01, err10, temp, g01, g10):
        propErr_1 = err01**2 * ( temp / (g01 *np.log10(g01/g10 ) ))**2
        propErr_2 = err10**2 * ( temp / (g10 *np.log10(g01/g10 ) ))**2
        propErr = np.sqrt(propErr_1 + propErr_2)
        return propErr
    
    def propT1Err(self, err01, err10, g01, g10):
        propErr2 = (err01**2 + err10**2) / ( g01 + g10 )**4
        return np.sqrt(propErr2)


    
####### test it out!!!
def main():
    # Load data from h5 file. Use this get centers and sigma
    loc = 'data/'
    #fname = "T1_PS_temp_15_2023_11_16_12_20_12_data.h5"
    fname = "T1_PS_temp_25_2023_11_16_14_57_08_data.h5"
    f = h5py.File(loc + fname, 'r')

    # Get all the keys in the file
    keys = list(f.keys())

    print(keys)

    ### Get the data from the keys :
    ### 'i_0_arr', 'i_1_arr', 'q_0_arr', 'q_1_arr', 'wait_arr'
    i_0_arr = np.array(f['i_0_arr'])
    i_1_arr = np.array(f['i_1_arr'])
    q_0_arr = np.array(f['q_0_arr'])
    q_1_arr = np.array(f['q_1_arr'])
    wait_arr = np.array(f['wait_vec'])

    data = [
        i_0_arr,
        i_1_arr,
        q_0_arr,
        q_1_arr,
        wait_arr
    ]

    gammafit = GammaFit(data)
    gammafit.plotlifetime()

    plt.show()
