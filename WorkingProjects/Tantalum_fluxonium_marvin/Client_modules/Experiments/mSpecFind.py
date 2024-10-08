"""
Created on 22nd August 2024
@author: pjatakia
------------------------------
The purpose of the code is to try to find a particular transition in the fluxonium.
This code assumes that you are approximately close to the transtions. Hence, this is recommended to be used in
combination with the Autocalibrator.py
"""
from matplotlib import pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
import scqubits as scq
# Create a class with parent as SpecSlice_bkg_sub

class SpecFind(SpecSlice_bkg_sub):
    """
    Finds the transition frequency by using scqubits to find the exact location
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        self.my_trans = Transmission(path="dataTestTransmission", cfg=cfg, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)

    def findTransition(self, w_trans = None,  debug = False):
        """
        Finds the transition in following steps
        1. Gets the transition (w0) at the voltage point (v0) recommended by the autocalibrator.py
        2. Increase the voltage point by the step (v1) to get a new transition frequency (w1).
        3. Extrapolate or interpolate to get the new recommended transition frequency
        4. Keep applying step 3 till value below the set threshold

        """
        if w_trans is None:
            w_trans = self.cfg['w_trans']

        # Step 1
        if debug:
            print("******* Beginning the search ********")
            print("Searching for transition frequency = ", w_trans, " MHz")
            print("Recommended flux value", self.cfg["flux"])
            print("Recommended yoko value", self.cfg["yokoVoltage"])
        f0 = self.cfg['flux']
        if f0 < 0.5:
            self.dir = -1
        else:
            self.dir = 1
        v0 = self.cfg['yokoVoltage']
        yoko1.SetVoltage(v0)
        self.data0 = self.acquire_calib()
        self.save_data()
        self.save_config()
        w0 = self.data0["data"]['f_reqd']
        if debug:
            self.display()
            print("Transition frequency = ", w0, " MHz")

        # Step 2:
        if w0 < w_trans:
            v1 = v0 + self.dir*self.cfg["volt_step"]
        else:
            v1 = v0 - self.dir*self.cfg["volt_step"]
        yoko1.SetVoltage(v1)
        self.new_file()
        self.data1 = self.acquire_calib()
        self.save_data()
        self.save_config()
        w1 = self.data1["data"]['f_reqd']
        delta = np.abs(w1 - w_trans)
        if debug:
            self.display()
            print("ITERATION 0")
            print("v0 ", v0, " V, w0 ", w0 , " MHz")
            print("v1 ", v1, " V, w1 ", w1, " MHz")
            print("Delta = ", delta, " MHz")

        # Step 3
        itr = 0
        while delta > self.cfg["threshold"] and itr < self.cfg["trials"]:
            v_new = self.getNewValue(w_trans, [v0,v1], [w0,w1])
            yoko1.SetVoltage(v_new)
            self.new_file()
            self.data_new = self.acquire_calib()
            w_new = self.data["data"]["f_reqd"]
            delta = np.abs(w_new - w_trans)
            w0, v0 = w1, v1
            w1, v1 = w_new, v_new
            itr += 1
            if debug:
                self.display()
                print("v0 ", v0, " V, w0 ", w0, " MHz")
                print("v1 ", v1, " V, w1 ", w1, " MHz")
                print("Delta = ", delta, " MHz")

        self.display(plotDisp=False)
        return v1, w1

    def getNewValue(self, w_trans, v, w):
        if w[1] == w[0]:
            v_new = v[1] + self.dir*self.cfg["volt_step"]
        else:
            slope = (v[1] - v[0])/(w[1]- w[0])
            v_new = slope*(w_trans - w[0]) + v[0]
        return v_new

    def acquire_calib(self):
        """
        Runs transmission to get cavity frequency and then runs acquire
        """
        self.my_trans.new_file()
        data_trans = self.my_trans.acquire()
        self.my_trans.display(plotDisp=False)
        self.my_trans.save_data(data_trans)
        self.my_trans.save_config()
        self.cfg['read_pulse_freq'] = self.my_trans.peakFreq

        data_spec = self.acquire()

        return data_spec
