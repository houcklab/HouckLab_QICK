from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from spirack import D5a_module, SPI_rack

import numpy as np
import time

"""
NOT TESTED
"""

class QBLOXchannel(VoltageInterface):
    """
    A Qblox Driver for a single channel. Implemented as a fixed channel D5a_module.
    """

    def __init__(self, channel, spi_rack=None, D5a=None, range_num=2, module=2, reset_voltages=False, num_dacs=16,
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

        if spi_rack is None:
            self.spi_rack = SPI_rack(self.port, self.COM_speed, self.timeout, use_locks=True)
        else:
            self.spi_rack = spi_rack

        if D5a is None:
            self.D5a = D5a_module(self.spi_rack, module=module, reset_voltages=reset_voltages)
            self.set_range(self.range_num)
        else:
            self.D5a = D5a

        print(self.D5a.get_settings(0)[1])

        super().__init__()

    def set_range(self, range_number=None):
        """
        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        """
        # self.spi_rack.unlock()

        DAC = self.DAC
        # time.sleep(2)
        if type(range_number) == int:
            if not self.D5a.get_settings(DAC)[1] == range_number:
                # current_settings = self.D5a.get_settings(DAC)
                self.D5a.change_span(DAC, range_number)
                # self.D5a.set_voltage(DAC, current_settings[0])
        else:
            span = self.D5a.range_4V_bi
            if not self.D5a.get_settings(DAC)[1] == span:
                # current_settings = self.D5a.get_settings(DAC)
                self.D5a.change_span(DAC, span)
                # self.D5a.set_voltage(DAC, current_settings[0])
        # time.sleep(2)

        # self.spi_rack.close()

    def set_voltage(self, voltage, DACs=None):
        """
        Ramp up the voltage (volts) in increments of rampstep, waiting rampinterval between each
        increment to the specified voltage for the specified DAC upon initialization.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: Should not be specified in QBLOXchannel.
        :type DACs: list
        """
        # self.spi_rack.unlock()

        DAC = self.DAC
        if self.D5a.span[self.DAC] == self.D5a.range_4V_uni:
            raise ValueError('Span is set to range_4V_uni (0). Negative values wanted. ')

        current_voltage = self.D5a.get_settings(DAC)[0]
        if np.abs(current_voltage - voltage) < self.ramp_step:  # No ramp up needed
            self.D5a.set_voltage(DAC, voltage)
            return

        steps = np.arange(current_voltage, voltage, np.sign(voltage - current_voltage) * self.ramp_step)
        for v in steps:
            self.D5a.set_voltage(DAC, v)
            time.sleep(self.ramp_interval)
        self.D5a.set_voltage(DAC, voltage)

        # self.spi_rack.close()

    def print_voltages(self):
        self.spi_rack.unlock()

        for i in range(self.D5a._num_dacs):
            print(f'{i}: {np.round(self.D5a.get_settings(i)[0], 4)} V')

        self.spi_rack.close()

    def __del__(self):
        if self.spi_rack:
            self.spi_rack.close()
