import sys
import numpy as np
import time
from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOXchannel import QBLOXchannel

class QBLOX(VoltageInterface):
    """
    A QBLOX Driver.
    """

    def __init__(self, num_dacs=16):
        """
        Initializes QBLOX Driver.
        """
        self.channels = {}

        for i in range(num_dacs):
            self.channels[i] = QBLOXchannel(i)

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