#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from STFU.Client_modules.Calib_escher.initialize import *
from STFU.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from STFU.Client_modules.Experiments.mSpecSlice import SpecSlice
from STFU.Client_modules.Experiments.mT1_PS import T1_PS
from matplotlib import pyplot as plt
import datetime

from sklearn.cluster import KMeans
from scipy.optimize import curve_fit

import socket

HOST = "Marvin"  # The server's hostname or IP address
PORT = 4000  # The port used by the server

# from STFU.Client_modules.PythonDrivers.LS370 import *

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF3SC1\\"



#### create timestamp for when scan starts
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
datestring = datetimenow.strftime("%Y_%m_%d")

#### create file path for the processed data
path = "TempSweeps_T1_PS_processed"
prefix='data'
##### check to see if the file path exists
DataFolderBool = Path(outerFolder + path).is_dir()
if DataFolderBool == False:
    os.mkdir(outerFolder + path)
DataSubFolderBool = Path(os.path.join(outerFolder + path, path + "_" + datestring)).is_dir()
if DataSubFolderBool == False:
    os.mkdir(os.path.join(outerFolder + path, path + "_" + datestring))

processed_name = os.path.join(outerFolder + path, path + "_" + datestring,
                          path + "_" + datetimestring + "_" + prefix + '.npz')

processed_fig_name = os.path.join(outerFolder + path, path + "_" + datestring,
                          path + "_" + datetimestring + "_" + prefix + '.png')
########################################################################################################################
### Define Functions that will be used for data processing and plotting
#############
def SelectShots(shots_1_i, shots_1_q, shots_0_i, shots_0_q, x, y, x_less=True, y_less=True):
    ### selects out shots and defines based on left being 1 and right being 2
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])

    if x_less == True and y_less == True:
        for i in range(len(shots_0_i)):
            if shots_0_i[i] < x and shots_0_q[i] < y:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
    elif x_less == True and y_less == False:
        for i in range(len(shots_0_i)):
            if shots_0_i[i] < x and shots_0_q[i] > y:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
    elif x_less == False and y_less == True:
        for i in range(len(shots_0_i)):
            if shots_0_i[i] > x and shots_0_q[i] < y:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
    elif x_less == False and y_less == False:
        for i in range(len(shots_0_i)):
            if shots_0_i[i] > x and shots_0_q[i] > y:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

    return shots_1_iSel, shots_1_qSel


############
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot


############
def popCalc(i_PP_1, q_PP_1, i_PP_2, q_PP_2, angle, threshold):
    #### want to remove any nan elements from the list
    i_PP_1 = i_PP_1[~np.isnan(i_PP_1)]
    q_PP_1 = q_PP_1[~np.isnan(q_PP_1)]
    i_PP_2 = i_PP_2[~np.isnan(i_PP_2)]
    q_PP_2 = q_PP_2[~np.isnan(q_PP_2)]

    i_PP_1_rot, q_PP_1_rot = rotateBlob(i_PP_1, q_PP_1, angle)
    i_PP_2_rot, q_PP_2_rot = rotateBlob(i_PP_2, q_PP_2, angle)

    populations = np.zeros(4)
    for i in range(len(i_PP_1_rot)):
        if i_PP_1_rot[i] < threshold:
            populations[0] += 1  ### blob1_g
        elif i_PP_1_rot[i] > threshold:
            populations[1] += 1  ### blob1_e

    for i in range(len(i_PP_2_rot)):
        if i_PP_2_rot[i] < threshold:
            populations[2] += 1  ### blob2_g
        elif i_PP_2_rot[i] > threshold:
            populations[3] += 1  ### blob2_e

    populations[0] = populations[0] / len(i_PP_1_rot) * 1.0
    populations[1] = populations[1] / len(i_PP_1_rot) * 1.0
    populations[2] = populations[2] / len(i_PP_2_rot) * 1.0


### define a function to cluster and sort the input data
def ClusterData(I, Q, cen_num=3, Centers=None):
    ### store the data
    i_raw = I
    q_raw = Q

    iqData = np.stack((i_raw, q_raw), axis=1)

    ### partition data into two cluster
    kmeans = KMeans(
        n_clusters=cen_num, n_init=7, max_iter=1000).fit(iqData)

    if Centers is not None:
        kmeans = KMeans(
            n_clusters=cen_num, n_init=1, max_iter=1000, init=Centers).fit(iqData)

    ### pull out the centers of the clusters
    Centers = kmeans.cluster_centers_
    ### pull out labels for the blobs
    blobNums = kmeans.labels_
    ### create an array to store all seperated blobs
    ### indexed as blobs[BLOB NUMBER][0 for I, 1 for Q][shot number]
    blobs = np.full([cen_num, 2, len(i_raw)], np.nan)
    dists = np.full([cen_num, len(i_raw)], np.nan)

    for idx_shot in range(len(i_raw)):
        for idx_cen in range(cen_num):
            if blobNums[idx_shot] == idx_cen:
                #### fill blob with I and Q data
                blobs[idx_cen][0][idx_shot] = i_raw[idx_shot]
                blobs[idx_cen][1][idx_shot] = q_raw[idx_shot]
                #### fill with distance info
                dists[idx_cen][idx_shot] = np.sqrt(
                    (Centers[idx_cen][0] - i_raw[idx_shot]) ** 2 +
                    (Centers[idx_cen][1] - q_raw[idx_shot]) ** 2)

    return kmeans, Centers, blobNums, blobs, dists


### define function to sort given data into defined kmeans cluster
def SortData(I0, Q0, I1, Q1, kmeans, dists):
    ### pull out the centers of the clusters
    Centers = kmeans.cluster_centers_
    ### pull out labels for the blobs
    blobNums = kmeans.labels_

    ### indexed as pops_arr[starting blob][resulting blob][time index]
    pops_arr = np.full([cen_num, cen_num, len(t_arr)], 0.0)

    #### using the blob centers sort out data
    blobSizes = dists

    #### loop over time steps
    for idx_t in range(len(t_arr)):
        #### create new set of blobs for each point in time
        blobs_0 = np.full([cen_num, 2, len(I0[idx_t])], np.nan)
        blobs_1 = np.full([cen_num, 2, len(I0[idx_t])], np.nan)

        for idx_shot in range(len(I0[idx_t])):
            for idx_cen in range(cen_num):
                pt_dist = np.sqrt((I0[idx_t][idx_shot] - Centers[idx_cen][0]) ** 2
                                  + (Q0[idx_t][idx_shot] - Centers[idx_cen][1]) ** 2)
                size_select = np.nanmean(dists[idx_cen])

                if pt_dist <= size_select:
                    #### fill blob with I and Q data
                    blobs_0[idx_cen][0][idx_shot] = I0[idx_t][idx_shot]
                    blobs_0[idx_cen][1][idx_shot] = Q0[idx_t][idx_shot]

                    blobs_1[idx_cen][0][idx_shot] = I1[idx_t][idx_shot]
                    blobs_1[idx_cen][1][idx_shot] = Q1[idx_t][idx_shot]

        #### using sorted blob data, find approximate population distribuitions
        for idx_cen_start in range(cen_num):
            #### grab i and q data from blob, removing out the nan values
            iData = blobs_1[idx_cen_start][0][~np.isnan(blobs_1[idx_cen_start][0])]
            qData = blobs_1[idx_cen_start][1][~np.isnan(blobs_1[idx_cen_start][1])]

            #### using the iq data check if point is inside close circle
            ### check all clusters that you could end up in
            num_count = 0
            for idx_cen_stop in range(cen_num):
                ### loop over all shots
                for idx_shot in range(len(iData)):
                    pt_dist = np.sqrt((iData[idx_shot] - Centers[idx_cen_stop][0]) ** 2
                                      + (qData[idx_shot] - Centers[idx_cen_stop][1]) ** 2)
                    size_select = np.nanmean(dists[idx_cen])

                    if pt_dist <= size_select:
                        pops_arr[idx_cen_start][idx_cen_stop][idx_t] += 1
                        num_count += 1

            pops_arr[idx_cen_start][:, idx_t] = pops_arr[idx_cen_start][:, idx_t] / num_count

    return pops_arr


### define T1 fitting function

def T1Fit(t_arr, pops_arr):
    ### create array to store T1 info
    T1_arr = np.zeros((2, len(pops_arr)))

    ### exponential fitting
    def expFit(x, a, T1, c):
        return a * np.exp(-1 * x / T1) + c

    #### find the T1 fit of the data
    for idx in range(len(pops_arr)):
        pop_list = pops_arr[idx][idx]
        a_guess = (np.max(pop_list) - np.min(pop_list)) * -1
        T1_guess = np.max(t_arr) / 5.0
        c_guess = np.min(pop_list)
        guess = [a_guess, T1_guess, c_guess]

        pOpt, pCov = curve_fit(expFit, t_arr, pop_list, p0=guess)
        pErr = np.sqrt(np.diag(pCov))

        T1 = pOpt[1]
        T1_err = pErr[1]

        T1_arr[0, idx] = T1
        T1_arr[1, idx] = T1_err

    return T1_arr


########################################################################################################################

print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

#### setup the lakeshore
# rm = pyvisa.ResourceManager()
#
# LS370_connection = rm.open_resource('GPIB0::12::INSTR')
#
# Lakeshore = Lakeshore370(LS370_connection)

################################## code for running qubit spec on repeat
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 0.815,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 8, # us
    "read_pulse_gain": 14000, # [DAC units]
    "read_pulse_freq": 5988.25,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 1715.6 - 25,
    "qubit_freq_stop": 1715.6 + 25,
    "SpecNumPoints": 201,  ### number of points
    "qubit_pulse_style": "arb",
    "qubit_freq": 1715.6,
    "sigma": 0.3,  ### units us
    "qubit_length": 1, ### units us, doesnt really get used though
    # "flat_top_length": 0.250, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    "qubit_gain": 18000, # Constant gain to use

    "spec_reps": 500,
    #### define shots
    "shots": 5000,  ### this gets turned into "reps"
    ### define the wait times
    "wait_start": 0,
    "wait_stop": 2000,
    "wait_num": 101,
    ##### define number of clusters to use
    "cen_num": 2, # let's do just 2 to prevent it from crashing -- when i do 4 and it gets no points in one circle, crash
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])

##### set the number of clusters to expect in kmeans
cen_num = config['cen_num']

##### loop over temperatures
# These are the temperatures reported by the server right before the measurement
temp_vec = []
# These are the temperatures reported by the server right after the measurement
temp_vec_fin = []

pops_mat = []

# Connect to the server computer so that we can get tha lakeshore information from it
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print('Connected.')

    # Keep looping until the server tells us we're done. Get temperatures from the server.
    # for idx_temp in range(len(temp_vec)):
    while True:
        print('Waiting to reach temperature setpoint...')
        # The server will set the temperature to reach the desired setpoint here
        # Get the temperature from the server, acknowledge receipt
        temp = float(s.recv(1024).decode())
        print('Current temperature:' + str(temp))
        temp_vec.append(temp)
        s.sendall("Roger.".encode())


        #### find the qubit frequency
        Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
        data_specSlice = SpecSlice.acquire(Instance_specSlice)
        # SpecSlice.save_data(Instance_specSlice, data_specSlice)
        # SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)

        ### find the qubit frequency
        peak_loc = np.argmax(data_specSlice['data']['avgq'])  # Maximum location
        qubitFreq = data_specSlice['data']['x_pts'][peak_loc]
        print("qubit_frequency = " + str(qubitFreq) + " MHz")

        config["qubit_freq"] = qubitFreq
        print('Found qubit frequency at ' + str(qubitFreq) + ' MHz')

        print('starting T1: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        Instance_T1_PS = T1_PS(path="dataTempSweeps_T1_PS", outerFolder=outerFolder, cfg=config,
                                                       soc=soc, soccfg=soccfg)
        data_T1_PS = T1_PS.acquire(Instance_T1_PS)
        # T1_PS.display(Instance_T1_PS, data_T1_PS, plotDisp=True, save_fig=True)
        T1_PS.save_data(Instance_T1_PS, data_T1_PS)
        T1_PS.save_config(Instance_T1_PS)

        print('finished T1: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        #### process the data
        data = data_T1_PS['data']
        i_0_arr = data['i_0_arr'][:]
        q_0_arr = data['q_0_arr'][:]

        i_1_arr = data['i_1_arr'][:]
        q_1_arr = data['q_1_arr'][:]

        t_arr = data['wait_vec'][:]

        #### Cluster the raw data
        I = i_0_arr[0]
        Q = q_0_arr[0]

        #### sort data into clusters, but only on the very first time
        if len(temp_vec) == 1:
            #### if it is the first round create the cluster
            kmeans, Centers, blobNums, blobs, dists = ClusterData(I, Q, cen_num = cen_num)

        #### use first round kmeans to sort new data
        I0 = i_0_arr
        Q0 = q_0_arr

        I1 = i_1_arr
        Q1 = q_1_arr

        pops_arr = SortData(I0, Q0, I1, Q1, kmeans, dists)

        pops_mat.append(pops_arr)

        ##### save the processed data
        # np.save(processed_name, pops_mat)
        np.savez(processed_name, temp_vec = temp_vec, temp_vec_int = temp_vec, temp_vec_fin = temp_vec_fin, pops_mat = pops_mat)
        # while True:
        #     s.sendall(b"Done measuring!")
        #     response = s.recv()

        # print("Done saving, waiting 5 minutes.")
        # time.sleep(60*5)

        # The server now sends us the temperature after the measurement, put this in the vector
        temp_vec_fin.append(float(s.recv(1024).decode()))

        # Tell the server that we're done measuring
        s.sendall("Done measuring.".encode())
        keep_measuring = s.recv(1024).decode()
        # The server tells us whether we want to keep measuring, or have no more temperatures we want to measure
        if keep_measuring == "continue measurement":
            print("Continuing to measure another temperature.")
        elif keep_measuring == "measurement complete":
            print("No more temperatures to measure.")
            break
        else:
            print("What nonsense is this: " + keep_measuring)


# The server will turn off the Lakeshore here

##### plot the T1s

### define lists for storing the coherence times and steady state populations
T1_mat = np.zeros((len(pops_mat[0]), len(pops_mat), 2))
pops_arr_SS = np.zeros((len(pops_mat[0]), len(pops_mat)))

for idx in range(len(pops_mat)):
    pops_arr = pops_mat[idx]

    T1s = T1Fit(t_arr, pops_arr)

    ##### filter out nonsense T1 numbers, if error is larger than value, set to 0
    if T1s[1, 0] < T1s[0, 0]:
        T1_mat[0][idx] = T1s[:, 0]
    else:
        T1_mat[0][idx] = 0

    if T1s[1, 1] < T1s[0, 1]:
        T1_mat[1][idx] = T1s[:, 1]
    else:
        T1_mat[1][idx] = 0

    for idx_cen in range(cen_num):
        pops_arr_SS[idx_cen][idx] = pops_arr[idx_cen][idx_cen][-1]


##### plot out
colors = ['b', 'r', 'm', 'c', 'g']

fig, axs = plt.subplots(2, 1, figsize=[5, 8])

for idx in range(cen_num):
    axs[0].errorbar(temp_vec, T1_mat[idx][:, 0], yerr=T1_mat[idx][:, 1],
                    color=colors[idx], marker='o', linestyle='', label='blob ' + str(idx))

    axs[1].plot(temp_vec, pops_arr_SS[idx], color=colors[idx], marker='o', linestyle='',
                label='blob ' + str(idx))

#### label axes and title
axs[0].set_xlabel('Fridge temp (mK)')
axs[0].set_ylabel('State Lifetime (us)')

axs[0].set_ylim([0, 300])

axs[1].set_xlabel('Fridge temp (mK)')
axs[1].set_ylabel('Steady State Population ')

plt.tight_layout()
plt.legend()

plt.savefig(processed_fig_name)

######################################################################################################################
plt.show()