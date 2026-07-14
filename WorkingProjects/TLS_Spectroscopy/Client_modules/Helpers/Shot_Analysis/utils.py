import numpy as np
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture as GMM
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.Shot_Analysis import constants

# Get the centers using GMM
def get_GMM_centers(i_arr, q_arr, cen_num, centers = None):
    """
    Get the centers using GMM
    """
    # Stack the datac
    iq_data = np.stack((i_arr, q_arr), axis = 1)

    # Fit the GMM
    gmm = GMM(n_components = cen_num, covariance_type = 'tied', means_init = centers).fit(iq_data)

    # Get the centers
    centers = gmm.means_

    return centers

# Get the centers using KMeans
def get_kmeans_centers(i_arr, q_arr, cen_num, centers = None):
    """
    Get the centers using KMeans
    """
    # Stack the data
    iq_data = np.stack((i_arr, q_arr), axis=1)

    # Fit the KMeans
    if centers is None:
        kmeans = KMeans(n_clusters = cen_num, n_init = 10).fit(iq_data)
    else:
        kmeans = KMeans(n_clusters = cen_num, init = centers, n_init = 1).fit(iq_data)

    # Get the centers
    centers = kmeans.cluster_centers_

    return centers

# Calculate temperature from population and frequency
def calc_tempr(pop0, pop1, freq):
    """
    Calculate the temperature of the two populations
    pop0 : population of lower energy state
    pop1 : population of the higher energy state
    freq : frequency of the energy gap between the two states. In MHz
    """
    temp = -1*constants.hbar * freq*1e6 * 2 *np.pi / (constants.kb * np.log(pop1 / pop0))
    return temp

# Calculate temperature from population and frequency
def calc_tempr_mat(pop_arr, freq_mat):
    """
    Calculate the temperature matrix of n populations
    pop_arr : array of n populations
    freq_mat : n x n matrix of frequencies between each state
    """
    tempr_mat = np.zeros((len(pop_arr),len(pop_arr)))
    for i in range(len(pop_arr)):
        for j in range(len(pop_arr)):
            if i == j:
                pass
            else:
                tempr_mat[i,j] = calc_tempr(pop_arr[i], pop_arr[j], freq_mat[i,j])
    return tempr_mat
