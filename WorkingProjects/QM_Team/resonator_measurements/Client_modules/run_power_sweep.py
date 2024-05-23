from getInputDicts import *
import mResSweepDouble
import tqdm
from PythonDrivers.control_atten import setatten
from PythonDrivers.ldausbcli import CLI_Vaunix_Attn
from contextlib import contextmanager,redirect_stderr,redirect_stdout
from os import devnull

def run_power_sweep(soc,soccfg,chipDict,dBm_lookup_file,channel_number=1):
    inputDicts = getInputDicts(chipDict,measType='power_sweep',dBm_lookup_file=dBm_lookup_file) # may have to move this outside for loop? so that inputDict center gets redefined
    for inputDict in inputDicts:
        attobj = CLI_Vaunix_Attn()
        attobj.set_attenuation(1,20,channel_number)
        print('Time per sweep (2 resonators):',sum(np.multiply(inputDict['n_roundsList'],inputDict['n_repsList']))*(.024*inputDict['n_expts'])/60,'min')
        # Run initial measurement using high power and current measurement configuration
        inputDictTemp = inputDict
        inputDictTemp['n_rounds'] = 1
        inputDictTemp['n_reps'] = 1
        inputDictTemp['readout_length'] = 10000
        inputDictTemp['powers']=inputDict['base_powers']-20
        inputDictTemp['span_f']=inputDict['span_f']  

        Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'],
                                                    prefix='data', inputDict=inputDict, soc=soc,
                                                    soccfg=soccfg, temperatureLogPath=r"Z:\t1Team\LogFiles")
        with open(devnull,'w') as f:
                with redirect_stderr(f):
                    data = mResSweepDouble.ResSweep.acquire(Instance)
        
        pOpt, pCov = mResSweepDouble.ResSweep.display(Instance, data,fit=True)            
        if len(inputDict['res_f']) == 2:
            inputDict['res_f'] = [pOpt[0][0] / 1e6,
              pOpt[1][0] / 1e6]
            lw1 = pOpt[0][0] * ((1 / pOpt[0][1]) + (1 / pOpt[0][2])) / 1e6
            lw2 = pOpt[1][0] * ((1 / pOpt[1][1]) + (1 / pOpt[1][2])) / 1e6
            inputDict['span_f'] = [8. * lw1, 8. * lw2]
        else:
            inputDict['res_f'] = [pOpt[0][0] / 1e6]
            lw1 = pOpt[0][0] * ((1 / pOpt[0][1]) + (1 / pOpt[0][2])) / 1e6
            inputDict['span_f'] = [8. * lw1]

        # Run power sweep with updated parameters
        for i, atten in enumerate(inputDict['attenList']):

            if atten == 20:
                span_factor = 1
            elif atten == 30:
                span_factor = 1
            elif atten == 40:
                span_factor = 1
            elif atten == 50:
                span_factor = 1.1
            elif atten == 60:
                span_factor = 1.2
            elif atten == 70:                                     
                span_factor = 1.3
            elif atten == 80:      
                span_factor = 1.4
            else:
                span_factor = 1

            initialSpan = np.asarray(inputDict['span_f'])
            inputDict['span_f'] = span_factor * initialSpan
            inputDict['powers'] = inputDict['base_powers']-atten
            inputDict['n_rounds'] = inputDict['n_roundsList'][i]
            inputDict['n_reps'] = inputDict['n_repsList'][i]
            inputDict['readout_length'] = inputDict['readout_lengthList'][i]
            attobj.set_attenuation(1,atten,channel_number)
            Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'], prefix='data_p'+str(inputDict['powers']), inputDict=inputDict, soc=soc, soccfg=soccfg)
            with open(devnull,'w') as f:
                with redirect_stderr(f):
                    data = mResSweepDouble.ResSweep.acquire(Instance)
            mResSweepDouble.ResSweep.display(Instance, data, fit=False)
            mResSweepDouble.ResSweep.save_data(Instance, data)