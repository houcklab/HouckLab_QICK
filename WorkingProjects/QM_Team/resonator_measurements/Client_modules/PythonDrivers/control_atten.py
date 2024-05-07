import sys
from ctypes import *
from distutils.util import strtobool
import os

# Python 3.7
# os.environ['PATH'] = os.getcwd() + '\\PythonDrivers' + os.pathsep + os.environ['PATH']
# Python 3.8 and newer
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')

# TODO make this computer agnostic
os.add_dll_directory(r'C:\Users\my\Documents\GitHub\ZCU216\res_dev\Client_modules\PythonDrivers')
# os.add_dll_directory(r'C:\Users\deleo\Documents\GitHub\HouckLab_QICK\WorkingProjects\QM_Team\resonator_measurements\Client_modules\PythonDrivers')

def setatten(attenu, serial, printv):
    if printv == True:
        print("Setting attenuation")
    vnx = cdll.VNX_atten64
    vnx.fnLDA_SetTestMode(False)

    DeviceIDArray = c_int * 20
    Devices = DeviceIDArray()

    # GetNumDevices will determine how many LDA devices are availible
    numDevices = vnx.fnLDA_GetNumDevices()
    if printv == True:
        print(str(numDevices), ' device(s) found')

    # GetDevInfo generates a list, stored in the devices array, of
    # every availible LDA device attached to the system
    # GetDevInfo will return the number of device handles in the array
    dev_info = vnx.fnLDA_GetDevInfo(Devices)
    #print('GetDevInfo returned', str(dev_info))

    for i in range(0,5):
        # GetSerialNumber will return the devices serial number
        ser_num_i = vnx.fnLDA_GetSerialNumber(Devices[i])
        if printv == True:
            print('Device ' + str(i) + ' Serial number:', str(ser_num_i))
        if ser_num_i == serial:
            if printv == True:
                print('Device was found to be device ' + str(i))
            # InitDevice wil prepare the device for operation
            init_dev = vnx.fnLDA_InitDevice(Devices[i])
            #print('InitDevice returned', str(init_dev))

            #### Device 0 ####
            # GetNumChannels will return the number of channels on the device
            num_channels = vnx.fnLDA_GetNumChannels(Devices[i]);
            if num_channels < 1:
                num_channels = 1

            #print("Num channels = %d" %num_channels)
            # Input desired attenuation level for channel 1
            #print('Set attenuation level for channel 1 of device')
            #atten = float(input(': '))
            atten = float(attenu)
            attenuation = atten / .05
            atten = round(attenuation)

            # Select channel 1
            channel_1 = vnx.fnLDA_SetChannel(Devices[i], 1)
            if channel_1 != 0:
                if printv == True:
                    print('SetChannel returned error', channel_1)
            # Set attenuation level for channe 1
            result_1 = vnx.fnLDA_SetAttenuationHR(Devices[i], int(atten))
            if result_1 != 0:
                if printv == True:
                    print('SetAttenuationHR returned error', result_1)

            # Get channel 1 attenuation
            result_1 = vnx.fnLDA_GetAttenuationHR(Devices[i])

            # Display attenuation level for channel 1
            if result_1 < 0:
                if printv == True:
                    print('GetAttenuationHR returned error', result)
            else:
                atten_db = result_1 / 20
                if printv == True:
                    print('Set attenuation:', atten_db)

            # Always close the device when done with it
            result = vnx.fnLDA_CloseDevice(Devices[i])

            if result != 0:
                if printv == True:
                    print('CloseDevice returned an error', result)

        else:
            pass

if __name__ == "__main__":
    atten = 30 #sys.argv[1]
    serial = 27786 #sys.argv[2]
    printv = True #sys.argv[3]
    boolprint = bool(strtobool(str(printv)))
    setatten(float(atten), int(serial), boolprint)