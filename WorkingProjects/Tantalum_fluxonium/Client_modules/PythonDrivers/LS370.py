# -*- coding: utf-8 -*-
"""
Created on Tue Aug 15 09:29:45 2023

@author: Jake and Lev
"""

import pyvisa
import time
import numpy as np


class Lakeshore370:
    ### class for controlling the lakeshore 370 model
    def __init__(self, connect_address):
        ### set the lakeshore object
        self.LS370 = connect_address

        self.LS370.timeout = 50000

        ### define some default parameters

        ### set the dfault ramp rate to 50 mK per minute
        self.set_ramp(1, 0.05)

        ### set the lakeshore into PID mode
        self.set_temp_control_mode(1)

        ### set hearter range to 1mA
        self.set_heater_range(4)

        ### Identity string
        self.id_string = self.identity()
        print("Connected to Lakeshore " + self.id_string)

        #### print out the current temperatures
        print("current temps: \n" +
              str(self.get_temp(1)) + 'K, \n' +
              str(self.get_temp(2)) + ' K, \n' +
              str(self.get_temp(5)) + ' K, \n' +
              str(self.get_temp(7)) + ' K, \n'
              )

    def clear_interface(self):
        """ Clears the interface -- does NOT reset the instrument"""
        self.LS370.write('CLS')

    def identity(self):
        """Returns the identity string of the instrument"""
        return self.LS370.query('IDN?').rstrip()

    def get_temp_control_mode(self):
        """Returns the temperature control mode of the instrument.
        1 is closed loop PID
        2 is zone tuning
        3 is open loop
        4 is off """
        while (True):
            try:
                mode = self.LS370.query('CMODE?').rstrip()

                if mode != self.id_string:
                    return mode
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def set_temp_control_mode(self, n):
        """Sets the temperature control mode of the instrument.
        1 is closed loop PID
        2 is zone tuning
        3 is open loop
        4 is off """
        if not int(n) in [1, 2, 3, 4]:
            print('n must be 1, 2, 3, or 4.')
            return
        self.LS370.write('CMODE ' + str(int(n)))

    def get_heater_output(self):
        """Returns the heater output in percent."""
        while (True):
            try:
                output = self.LS370.query('HTR?').rstrip()

                if output != self.id_string:
                    return output
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def get_heater_range(self):
        """Returns the range of the heater.
        0 is off
        1 is 31.6 uA
        2 is 100 uA
        3 is 316 uA
        4 is 1 mA
        5 is 3.16 mA
        6 is 10 mA
        7 is 31.6 mA
        8 is 100 mA."""
        while (True):
            try:
                heater_range = self.LS370.query('HTRRNG?').rstrip()

                if heater_range != self.id_string:
                    return heater_range
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def set_heater_range(self, n):
        """Sets the range of the heater.
        0 is off
        1 is 31.6 uA
        2 is 100 uA
        3 is 316 uA
        4 is 1 mA
        5 is 3.16 mA
        6 is 10 mA
        7 is 31.6 mA
        8 is 100 mA."""
        if not n in [0, 1, 2, 3, 4, 5, 6, 7, 8]:
            print('n must be 0, 1, 2, 3, 4, 5, 6, 7, or 8.')
            return

        while (True):
            try:
                self.LS370.write('HTRRNG ' + str(n))
                return
            except:
                time.sleep(1)

    def heater_status(self):
        """Returns the status ofthe heater:
            0 is no error
            1 is heater open error."""
        return self.LS370.query('HTRST?').rstrip()

    def get_min_max(self, n):
        """Returns the min and max data recorded on channel n."""
        while (True):
            try:
                min_max = self.LS370.query('MDAT? ' + str(n)).rstrip()

                if min_max != self.id_string:
                    return min_max
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def reset_min_max(self):
        """Resets the min and max data for all channels."""
        self.LS370.write('MNMXRST')

    def set_manual_heater_output(self, v):
        """Sets the manual heater output in percent of full scale current."""
        self.LS370.write('MOUT ' + str(v))

    def get_manual_heater_output(self):
        """Returns the manual heater output."""
        while (True):
            try:
                output = self.LS370.query('MOUT?').rstrip()

                if output != self.id_string:
                    return output
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def get_ramp(self):
        """Returns the setpoint ramp parameters.
        First parameter: 0 if off, 1 if on
        Second parameter: ramp rate in K per min."""

        while (True):
            try:
                outp = self.LS370.query('RAMP?').rstrip().split(',')

                if outp != 'LSCI,MODEL370,370AF8,04102008':
                    return [int(outp[0]), float(outp[1])]
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def set_ramp(self, o, r):
        """Sets the setpoint ramp parameters.
        o: 0 if off, 1 if on
        r: rate in K per min, from 0.001 to 10."""

        if o not in [0, 1]:
            print('o must be 0 or 1.')
            return
        if float(r) > 10 or float(r) < 0.001:
            print('Need 0.001 < r < 10.')
            return
        self.LS370.write('RAMP ' + str(o) + ',' + str(r))

    def is_setpoint_ramping(self):
        """Returns whether the setpoint is currently ramping."""
        return self.LS370.query('RAMPST?').rsplit()

    def get_temp(self, chan):
        """Returns the temperature in K of channel chan."""
        while (True):
            try:
                temp = self.LS370.query('RDGK? ' + str(chan)).rstrip()

                if temp != self.id_string:
                    return temp
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def get_controlsetup(self):
        """ returns the control settings for the different channels """

        while (True):
            try:
                setup = self.LS370.query("CSET?")

                if setup != self.id_string:
                    return setup
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def get_setpoint(self):
        """Returns the temperature control setpoint in the control units (likely K)."""
        while (True):
            try:
                setpoint = self.LS370.query('SETP?').rstrip()

                if setpoint != self.id_string:
                    return setpoint
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def set_setpoint(self, s):
        """Sets the temperature control setpoint in the control units."""
        s = s * 1e-3  ### convert to mK

        while (True):
            try:
                self.LS370.write('SETP ' + str(s))
                return
            except:
                time.sleep(1)

    def get_scan(self):
        """ check for which channel is being scanned """
        while (True):
            try:
                scan = self.LS370.query("SCAN?")

                if scan != self.id_string:
                    return scan
                else:
                    time.sleep(1)

            except:
                time.sleep(1)

    def set_scan(self, n, auto):
        """ sets the channel being scanned and toggles autoscan """
        if not n in [1, 2, 5, 7]:
            print('n must be integer 1, 2, 5, or 7')
            return
        if not auto in [0, 1]:
            print('auto must be 0 (autoscan off) or 1 (autoscan on)')
            return

        while (True):
            try:
                self.LS370.write('SCAN ' + str(n) + ', ' + str(auto))
                return
            except:
                time.sleep(1)

    ### define function to set temperature and wait to stabilize
    def set_temp(self, temperature, heater_range=4):

        print("setting temperature: " + str(temperature) + " mK")

        #### set heater setting, if below 10 turn heater off
        if temperature < 10:
            self.set_heater_range(0)
        else:
            self.set_heater_range(heater_range)

        #### set the temperature point
        self.set_setpoint(temperature)

        ### wait 15s initially
        time.sleep(15)

        idx = 0
        while (True):
            idx += 1
            print('current temp: ' + str(self.get_temp(7)) + ' K')
            time.sleep(30)

            if np.abs(float(self.get_temp(7)) - temperature * 1e-3) < 0.001:

                print('almost there! \n'
                      'current temp: ' + str(self.get_temp(7)))
                time.sleep(60)
                temp_diff = np.abs(float(self.get_temp(7)) - temperature * 1e-3)
                if temp_diff < 0.001:
                    print('congrats! \n'
                          'current temp: ' + str(self.get_temp(7)))
                    break
                else:
                    continue

            #### if 15 minutes have paused turn the temp to 0
            if idx >= 30:
                ### set temp to 9mK and turn off heater
                self.set_setpoint(9)

                self.set_heater_range(0)
                print('temp not reached, turnning off heater and trying again')
                time.sleep(300)
                ### turn the heater back on
                self.set_heater_range(heater_range)
                idx = 0

