import numpy as np
import os

def getInputDicts(chipDict,measType='power_sweep',dBm_lookup_file=''):
    inputDicts=[]
    # n = int(chipDict['n_resonators']/2)
    if measType == 'FFS':
        print(os.getcwd())
        dBm_lookup = np.load(os.path.join('..','dBm_lookup',dBm_lookup_file))
        f = dBm_lookup['f']
        dBm = dBm_lookup['dBm']
        for i in range(0,int(chipDict['n_resonators']),2):
            inputDict = chipDict.copy()
            inputDict['gain']=inputDict['gain'][i:i + 2]
            inputDict['names'] = inputDict['names'][i:i + 2]
            inputDict['res_f'] = inputDict['res_f'][i:i + 2]
            inputDict['span_f'] = inputDict['span_f'][i:i + 2]
            try:
                idxs = [np.argmin(np.abs(np.array(f)-inputDict['res_f'][0])),np.argmin(np.abs(np.array(f)-inputDict['res_f'][1]))]
            except:
                idxs = [np.argmin(np.abs(np.array(f)-inputDict['res_f'][0]))]
            inputDict['base_powers'] = dBm[idxs]
            inputDicts.append(inputDict)
    elif measType == 'power_sweep':
        # print(os.getcwd())
        # print(os.path.join(os.getcwd(),'..','dBm_lookup',dBm_lookup_file))
        dBm_lookup = np.load(os.path.join('..','dBm_lookup',dBm_lookup_file))
        f = dBm_lookup['f']
        dBm = dBm_lookup['dBm']
        for i in range(0,int(chipDict['n_resonators']),2):
            inputDict = chipDict.copy()
            inputDict['gain']=inputDict['gain'][i:i + 2]
            inputDict['names'] = inputDict['names'][i:i + 2]
            inputDict['res_f'] = inputDict['res_f'][i:i + 2]
            inputDict['span_f'] = inputDict['span_f'][i:i + 2]
            try:
                idxs = [np.argmin(np.abs(np.array(f)-inputDict['res_f'][0])),np.argmin(np.abs(np.array(f)-inputDict['res_f'][1]))]
            except:
                idxs = [np.argmin(np.abs(np.array(f)-inputDict['res_f'][0]))]
            inputDict['base_powers'] = dBm[idxs]
            inputDicts.append(inputDict)
    return inputDicts