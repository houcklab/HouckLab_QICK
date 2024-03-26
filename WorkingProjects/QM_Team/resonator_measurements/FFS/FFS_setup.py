#Set up a yaml file containing the measurement parameters used by the FFS notebook

import yaml
import os

# chipDict
# - chip 1
#   - param denoting number of resonators on this chip
#   - resonator 1
#     - sweep params (res_f, span, n_rounds, ... , savepath?)
#   - resonator 2
#   - ...
# - chip 2
# - ...
# -

def main():
    filename='2023-02-29_cooldown_au-chips_NFS_setup.yaml'

    fullfilename = os.path.join('setup_files', filename)
    try:
        stream = open(fullfilename, 'r')
        setupDict = yaml.full_load(stream)
        stream.close()
    except:
        print('Creating new setup file')
        setupDict={}

    savepath=os.path.join('Z:','t1Team','Data')


    # chip 1
    
    chipDict = {}
    chipName = '2024-02-25 TAHP02_Au_StarCryo230518-1+144nm'
    chipDict['n_resonators'] = 4
    chipDict['names'] = ['5p96','6p26','6p54','6p83']
    chipDict['save_path']= os.path.join(savepath,
                                        '2024-02-29_BFG_cooldown',
                                        '2024-02-25_TAHP02_Au+144nm',
                                        'NFS')

    chipDict['LO_f'] = 0

    # define frequencies
    chipDict['span_f'] = [1.2,
                          1.5,
                          1.5,
                          1.5]
    chipDict['res_f'] = [5957.124,
                         6262.567,
                         6536.59,
                         6829.28]
    # define numbers of points
    chipDict['n_expts'] = 700  # number of points along the frequency axis
    chipDict['n_rounds'] = 3  # number of times to sweep along the frequency axis
    chipDict['n_reps'] = 1  # number of repetitions to take at each frequency point
    # chipDict['n_reps'] = 1

    # timing. Units are clock cycles, but converted from us
    chipDict['ring_up_time'] = 500  # time waiting for the resonator to ring up at the start of each sweep
    chipDict['ring_between_time'] = 50  # time waiting for the resonator to ring up at the start of each sweep
    chipDict['readout_length'] = 10000  # time to average over
    chipDict[
        'adc_trig_offset'] = 0.1  # time after the DAC starts the final steady pulse before the ADC starts it's read
    # power
    chipDict['basePower'] = 0  # dBm
    chipDict['gain'] = [30000,30000,30000,30000]

    setupDict[chipName]=chipDict

    stream = open(fullfilename, 'w')
    yaml.dump(setupDict, stream)
    stream.close()

if __name__=="__main__":
    main()