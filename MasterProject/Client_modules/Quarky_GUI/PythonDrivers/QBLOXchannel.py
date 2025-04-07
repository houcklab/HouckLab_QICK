from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from spirack import D5a_module, SPI_rack

import numpy as np
import time

"""
NOT TESTED
"""

class QBLOXchannel(D5a_module, VoltageInterface):
    """
    A Qblox Driver for a single channel. Implemented as a fixed channel D5a_module.
    """

    def __init__(self, channel, spi_rack=None, range_num=2, module=2, reset_voltages=False, num_dacs=16,
                 ramp_step=0.003, ramp_interval=0.05, COM_speed=1e6, port='COM3', timeout=1):
        """
        Initializes a single Qblox channel.
        """
        self.DAC = int(channel)

        self.ramp_step = ramp_step
        self.ramp_interval = ramp_interval
        self.COM_speed = COM_speed
        self.port = port
        self.timeout = timeout

        self.range_num = range_num
        self.set_range(self.range_num)

        if spi_rack is None:
            self.spi_rack = SPIRack(self.port, self.COM_speed, self.timeout)
        else:
            self.spi_rack = spi_rack

        super(QBLOXchannel, self).__init__(self.spi_rack, module=module,
                                           reset_voltages=reset_voltages, num_dacs=num_dacs)


    def set_range(self, range_number = None):
        '''
        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        '''
        self.spi_rack.unlock()

        time.sleep(2)
        if type(range_number) == int:
            for i in range(self._num_dacs):
                if not self.get_settings(i)[1] == range_number:
                    current_settings = self.get_settings(i)
                    self.change_span(i, range_number)
                    self.set_voltage(i, current_settings[0])
        else:
            span = self.range_4V_bi
            for i in range(self._num_dacs):
                if not self.get_settings(i)[1] == span:
                    current_settings = self.get_settings(i)
                    self.change_span(i, span)
                    self.set_voltage(i, current_settings[0])
        time.sleep(2)

        self.spi_rack.close()

    def set_voltage(self, voltage, DACs=None):
        """
        Ramp up the voltage (volts) in increments of rampstep, waiting rampinterval between each
        increment to the specified voltage for the specified DAC upon initialization.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: Should not be specified in QBLOXchannel.
        :type DACs: list
        """
        self.spi_rack.unlock()

        DAC = self.DAC
        if self.span[self.DAC] == self.range_4V_uni:
            raise ValueError('Span is set to range_4V_uni (0). Check connection ')

        current_voltage = self.get_settings(DAC)[0]
        if np.abs(current_voltage - voltage) < self.ramp_step:
            self.set_voltage(DAC, voltage)
            return
        steps = np.arange(current_voltage, voltage, np.sign(voltage - current_voltage) * self.ramp_step)
        for v in steps:
            self.set_voltage(DAC, v)
            time.sleep(self.ramp_interval)
        self.set_voltage(DAC, voltage)

        self.spi_rack.close()

    def print_voltages(self):
        self.spi_rack.unlock()

        for i in range(self._num_dacs):
            print(f'{i}: {np.round(self.get_settings(i)[0], 4)} V')

        self.spi_rack.close()

    def __del__(self):
        self.spi_rack.close()

class SPIRack(SPI_rack):

    def __init__(self, port, baud, timeout, use_locks=True):
        super(SPIRack, self).__init__(port, baud, timeout, use_locks)
        # self.unlock()  # Unlock the controller to be able to send data

    def __del__(self):
        self.close()