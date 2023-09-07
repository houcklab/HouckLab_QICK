import sys
import pyvisa as visa
#import visa
import numpy as np
import time

class E8257DGenerator:

    # Initializes session for device.
    # VISAaddress: address of device, rm: VISA resource manager
    def __init__(self, VISAaddress, rm):
        self.VISAaddress = VISAaddress
        try: self.session = rm.open_resource(VISAaddress)
        except visa.Error as ex:
            print('Couldn\'t connect to \'%s\', exiting now...' % VISAaddress)
            sys.exit()

    #==========================================================================#

    ## To do, incomplete

    # Turn off power
    def PowerOff(self):
        self.session.write('OUTPut 0')

    # Turn on output
    def OutputOn(self):
        self.session.write('OUTPut ON')

    # Turn off output
    def OutputOff(self):
        self.session.write('OUTPut OFF')

    # Turn on output if state is true, else turn off output
    def SetOutput(self, state):
        if state: self.OutputOn()
        else: self.OutputOff()

    #==========================================================================#

    # Set frequency
    def SetFreq(self, frequency):
        self.session.write('FREQuency %f' %frequency)

    # Set period
    def SetPeriod(self, period):
        self.session.write('FREQuency %f' %1/period)

    # Set power
    def SetPower(self, power):
        self.session.write('POWer %f' %power)

    # Set phase in radians
    def SetPhase(self, phase):
        self.session.write('PHASe %fRAD' %phase)

    # Enables/disables RF modulation
    def SetModulation(self, state):
        if state: self.session.write('OUTPut:MODulation 1')
        else: self.session.write('OUTPut:MODulation 0')

    # Enables/disables pulse modulation
    def SetPulse(self, state):
        if state: self.session.write('PULM:STATe 1')
        else: self.session.write('PULM:STATe 0')

    # Enables/disables ALC circuit
    def SetALC(self, state):
        if state: self.session.write('POWer:ALC 1')
        else: self.session.write('POWer:ALC 0')

    #==========================================================================#

    # Prints the freq
    def GetFreq(self):
        self.session.write('FREQuency?')
        result = self.session.read()
        print("%f" %float(result.rstrip('\n')))

    # Prints the period
    def GetPeriod(self):
        self.session.write('FREQuency?')
        result = self.session.read()
        print("%f" %(1/float(result.rstrip('\n'))))

    # Get power
    def GetPower(self):
        self.session.write('POWer?')
        result = self.session.read()
        print("%f" %float(result.rstrip('\n')))

    def GetPhase(self):
        self.session.write('PHASe?')
        result = self.session.read()
        print("%f" %float(result.rstrip('\n')))

    def GetOutput(self):
        self.session.write('OUTPut?')
        result = self.session.read()
        print("%d" %int(result.rstrip('\n')))

    def GetModulation(self):
        self.session.write('OUTPut:MODulation?')
        result = self.session.read()
        print("%d" %int(result.rstrip('\n')))

    def GetPulse(self):
        self.session.write('PULM:STATe?')
        result = self.session.read()
        print("%d" %int(result.rstrip('\n')))

    def GetALC(self):
        self.session.write('POWer:ALC?')
        result = self.session.read()
        print("%d" %int(result.rstrip('\n')))

    #==========================================================================#


def main(freq,address):
    rm = visa.ResourceManager()
    # VISAaddress = 'GPIB2::28::INSTR' #q1
    VISAaddress = address
    sg = E8257DGenerator(VISAaddress, rm)
    print("Power")
    sg.GetPower()
    print("Freq")
    sg.GetFreq()
    print("Mod")
    sg.GetModulation()

    print("Set freq")
    sg.SetFreq(freq)
    time.sleep(2)

    print("Turn on output")
    sg.SetOutput(True)
    # time.sleep(5)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1],sys.argv[2],sys.argv[3]))
