import sys
import pyvisa as visa
import numpy as np
import time
from MasterProject.Client_modules.Desq_GUI.CoreLib.VoltageInterface import VoltageInterface


class YOKOGS200(VoltageInterface):
    """
    A YOKOGS200 Driver.
    """

    def __init__(self, VISAaddress, rm):
        """
        Initializes session for YOKO device. 
        
        :param VISAaddress: VISA address of device
        :type VISAaddress: str
        :param rm: VISA resource manager
        :type rm: VisaResourceManager        
        """
        super(YOKOGS200, self).__init__()

        self.VISAaddress = VISAaddress
        
        # Device parameters and universal constants
        self.maxVoltage = 1.3
        self.rampstep = 0.001 # increment step when setting voltage/current
        self.rampinterval = 0.01  # dwell time for each voltage step # Default MATLAB is 0.01, CANNOT be lower than 0.001 otherwise fridge heats up
        
        # attempt connection
        try: self.session = rm.open_resource(VISAaddress)
        except visa.Error as ex:
            sys.stderr.write('Couldn\'t connect to \'%s\', exiting now...' \
                    %VISAaddress)
            raise ex

    def __del__(self):
        if hasattr(self, "session") and self.session is not None:
            try:
                self.session.close()
                del self.session
            except Exception as e:
                print(f"Warning: Failed to close session: {e}")

    def output_on(self):
        """
        Turn on output.
        """
        self.session.write('OUTPut 1')

    def output_off(self):
        """
        Turn off output.
        """
        self.session.write('OUTPut 0')


    def set_voltage(self, voltage, DACs=None):
        """
        Ramp up the voltage (volts) in increments of rampstep, waiting rampinterval between each
        increment to the specified voltage.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: Should not be specified in YOKOGS200.
        :type DACs: list
        """
        
        if np.abs(voltage) > self.maxVoltage:
            raise ValueError('Voltage greater than maximum voltage [', self.maxVoltage, ']. Reduce or change max.')
            return()

        start = self.GetVoltage()
        stop = voltage
        steps = max(2, round(abs(stop-start)/self.rampstep))
        tempvolts = np.linspace(start, stop, num=steps)

        self.output_on()
        # ramping up loop
        for tempvolt in tempvolts:
            self.session.write(':SOURce:LEVel:AUTO %.8f' %tempvolt) # sets the voltage via VISA
            time.sleep(self.rampinterval)

    # Ramp up the current (amps) in increments of rampstep, waiting rampinterval
    # between each increment.
    def SetCurrent(self, current):
        """
        Ramp up the current (amps) in increments of rampstep, waiting rampinterval between each increment to
        the specified current.

        :param current: current to ramp
        :type current: float
        """

        start = self.GetCurrent()
        stop = current
        steps = max(1, round(abs(stop-start)/self.rampstep))
        tempcurrents = np.linspace(start, stop, num=steps)
        self.output_on()
        for tempcurrent in tempcurrents:
            self.session.write(':SOURce:LEVel:AUTO %.8f' %tempcurrent)

    def SetMode(self, mode):
        """
        Set to either current or voltage mode.

        :param mode: current or voltage
        :type mode: str
        """
        if not (mode == 'voltage' or mode == 'current'):
            sys.stderr.write("Unknown output mode %s." %mode)
            return
        self.session.write('SOURce:FUNCtion %s' %mode)

    def GetVoltage(self):
        """
        Returns the voltage in volts as a float.
        """
        self.session.write('SOURce:FUNCtion VOLTage')
        self.session.write('SOURce:LEVel?')
        result = self.session.read()
        return float(result.rstrip('\n'))

    def GetCurrent(self):
        """
        Returns the current in amps as a float
        """
        self.session.write('SOURce:FUNCtion CURRent')
        self.session.write('SOURce:LEVel?')
        result = self.session.read()
        return float(result.rstrip('\n'))

    def GetMode(self):
        """
        Returns the mode (voltage or current)
        """
        self.session.write('SOURce:FUNCtion?')
        result = self.session.read()
        result = result.rstrip('\n')
        if result == 'VOLT': return 'voltage'
        else: return 'current'


# def main(i):
#     rm = visa.ResourceManager()
#     # VISAaddress = 'GPIB2::2::INSTR'
#     VISAaddress = 'USB0::0x0B21::0x0039::91S929901::0::INSTR' #'USB0::0x0B21::0x0039::91T515414::0::INSTR'
#     yoko = YOKOGS200(VISAaddress, rm)
#     print("Setting voltage to ", i, " Volts")
#     yoko.SetVoltage(i)
#     print("Voltage is ", yoko.GetVoltage(), " Volts")
#     # print("Current is ", yoko.GetCurrent(), " Amps")
#     yoko.GetVoltage()
#     yoko.OutputOn()
#     # time.sleep(5)
#     # yoko.OutputOff()
#
# if __name__ == "__main__":
#     # main(-1)
#     sys.exit(main(sys.argv[1]))

