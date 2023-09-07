from qick.qick import *

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

class AxisPfbReadoutX8V2(SocIp):
    bindto = ['user.org:user:axis_pfb_readout_v2:1.0']
    REGISTERS = {'freq0_reg':0, 
                 'freq1_reg':1, 
                 'freq2_reg':2, 
                 'freq3_reg':3, 
                 'freq4_reg':4, 
                 'freq5_reg':5,
                 'freq6_reg':6, 
                 'freq7_reg':7,
                 'outsel_reg':8,
                 'ch0sel_reg':9,
                 'ch1sel_reg':10,
                 'ch2sel_reg':11,
                 'ch3sel_reg':12}
    
    # Bits of DDS.
    B_DDS = 32
    NCH = 8
    
    def __init__(self, description, **kwargs):
        """
        Constructor method
        """
        super().__init__(description)
        
        # Default registers.
        self.outsel_reg = 1
        self.ch0sel_reg = 0
        self.ch1sel_reg = 1
        self.ch2sel_reg = 2
        self.ch3sel_reg = 3
        
    # Configure this driver with the sampling frequency.
    def configure(self, fs):
        # Sampling frequency.
        self.fs = fs/(self.NCH/2)
        
        # Frequency step for rounding.
        self.fstep = self.fs/(2**self.B_DDS)                
        
    def set_out(self,sel="product"):
        self.outsel_reg={"product":0,"input":1,"dds":2}[sel]
        
    def set_chsel(self,ch=0, out=0):
        if (out==0):
            self.ch0sel_reg = ch
        elif (out==1):
            self.ch1sel_reg = ch
        elif (out==2):
            self.ch2sel_reg = ch
        elif (out==3):
            self.ch3sel_reg = ch
            
    def set_freq(self, f, ch=0):
        # Sanity check.
        if f<self.fs:
            ki = np.int64(f/self.fstep)            
            if (ch == 0):
                self.freq0_reg = ki
            elif (ch == 1):
                self.freq1_reg = ki
            elif (ch == 2):
                self.freq2_reg = ki
            elif (ch == 3):
                self.freq3_reg = ki
            elif (ch == 4):
                self.freq4_reg = ki
            elif (ch == 5):
                self.freq5_reg = ki
            elif (ch == 6):
                self.freq6_reg = ki
            elif (ch == 7):
                self.freq7_reg = ki
        