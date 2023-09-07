from PythonDrivers.YOKOGS200 import *

yoko69 = YOKOGS200(VISAaddress='GPIB0::1::INSTR', rm=visa.ResourceManager())
yoko70 = YOKOGS200(VISAaddress='GPIB0::2::INSTR', rm=visa.ResourceManager())
yoko71 = YOKOGS200(VISAaddress='GPIB0::3::INSTR', rm=visa.ResourceManager())
yoko72 = YOKOGS200(VISAaddress='GPIB0::4::INSTR', rm=visa.ResourceManager())


yoko69.SetVoltage(0.0)
yoko70.SetVoltage(0.0)
yoko71.SetVoltage(0.0)
yoko72.SetVoltage(0.0)


