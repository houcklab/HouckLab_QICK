# pip install pyvisa
import pyvisa

class Agilent33250A:
    """
    Minimal GPIB driver for Agilent/Keysight 33250A.
    Supports: selecting NOISE output, setting amplitude (voltage), output ON/OFF.
    """

    def __init__(self, resource="GPIB0::10::INSTR", timeout_ms=5000):
        self.rm = pyvisa.ResourceManager()
        self.awg = self.rm.open_resource(resource)
        self.awg.timeout = timeout_ms
        self.awg.write_termination = "\n"
        self.awg.read_termination = "\n"

    # ---------- output control ----------
    def output_on(self):
        self.awg.write("OUTP ON")

    def output_off(self):
        self.awg.write("OUTP OFF")

    def set_output(self, on: bool):
        self.awg.write(f"OUTP {'ON' if on else 'OFF'}")

    # ---------- amplitude ----------
    def set_voltage(self, amplitude, unit="VPP"):
        """unit ∈ {'VPP','VRMS','DBM'}"""
        self.awg.write(f"VOLT:UNIT {unit}")
        self.awg.write(f"VOLT {amplitude}")

    # ---------- noise ----------
    def set_noise(self, amplitude=None, unit="VPP", offset=None):
        """
        Select NOISE. Optionally set amplitude and/or DC offset.
        (Uses low-level commands so we don't auto-enable output.)
        """
        self.awg.write("FUNC NOIS")
        if unit:
            self.awg.write(f"VOLT:UNIT {unit}")
        if amplitude is not None:
            self.awg.write(f"VOLT {amplitude}")
        if offset is not None:
            self.awg.write(f"VOLT:OFFS {offset}")

    def close(self):
        self.awg.close()
        self.rm.close()


    def set_freq(self, freq):
        self.awg.write('FREQuency %f' % freq)
    def set_period(self, period):
        self.awg.write('FREQuency %s' % str(1/period))

    def set_waveform(self, waveform):
        waveforms_list = ['SIN', 'SQUARE', 'RAMP', 'PULSE', 'NOISE', 'DC']
        self.awg.write('FUNCtion %s' % waveform)

    def set_duty_cycle(self, duty_cycle):
        self.awg.write('FUNCtion:SQUare:DCYCle %.8f' % duty_cycle)

    def set_voltage(self, volt):
        self.awg.write('VOLTage %f' % volt)

    def set_offset(self, offset):
        self.awg.write('VOLTage:OFFSet %f' % offset)


if __name__ == '__main__':
    # ##### running the control
    # duty_cycle = 20
    # waveform = 'SQUARE'
    # freq = 1e6
    # period = 0.1
    # volts = 0.5
    # offset = 0.0

    awg = Agilent33250A(resource = 'GPIB1::13::INSTR')

    # awg.set_waveform(waveform)
    # awg.set_period(period)
    # awg.set_duty_cycle(duty_cycle)
    # awg.set_voltage(volts)
    # awg.set_offset(volts / 2)
    #
    # awg.outputON()