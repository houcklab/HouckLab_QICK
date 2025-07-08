import numpy as np

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
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                raise Exception("IQPulseArray[{}] goes out of range: [{}, {}]".format(i,
                                                                                      -gencfg['maxv'],
                                                                                      gencfg['maxv']))

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

        instance.add_pulse(ch=instance.FFChannels[i], name=waveform_label,
                           idata=IQPulse, qdata=np.zeros_like(IQPulse))
        instance.set_pulse_registers(ch=instance.FFChannels[i], freq=0, style='arb',
                                     phase=0, gain=gencfg['maxv'],
                                     waveform=waveform_label, outsel="input")


    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.dac_t0[channel]
        else:
            t_start_ = 'auto'
        instance.pulse(ch=channel, t=t_start_)

def FFPulses(instance, list_of_gains, length_us, t_start='auto', IQPulseArray=None, **kwargs):
    for i, gain in enumerate(list_of_gains):
        length = instance.us2cycles(length_us, gen_ch=instance.FFChannels[i])
        # print(length)
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        IQPulseArray = [None] * len(list_of_gains) if IQPulseArray is None else IQPulseArray

        if IQPulseArray[i] is None:
            instance.set_pulse_registers(ch=instance.FFChannels[i], style='const', freq=0, phase=0,
                                         gain=gain,
                                         length=length, **kwargs)
        else:
            raise ValueError("Obsoleted, use FFPulses_direct for arbitrary waveforms.")

    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
            # t_start_ += instance.dac_t0[channel]
        else:
            t_start_ = 'auto'
            # t_start_ = int(instance._dac_ts[channel]) + instance.dac_t0[channel]
        # print(t_start_)
        instance.pulse(ch=channel, t=t_start_)

def FFPulses_directPULSE(instance,t_start='auto'):
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
        else:
            t_start_ = 'auto'
        print(f't_start: {t_start_}')
        instance.pulse(ch=channel, t=t_start_)

def FFPulses_directSET_REGS(instance, list_of_gains, length_dt,  previous_gains, IQPulseArray=None, waveform_label = "FF", invert=False, ):
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
        gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            if np.max(IQPulse) > gencfg['maxv'] or np.min(IQPulse) < -gencfg['maxv']:
                raise Exception("IQPulseArray[{}] goes out of range: [{}, {}]".format(i,
                                                                                      -gencfg['maxv'],
                                                                                      gencfg['maxv']))

        IQPulse = IQPulse[:length_dt]  # truncate pulse to desired length

        if len(IQPulse) % 16 != 0:  # need to pad beginning
            extralen = 16 - (len(IQPulse) % 16)

            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        if len(IQPulse) // 16 < 3:

            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])

        instance.add_pulse(ch=instance.FFChannels[i], name=waveform_label,
                           idata=IQPulse, qdata=np.zeros_like(IQPulse))
        instance.set_pulse_registers(ch=instance.FFChannels[i], freq=0, style='arb',
                                     phase=0, gain=gencfg['maxv'] * (-1 if invert else 1),
                                     waveform=waveform_label, outsel="input")


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

def FFPulses_hires(*args, **kwargs):
    raise NotImplementedError("Obsoleted, use FFPulses_direct instead.")

def LoadWaveforms(instance, prev_value=0):
    raise NotImplementedError("Obsoleted, already done in FFPulses and FFPulses_direct.")