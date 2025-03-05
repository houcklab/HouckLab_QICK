import numpy as np


# def LoadWaveforms_initial(instance, gains, length):
#     """
#     Load initialization waveform into FF channel
#     :param instance:
#     :param length:
#     :return:
#     """
#     for i, gain in enumerate(gains):
#         gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
#         instance.set_pulse_registers(ch=instance.FFChannels[i], style='const', freq=0, phase=0,
#                                      gain=gain, length=length)

def LoadWaveforms(instance, prev_value=0):
    if type(prev_value) in [int, float]:
        prev_value = [prev_value] * len(instance.FFChannels)
    for gain, IQPulse, FFChannel, prev_val in zip(instance.FFExpts, instance.cfg["IDataArray"], instance.FFChannels,
                                                  prev_value):
        # print("prev val {}, gain {}".format(prev_val, gain))
        gencfg = instance.soccfg['gens'][FFChannel]
        if IQPulse is None:  # if not specified, assume constant of max value
            # print("IQPulse is none, setting to length ", instance.cfg['FFlength'])
            IQPulse = gain * np.ones(instance.cfg['FFlength'])
        # add buffer to beginning of IQPulse
        IQPulse = np.concatenate([prev_val * np.ones(48), IQPulse])
        # print(IQPulse[:48 + 16])
        # now iterate through and add pulses
        for i in range(1, 17):
            # create shifted pulse. Note all pulses are len(IQPulse) + 2 clock cycles!
            idata = IQPulse[i:len(IQPulse) - 16 + i]
            instance.add_pulse(ch=FFChannel, name=str(i), idata=idata, qdata=np.zeros_like(idata))
        # set pulse register because we want to save the correct one (in register 4)
        instance.set_pulse_registers(ch=FFChannel, freq=0, phase=0, gain=gencfg['maxv'], style='arb',
                                     waveform='1', outsel="input")


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
    IQPulseArray = [None] * len(instance.FFChannels) if IQPulseArray is None else IQPulseArray

    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        # print("prev val {}, gain {}".format(previous_gains[i], gain))
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulse is None:
            # print("[IQPulse] Using array of {}".format(gencfg['maxv']))
            IQPulse = np.ones(length_dt) * gain
        else:
            # print("[IQPulse] Using custom array in gain units, assuming sampling per 1/16 clock cycle")

            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                raise Exception("IQPulseArray[{}] goes out of range: [{}, {}]".format(i,
                                                                                      -gencfg['maxv'],
                                                                                      gencfg['maxv']))

        IQPulse = IQPulse[:length_dt]  # truncate pulse to desired length
        if len(IQPulse) % 16 != 0:  # need to pad beginning
            extralen = 16 - (len(IQPulse) % 16)
            # print("  Padding pulse beginning: length {}, value {}".format(extralen, padval))
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        if len(IQPulse) // 16 < 3:
            # print("  Padding pulse to 3ccs")
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
            # print(IQPulse[:48])
        # print(IQPulse)
        # print(len(IQPulse))

        # figure out name and add pulse
        # print("waveforms: ", instance._gen_mgrs[i].pulses.keys())
        # print("IQPulse[:48]:", i, IQPulse[:48])
        instance.add_pulse(ch=instance.FFChannels[i], name=waveform_label,
                           idata=IQPulse, qdata=np.zeros_like(IQPulse))
        instance.set_pulse_registers(ch=instance.FFChannels[i], freq=0, style='arb',
                                     phase=0, gain=gencfg['maxv'],
                                     waveform=waveform_label, outsel="input")

    # for channel in instance.FFChannels:
    #     if t_start != 'auto':
    #         t_start += instance.dac_t0[channel]
    #     instance.pulse(ch=channel, t=t_start)
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.dac_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)


def FFPulses_hires(instance, list_of_gains, length_dt, t_start='auto', IQPulseArray=None, padval=0, waveform_label = 'FF'):
    """
    Same as FFPulses, but all in units of 1/16 clock cycle
    :param instance: Instance of program (e.g. AveragerProgram or RAveragerProgram)
    :param list_of_gains: gains for all FF channels
    :param length_dt: length in units of 1/16 clock cycle, often corresponds to variable wait
    :param waveform_label: string to label waveform
    :param t_start: time offset to start pulse
    :param IQPulseArray: Assumed to be sampled in units of 1/16 clock cycle
    :param padval: value to pad beginning of IQPulse for commensurability with clock cycles
    :return:
    """
    IQPulseArray = [None] * len(list_of_gains) if IQPulseArray is None else IQPulseArray

    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulse is None:
            # print("[IQPulse] Using array of ones")
            IQPulse = np.ones(length_dt)
        # else:
            # print("[IQPulse] Using custom array, assuming sampling per 1/16 clock cycle")

        IQPulse = IQPulse[:length_dt]  # truncate pulse to desired length
        if len(IQPulse) % 16 != 0:  # need to pad beginning
            extralen = 16 - (len(IQPulse) % 16)
            # print("  Padding pulse beginning: length {}, value {}".format(extralen, padval))
            IQPulse = np.concatenate([padval * np.ones(extralen), IQPulse])
        if len(IQPulse) // 16 < 3:
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([padval * np.ones(extralen), IQPulse])

        # convert to idata and qdata
        maxval = max(np.max(np.abs(IQPulse)), 1)
        idata = (IQPulse * gencfg['maxv'] * gencfg['maxv_scale']) / maxval
        # IQPulse[IQPulse > gencfg['maxv'] * gencfg['maxv_scale']] = gencfg['maxv'] * gencfg['maxv_scale']
        qdata = np.zeros_like(IQPulse) * gencfg['maxv']

        # figure out name and add pulse
        instance.add_pulse(ch=instance.FFChannels[i], name=waveform_label,
                           idata=idata, qdata=qdata)
        instance.set_pulse_registers(ch=instance.FFChannels[i], freq=0, style='arb',
                                     phase=0, gain=int(gain * maxval),
                                     waveform=waveform_label, outsel="input")

    # for channel in instance.FFChannels:
    #     if t_start != 'auto':
    #         t_start += instance.dac_t0[channel]
    #     instance.pulse(ch=channel, t=t_start)
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.dac_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)

def FFPulses(instance, list_of_gains, length_us, t_start='auto', IQPulseArray=None, waveform_label="FF"):
    for i, gain in enumerate(list_of_gains):
        length = instance.us2cycles(length_us, gen_ch=instance.FFChannels[i])
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        IQPulseArray = [None] * len(list_of_gains) if IQPulseArray is None else IQPulseArray

        if IQPulseArray[i] is None:
            instance.set_pulse_registers(ch=instance.FFChannels[i], style='const', freq=0, phase=0,
                                         gain=gain,
                                         length=length)
        else:
            # print('Using IQPulseArray')
            if length > len(IQPulseArray[i]):  # pulse array only has 1 clock cycle (2.4 ns) resolution
                additional_array = np.ones(length - len(IQPulseArray[i]))
            else:
                additional_array = np.array([])
            # print(np.array(IQPulseArray[i][:length]), additional_array)
            idata = np.concatenate([np.array(IQPulseArray[i][:length]), additional_array])  # ensures
            # print(idata)
            maximum_value = np.max(np.abs(idata))
            if maximum_value < 1:
                maximum_value = 1
            idata = idata.repeat(16)  # if you want more resolution, remove this and add it in your definition
            idata = (idata * gencfg['maxv'] * gencfg['maxv_scale']) / maximum_value
            idata[idata > gencfg['maxv'] * gencfg['maxv_scale']] = gencfg['maxv'] * gencfg['maxv_scale']
            qdata = np.zeros(length * 16) * gencfg['maxv']
            instance.add_pulse(ch=instance.FFChannels[i], name=waveform_label,
                           idata=idata, qdata=qdata)
            instance.set_pulse_registers(ch=instance.FFChannels[i], freq=0, style='arb',
                                     phase=0, gain=int(gain * maximum_value),
                                     waveform=waveform_label, outsel="input")

    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.dac_t0[channel]
            # t_start_ += instance.dac_t0[channel]
        else:
            t_start_ = 'auto'
            # t_start_ = int(instance._dac_ts[channel]) + instance.dac_t0[channel]
        # print(t_start_)
        instance.pulse(ch=channel, t=t_start_)


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




