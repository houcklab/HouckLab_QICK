from qick import *
import xrfdc
from pynq import allocate

class AxisConstantIQ(SocIp):
    # AXIS Constant IQ registers:
    # REAL_REG : 16-bit.
    # IMAG_REG : 16-bit.
    # WE_REG   : 1-bit. Update registers.
    bindto = ['user.org:user:axis_constant_iq:1.0']
    REGISTERS = {'real_reg':0, 'imag_reg':1, 'we_reg':2}
    
    # Number of bits.
    B = 16
    MAX_V = 2**(B-1)-1
        
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.real_reg = 30000
        self.imag_reg = 30000
        
        # Register update.
        self.update()
        
    def config(self, tile, block, fs):
        self.tile = tile
        self.dac = block
        self.fs = fs

    def update(self):
        self.we_reg = 1        
        self.we_reg = 0
        
    def set_iq(self,i=1,q=1):
        # Set registers.
        self.real_reg = int(i*self.MAX_V)
        self.imag_reg = int(q*self.MAX_V)
        
        # Register update.
        self.update()                

class MrBufferEt(SocIp):
    # Registers.
    # DW_CAPTURE_REG
    # * 0 : Capture disabled.
    # * 1 : Capture enabled (capture started by external trigger).
    #
    # DR_START_REG
    # * 0 : don't send.
    # * 1 : start sending data.
    #
    # DW_CAPTURE_REG needs to be de-asserted and asserted again to allow a new capture.
    # DR_START_REG needs to be de-assereted and asserted again to allow a new transfer.
    #
    bindto = ['user.org:user:mr_buffer_et:1.0']
    REGISTERS = {'dw_capture_reg':0, 'dr_start_reg':1}
        
    def __init__(self, description):    
        # Init IP.
        super().__init__(description)
        
        # Default registers.
        self.dw_capture_reg=0
        self.dr_start_reg=0
        
        # Generics
        self.B = int(description['parameters']['B'])
        self.N = int(description['parameters']['N'])
        self.NM = int(description['parameters']['NM'])

        # Maximum number of samples
        self.MAX_LENGTH = 2**self.N * self.NM          

        # Preallocate memory buffers for DMA transfers.
        self.buff = allocate(shape=self.MAX_LENGTH, dtype=np.int32)        
    
    def config(self, dma, switch):
        self.dma = dma
        self.switch = switch
        
    def transfer(self,ch):
        # Route switch to channel.
        self.switch.sel(slv=ch)
        
        # Start send data mode.
        self.dr_start_reg = 1
        
        # DMA data.        
        buff = self.buff
        self.dma.recvchannel.transfer(buff)
        self.dma.recvchannel.wait()        

        # Stop send data mode.
        self.dr_start_reg = 0
        
        # Format:
        # -> lower 16 bits: I value.
        # -> higher 16 bits: Q value.
        data = buff
        dataI = data & 0xFFFF
        dataQ = data >> 16
        
        return np.stack((dataI,dataQ)).astype(np.int16)        
        
    def enable(self):
        self.dw_capture_reg = 1
        
    def disable(self):
        self.dw_capture_reg = 0
        