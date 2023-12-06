import numpy as np
from sklearn.cluster import KMeans
from scipy.optimize import curve_fit
from matplotlib import pyplot as plt
from matplotlib.colors import LogNorm
from tqdm import tqdm

def plotCenter(iq_data, centers, fname, loc):
    # Plot the centers
    plt.figure()
    plt.scatter(iq_data[0,:], iq_data[1,:], s = 0.1)
    plt.scatter(centers[:,0], centers[:,1], s = 10, c = 'r')
    plt.xlabel('I')
    plt.ylabel('Q')
    plt.savefig(loc+fname+'_centers.png')
    plt.close()
    return 

def getCenters(iq_data, cen_num,**kwargs):
    # use kmeans to cluster the data
    kmeans = KMeans(n_clusters=cen_num, n_init = 7, max_iter = 10000).fit(iq_data.T)
    
    # Get the centers of the clusters
    centers = kmeans.cluster_centers_

    # Check if plot is given as input
    if 'plot' in kwargs:
        if kwargs['plot'] == True:
            #Check if fname and loc are given as input. If not give error
            if 'fname' not in kwargs:
                raise ValueError('fname is not given as input')
            if 'loc' not in kwargs:
                raise ValueError('loc is not given as input')
            # Plot the centers
            plotCenter(iq_data, centers, kwargs['fname'], kwargs['loc'])

    return centers

def createHistogram(iq_data, bin_size):
    hist2d = np.histogram2d(iq_data[0,:], iq_data[1,:], bins = bin_size)
    return hist2d

# Define the 2D Gaussian function
def gaussian_2d(points, A, x0, y0, sigma_x):
    x,y = points
    theta = 0
    sigma_y = sigma_x
    a = np.cos(theta)**2 / (2*sigma_x**2) + np.sin(theta)**2 / (2*sigma_y**2)
    b = -np.sin(2*theta) / (4*sigma_x**2) + np.sin(2*theta) / (4*sigma_y**2)
    c = np.sin(theta)**2 / (2*sigma_x**2) + np.cos(theta)**2 / (2*sigma_y**2)
    return A * np.exp(-(a*(x-x0)**2 + 2*b*(x-x0)*(y-y0) + c*(y-y0)**2))

# Define the function to fit the double 2D Gaussian. The number of gaussians is given by cen_num
def double_gaussian_2d(points, *p):
    no_of_params = 4
    cen_num = int(len(p)/no_of_params)
    result = np.zeros(points[0].shape)
    for i in range(cen_num):
        result += gaussian_2d(points, *p[i*no_of_params:(i+1)*no_of_params])
    return result

# Plot the 2d gaussians
def plotGaussians(gaussians, x_points, y_points, fname, loc):
    # Plot the 2d gaussians
    plt.figure()
    total_gaussian = np.zeros(gaussians[0].shape)
    for j in range(len(gaussians)): 
        total_gaussian += gaussians[j] 
    # Use imshow to plot the 2d gaussian i
    plt.imshow(total_gaussian, extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]], 
               origin = 'lower', norm=LogNorm())
    plt.colorbar()
    plt.xlabel('I')
    plt.ylabel('Q')
    plt.savefig(loc+fname+'_gaussianlog_'+str(j)+'.png', dpi = 300)
    plt.close()
    plt.imshow(total_gaussian, extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]], 
               origin = 'lower')
    plt.colorbar()
    plt.xlabel('I')
    plt.ylabel('Q')
    plt.savefig(loc+fname+'_gaussian_'+str(j)+'.png', dpi = 300)
    plt.close()

    # Plot each gaussian in a separate subplot
    plt.figure()
    for j in range(len(gaussians)):
        plt.subplot(1,len(gaussians),j+1)
        plt.imshow(gaussians[j], extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]], 
                   origin = 'lower', norm=LogNorm())
        plt.colorbar()
        plt.xlabel('I')
        plt.ylabel('Q')
    plt.savefig(loc+fname+'_gaussianlog_individual.png', dpi = 300)
    plt.close()
    return


def findGaussians(hist2d, centers, cen_num, return_bounds = False, 
    input_bounds = None, p_guess = None, **kwargs):

    gaussians = []

     # Fit the double 2D Gaussian to the histogram
    xedges = hist2d[1]
    yedges = hist2d[2]
    xedges_mid = (xedges[1:] + xedges[:-1])/2
    yedges_mid = (yedges[1:] + yedges[:-1])/2
    x_points = xedges_mid
    y_points = yedges_mid
    X, Y = np.meshgrid(xedges_mid, yedges_mid)

    # find the initial guess for the parameters
    p0 = []
    no_of_params = 4
    bounds = (np.full((cen_num*no_of_params), -np.inf), np.full((cen_num*no_of_params), np.inf))
    for j in range(cen_num):
        #Find the closes point to the center
        indx_x = np.argmin(np.abs(x_points - centers[j,0]))
        indx_y = np.argmin(np.abs(y_points - centers[j,1]))
        p0.append(hist2d[0][indx_x, indx_y])
        p0.append(centers[j,0])
        p0.append(centers[j,1])
        # Check if sigma is given as input in kwargs
        if 'sigma' in kwargs:
            p0.append(kwargs['sigma'][j])
        else:
            p0.append((x_points[-1] - x_points[0])/32)

        # p0.append((y_points[-1] - y_points[0])/32)
        # p0.append(0)
        # Set the bounds for the parameters

        bounds[0][j*no_of_params] = 0
        bounds[1][j*no_of_params] = np.inf #hist2d[0][indx_x, indx_y]*1.1
        bounds[0][j*no_of_params+1] = centers[j,0] - np.abs(centers[j,0])*0.05
        bounds[1][j*no_of_params+1] = centers[j,0] + np.abs(centers[j,0])*0.05
        bounds[0][j*no_of_params+2] = centers[j,1] - np.abs(centers[j,1])*0.05
        bounds[1][j*no_of_params+2] = centers[j,1] + np.abs(centers[j,1])*0.05
        
        # Check if sigma is given as input in kwargs
        if 'sigma' in kwargs:
            bounds[0][j*no_of_params+3] = kwargs['sigma'][j]*0.95
            bounds[1][j*no_of_params+3] = kwargs['sigma'][j]*1.05
        else:
            bounds[0][j*no_of_params+3] = 0
            bounds[1][j*no_of_params+3] = (x_points[-1] - x_points[0])/2

        # bounds[0][j*no_of_params+4] = y_points[1] - y_points[0]
        # bounds[1][j*no_of_params+4] = (y_points[-1] - y_points[0])/2
        # bounds[0][j*no_of_params+5] = -0.05
        # bounds[1][j*no_of_params+5] = 0.05
    
    if input_bounds is not None:
        if p_guess is not None:
            popt = curve_fit(
                double_gaussian_2d, (X.ravel(),Y.ravel()), 
                np.transpose(hist2d[0]).ravel(), p0 = p_guess, maxfev = 100000, 
                bounds = input_bounds, )[0]
        else:
            popt = curve_fit(
                double_gaussian_2d, (X.ravel(),Y.ravel()), 
                np.transpose(hist2d[0]).ravel(), p0 = p0, maxfev = 100000, 
                bounds = input_bounds, )[0]

    else:
        popt = curve_fit(
            double_gaussian_2d, (X.ravel(),Y.ravel()), 
            np.transpose(hist2d[0]).ravel(), p0 = p0, maxfev = 100000, 
            bounds = bounds, )[0]
 
    
    for j in range(cen_num):
        gaussians.append(gaussian_2d((X,Y), 
        *popt[j*no_of_params:(j+1)*no_of_params]).reshape(
                                hist2d[0][0].size,hist2d[0][0].size))
        # Use p0 to create the gaussians
        # gaussians.append(gaussian_2d((X,Y), *p0[j*6:(j+1)*6]).reshape(hist2d[0][0].size,hist2d[0][0].size))
    # Check if plot is given as input
    if 'plot' in kwargs:
        if kwargs['plot'] == True:
            #Check if fname and loc are given as input. If not give error
            if 'fname' not in kwargs:
                raise ValueError('fname is not given as input')
            if 'loc' not in kwargs:
                raise ValueError('loc is not given as input')
            # Plot the gaussians
            plotGaussians(gaussians, x_points, y_points, 
                kwargs['fname'], kwargs['loc'])
    if return_bounds:
        return gaussians, popt, x_points, y_points, bounds
    else: 
        return gaussians, popt, x_points, y_points

def calcPDF(gaussians):
    pdf = []
    total_gauss = 0
    for j in range(len(gaussians)):
        total_gauss += gaussians[j]
    for j in range(len(gaussians)):
        pdf.append(gaussians[j]/total_gauss)
    return pdf

def plotPDF(pdf, x_points, y_points, fname, loc):
    # Plot the pdf in a figure with one subplots for each gaussian
    plt.figure()
    for j in range(len(pdf)):
        plt.subplot(1,len(pdf),j+1)
        plt.imshow(pdf[j], extent = [x_points[0], x_points[-1], y_points[0], y_points[-1]], origin = 'lower')
        plt.colorbar()
        plt.xlabel('I')
        plt.ylabel('Q')
    plt.savefig(loc+fname+'_pdf.png', dpi = 300)
    plt.close()
    return

def calcNumSamplesInGaussian(hist2d, pdf, cen_num, **kwargs):
    num_samples_in_gaussian = np.zeros(cen_num)
    # Create expected_dist to store the expected distribution of each gaussian
    # The shape is (cen_num, hist2d[0].shape)
    expected_dist = np.zeros((cen_num,) + hist2d[0].shape)
    for i in range(cen_num):
        expected_dist[i] = pdf[i]*np.transpose(hist2d[0])
        num_samples_in_gaussian[i] = np.sum(expected_dist[i])
    
    # Check if plot is given as input
    if 'plot' in kwargs:
        if kwargs['plot'] == True:
            #Check if fname, loc, x_points and y_points are given as input. If not give error
            if 'fname' not in kwargs:
                raise ValueError('fname is not given as input')
            if 'loc' not in kwargs:
                raise ValueError('loc is not given as input')
            if 'x_points' not in kwargs:
                raise ValueError('x_points is not given as input')
            if 'y_points' not in kwargs:
                raise ValueError('y_points is not given as input')
            # Plot the data with each center having a different subplot
            plt.figure()
            for i in range(cen_num):
                plt.subplot(1,cen_num,i+1)
                plt.imshow(expected_dist[i], 
                           extent = [
                           kwargs["x_points"][0], kwargs["x_points"][-1], 
                           kwargs["y_points"][0], kwargs["y_points"][-1]
                           ], 
                           origin = 'lower')
                plt.colorbar()
                plt.xlabel('I')
                plt.ylabel('Q')
            plt.savefig(kwargs["loc"]+kwargs["fname"]+
                    '_expected_dist.png', dpi = 300)  
            plt.close()
        
    return num_samples_in_gaussian
            
def calcNumSamplesInGaussianSTD(hist2d, pdf, cen_num, **kwargs):
    num_samples_in_gaussian_std = np.zeros(cen_num)
    expected_dist_std = np.zeros((cen_num,) + hist2d[0].shape)
    for i in range(cen_num):
        expected_dist_std[i] = pdf[i]*(1-pdf[i])*np.transpose(hist2d[0])
        num_samples_in_gaussian_std[i] = np.sqrt(np.sum(expected_dist_std[i]))
            
    # Check if plot is given as input
    if 'plot' in kwargs:
        if kwargs['plot'] == True:
            #Check if fname, loc, x_points and y_points are given as input. If not give error
            if 'fname' not in kwargs:
                raise ValueError('fname is not given as input')
            if 'loc' not in kwargs:
                raise ValueError('loc is not given as input')
            if 'x_points' not in kwargs:
                raise ValueError('x_points is not given as input')
            if 'y_points' not in kwargs:
                raise ValueError('y_points is not given as input')
            # Plot the data with each center having a different subplot
            plt.figure()
            for i in range(cen_num):
                plt.subplot(1,cen_num,i+1)
                plt.imshow(expected_dist_std[i], 
                           extent = [
                           kwargs["x_points"][0], kwargs["x_points"][-1], 
                           kwargs["y_points"][0], kwargs["y_points"][-1]
                           ], 
                           origin = 'lower')
                plt.colorbar()
                plt.xlabel('I')
                plt.ylabel('Q')
            plt.savefig(kwargs["loc"]+kwargs["fname"]+
                '_expected_dist_std.png', dpi = 300)  
            plt.close()
    
    return num_samples_in_gaussian_std

def calcProbability(
            num_samples_in_gaussian, num_samples_in_gaussian_std, cen_num
            ):
    probability = np.zeros(cen_num)
    std_probability = np.zeros(cen_num)
    total_samples = np.sum(num_samples_in_gaussian)
    for i in range(cen_num):
        probability[i] = num_samples_in_gaussian[i]/total_samples
        std_probability[i] = num_samples_in_gaussian_std[i]/total_samples

    return probability, std_probability

def findProb(iq_data, cen_num, **kwargs):
    
    # Check if plot is given as input
    if 'plot' in kwargs:
        plot = kwargs['plot']
        # Check if fname and loc is given as input. If not raise error
        if 'fname' in kwargs and 'loc' in kwargs:
            fname = kwargs['fname']
            loc = kwargs['loc']
        else:
            raise ValueError("fname and loc should be given as input")
    else:
        plot = False

    # Get centers of the data
    centers = getCenters(iq_data, cen_num, plot= plot, fname = fname, loc = loc)

    # Converting the data to 2d histogram
    # Check if bin_size is given as input
    if 'bin_size' in kwargs:
        bin_size = kwargs['bin_size']
    else:
        bin_size = 51
    hist2d = createHistogram(iq_data, bin_size)

    # Find the fit parameters for the double 2D Gaussian
    gaussians, popt, x_points, y_points = findGaussians(
        hist2d, centers, cen_num, plot= plot, fname = fname, loc = loc)
    
    # Calculate the probability function
    pdf = calcPDF(gaussians)
    if plot:
        plotPDF(pdf, x_points, y_points, fname, loc)
    
    # Calculate the extected probability
    num_samples_in_gaussian = calcNumSamplesInGaussian(
        hist2d, pdf, cen_num, plot = plot, fname = fname, 
        loc = loc, x_points = x_points, y_points = y_points)
    
    num_samples_in_gaussian_std = calcNumSamplesInGaussianSTD(
        hist2d, pdf, cen_num, plot = plot, fname = fname,
        loc = loc, x_points = x_points, y_points = y_points)

    probability, std_probability = calcProbability(
        num_samples_in_gaussian, num_samples_in_gaussian_std,cen_num)

    return probability, std_probability


def findTempr(probability, std_probability, f1):
    h = 6.62607015e-34
    kb = 1.380649e-23
    # Calculate the temperature between state 0 and 1
    T = -(h*f1/kb) /np.log(probability[0]/probability[1])
    # Calculate the uncertainty in the temperature
    u_T = std_probability[0]**2*(T/(probability[0]*np.log(probability[0]/probability[1])))**2 \
        + std_probability[1]**2*(T/(probability[1]*np.log(probability[0]/probability[1])))**2 
    
    return np.abs(T), np.sqrt(u_T)


def oendim_projection(iq_data):
    # Calculate the center
    # Rotate the data
    # Project in 1d dimension
    # Return the data
    return