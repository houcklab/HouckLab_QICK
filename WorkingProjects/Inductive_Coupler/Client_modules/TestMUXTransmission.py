from initialize import *
cavityAtten.SetAttenuation(35)
qubitAtten.SetAttenuation(35)

yoko75.SetVoltage(0.0)
yoko72.SetVoltage(0.0)
yoko78.SetVoltage(0.0)

# yoko75.rampstep = 0.001

config = {
    # constant for the current firmware
    "res_ch": 6,  # --Fixed
    "ro_chs": [0, 1, 2],  # --Fixed
    "pulse_style": "const",  # --Fixed
    "length": 2 ** 31 - 1,  # [Clock ticks], set to maximum allowable length

    # constant for the given experiment
    "readout_length": readout_length,  # [Clock ticks]
    "relax_delay": relax_delay,  # --Fixed
    "pulse_freqs": pulse_freqs,

    # will be altered during the experiment
    "adc_trig_offset": [],  # [Clock ticks]
    "reps": [],  # --Fixed
    "mixer_freq": [],  # MHz
}

iqListRound = [[] for i in mixerArray_f]
IArray = [np.asarray([0. for ii in mixerArray_f]) for i in range(4)]
QArray = [np.asarray([0. for ii in mixerArray_f]) for i in range(4)]

start = time.time()
# for attenInd, atten in enumerate(attenList):
for roundInd in range(n_rounds):
    roundStart = time.time()
    # ring up the resonator
    config['adc_trig_offset'] = ring_up_time
    config['reps'] = 2
    config['mixer_freq'] = mixerArray_f[0]

    prog = MuxProgram(soccfg, config)
    dummy = prog.acquire(soc, load_pulses=True, debug=False)

    # sweep across the frequency range
    config['adc_trig_offset'] = ring_between_time
    config['reps'] = n_reps
    for fInd, f in enumerate(mixerArray_f):
        config['mixer_freq'] = f
        prog = MuxProgram(soccfg, config)
        iqListRound[fInd] = prog.acquire(soc, load_pulses=True, debug=False)

    # add the frequencies to older measurements
    for IQInd in range(4):
        for freqInd, iq in enumerate(iqListRound):
            IArray[IQInd][freqInd] += np.asarray(iq[0][IQInd])
            QArray[IQInd][freqInd] += np.asarray(iq[1][IQInd])

    print('Round {0}, time {1:0.3f} s'.format(roundInd, time.time() - roundStart))

print('Final time = {0:0.3f} s'.format(time.time() - start))

# normalize measurements and find amplitudes
for i, dummy in enumerate(IArray):
    IArray[i] = IArray[i] / n_rounds
    QArray[i] = QArray[i] / n_rounds
ampArray = [np.abs(IArray[i] + 1j * Q) for i, Q in enumerate(QArray)]
ampArray_log = [10 * np.log10(amp) for amp in ampArray]