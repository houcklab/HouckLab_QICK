import numpy as np
from scipy.linalg import sqrtm

def mahalanobis_distance(mu1, sigma1, mu2, sigma2):
    mean_diff = mu1 - mu2
    cov_avg = (sigma1 + sigma2) / 2
    inv_cov_avg = np.linalg.inv(cov_avg)
    return np.sqrt(mean_diff.T @ inv_cov_avg @ mean_diff)

def bhattacharyya_distance(mu1, sigma1, mu2, sigma2):
    mean_diff = mu1 - mu2
    cov_avg = (sigma1 + sigma2) / 2
    inv_cov_avg = np.linalg.inv(cov_avg)
    term1 = 0.125 * mean_diff.T @ inv_cov_avg @ mean_diff
    term2 = 0.5 * np.log(np.linalg.det(cov_avg) / np.sqrt(np.linalg.det(sigma1) * np.linalg.det(sigma2)))
    return term1 + term2

def kl_divergence(mu1, sigma1, mu2, sigma2):
    inv_sigma2 = np.linalg.inv(sigma2)
    mean_diff = mu2 - mu1
    term1 = np.trace(inv_sigma2 @ sigma1)
    term2 = mean_diff.T @ inv_sigma2 @ mean_diff
    term3 = np.log(np.linalg.det(sigma2) / np.linalg.det(sigma1))
    return 0.5 * (term1 + term2 - len(mu1) + term3)

def hellinger_distance(mu1, sigma1, mu2, sigma2):
    mean_diff = mu1 - mu2
    cov_avg = (sigma1 + sigma2) / 2
    inv_cov_avg = np.linalg.inv(cov_avg)
    term1 = -0.125 * mean_diff.T @ inv_cov_avg @ mean_diff
    term2 = 0.5 * np.log(np.linalg.det(cov_avg) / np.sqrt(np.linalg.det(sigma1) * np.linalg.det(sigma2)))
    return np.sqrt(1 - np.exp(term1 + term2))

# def brute(amp1, mu1, sigma1, amp2, mu2, sigma2):