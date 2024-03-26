#Set up a yaml file containing the measurement parameters used by the FFS notebook

import yaml
import numpy as np
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
    filename='2023-10-19_cooldown_setup.yaml'

    fullfilename = os.path.join('power_sweep','setup_files',filename)
    try:
        stream = open(fullfilename, 'r')
        setupDict = yaml.full_load(stream)
        stream.close()
    except:
        print('Creating new setup file')
        setupDict={}

    savepath=os.path.join('Z:','t1Team','Data')

    # dBm_lookup_file = r'C:\Users\my\Documents\GitHub\ZCU216\res_dev\dBm_lookup\11_atten_1gold-amp_08-10-2023.npz'
    # dBm_lookup = np.load(dBm_lookup_file)
    # f = dBm_lookup['f']
    # dBm = dBm_lookup['dBm']

    # chip 1
    chipDict = {}
    chipName = '2023-10-12_TAHP02_dep100'
    chipDict['n_resonators'] = 5
    chipDict['names'] = ['5p95', '6p26', '6p53', '6p82', '7p38']
    chipDict['save_path']= os.path.join(savepath,'2023-10-19_cooldown','2023-10-12_TAHP02_dep100','RFSOC','PS')

    chipDict['LO_f'] = 0

    # define frequencies
    chipDict['span_f'] = [0.05,
                          0.03,
                          0.03,
                          0.03,
                          0.06]
    chipDict['res_f'] = [5946.615,
                         6255.0931,
                         6531.8177,
                         6824.4843,
                         7378.945]
    # define numbers of points
    chipDict['n_expts'] = 600  # number of points along the frequency axis
    chipDict['n_roundsList'] = [20,50,100,200,400,800,1600]  # number of times to sweep along the frequency axis
    chipDict['n_repsList'] = [1,1,1,1,1,1,1]  # number of repetitions to take at each frequency point
    # chipDict['n_reps'] = 1

    # timing. Units are clock cycles, but converted from us
    chipDict['ring_up_time'] = 500  # time waiting for the resonator to ring up at the start of each sweep
    chipDict['ring_between_time'] = 50  # time waiting for the resonator to ring up at the start of each sweep
    chipDict['readout_lengthList'] = [10000,10000,10000,10000,10000,10000,10000]  # time to average over
    chipDict['adc_trig_offset'] = 0.1  # time after the DAC starts the final steady pulse before the ADC starts it's read
    # power


    chipDict['basePowers'] = 0  #these get set later through getInputDicts.py
    # idxs = [np.argmin(np.abs(np.array(f)-res_f)) for res_f in chipDict['res_f']]
    # chipDict['basePowers'] = dBm[idxs] # dBm



    chipDict['gain'] = [30000, 30000, 30000, 30000,
                        30000, 30000, 30000]
    chipDict['attenList'] = [0,10,20,30,40,50,60]
    setupDict[chipName]=chipDict

    stream = open(fullfilename, 'w')
    yaml.dump(setupDict, stream)
    stream.close()

if __name__=="__main__":
    main()