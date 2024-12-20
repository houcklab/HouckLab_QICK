import numpy as np
import h5py
from tqdm import tqdm
import json
import csv
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers.SingleShotAnalysis import PS_Analysis

# Get all the filenames from the csv
pathdata_csv_filename = r"Z:\TantalumFluxonium\Data\2023_10_31_BF2_cooldown_6\WTF\TempChecks\Summary\WTF_cooldown6_pathtodata_all.csv"

with open(pathdata_csv_filename, 'r') as file:
    reader = csv.reader(file)
    data = list(reader)

# Index for single shot data is 5

# Looping over all the rows
for row in tqdm(data[1:]):

    # Find the name for single shot data path and removing the .h5
    file_loc = row[6][:-3]

    # Get the filename and the path
    path_split = file_loc.split('\\')
    path = '\\'.join(path_split[:-1])
    print("Path is ",path)
    fname = path_split[-1]
    print("Filename is ",fname)


    # try to extract the qubit frequency
    json_path = file_loc + '.json'

    with open(json_path, "r") as json_file:
        config = json.loads(json_file.read())
        qubit_freq = config["qubit_freq"]
        yoko_volt = config["yokoVoltage"]
        try :
            fridge_tempr = config["fridge_temp"]
        except:
            fridge_tempr = float(row[0])
        json_file.close()

    if float(row[2]) - qubit_freq > 50 :
        qubit_freq = float(row[2])

    print("qubit frequency " + str(qubit_freq))

    # Loading the data
    data_exp = h5py.File(file_loc + ".h5", 'r')
    print(data_exp.keys())
    # Creating the class object for analyzing post-selected data
    cen_num = 2

    ### try to perform the fit and if it fails continue
    try:
        SSData = PS_Analysis(
            data=data_exp,
            cen_num=cen_num,
            cluster_method='gmm',
            init_method='all',
            data_name=fname,
            outerFolder=path,
            gauss_fit=True,
        )

        # Calculate the populations and temperatures
        estimates_full = SSData.GaussFitMeasurement(
            wait_num=0,
            confidence_selection=0.0,
            bin_size=51,
            plot_title='Final_Meas_Fit',
            save_estimates_name='Value_Estimates',
            save_pop_results=True,
            qubit_freq=qubit_freq
        )
    except:
        ### fill in empty estimates
        estimates_full = {}
        estimates_full['Starting_0'] = {}
        estimates_full['Starting_0']['PopState_0_mean'] = 0.0
        estimates_full['Starting_0']['PopState_0_std'] = 0.0
        estimates_full['Starting_0']['PopState_0_median'] = 0.0
        estimates_full['Starting_0']['PopState_0_median'] = 0.0
        estimates_full['Starting_0']['PopState_0_95_low'] = 0.0
        estimates_full['Starting_0']['PopState_0_95_high'] = 0.0

        estimates_full['Starting_0']['PopState_1_mean'] = 0.0
        estimates_full['Starting_0']['PopState_1_std'] = 0.0
        estimates_full['Starting_0']['PopState_1_median'] = 0.0
        estimates_full['Starting_0']['PopState_1_median'] = 0.0
        estimates_full['Starting_0']['PopState_1_95_low'] = 0.0
        estimates_full['Starting_0']['PopState_1_95_high'] = 0.0

    # Create an empty list to collect all data to be stored in a csv
    processed_data = []

    # Experiment information
    processed_data.append(yoko_volt)
    processed_data.append(qubit_freq)
    try:
        processed_data.append(fridge_tempr)
    except:
        processed_data.append('0')


    # Procesesd information
    try:
        processed_data.append(estimates_full['Starting_0']['temp_mean'])
        processed_data.append(estimates_full['Starting_0']['temp_std'])
        processed_data.append(estimates_full['Starting_0']['temp_median'])
        processed_data.append(estimates_full['Starting_0']['temp_95_low'])
        processed_data.append(estimates_full['Starting_0']['temp_95_high'])
    except:
        processed_data.append('0')
        processed_data.append('0')
        processed_data.append('0')
        processed_data.append('0')
        processed_data.append('0')

    processed_data.append(estimates_full['Starting_0']['PopState_0_mean'])
    processed_data.append(estimates_full['Starting_0']['PopState_0_std'])
    processed_data.append(estimates_full['Starting_0']['PopState_0_median'])
    processed_data.append(estimates_full['Starting_0']['PopState_0_95_low'])
    processed_data.append(estimates_full['Starting_0']['PopState_0_95_high'])

    processed_data.append(estimates_full['Starting_0']['PopState_1_mean'])
    processed_data.append(estimates_full['Starting_0']['PopState_1_std'])
    processed_data.append(estimates_full['Starting_0']['PopState_1_median'])
    processed_data.append(estimates_full['Starting_0']['PopState_1_95_low'])
    processed_data.append(estimates_full['Starting_0']['PopState_1_95_high'])

    # Save it as a new row to a csv
    save_csv_path = r'Z:\TantalumFluxonium\Data\2023_10_31_BF2_cooldown_6\WTF\TempChecks\Summary\PostProcessed\WTF_cooldown6_tempData_postprocessed.csv'

    # Open the existing CSV file in append mode
    with open(save_csv_path, mode='a', newline='') as file:
        # Create a CSV writer object
        writer = csv.writer(file)

        # Write the list to the CSV file
        writer.writerow(processed_data)

    # Close the open csv
    file.close()

