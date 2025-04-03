# Import parts of the SPI Rack library
from spirack import SPI_rack, D5a_module, S4g_module
import time

COM_speed = 1e6 # Baud rate, doesn't matter much
timeout = 1 # In seconds

spi_rack = SPI_rack('COM3', COM_speed, timeout)
spi_rack.unlock() # Unlock the controller to be able to send data

D5a = D5a_module(spi_rack, module=2, reset_voltages=False)

# for idx in range(100):
#     D5a = D5a_module(spi_rack, module=idx, reset_voltages=False)
#     D5a.set_voltage(0, 1.0)
#     print(idx)

# D5a.change_span_update(1, D5a.range_2V_bi)
#
# stepsize =  D5a.get_stepsize(1) # Get the stepsize of DAC 1
# print("Stepsize: " + str(stepsize) + " V")

# Changing the output by voltage
D5a.set_voltage(0, 0.31)

