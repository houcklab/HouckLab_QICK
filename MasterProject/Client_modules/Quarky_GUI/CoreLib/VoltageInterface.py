class VoltageInterface:
    """
    The Parent class for all voltage interface classes: Yoko, Qblox.
    Extremely simple, and its purpose is so the GUI can pass references to Yoko or Qblox without caring about the class.
    """

    def __init__(self, interface):
        self.interface = interface

    def set_voltage(self, voltage, DACs=None):
        raise NotImplementedError("Subclasses must implement setVoltage")