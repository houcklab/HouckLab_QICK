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
                 ramp_step=0.003, ramp_interval=0.05, COM_speed=1e6, port='COM3', timeout=1):
        """
        Initializes QBLOX Driver.
        """
        super(QBLOX, self).__init__()

        self.channels = {}
        self.num_dacs = num_dacs
        self.spi_rack = SPI_rack(port, COM_speed, timeout, use_locks=True)
        print("Creating D5a")
        print(port, COM_speed, timeout, module, reset_voltages, num_dacs)
        self.D5a = D5a_module(self.spi_rack, module=module, reset_voltages=reset_voltages, num_dacs=num_dacs)

        print(self.D5a.get_settings(0)[1])

        print("Creating Channels")
        for i in range(self.num_dacs):
            self.channels[i] = QBLOXchannel(i, spi_rack=self.spi_rack, D5a=self.D5a, range_num=range_num, module=module,
                                            reset_voltages=reset_voltages, num_dacs=num_dacs, ramp_step=ramp_step,
                                            ramp_interval=ramp_interval, COM_speed=COM_speed, port=port, timeout=timeout)

        # self.spi_rack.unlock()
        # self.spi_rack.close()

        print('yes')

        self.spi_rack.open()
        self.spi_rack.close()

        self.set_range(range_num)

    def set_range(self, range_number=None):
        """
        Set the range of all channels.

        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        """
        self.spi_rack.unlock()

        # time.sleep(2)
        for i in range(self.num_dacs):
            print(f' setting range for channel {i}')
            self.channels[i].set_range(range_number)
        # time.sleep(2)

        self.spi_rack.close()


    def set_voltage(self, voltage, DACs=None):
        """
        Calls the set_voltage function on each channel specified in the DACs list to the voltage given.

        :param voltage: voltage to ramp
        :type voltage: float
        :param DACs: list of DACs to ramp to
        :type DACs: list
        """
        self.spi_rack.unlock()

        for i in DACs:
            self.channels[i].set_voltage(voltage)

        self.spi_rack.close()

        pass

    def __del__(self):
        for i in range(self.num_dacs):
            if i in self.channels:
                del self.channels[i]
        if self.spi_rack is not None:
            self.spi_rack.close()
            del self.spi_rack
