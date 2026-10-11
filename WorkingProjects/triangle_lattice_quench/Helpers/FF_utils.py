import numpy as np
from random import random
from math import ceil

from triangle_lattice_quench.Helpers import FF_Crosstalk_Helper
from triangle_lattice_quench.Helpers.Compensated_Pulse_Josh import Compensated_Pulse


def FFPlay_Arb(instance, list_of_gains, length_dt, previous_gains, t_start='auto', IQPulseArray=None, waveform_label ="FF"):
    """
    Same as FFPulses_hires, but directly in units of the full gain range [-32766, 32766]
    :param instance: Instance of program (e.g. AveragerProgram or RAveragerProgram)
    :param list_of_gains: gains for all FF channels
    :param length_dt: length in units of 1/16 clock cycle, often corresponds to variable wait
    :param previous_gains: value to pad beginning of IQPulse for commensurability with clock cycles
    :param t_start: time offset to start pulse
    :param IQPulseArray: Assumed to be sampled in units of 1/16 clock cycle
    :param waveform_label: string to label waveform
    :return:
    """
    # if length_dt == 0:
    #     pass
    if IQPulseArray is None:
        print("FFPlay_Arb: IQPulseArray is None, prefer using FFPulses for const pulses instead.")

    IQPulseArray = [None] * len(instance.FFChannels) if IQPulseArray is None else IQPulseArray

    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        channel = instance.FFChannels[i]
        gencfg = instance.soccfg['gens'][channel]
        if IQPulse is None:
            IQPulse = np.ones(length_dt) * gain
        else:
            if np.max(IQPulse) > gencfg['maxv']:
                print(f"IQPulseArray[{i}] goes out of range, exceeds +{+gencfg['maxv']}, clipping.")
                IQPulse[IQPulse > gencfg['maxv']] = gencfg['maxv']
            if np.min(IQPulse) < -gencfg['maxv']:
                print(f"IQPulseArray[{i}] goes out of range, exceeds -{-gencfg['maxv']}, clipping.")
                IQPulse[IQPulse < -gencfg['maxv']] = -gencfg['maxv']

        IQPulse = IQPulse[:length_dt]  # truncate pulse to desired length
        if len(IQPulse) % 16 != 0:  # Pad beginning, len must be a multiple of 16
            extralen = 16 - (len(IQPulse) % 16)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])
        if len(IQPulse) // 16 < 3: # Pad beginning, len is minimum 3 clock cycles * 16 = 48
            extralen = 48 - len(IQPulse)
            IQPulse = np.concatenate([previous_gains[i] * np.ones(extralen), IQPulse])


        instance.add_envelope(ch=channel, name=f"{waveform_label}_{channel}",
                           idata=IQPulse)
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
def FFPlay_Const(instance, list_of_gains, length_us, t_start='auto', waveform_label=None, **kwargs):
    if kwargs:
        print("FFPulses: kwargs:", kwargs)

    if waveform_label is None:
        waveform_label = str(random())

    IQPulseArray = [None] * len(list_of_gains)
    for i, gain in enumerate(list_of_gains):
        channel = instance.FFChannels[i]

        waveform_name = f"{waveform_label}_{channel}"
        # length = instance.us2cycles(length_us, gen_ch=instance.FFChannels[i])
        # gencfg = instance.soccfg['gens'][instance.FFChannels[i]]
        if IQPulseArray[i] is None:
            instance.add_pulse(ch=channel, name=waveform_name,
                           style="const",
                           length=length_us,
                           freq=0,
                           phase=0,
                           gain=gain / 32766, **kwargs
                           )

        if t_start != 'auto':
            t_start_ = t_start + instance.gen_t0[channel]
        else:
            t_start_ = 'auto'

        instance.pulse(ch=channel, name=waveform_name, t=t_start_)

def FFPlay_CompensatedConst(instance, list_of_gains, previous_gains, length_us, t_start='auto', compensated_cycles=80, waveform_label = None):
    """
    Convenience function to do a compensated step pulse followed by a const pulse of arbitrary length, to preserve waveform memory.
    :param instance: Instance of program (e.g. AveragerProgram or RAveragerProgram)
    :param list_of_gains: gains for all FF channels
    :param previous_gains: value to pad beginning of IQPulse for commensurability with clock cycles
    :param length_us: total length of pulse (compensated + const parts)
    :param compensated_cycles: number of clock cycles in the beginning to compensate
    :param waveform_label: string to label waveform
    :param t_start: time offset to start pulse
    :param IQPulseArray: Assumed to be sampled in units of 1/16 clock cycle
    :return:
    """
    assert compensated_cycles > 2, "compensated_cycles must be >= 3"
    print("Using FFPulses_compensated")
    if waveform_label is None:
        waveform_label = str(random())

    IQPulseArray = [Compensated_Pulse(fgain, igain, Qubit=j+1) for j, (igain, fgain) in enumerate(zip(previous_gains, list_of_gains))]

    for i, (gain, IQPulse) in enumerate(zip(list_of_gains, IQPulseArray)):
        channel = instance.FFChannels[i]
        gencfg = instance.soccfg['gens'][channel]
        # print('FFPulse_direct gencfg["maxv"]:', gencfg['maxv'])
        if np.max(IQPulse) > gencfg['maxv']:
            print(f"IQPulseArray[{i}] goes out of range, exceeds +{+gencfg['maxv']}, clipping.")
            IQPulse[IQPulse > gencfg['maxv']] = gencfg['maxv']
        if np.min(IQPulse) < -gencfg['maxv']:
            print(f"IQPulseArray[{i}] goes out of range, exceeds -{-gencfg['maxv']}, clipping.")
            IQPulse[IQPulse < -gencfg['maxv']] = -gencfg['maxv']

        IQPulse = IQPulse[:16*compensated_cycles]  # truncate pulse to desired length

        instance.add_envelope(ch=channel, name=f"{waveform_label}_{channel}",
                           idata=IQPulse, qdata=np.zeros_like(IQPulse))
        instance.add_pulse(ch=channel, name=f"{waveform_label}_{channel}",
                       style="arb",
                       envelope=f"{waveform_label}_{channel}",
                       freq=0,
                       phase=0,
                       gain=1.0, outsel="input")
        # Ensure that total length of pulse matches with cycles2us(length_us) regardless of rounding
        const_length_us = instance.cycles2us(instance.us2cycles(length_us, gen_ch=channel) - compensated_cycles, gen_ch=channel)
        instance.add_pulse(ch=channel, name=f"{waveform_label}_const_{channel}",
                           style="const",
                           length=const_length_us,
                           freq=0,
                           phase=0,
                           gain=gain / 32766,
                           )

        if t_start != 'auto':
            t_start = t_start + instance.gen_t0[channel]
        instance.pulse(ch=channel, name=f"{waveform_label}_{channel}", t=t_start)
        if t_start != 'auto':
            t_start2 = t_start + instance.cycles2us(compensated_cycles, gen_ch=channel)
        else:
            t_start2 = 'auto'
        instance.pulse(ch=channel, name=f"{waveform_label}_const_{channel}", t=t_start2)
        if t_start != 'auto':
            t_start_cycles = instance.us2cycles(t_start)
            t_start2_cycles = instance.us2cycles(t_start2)
            if t_start2_cycles != t_start_cycles + instance.cycles2us(length_us):
                print("Warning: It's possible there is a delay between the compensated part and the const part, check this.")

def FFDefinitions(instance):
    # Start fast flux
    instance.FFChannels = instance.cfg["fast_flux_chs"]
    instance.FFQubits = list(range(len(instance.FFChannels)))

    for channel in instance.FFChannels:
        instance.declare_gen(ch=int(channel))

    instance.FFReadouts = np.asarray(instance.cfg["FF_Readouts"])
    instance.FFReadouts = FF_Crosstalk_Helper.correct(instance.FFReadouts)

    if "FF_Pulses" in instance.cfg:
        instance.FFPulses = np.asarray(instance.cfg["FF_Pulses"])
        instance.FFPulses = FF_Crosstalk_Helper.correct(instance.FFPulses)

    if "FF_Expts" in instance.cfg:
        instance.FFExpts = np.asarray(instance.cfg["FF_Expts"])
        instance.FFExpts = FF_Crosstalk_Helper.correct(instance.FFExpts)

    # Additional delay added to every non-"auto" t value for each channel
    instance.gen_t0 = np.asarray(instance.cfg["fast_flux_delays"])


'''These assume that each pulse name has the format f"{waveform_label}_{channel_num}"'''
def FFPlayWaveforms(instance, waveform_label, t_start='auto'):
    for channel in instance.FFChannels:
        if t_start != 'auto':
            t_start = t_start + instance.gen_t0[channel]

        instance.pulse(ch=channel, name=f"{waveform_label}_{channel}", t=t_start)

def FFInvertWaveforms(instance, waveform_label, t_start='auto'):
    for channel in instance.FFChannels:
        pulse_name = f"{waveform_label}_{channel}"
        gencfg = instance.soccfg['gens'][channel]
        # print("FF_utils.FFInvertWaveforms: gencfg['maxv'] =", gencfg['maxv'])
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
