from ctypes import *
import os
import subprocess
import sys

def printf(format, *args):
    sys.stdout.write(format % args)
    
def setyoko(voltage=0, num='99L'):
    cmdstring = "py control_yoko.py " + str(voltage) + ' ' + num
    script = '/home/xilinx/jupyter_notebooks/ProtomonQubit/bash_scripts/remoteyoko.sh'
    cmd0 = ' echo "cd Documents\GitHub\pythonsandbox\PythonDrivers" >> ' + script
    cmd1 = ' echo "' + cmdstring + '" >> ' + script
    #cmd2 = 'su - xilinx -c "cat /home/xilinx/jupyter_notebooks/ProtomonQubit/bash_scripts/remoteyoko.sh | ssh escher@192.168.1.123" '
    cmd2 = 'su - xilinx -c "cat /home/xilinx/jupyter_notebooks/ProtomonQubit/bash_scripts/remoteyoko.sh | ssh oxfordnew@192.168.1.122" '
    subprocess.call('rm ' + script, shell=True)
    out0 = subprocess.check_output(cmd0, shell=True)
    out1 = subprocess.check_output(cmd1, shell=True)
    out2 = subprocess.check_output(cmd2, shell=True)
    printf(out2)
    return