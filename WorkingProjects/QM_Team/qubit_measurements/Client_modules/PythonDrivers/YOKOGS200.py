import sys
import pyvisa as visa
import numpy as np
import time

class YOKOGS200:
    _rampstep = 0.0001 #0.0001 #0.001 # increment step when setting voltage/current
    _rampinterval = 0.01 # dwell time for each voltage step # Default MATLAB is 0.01, CANNOT be lower than 0.001 otherwise fridge heats up

    # Initializes session for device.
    # VISAaddress: address of device, rm: VISA resource manager
    def __init__(self, VISAaddress, rm):
        self.VISAaddress = VISAaddress
        try: self.session = rm.open_resource(VISAaddress)
        except visa.Error as ex:
            sys.stderr.write('Couldn\'t connect to \'%s\', exiting now...' \
                    %VISAaddress)
            sys.exit()

    #==========================================================================#

    # Turn on output
    def OutputOn(self):
        self.session.write('OUTPut 1')

    # Turn off output
    def OutputOff(self):
        self.session.write('OUTPut 0')

    #==========================================================================#

    # Ramp up the voltage (volts) in increments of _rampstep, waiting _rampinterval
    # between each increment.
    def SetVoltage(self, voltage):
        start = self.GetVoltage()
        stop = voltage
        steps = max(1, round(abs(stop-start)/self._rampstep))
        tempvolts = np.linspace(start, stop, num=steps+1, endpoint=True)
        # print(tempvolts)
        self.OutputOn()
        for tempvolt in tempvolts:
            self.session.write(':SOURce:LEVel:AUTO %.8f' %tempvolt)
            time.sleep(self._rampinterval)

    # Ramp up the current (amps) in increments of _rampstep, waiting _rampinterval
    # between each increment.
    def SetCurrent(self, current):
        start = self.GetCurrent()
        stop = current
        steps = max(1, round(abs(stop-start)/self._rampstep))
        tempcurrents = np.linspace(start, stop, num=steps)
        self.OutputOn()
        for tempcurrent in tempcurrents:
            self.session.write(':SOURce:LEVel:AUTO %.8f' %tempcurrent)

    # Set to either current or voltage mode.
    def SetMode(self, mode):
        if not (mode == 'voltage' or mode == 'current'):
            sys.stderr.write("Unknown output mode %s." %mode)
            return
        self.session.write('SOURce:FUNCtion %s' %mode)

    #==========================================================================#

    # Returns the voltage in volts as a float
    def GetVoltage(self):
        self.session.write('SOURce:FUNCtion VOLTage')
        self.session.write('SOURce:LEVel?')
        result = self.session.read()
        return float(result.rstrip('\n'))

    # Returns the current in amps as a float
    def GetCurrent(self):
        self.session.write('SOURce:FUNCtion CURRent')
        self.session.write('SOURce:LEVel?')
        result = self.session.read()
        return float(result.rstrip('\n'))

    # Returns the mode (voltage or current)
    def GetMode(self):
        self.session.write('SOURce:FUNCtion?')
        result = self.session.read()
        result = result.rstrip('\n')
        if result == 'VOLT': return 'voltage'
        else: return 'current'

    #==========================================================================#
