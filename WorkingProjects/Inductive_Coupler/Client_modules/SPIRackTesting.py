globals().clear()

from q4diamond.Client_modules.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
import serial
COM_speed = 1e6  # Baud rate, doesn't matter much
timeout = 1  # In seconds
port = 'COM3'
# serial = serial.Serial(port='COM3', baudrate=250000)
with serial.Serial('COM3', 9600, serial.EIGHTBITS,timeout=0,parity=serial.PARITY_NONE,
rtscts=1) as ser:
  print(ser.is_open)
  ser.close()


spi_rack = SPIRack(port, COM_speed, timeout)


D5a = D5aModule(spi_rack, module=2, reset_voltages=False)
# 0 to 4 Volt: range_4V_uni
# -4 to 4 Volt: range_4V_bi
# -2 to 2 Volt: range_2V_bi
D5a.change_span_update(0, D5a.range_4V_bi)
D5a.set_voltage_ramp(0, 0)

print(D5a.get_settings(0)[0])

D5a.change_span_update(1, D5a.range_4V_bi)
D5a.set_voltage_ramp(1, 0)

print(D5a.get_settings(1)[0])

spi_rack.close()

