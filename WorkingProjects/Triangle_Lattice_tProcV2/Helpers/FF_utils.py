import numpy as np
from random import random
from math import ceil

def FFPulses_direct(instance, list_of_gains, length_dt,  previous_gains, t_start='auto', IQPulseArray=None, waveform_label = "FF"):
    """
    Same as FFPulses_hires, but directly in units of the full gain range [-32766, 32766]
    :param instance: Instance of program (e.g. AveragerProgram or RAveragerProgram)
    :param list_of_gains: gains for all FF channels
    :param length_dt: length in units of 1/16 clock cycle, often corresponds to variable wait
    :param previous_gains: value to pad beginning of IQPulse for commensurability with clock cycles
    :param waveform_label: string to label waveform
    :param t_start: time offset to start pulse
    :param IQPulseArray: Assumed to be sampled in units of 1/16 clock cycle
    :return:
    """
    if IQPulseArray is None:
        print("FFPulses_direct: IQPulseArray is None, prefer using FFPulses for const pulses instead.")

    IQPulseArray = [None] * len(instance.FFChannels) if IQPulseArray is None else IQPulseArray

    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        channel = instance.FFChannels[i]
        gencfg = instance.soccfg['gens'][channel]
        # print('FFPulse_direct gencfg["maxv"]:', gencfg['maxv'])
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                # print(IQPulse)
                # print("IQPulseArray[{}] goes out of range: [{}, {}]".format(i, -gencfg['maxv'],
                #                                                                       gencfg['maxv']))
                IQPulse[IQPulse < -gencfg['maxv']] = -gencfg['maxv']
                IQPulse[IQPulse > gencfg['maxv']] =  gencfg['maxv']

        IQPulse = IQPulse[:length_dt]  # truncate pulse to desired length
        # print(f'truncated IQPulse: {IQPulse}')
        if len(IQPulse) % 16 != 0:  # need to pad beginning
            extralen = 16 - (len(IQPulse) % 16)
            # print("  Padding pulse beginning: length {}, value {}".format(extralen, padval))
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        if len(IQPulse) // 16 < 3:
            # print("  Padding pulse to 3ccs")
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
            # print(IQPulse[:48])
        # figure out name and add pulse
        # print("waveforms: ", instance._gen_mgrs[i].pulses.keys())
        # print("IQPulse[:48]:", i, IQPulse[:48], IQPulse[-48:])
        # print(len(IQPulse)/16)
        instance.add_envelope(ch=channel, name=f"{waveform_label}_{channel}",
                           idata=IQPulse, qdata=np.zeros_like(IQPulse))
        instance.add_pulse(ch=channel, name=f"{waveform_label}_{channel}",
                       style="arb",
                       envelope=f"{waveform_label}_{channel}",
                       freq=0,
                       phase=0,
                       gain=1.0, outsel="input")


        if t_start != 'auto':
            t_start = t_start + instance.gen_t0[channel]
        instance.pulse(ch=channel, name=f"{waveform_label}_{channel}", t=t_start)


# For constant FF pulses
def FFPulses(instance, list_of_gains, length_us, t_start='auto', waveform_label=None):
    if waveform_label is None:
        waveform_label = str(random())

    IQPulseArray = [None] * len(list_of_gains)
    for i, gain in enumerate(list_of_gains):
        channel = instance.FFChannels[i]

        waveform_name = f"{waveform_label}_{channel}"
        # print(waveform_name)
        # length = instance.us2cycles(length_us, gen_ch=instance.FFChannels[i])
        # gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulseArray[i] is None:
            # print(instance.FFChannels[i])
            instance.add_pulse(ch=channel, name=waveform_name,
                           style="const",
                           length=length_us,
                           freq=0,
                           phase=0,
                           gain=gain / 32766,
                           )

        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
            # t_start_ += instance.dac_t0[channel]
        else:
            t_start_ = 'auto'

        instance.pulse(ch=channel, name=waveform_name, t=t_start_)

def FFDefinitions(instance):
    # Start fast flux
    instance.FFQubits = sorted(instance.cfg["FF_Qubits"].keys())
    instance.FFChannels = [instance.cfg["FF_Qubits"][q]['channel'] for q in instance.FFQubits]

    for channel in instance.FFChannels:
        instance.declare_gen(ch=int(channel))

    instance.FFReadouts = np.array([instance.cfg["FF_Qubits"][q]["Gain_Readout"] for q in instance.FFQubits])
    if "Gain_Expt" in instance.cfg["FF_Qubits"][str(1)]:
        instance.FFExpts = np.array([instance.cfg["FF_Qubits"][q]["Gain_Expt"] for q in instance.FFQubits])

    if "Gain_Init" in instance.cfg["FF_Qubits"][str(1)]:
        instance.FFRamp = np.array([instance.cfg["FF_Qubits"][q]["Gain_Init"] for q in instance.FFQubits])

    if "Gain_Pulse" in instance.cfg["FF_Qubits"][str(1)]:
        instance.FFPulse = np.array([instance.cfg["FF_Qubits"][q]["Gain_Pulse"] for q in instance.FFQubits])

    if "Gain_BS" in instance.cfg["FF_Qubits"][str(1)]:
        instance.FFBS = np.array([instance.cfg["FF_Qubits"][q]["Gain_BS"] for q in instance.FFQubits])

    # FFDelays = np.array([instance.cfg["FF_Channels"][str(c)]["delay_time"] for c in instance.FFChannels])
    FFDelays = np.array([instance.cfg["FF_Qubits"][q]["delay_time"] for q in instance.FFQubits])

    if 'Additional_Delays' not in instance.cfg:
        # print('not there')
        instance.cfg['Additional_Delays'] = {}
    # print()
    additional_delay_keys = instance.cfg['Additional_Delays'].keys()
    Additional_delay_channels = [instance.cfg['Additional_Delays'][k]['channel'] for k in additional_delay_keys]
    Additional_delay_times = [instance.us2cycles(instance.cfg['Additional_Delays'][k]['delay_time']) for k in additional_delay_keys]
    # print(additional_delay_keys, Additional_delay_channels, Additional_delay_times)
    instance.gen_t0 = np.array([0] * len(instance._gen_ts))
    instance.gen_t0[instance.FFChannels] = [instance.us2cycles(d) for d in FFDelays]
    instance.gen_t0[Additional_delay_channels] = Additional_delay_times
    instance.gen_t0 = list(instance.gen_t0)

    # print(instance.dac_t0)

'''Load 16 waveforms, one for each starting sample within the first clock cycle. Use for sweeping
the length of arbitrary pulses.'''
def FFLoad16Waveforms(instance, prev_value=0, waveform_label="swept_FF", truncation_length=None):
    if type(prev_value) in [int, float]:
        prev_value = [prev_value] * len(instance.FFChannels)
    if truncation_length is not None:
        truncation_length = ceil(truncation_length / 16) * 16
    for gain, IQPulse, channel, prev_val in zip(instance.FFExpts, instance.cfg["IDataArray"], instance.FFChannels,
                                                  prev_value):
        # print("prev val {}, gain {}".format(prev_val, gain))
        gencfg = instance.soccfg['gens'][channel]
        if IQPulse is None:  # if not specified, assume constant of max value
            # print("IQPulse is none, setting to length ", instance.cfg['FFlength'])
            IQPulse = gain * np.ones(instance.cfg['FFlength'])
        # add buffer to beginning of IQPulse
        IQPulse = np.concatenate([prev_val * np.ones(48), IQPulse[:truncation_length]])
        # print(IQPulse[:48 + 16])
        # now iterate through and add pulses
        for i in range(1, 17):
            # create shifted pulse. Note all pulses are len(IQPulse) + 2 clock cycles!
            idata = IQPulse[i:len(IQPulse) - 16 + i]
            wname = f"{waveform_label}_{i}_{channel}"
            instance.add_envelope(ch=channel, name=wname,
                                  idata=idata, qdata=np.zeros_like(idata))
            instance.add_pulse(ch=channel, name=wname,
                               style="arb", envelope=wname,
                               freq=0, phase=0, gain=1.0, outsel="input")
        # print(len(idata))



def FFPlayWaveforms(instance, waveform_label, t_start='auto'):
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start = t_start + instance.gen_t0[channel]

        instance.pulse(ch=channel, name=f"{waveform_label}_{channel}", t=t_start)

def FFPlayChangeLength(instance, waveform_label, length_src, t_start='auto'):
    for channel in instance.FFChannels:
        pulse_name = f"{waveform_label}_{channel}"
        for wname in instance.list_pulse_waveforms(pulse_name):
            instance.read_wmem(name=wname)
            instance.write_reg(dst='w_length', src= length_src)
            instance.write_wmem(name=wname)

            if t_start != 'auto':
                t_start = t_start + 0# instance.gen_t0[channel]
            instance.pulse(ch=channel, name=pulse_name, t=t_start)

def FFInvertWaveforms(instance, waveform_label, t_start='auto'):
    for channel in instance.FFChannels:
        pulse_name = f"{waveform_label}_{channel}"
        gencfg = instance.soccfg['gens'][channel]
        for wname in instance.list_pulse_waveforms(pulse_name):
            instance.read_wmem(name=wname)
            instance.write_reg(dst='w_gain', src= - gencfg['maxv']) # -32766
            instance.write_wmem(name=wname)

            if t_start != 'auto':
                t_start = t_start + instance.gen_t0[channel]
            instance.pulse(ch=channel, name=pulse_name, t=t_start)

            instance.read_wmem(name=wname)
            instance.write_reg(dst='w_gain', src= + gencfg['maxv']) # + 32766
            instance.write_wmem(name=wname)

