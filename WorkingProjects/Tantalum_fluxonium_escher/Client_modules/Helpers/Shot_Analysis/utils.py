import numpy as np
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture as GMM

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