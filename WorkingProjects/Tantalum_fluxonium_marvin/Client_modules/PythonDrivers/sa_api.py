# -*- coding: utf-8 -*-

# Copyright (c) 2022 Signal Hound
# For licensing information, please see the API license in the software_licenses folder

from ctypes import *
import numpy
loc = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers\sa_api.dll'
salib = CDLL(loc)


# ---------------------------------- Defines -----------------------------------

SA_TRUE = 1
SA_FALSE = 0

SA_MAX_DEVICES = 8

SA_FIRMWARE_STR_LEN = 16
SA_NUM_AUDIO_SAMPLES = 4096

# Modes
SA_IDLE = -1
SA_SWEEPING = 0
SA_REAL_TIME = 1
SA_IQ = 2
SA_AUDIO = 3
SA_TG_SWEEP = 4

# RBW shapes
SA_RBW_SHAPE_FLATTOP = 1
SA_RBW_SHAPE_CISPR = 2

# Detectors
SA_MIN_MAX = 0
SA_AVERAGE = 1

# Scales
SA_LOG_SCALE = 0
SA_LIN_SCALE = 1
SA_LOG_FULL_SCALE = 2
SA_LIN_FULL_SCALE = 3

# Levels
SA_AUTO_ATTEN = -1
SA_AUTO_GAIN = -1

# Video processing units
SA_LOG_UNITS = 0
SA_VOLT_UNITS = 1
SA_POWER_UNITS = 2
SA_BYPASS = 3

# Audio
SA_AUDIO_AM = 0
SA_AUDIO_FM = 1
SA_AUDIO_USB = 2
SA_AUDIO_LSB = 3
SA_AUDIO_CW = 4


# --------------------------------- Mappings ----------------------------------

saOpenDeviceBySerialNumber = salib.saOpenDeviceBySerialNumber
saOpenDevice = salib.saOpenDevice
saCloseDevice = salib.saCloseDevice
saPreset = salib.saPreset

saGetSerialNumber = salib.saGetSerialNumber
saGetDeviceType = salib.saGetDeviceType
saConfigAcquisition = salib.saConfigAcquisition
saConfigCenterSpan = salib.saConfigCenterSpan
saConfigLevel = salib.saConfigLevel
saConfigGainAtten = salib.saConfigGainAtten
saConfigSweepCoupling = salib.saConfigSweepCoupling
saConfigRBWShape = salib.saConfigRBWShape
saConfigProcUnits = salib.saConfigProcUnits
saConfigIQ = salib.saConfigIQ
saConfigAudio = salib.saConfigAudio
saConfigRealTime = salib.saConfigRealTime
saConfigRealTimeOverlap = salib.saConfigRealTimeOverlap

saSetTimebase = salib.saSetTimebase

saInitiate = salib.saInitiate
saAbort = salib.saAbort

saQuerySweepInfo = salib.saQuerySweepInfo
saQueryStreamInfo = salib.saQueryStreamInfo
saQueryRealTimeFrameInfo = salib.saQueryRealTimeFrameInfo
saQueryRealTimePoi = salib.saQueryRealTimePoi
saQueryTemperature = salib.saQueryTemperature
saQueryDiagnostics = salib.saQueryDiagnostics

saGetSweep_32f = salib.saGetSweep_32f
saGetSweep_32f.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C')
]
saGetSweep_64f = salib.saGetSweep_64f
saGetSweep_64f.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float64, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float64, ndim=1, flags='C')
]
saGetPartialSweep_32f = salib.saGetPartialSweep_32f
saGetPartialSweep_32f.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    POINTER(c_int),
    POINTER(c_int)
]
saGetPartialSweep_64f = salib.saGetPartialSweep_64f
saGetPartialSweep_64f.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float64, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float64, ndim=1, flags='C'),
    POINTER(c_int),
    POINTER(c_int)
]
saGetRealTimeFrame = salib.saGetRealTimeFrame
saGetRealTimeFrame.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C'),
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C')
]
saGetIQ_32f = salib.saGetIQ_32f
saGetIQ_32f.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.complex64, ndim=1, flags='C')
]
saGetIQ_64f = salib.saGetIQ_64f
saGetIQ_64f.argtypes = [
     c_int,
    numpy.ctypeslib.ndpointer(numpy.complex128, ndim=1, flags='C')
]
saGetIQDataUnpacked = salib.saGetIQDataUnpacked
saGetIQDataUnpacked.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.complex64, ndim=1, flags='C'),
    c_int,
    c_int,
    POINTER(c_int),
    POINTER(c_int),
    POINTER(c_int),
    POINTER(c_int)
]
saGetAudio = salib.saGetAudio
saGetAudio.argtypes = [
    c_int,
    numpy.ctypeslib.ndpointer(numpy.float32, ndim=1, flags='C')
]

saAttachTg = salib.saAttachTg
saIsTgAttached = salib.saIsTgAttached
saConfigTgSweep = salib.saConfigTgSweep
saStoreTgThru = salib.saStoreTgThru
saSetTg = salib.saSetTg
saSetTgReference = salib.saSetTgReference
saGetTgFreqAmpl = salib.saGetTgFreqAmpl

saConfigIFOutput = salib.saConfigIFOutput

saGetAPIVersion = salib.saGetAPIVersion
saGetAPIVersion.restype = c_char_p
saGetProductID = salib.saGetProductID
saGetProductID.restype = c_char_p
saGetErrorString = salib.saGetErrorString
saGetErrorString.restype = c_char_p


# ---------------------------------- Utility ----------------------------------

def error_check(func):
    def print_status_if_error(*args, **kwargs):
        return_vars = func(*args, **kwargs)
        if "status" not in return_vars.keys():
            return return_vars
        status = return_vars["status"]
        if status != 0:
            print (f"{'Error' if status < 0 else 'Warning'} {status}: {sa_get_error_string(status)} in {func.__name__}()")
        if status < 0:
            exit()
        return return_vars
    return print_status_if_error


# --------------------------------- Functions ---------------------------------

@error_check
def sa_open_device_by_serial(serial_number):
    device = c_int(-1)
    status = saOpenDeviceBySerialNumber(byref(device), serial_number)
    return {
        "status": status,
        "handle": device.value
    }

@error_check
def sa_open_device():
    device = c_int(-1)
    status = saOpenDevice(byref(device))
    return {
        "status": status,
        "handle": device.value
    }

@error_check
def sa_close_device(device):
    return {
        "status": saCloseDevice(device)
    }

@error_check
def sa_preset(device):
    return {
        "status": saPreset(device)
    }

@error_check
def sa_get_serial_number(device):
    serial = c_int(-1)
    status = saGetSerialNumber(device, byref(serial))
    return {
        "status": status,
        "serial": serial.value
    }

@error_check
def sa_get_device_type(device, device_type):
    device_type = c_int(-1)
    status = saGetDeviceType(device, byref(device_type))
    return {
        "status": status,
        "device_type": device_type.value
    }

@error_check
def sa_config_acquisition(device, detector, scale):
    return {
        "status": saConfigAcquisition(device, detector, scale)
    }

@error_check
def sa_config_center_span(device, center, span):
    return {
        "status": saConfigCenterSpan(device, c_double(center), c_double(span))
    }

@error_check
def sa_config_level(device, ref):
    return {
        "status": saConfigLevel(device, c_double(ref))
    }

@error_check
def sa_config_gain_atten(device, atten, gain, pre_amp):
    return {
        "status": saConfigGainAtten(device, atten, gain, pre_amp)
    }

@error_check
def sa_config_sweep_coupling(device, rbw, vbw, reject):
    return {
        "status": saConfigSweepCoupling(device, c_double(rbw), c_double(vbw), reject)
    }

@error_check
def sa_config_RBW_shape(device, rbw_shape):
    return {
        "status": saConfigRBWShape(device, rbw_shape)
    }

@error_check
def sa_config_proc_units(device, units):
    return {
        "status": saConfigProcUnits(device, units)
    }

@error_check
def sa_config_IQ(device, decimation, bandwidth):
    return {
        "status": saConfigIQ(device, decimation, c_double(bandwidth))
    }

@error_check
def sa_config_audio(device, audio_type, center_freq, bandwidth, audio_low_pass_freq, audio_high_pass_freq, fm_deemphasis):
    return {
        "status": saConfigAudio(device, audioType, c_double(centerFreq), c_double(bandwidth), c_double(audio_low_pass_freq), c_double(audio_high_pass_freq), c_double(fm_deemphasis))
    }

@error_check
def sa_config_real_time(device, frame_scale, frame_rate):
    return {
        "status": saConfigRealTime(device, c_double(frame_scale), frame_rate)
    }

@error_check
def sa_config_real_time_overlap(device, advance_rate):
    return {
        "status": saConfigRealTimeOverlap(device, c_double(advance_rate))
    }

@error_check
def sa_set_timebase(device, timebase):
    return {
        "status": saSetTimebase(device, timebase)
    }

@error_check
def sa_initiate(device, mode, flag):
    return {
        "status": saInitiate(device, mode, flag)
    }

@error_check
def sa_abort(device):
    return {
        "status": saAbort(device)
    }

@error_check
def sa_query_sweep_info(device):
    sweep_length = c_int(-1)
    start_freq = c_double(-1)
    bin_size = c_double(-1)
    status = saQuerySweepInfo(device, byref(sweep_length), byref(start_freq), byref(bin_size))
    return {
        "status": status,
        "sweep_length": sweep_length.value,
        "start_freq": start_freq.value,
        "bin_size": bin_size.value
    }

@error_check
def sa_query_stream_info(device):
    return_len = c_int(-1)
    bandwidth = c_double(-1)
    samples_per_second = c_double(-1)
    status = saQueryStreamInfo(device, byref(return_len), byref(bandwidth), byref(samples_per_second))
    return {
        "status": status,
        "return_len": return_len.value,
        "bandwidth": bandwidth.value,
        "samples_per_second": samples_per_second.value
    }

@error_check
def sa_query_real_time_frame_info(device):
    frame_width = c_int(-1)
    frame_height = c_int(-1)
    status = saQueryRealTimeFrameInfo(device, byref(frame_width), byref(frame_height))
    return {
        "status": status,
        "frame_width": frame_width.value,
        "frame_height": frame_height.value
    }

@error_check
def sa_query_real_time_POI(device):
    poi = c_double(-1)
    status = saQueryRealTimePoi(device, byref(poi))
    return {
        "status": status,
        "poi": poi.value
    }

@error_check
def sa_query_temperature(device):
    temp = c_float(-1)
    status = saQueryTemperature(device, byref(temp))
    return {
        "status": status,
        "temp": temp.value
    }

@error_check
def sa_query_diagnostics(device):
    voltage = c_float(-1)
    status = saQueryDiagnostics(device, byref(voltage))
    return {
        "status": status,
        "voltage": voltage.value
    }

@error_check
def sa_get_sweep_32f(device):
    sweep_length = sa_query_sweep_info(device)["sweep_length"]
    sweep_min = numpy.zeros(sweep_length).astype(numpy.float32)
    sweep_max = numpy.zeros(sweep_length).astype(numpy.float32)
    status = saGetSweep_32f(device, sweep_min, sweep_max)
    return {
        "status": status,
        "min": sweep_min,
        "max": sweep_max
    }

@error_check
def sa_get_sweep_64f(device):
    sweep_length = sa_query_sweep_info(device)["sweep_length"]
    sweep_min = numpy.zeros(sweep_length).astype(numpy.float64)
    sweep_max = numpy.zeros(sweep_length).astype(numpy.float64)
    status = saGetSweep_64f(device, sweep_min, sweep_max)
    return {
        "status": status,
        "min": sweep_min,
        "max": sweep_max
    }

@error_check
def sa_get_partial_sweep_32f(device):
    sweep_length = sa_query_sweep_info(device)["sweep_length"]
    sweep_min = numpy.zeros(sweep_length).astype(numpy.float32)
    sweep_max = numpy.zeros(sweep_length).astype(numpy.float32)
    start = c_int(-1)
    stop = c_int(-1)
    status = saGetPartialSweep_32f(device, sweep_min, sweep_max, byref(start), byref(stop))
    return {
        "status": status,
        "min": sweep_min,
        "max": sweep_max,
        "start": start.value,
        "stop": stop.value
    }

@error_check
def sa_get_partial_sweep_64f(device):
    sweep_length = sa_query_sweep_info(device)["sweep_length"]
    sweep_min = numpy.zeros(sweep_length).astype(numpy.float64)
    sweep_max = numpy.zeros(sweep_length).astype(numpy.float64)
    start = c_int(-1)
    stop = c_int(-1)
    status = saGetPartialSweep_64f(device, sweep_min, sweep_max, byref(start), byref(stop))
    return {
        "status": status,
        "min": sweep_min,
        "max": sweep_max,
        "start": start.value,
        "stop": stop.value
    }

@error_check
def sa_get_real_time_frame(device):
    sweep_length = sa_query_sweep_info(device)["sweep_length"]
    query = sa_query_real_time_frame_info(device)
    frame_width = query["frame_width"]
    frame_height = query["frame_height"]
    sweep_min = numpy.zeros(sweep_length).astype(numpy.float32)
    sweep_max = numpy.zeros(sweep_length).astype(numpy.float32)
    color_frame = numpy.zeros(frame_width * frame_height).astype(numpy.float32)
    alpha_frame = numpy.zeros(frame_width * frame_height).astype(numpy.float32)
    status = saGetRealTimeFrame(device, sweep_min, sweep_max, color_frame, alpha_frame)
    return {
        "status": status,
        "sweep_min": sweep_min,
        "sweep_max": sweep_max,
        "color_frame": color_frame,
        "alpha_frame": alpha_frame,
    }

@error_check
def sa_get_IQ_32f(device):
    return_len = sa_query_stream_info(device)["return_len"]
    iq = numpy.zeros(return_len).astype(numpy.complex64)
    status = saGetIQ_32f(device, iq)
    return {
        "status": status,
        "iq": iq
    }

@error_check
def sa_get_IQ_64f(device):
    return_len = sa_query_stream_info(device)["return_len"]
    iq = numpy.zeros(return_len).astype(numpy.complex128)
    status = saGetIQ_64f(device, iq)
    return {
        "status": status,
        "iq": iq
    }

@error_check
def sa_get_IQ_data_unpacked(device, iq_count, purge):
    iq_data = numpy.zeros(iq_count).astype(numpy.complex64)
    data_remaining = c_int(-1)
    sample_loss = c_int(-1)
    sec = c_int(-1)
    milli = c_int(-1)
    status = saGetIQDataUnpacked(device, iq_data, iq_count, purge, byref(data_remaining), byref(sample_loss), byref(sec), byref(milli))
    return {
        "status": status,
        "iq_data": iq_data,
        "data_remaining": data_remaining.value,
        "sample_loss": sample_loss.value,
        "sec": sec.value,
        "milli": milli.value
    }

@error_check
def sa_get_audio(device):
    audio = numpy.zeros(SA_NUM_AUDIO_SAMPLES).astype(numpy.float32)
    status = saGetAudio(device, audio)
    return {
        "status": status,
        "audio": audio
    }

@error_check
def sa_attach_tg(device):
    return {
        "status": saAttachTg(device)
    }

@error_check
def sa_is_tg_attached(device):
    attached = c_int(-1)
    status = saIsTgAttached(device, byref(attached))
    return {
        "status": status,
        "attached": attached.value
    }

@error_check
def sa_config_tg_sweep(device, sweep_size, high_dynamic_range, passive_device):
    return {
        "status": saConfigTgSweep(device, sweep_size, high_dynamic_range, passive_device)
    }

@error_check
def sa_store_tg_thru(device, flag):
    return {
        "status": saStoreTgThru(device, flag)
    }

@error_check
def sa_set_tg(device, frequency, amplitude):
    return {
        "status": saSetTg(device, c_double(frequency), c_double(amplitude))
    }

@error_check
def sa_set_tg_reference(device, reference):
    return {
        "status": saSetTgReference(device, reference)
    }

@error_check
def sa_get_tg_freq_ampl(device):
    frequency = c_double(-1)
    amplitude = c_double(-1)
    status = saGetTgFreqAmpl(device, byref(frequency), byref(amplitude))
    return {
        "status": status,
        "frequency": frequency.value,
        "amplitude": amplitude.value
    }

@error_check
def sa_config_IF_output(device, input_freq, output_freq, input_atten, output_gain):
    return {
        "status": saConfigIFOutput(device, c_double(input_freq), c_double(output_freq), input_atten, output_gain)
    }

def sa_get_API_version():
    return {
        "api_version": saGetAPIVersion()
    }

def sa_get_product_ID():
    return {
        "product_id": saGetProductID()
    }

def sa_get_error_string(status):
    return {
        "error_string": saGetErrorString(status)
    }
