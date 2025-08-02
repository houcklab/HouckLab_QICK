#%%
import numpy as np
from matplotlib import pyplot as plt
import time
import h5py
import datetime
import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *

import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.LS370 as lk
import WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Helpers.LakeshoreChannel8Calib as lk8calib
import pyvisa

outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_10_14_cooldown\\HouckCage_dev\\FridgeHeatingWithMagnet\\"



#%%
def create_plot_figure():
    """
    Create a persistent figure with three subplots and return the figure,
    axes, and line objects for updating.
    """
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12))

    # Initialize empty lines that will be updated later
    line1, = ax1.plot([], [], 'b.-', label='Voltage')
    line2, = ax2.plot([], [], 'r.-', label='Base Temperature')
    line3, = ax3.plot([], [], 'g.-', label='QCage Temperature')

    # Set titles and labels
    ax1.set_title("Voltage vs Time")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Voltage (V)")

    ax2.set_title("Base Temperature vs Time")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Temperature (K)")

    ax3.set_title("QCage Temperature vs Time")
    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("Temperature (K)")

    # Enable grid on all subplots
    for ax in [ax1, ax2, ax3]:
        ax.grid(True)

    plt.tight_layout()
    return fig, ax1, ax2, ax3, line1, line2, line3


def update_plots(time_vals, voltage_vals, base_temp_vals, qcage_temp_vals,
                 fig, ax1, ax2, ax3, line1, line2, line3,
                 finalize=False, filename="final_plot.png"):
    """
    Update the existing plot with new data. If finalize=True, save the figure
    to filename and close the figure.
    """
    # Update the data for each line
    line1.set_data(time_vals, voltage_vals)
    line2.set_data(time_vals, base_temp_vals)
    line3.set_data(time_vals, qcage_temp_vals)

    # Update x-axis limits if time_vals available
    if time_vals:
        xmin, xmax = min(time_vals), max(time_vals)
        ax1.set_xlim(xmin, xmax)
        ax2.set_xlim(xmin, xmax)
        ax3.set_xlim(xmin, xmax)

    # Optionally update y-axis limits; adjust these as needed for your data
    if voltage_vals:
        ax1.set_ylim(min(voltage_vals) - 1, max(voltage_vals) + 1)
    if base_temp_vals:
        ax2.set_ylim(min(base_temp_vals) - 0.001, max(base_temp_vals) + 0.001)
    if qcage_temp_vals:
        ax3.set_ylim(min(qcage_temp_vals) - 0.001, max(qcage_temp_vals) + 0.001)

    # Redraw the canvas
    fig.canvas.draw()
    fig.canvas.flush_events()

    # If finalizing, save and close the figure
    if finalize:
        plt.savefig(filename)
        plt.close(fig)
        print(f"Plot saved as {filename} and figure closed.")
    else:
        # Short pause to allow GUI events to be processed
        plt.pause(0.1)


def save_data_as_h5(filename, time_vals, voltage_vals, base_temp_vals, qcage_temp_vals):
    """
    Save experimental data lists to an HDF5 file.

    Parameters:
      filename (str): Path and name for the output .h5 file.
      time_vals (list or np.array): List of time values.
      voltage_vals (list or np.array): List of voltage measurements.
      base_temp_vals (list or np.array): List of base temperature measurements.
      qcage_temp_vals (list or np.array): List of QCage temperature measurements.
    """
    # Optionally convert lists to numpy arrays if not already in that format.
    time_data = np.array(time_vals)
    voltage_data = np.array(voltage_vals)
    base_temp_data = np.array(base_temp_vals)
    qcage_temp_data = np.array(qcage_temp_vals)

    # Open a new HDF5 file (or overwrite an existing one) for writing.
    with h5py.File(filename, 'w') as hf:
        hf.create_dataset('time', data=time_data)
        hf.create_dataset('voltage', data=voltage_data)
        hf.create_dataset('base_temperature', data=base_temp_data)
        hf.create_dataset('qcage_temperature', data=qcage_temp_data)

    print(f"Data successfully saved to {filename}")

#%%

# Set up the Lakeshore
rm = pyvisa.ResourceManager()
LS370_connection = rm.open_resource('GPIB0::12::INSTR')
lakeshore = lk.Lakeshore370(LS370_connection)
lakeshore.set_temp_control_mode(4)
# Set yoko voltage
start = 0
yoko1.SetVoltage(start)

# Defining the ramp up and ramp down voltages
ramp_up_max = 30 # Volts
ramp_down_max = -30 # Volts
step = 0.25
ramp_up_vec = np.arange(start, ramp_up_max + step, step)
print("Ramp up: ", ramp_up_vec)
ramp_down_vec = np.arange(ramp_up_max, ramp_down_max - step, -step)
print("Ramp down: ", ramp_down_vec)

# Defining max threshold temperature
tempr_max = 50e-3 # Kelvin

# Defining max stabilizing temperature
tempr_stab = 0.5e-3 # Kelvin

#%%
#TITLE : Begin the ramp up experiment
time.sleep(300)
# Book Keeping
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
print("Starting the ramp up experiment at ", datetimestring)
filename = outerFolder + "Data_" + datetimestring + "_"

# Plotting
plt.ion()
# Create the persistent figure and get the line handles
fig, ax1, ax2, ax3, line1, line2, line3 = create_plot_figure()


# Define lists to store temperature
base_tempr_list = []
qcage_tempr_list = []
time_val_list = []
voltage_list = []

# Start time
start_time = time.time()

for i in range(ramp_up_vec.size):
    yoko1.SetVoltage(ramp_up_vec[i])

    # Creating error and iteration variables
    error = np.inf
    itr = 0

    while error > tempr_stab:
        # Measure Time
        time_now = time.time()
        time_now = time_now - start_time
        time_val_list.append(time_now)

        # Measure voltage
        voltage = yoko1.GetVoltage()
        voltage_list.append(voltage)

        # Measure temperatures
        base_tempr = float(lakeshore.get_temp(7))
        base_tempr_list.append(base_tempr)

        # Measure resistance
        qcage_resist = float(lakeshore.get_resist(8))
        qcage_tempr, conf_lower, conf_upper = lk8calib.poly8_with_confidence(qcage_resist)
        qcage_tempr_list.append(qcage_tempr)

        # Increase iteration count
        itr += 1

        # Check if the temperature is greater than tempr_max
        if base_tempr > tempr_max:
            print("Max Temperature Reached")
            break

        if itr > 1 :
            error = np.abs(base_tempr_list[-1] - base_tempr_list[-2])
            print("Temperature changed by ", base_tempr_list[-1] - base_tempr_list[-2], " K")

        # Plotting function
        update_plots(time_val_list, voltage_list, base_tempr_list, qcage_tempr_list,
                     fig, ax1, ax2, ax3, line1, line2, line3,
                     finalize=False)

        # Wait
        time.sleep(15)

update_plots(time_val_list, voltage_list, base_tempr_list, qcage_tempr_list,
                     fig, ax1, ax2, ax3, line1, line2, line3, finalize=True, filename=filename + "ramp_up_plot.png")
save_data_as_h5(filename = filename + "ramp_up_data.h5", time_vals = time_val_list, voltage_vals = voltage_list,
                base_temp_vals = base_tempr_list, qcage_temp_vals = qcage_tempr_list)
#%%
#TITLE : Begin the ramp down experiment

ramp_down_vec = np.arange(int(yoko1.GetVoltage()), ramp_down_max - step, -step)
print("Ramp down: ", ramp_down_vec)

#%%

# Book Keeping
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
print("Starting the ramp up experiment at ", datetimestring)
filename = outerFolder + "Data_" + datetimestring + "_"

# Plotting
plt.ion()
# Create the persistent figure and get the line handles
fig, ax1, ax2, ax3, line1, line2, line3 = create_plot_figure()


# Define lists to store temperature
base_tempr_list = []
qcage_tempr_list = []
time_val_list = []
voltage_list = []

# Start time
start_time = time.time()

for i in range(ramp_down_vec.size):
    yoko1.SetVoltage(ramp_down_vec[i])

    # Creating error and iteration variables
    error = np.inf
    itr = 0

    while error > tempr_stab:
        # Measure Time
        time_now = time.time()
        time_now = time_now - start_time
        time_val_list.append(time_now)

        # Measure voltage
        voltage = yoko1.GetVoltage()
        voltage_list.append(voltage)

        # Measure temperatures
        base_tempr = float(lakeshore.get_temp(7))
        base_tempr_list.append(base_tempr)

        # Measure resistance
        qcage_resist = float(lakeshore.get_resist(8))
        qcage_tempr, conf_lower, conf_upper = lk8calib.poly8_with_confidence(qcage_resist)
        qcage_tempr_list.append(qcage_tempr)

        # Increase iteration count
        itr += 1

        # Check if the temperature is greater than tempr_max
        if base_tempr > tempr_max:
            print("Max Temperature Reached")
            break

        if itr > 1 :
            error = np.abs(base_tempr_list[-1] - base_tempr_list[-2])
            print("Temperature changed by ", base_tempr_list[-1] - base_tempr_list[-2], " K")

        # Plotting function
        update_plots(time_val_list, voltage_list, base_tempr_list, qcage_tempr_list,
                     fig, ax1, ax2, ax3, line1, line2, line3,
                     finalize=False)

        # Wait
        time.sleep(15)

update_plots(time_val_list, voltage_list, base_tempr_list, qcage_tempr_list,
                     fig, ax1, ax2, ax3, line1, line2, line3, finalize=True, filename=filename + "ramp_down_plot.png")
save_data_as_h5(filename = filename + "ramp_down_data.h5", time_vals = time_val_list, voltage_vals = voltage_list,
                base_temp_vals = base_tempr_list, qcage_temp_vals = qcage_tempr_list)