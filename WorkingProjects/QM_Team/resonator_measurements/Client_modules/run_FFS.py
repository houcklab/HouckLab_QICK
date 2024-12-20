from mTempControl import *
from getInputDicts import *
import mResSweepDouble
import tqdm
import time
from contextlib import contextmanager,redirect_stderr,redirect_stdout
from os import devnull

def run_FFS(temps, socs, chipDicts, soccfgs, dBm_lookups=['','','',''],turbo=True):
    print('new')
    for temp in tqdm.tqdm(temps):
        # Step heater percent - note that this means we should include 0 in the heater percents file
        tc = tempController()
        tc.setTemp(temp)
        #tc.changeHeaterCurrentPercent(hp)
        # Wait for temperature to settle - at this point the measurements should be ready to be run
        #tc.waitUntilFridgeStableAfterHeaterChange()
        time.sleep(40*60)
        for soc, chipDict, soccfg, dBm_lookup in zip(socs, chipDicts, soccfgs,dBm_lookups):
            inputDicts = getInputDicts(chipDict, measType='FFS', dBm_lookup_file=dBm_lookup) # may have to move this outside for loop? so that inputDict center gets redefined
            for inputDict in inputDicts:
                if turbo:
                    span_factor = 1.0  # when turbo is on
                else:
                    span_factor = temp * 1000 / 250 # when turbo is off
                inputDict['powers'] = inputDict['base_powers']
                if len(inputDict['span_f']) == 2:
                    inputDict['span_f'] = [span_factor * inputDict['span_f'][0],
                                           span_factor * inputDict['span_f'][1]]
                else:
                    inputDict['span_f'] = [span_factor * inputDict['span_f'][0]]
                # Run initial measurement using current measurement configuration, but with no averaging for speed reasons
                tempReps = inputDict['n_reps']
                tempRounds = inputDict['n_rounds']
                inputDict['n_reps']=1
                inputDict['n_rounds']=1
                Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'],
                                                    prefix='data', inputDict=inputDict, soc=soc,
                                                    soccfg=soccfg, temperatureLogPath=r"Z:\t1Team\LogFiles")
                with open(devnull,'w') as f:
                    with redirect_stderr(f):
                        data = mResSweepDouble.ResSweep.acquire(Instance)

                # Fit trace, and redefine measurement parameters using results of fit
                init_rounds = int(inputDict['n_rounds'])
                for attempt_num in range(3):
                    try:
                        num_lws = 20
                        pOpt, pCov = mResSweepDouble.ResSweep.display(Instance, data)
                        if len(inputDict['res_f']) == 2:
                            inputDict['res_f'] = [pOpt[0][0] / 1e6,
                                                  pOpt[1][0] / 1e6]
                            lw1 = pOpt[0][0] * ((1 / pOpt[0][1]) + (1 / pOpt[0][2])) / 1e6
                            lw2 = pOpt[1][0] * ((1 / pOpt[1][1]) + (1 / pOpt[1][2])) / 1e6
                            inputDict['span_f'] = [num_lws * lw1, num_lws * lw2]
                        else:
                            inputDict['res_f'] = [pOpt[0][0] / 1e6]
                            lw1 = pOpt[0][0] * ((1 / pOpt[0][1]) + (1 / pOpt[0][2])) / 1e6
                            inputDict['span_f'] = [num_lws * lw1]

                        # Re-do the measurement using the new parameters
                        # Reset averaging parameteres
                        inputDict['n_reps']=tempReps
                        inputDict['n_rounds']=tempRounds
                        Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'],
                                                            prefix='data', inputDict=inputDict, soc=soc,
                                                            soccfg=soccfg, temperatureLogPath=r"Z:\t1Team\LogFiles")
                        with open(devnull,'w') as f:
                            with redirect_stderr(f):
                                data = mResSweepDouble.ResSweep.acquire(Instance)

                        # Save the data (write out average temperature, raw trace data, etc)
                        mResSweepDouble.ResSweep.display(Instance, data, fit=False)
                        mResSweepDouble.ResSweep.save_data(Instance, data)
                    except RuntimeError:
                        inputDict['n_rounds'] = init_rounds*(attempt_num+2)
                    else:
                        inputDict['n_rounds'] = init_rounds
                        break
                else:
                    print("Failed to fit trace, skipping this resonator:")
                    print(inputDict['save_path'],inputDict['names'])

def run_TT(socs, chipDicts, soccfgs, turbo=True):
    
    start_time = time.time()
    duration = 12 * 60 * 60
    
    while True:

        for soc, chipDict, soccfg in zip(socs, chipDicts, soccfgs):
            inputDicts = getInputDicts(chipDict, measType='FFS') # may have to move this outside for loop? so that inputDict center gets redefined
            for inputDict in inputDicts:
                if turbo:
                    span_factor = 1.0  # when turbo is on
                else:
                    span_factor = 4.0 # when turbo is off
                inputDict['power'] = inputDict['base_powers']
                if len(inputDict['span_f']) == 2:
                    inputDict['span_f'] = [span_factor * inputDict['span_f'][0],
                                            span_factor * inputDict['span_f'][1]]
                else:
                    inputDict['span_f'] = [span_factor * inputDict['span_f'][0]]
                # Run initial measurement using current measurement configuration, but with no averaging for speed reasons
                tempReps = inputDict['n_reps']
                tempRounds = inputDict['n_rounds']
                inputDict['n_reps']=1
                inputDict['n_rounds']=1
                Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'],
                                                    prefix='data', inputDict=inputDict, soc=soc,
                                                    soccfg=soccfg, temperatureLogPath=r"Z:\t1Team\LogFiles")
                with open(devnull,'w') as f:
                    with redirect_stderr(f):
                        data = mResSweepDouble.ResSweep.acquire(Instance)

                # Fit trace, and redefine measurement parameters using results of fit
                init_rounds = int(inputDict['n_rounds'])
                for attempt_num in range(3):
                    try:
                        pOpt, pCov = mResSweepDouble.ResSweep.display(Instance, data)
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

                        # Re-do the measurement using the new parameters
                        # Reset averaging parameteres
                        inputDict['n_reps']=tempReps
                        inputDict['n_rounds']=tempRounds
                        Instance = mResSweepDouble.ResSweep(path=inputDict['save_path'],
                                                            prefix='data', inputDict=inputDict, soc=soc,
                                                            soccfg=soccfg, temperatureLogPath=r"Z:\t1Team\LogFiles")
                        with open(devnull,'w') as f:
                            with redirect_stderr(f):
                                data = mResSweepDouble.ResSweep.acquire(Instance)

                        # Save the data (write out average temperature, raw trace data, etc)
                        mResSweepDouble.ResSweep.display(Instance, data, fit=False)
                        mResSweepDouble.ResSweep.save_data(Instance, data)
                    except RuntimeError:
                        inputDict['n_rounds'] = init_rounds*(attempt_num+2)
                    else:
                        inputDict['n_rounds'] = init_rounds
                        break
                else:
                    print("Failed to fit trace, skipping this resonator:")
                    print(inputDict['save_path'],inputDict['names'])

        elapsed_time = time.time() - start_time
        if elapsed_time >= duration:
            break

