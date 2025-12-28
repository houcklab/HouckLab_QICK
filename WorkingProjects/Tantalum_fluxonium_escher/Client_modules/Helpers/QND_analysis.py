import numpy as np
import matplotlib.pyplot as plt
import h5py
from tqdm import tqdm
# Set default font size
# plt.rcParams.update({'font.size': 10})
# Add latex support
#plt.rc('text', usetex=True)
# plt.rc('font', family='serif')

import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.SingleShot_ErrorCalc_2 as sse2

confidence_selection = 0.99

def QND_analysis(i_0_arr, q_0_arr, i_1_arr, q_1_arr, centers, 
    confidence_selection = 0.99):
    cen_num = 2

    ##### loop over the time steps
    # The format in which the data is going to be stored is
    # state0_prob = [P(0|0), P(1|0)]
    # state1_prob = [P(0|1), P(1|1)]
    state0_probs = []
    state0_probs_err = []
    state1_probs = []
    state1_probs_err = []
    
    #### define new arrays
    i_arr = i_0_arr
    q_arr = q_0_arr
    # Changing the way data is stored for kmeans
    iq_data = np.stack((i_arr, q_arr), axis = 0)
    
    # Converting the data to 2d histogram
    # Check if bin_size is given as input
    bin_size = 101
    hist2d = sse2.createHistogram(iq_data, bin_size)
    
    # Find the fit parameters for the double 2D Gaussian
    gaussians, popt, x_points, y_points, bounds = sse2.findGaussians(
        hist2d, centers, cen_num, plot = False, 
        return_bounds = True, 
        fname = "Wait_Arr_0_0", loc = "plots_QND/")
    
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
    i0_0_shots = [] # initial shots if in state 0
    q0_0_shots = [] # initial shots if in state 0
    
    i0_1_shots = [] # initial shots if in state 1
    q0_1_shots = [] # initial shots if in state 1
    
    i0_shots = [] # final shots if initially in state 0
    q0_shots = [] # final shots if initially in state 0
    
    i1_shots = [] # final shots if initially in state 1
    q1_shots = [] # final shots if initially in state 1
    
    for idx in range(len(sorted_shots_0)):
        if sorted_shots_0[idx] > confidence_selection:
            i0_0_shots.append(i_0_arr[idx])
            q0_0_shots.append(q_0_arr[idx])
    
            i0_shots.append(i_1_arr[idx])
            q0_shots.append(q_1_arr[idx])
        if sorted_shots_1[idx] > confidence_selection:
            i0_1_shots.append(i_0_arr[idx])
            q0_1_shots.append(q_0_arr[idx])
    
            i1_shots.append(i_1_arr[idx])
            q1_shots.append(q_1_arr[idx])
    
#    ##### plot the shots
#    plt.figure()
#    plt.plot(i_0_arr, q_0_arr, 'm.', alpha = 0.2)
#    plt.plot(i0_0_shots, q0_0_shots, 'r.')
#    plt.plot(i0_1_shots, q0_1_shots, 'b.')
#    
#    plt.xlabel('I (arb. units)')
#    plt.ylabel('Q (arb. units)')
#    
#    plt.show()
#    
#    ###
    
    ##### use the sorted shots
    for idx_cen in range(2):
        if idx_cen == 0:
            iq_data = np.stack((i0_shots, q0_shots), axis = 0)
        if idx_cen == 1:
            iq_data = np.stack((i1_shots, q1_shots), axis = 0)
    
        hist2d = sse2.createHistogram(iq_data, bin_size)
        
        # Find the fit parameters for the double 2D Gaussian
        gaussians, popt, x_points, y_points = sse2.findGaussians(
            hist2d, centers, cen_num, plot = False, 
            input_bounds = bounds,
            sigma = sigma,
            fname = "Wait_Arr_0_0", loc = "plots_QND/")
        
        
        # Extract the sigma 
        sigma = []
        for i in range(cen_num):
            sigma.append(popt[i*4+3])
        
        # Calculate the probability function
        pdf = sse2.calcPDF(gaussians)
        
        # Calculate the extected probability
        num_samples_in_gaussian = sse2.calcNumSamplesInGaussian(
            hist2d, pdf, cen_num, plot = False, 
            fname = "Wait_Arr_0_1", loc = "plots_QND/", 
            x_points = x_points, y_points = y_points)
        
        num_samples_in_gaussian_std = sse2.calcNumSamplesInGaussianSTD(
            hist2d, pdf, cen_num, plot = False, 
            fname = "Wait_Arr_0_1",loc = "plots_QND/", 
            x_points = x_points, y_points = y_points)
        
        probability, std_probability = sse2.calcProbability(
            num_samples_in_gaussian, num_samples_in_gaussian_std,cen_num)
    
        if idx_cen == 0:
            state0_probs.append(probability[0])
            state0_probs.append(probability[1])
            state0_probs_err.append(std_probability[0])
    
        if idx_cen == 1:
            state1_probs.append(probability[0])
            state1_probs.append(probability[1])
            state1_probs_err.append(std_probability[0])

    ### return all values
    return (state0_probs, state0_probs_err, len(i0_shots), 
            state1_probs, state1_probs_err, len(i1_shots),
            i0_shots, q0_shots, i1_shots, q1_shots)


