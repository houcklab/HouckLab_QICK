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

    def __init__(self, channel, range_num=2, module=2, reset_voltages=False, num_dacs=16,
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
        self.module = module
        self.reset_voltages = reset_voltages
        self.num_dacs = num_dacs

        # self.set_range(range_num)
        # self.get_voltage()

        super().__init__()

    def set_range(self, range_number=None):
        """
        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        """
        spi_rack = SPI_rack(self.port, self.COM_speed, self.timeout, use_locks=True)
        D5a = D5a_module(spi_rack, module=self.module, reset_voltages=self.reset_voltages, num_dacs=self.num_dacs)

        DAC = self.DAC
        time.sleep(1)
        if type(range_number) == int:
            if not D5a.get_settings(DAC)[1] == range_number:
                current_settings = D5a.get_settings(DAC)
                D5a.change_span(DAC, range_number)
                D5a.set_voltage(DAC, current_settings[0])
        else:
            span = D5a.range_4V_bi
            if not D5a.get_settings(DAC)[1] == span:
                current_settings = D5a.get_settings(DAC)
                D5a.change_span(DAC, span)
                D5a.set_voltage(DAC, current_settings[0])
        time.sleep(1)

        spi_rack.close()

    def set_voltage(self, voltage, DACs=None):
        """
        Ramp up the voltage (volts) in increments of rampstep, waiting rampinterval between each
        increment to the specified voltage for the specified DAC upon initialization.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: Should not be specified in QBLOXchannel.
        :type DACs: list
        """

        spi_rack = SPI_rack(self.port, self.COM_speed, self.timeout, use_locks=True)
        D5a = D5a_module(spi_rack, module=self.module, reset_voltages=self.reset_voltages)

        # Slow ramp up
        DAC = self.DAC
        if D5a.span[self.DAC] == D5a.range_4V_uni:
            raise ValueError('Span is set to range_4V_uni (0). Negative values wanted. ')
        current_voltage = D5a.get_settings(DAC)[0]
        if np.abs(current_voltage - voltage) < self.ramp_step:  # No ramp up needed
            D5a.set_voltage(DAC, voltage)
            return

        steps = np.arange(current_voltage, voltage, np.sign(voltage - current_voltage) * self.ramp_step)
        for v in steps:
            D5a.set_voltage(DAC, v)
            time.sleep(self.ramp_interval)
        D5a.set_voltage(DAC, voltage)

        spi_rack.close()
        return voltage

    def get_voltage(self):

        spi_rack = SPI_rack(self.port, self.COM_speed, self.timeout, use_locks=True)
        D5a = D5a_module(spi_rack, module=self.module, reset_voltages=self.reset_voltages)
        DAC = self.DAC
        curr_voltage = D5a.get_settings(DAC)[0]

        # print(f'{DAC}: {np.round(curr_voltage, 4)} V')
        spi_rack.close()

        return curr_voltage
