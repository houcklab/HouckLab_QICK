from q4diamond.Client_modules.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
import numpy as np
import time

class Qblox():
    def __init__(self, COM_speed = 1e6, port = 'COM3', timeout = 1, reset_voltages = False):
        self.COM_speed = COM_speed
        self.port = port
        self.timeout = timeout
        self.reset_voltages = reset_voltages
    def set_range(self, range_number = None):
        '''
        range_numbers:
        # 0 to 4 Volt: range_4V_uni (span 0)
        # -4 to 4 Volt: range_4V_bi (span 2)
        # -2 to 2 Volt: range_2V_bi (span 4)
        '''
        spi_rack = SPIRack(self.port, self.COM_speed, self.timeout)
        D5a = D5aModule(spi_rack, module=2, reset_voltages=self.reset_voltages)
        time.sleep(2)
        if type(range_number) == int:
            for i in range(D5a._num_dacs):
                if not D5a.get_settings(i)[1] == range_number:
                    current_settings = D5a.get_settings(i)
                    D5a.change_span(i, range_number)
                    D5a.set_voltage(i, current_settings[0])
        else:
            span = D5a.range_4V_bi
            for i in range(D5a._num_dacs):
                if not D5a.get_settings(i)[1] == span:
                    current_settings = D5a.get_settings(i)
                    D5a.change_span(i, span)
                    D5a.set_voltage(i, current_settings[0])
        time.sleep(2)
        spi_rack.close()

    def set_voltage(self, DACs, voltages, ramp_step=None, ramp_interval=None):
        spi_rack = SPIRack(self.port, self.COM_speed, self.timeout)
        D5a = D5aModule(spi_rack, module=2, reset_voltages=self.reset_voltages)
        time.sleep(2)
        for DA, vol in zip(DACs, voltages):
            D5a.set_voltage_ramp(DA, vol, ramp_step=ramp_step, ramp_interval=ramp_interval)
        time.sleep(2)
        spi_rack.close()

    def print_voltages(self):
        spi_rack = SPIRack(self.port, self.COM_speed, self.timeout)
        D5a = D5aModule(spi_rack, module=2, reset_voltages=self.reset_voltages)
        for i in range(D5a._num_dacs):
            print(f'{i}: {np.round(D5a.get_settings(i)[0], 4)} V')
        spi_rack.close()
