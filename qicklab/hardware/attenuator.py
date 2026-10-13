import os
from ctypes import c_int, cdll

# Python >= 3.8 does not search PATH for DLLs: docs/hardware.md#attenuator-vaunix-lda
os.add_dll_directory(os.getcwd())


def _strtobool(val):
    """Same as the removed ``distutils.util.strtobool``: 1 or 0, ValueError otherwise."""
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError(f"invalid truth value {val!r}")


def setatten(attenu, serial, printv):
    if printv == True:
        print("Setting attenuation")
    vnx = cdll.VNX_atten64
    vnx.fnLDA_SetTestMode(False)

    DeviceIDArray = c_int * 20
    Devices = DeviceIDArray()

    numDevices = vnx.fnLDA_GetNumDevices()
    if printv == True:
        print(str(numDevices), " device(s) found")

    dev_info = vnx.fnLDA_GetDevInfo(Devices)

    for i in range(0, 5):
        ser_num_i = vnx.fnLDA_GetSerialNumber(Devices[i])
        if printv == True:
            print("Device " + str(i) + " Serial number:", str(ser_num_i))
        if ser_num_i == serial:
            if printv == True:
                print("Device was found to be device " + str(i))
            init_dev = vnx.fnLDA_InitDevice(Devices[i])

            num_channels = vnx.fnLDA_GetNumChannels(Devices[i])
            if num_channels < 1:
                num_channels = 1

            atten = float(attenu)
            attenuation = atten / 0.05
            atten = round(attenuation)

            channel_1 = vnx.fnLDA_SetChannel(Devices[i], 1)
            if channel_1 != 0:
                if printv == True:
                    print("SetChannel returned error", channel_1)
            result_1 = vnx.fnLDA_SetAttenuationHR(Devices[i], int(atten))
            if result_1 != 0:
                if printv == True:
                    print("SetAttenuationHR returned error", result_1)

            result_1 = vnx.fnLDA_GetAttenuationHR(Devices[i])

            if result_1 < 0:
                if printv == True:
                    print("GetAttenuationHR returned error", result)
            else:
                atten_db = result_1 / 20
                if printv == True:
                    print("Set attenuation:", atten_db)

            result = vnx.fnLDA_CloseDevice(Devices[i])

            if result != 0:
                if printv == True:
                    print("CloseDevice returned an error", result)

        else:
            pass


if __name__ == "__main__":
    atten = 30
    serial = 27786
    printv = True
    boolprint = bool(_strtobool(str(printv)))
    setatten(float(atten), int(serial), boolprint)
