import sys
import numpy as np
import time
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOXchannel import QBLOXchannel, SPIRack

class QBLOX(VoltageInterface):
    """
    A QBLOX Driver.
    """

    def __init__(self, range_num=2, module=2, reset_voltages=False, num_dacs=16,
                 ramp_step=0.003, ramp_interval=0.05, COM_speed=1e6, port='COM3', timeout=1):
        """
        Initializes QBLOX Driver.
        """
        super(QBLOX, self).__init__()

        self.channels = {}
        self.spi_rack = SPIRack(port, COM_speed, timeout)

        for i in range(num_dacs):
            self.channels[i] = QBLOXchannel(i, spi_rack=self.spi_rack, range_num=range_num, module=module,
                                            reset_voltages=reset_voltages, num_dacs=num_dacs, ramp_step=ramp_step,
                                            ramp_interval=ramp_interval, COM_speed=COM_speed, port=port, timeout=timeout)

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

    def __del__(self):
        for channel in self.channels.keys():
            del self.channels[channel]
        if self.spi_rack is not None:
            del self.spi_rack
