import sys
import numpy as np
import time
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOXchannel import QBLOXchannel
from spirack import SPI_rack, D5a_module

class QBLOX(VoltageInterface):
    """
    A QBLOX Driver.
    """

    def __init__(self, range_num=2, module=2, reset_voltages=False, num_dacs=16,
                 ramp_step=0.004, ramp_interval=0.005, COM_speed=1e6, port='COM3', timeout=1):
        """
        Initializes QBLOX Driver.
        """
        super(QBLOX, self).__init__()

        self.channels = {}
        self.num_dacs = num_dacs

        for i in range(self.num_dacs):
            self.channels[i] = QBLOXchannel(i, range_num=range_num, module=module,
                                            reset_voltages=reset_voltages, num_dacs=num_dacs, ramp_step=ramp_step,
                                            ramp_interval=ramp_interval, COM_speed=COM_speed, port=port, timeout=timeout)

        self.set_range(range_num)

    def set_range(self, range_number=None):
        """
        Set the range of all channels.

        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        """

        for i in range(self.num_dacs):
            self.channels[i].set_range(range_number)

    def set_voltage(self, voltage, DACs=None):
        """
        Calls the set_voltage function on each channel specified in the DACs list to the voltage given.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: list of DACs to ramp to
        :type DACs: list
        """

        for i in DACs:
            self.channels[i].set_voltage(voltage)

        pass

    def get_voltage(self, DAC=None):
        """
        Calls the get_voltage function on the specified DAC channel

        :param DAC: DAC to get voltage from
        :type DAC: int
        """

        return self.channels[DAC].get_voltage()

    def __del__(self):
        for i in range(self.num_dacs):
            if i in self.channels:
                del self.channels[i]
