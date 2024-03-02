import time

import numpy as np

from spirack import SPI_rack, D5a_module


class SPIRack(SPI_rack):

    def __init__(self, port, baud, timeout, use_locks=True):
        super(SPIRack, self).__init__(port, baud, timeout, use_locks)
        self.unlock()  # Unlock the controller to be able to send data

    def __del__(self):
        self.close()


class D5aModule(D5a_module):

    def __init__(self, spi_rack, module, reset_voltages=False, ramp_step=0.003, ramp_interval=0.05, num_dacs=16):
        '''
        :param spi_rack:
        :param module:
        :param reset_voltages:
        :param ramp_step: Voltage ste
        :param ramp_interval:
        :param num_dacs:
        :param span: 4V_bi = 2,
                     2V_bi = 4
        '''

        self.ramp_step = ramp_step
        self.ramp_interval = ramp_interval

        super(D5aModule, self).__init__(spi_rack, module, reset_voltages, num_dacs)


    def set_voltage_ramp(self, DAC, voltage, ramp_step=None, ramp_interval=None):
        DAC = int(DAC)
        print(DAC)
        if self.span[DAC] == self.range_4V_uni:
            raise ValueError('Span is set to range_4V_uni (0). Check connection ')

        if ramp_step is None:
            ramp_step = self.ramp_step

        if ramp_interval is None:
            ramp_interval = self.ramp_interval

        current_voltage = self.get_settings(DAC)[0]
        if np.abs(current_voltage - voltage) < ramp_step:
            self.set_voltage(DAC, voltage)
            return
        steps = np.arange(current_voltage, voltage, np.sign(voltage - current_voltage) * ramp_step)
        for v in steps:
            self.set_voltage(DAC, v)
            time.sleep(ramp_interval)
        self.set_voltage(DAC, voltage)


if __name__ == '__main__':

    COM_speed = 1e6  # Baud rate, doesn't matter much
    timeout = 1  # In seconds
    port = 'COM3'

    from spirack import SPI_rack
    # spi_rack = SPI_rack(port, COM_speed, timeout)
    # spi_rack.close()

    spi_rack = SPIRack(port, COM_speed, timeout)
    # spi_rack = SPI_rack(port, COM_speed, timeout)
    # spi_rack.unlock()

    D5a = D5aModule(spi_rack, module=2, reset_voltages=False)
    for i in range(D5a._num_dacs):
        print(D5a.get_settings(i))

    for i in range(D5a._num_dacs):
        D5a.change_span_update(i, D5a.range_4V_bi)
        D5a.set_voltage_ramp(i, 0)

    for i in range(D5a._num_dacs):
        print(D5a.get_settings(i))

    # 0 to 4 Volt: range_4V_uni (span 0)
    # -4 to 4 Volt: range_4V_bi (span 2)
    # -2 to 2 Volt: range_2V_bi (span 4)

