from ctypes import *
import os
import subprocess
import sys

def printf(format, *args):
    sys.stdout.write(format % args)
    
def setsignalcore(module=36,output=1,power=-10,freq=10e9):
    cmdstring = "python control_signalcore.py " + str(module) + " " + str(output) + " " + str(power) + " " + str(freq)
    script = '/home/xilinx/jupyter_notebooks/KerrCat/bash_scripts/remotesignalcore.sh'
    cmd0 = ' echo "cd Documents\GitHub\pythonsandbox\PythonDrivers" >> ' + script
    cmd1 = ' echo "' + cmdstring + '" >> ' + script
    cmd2 = 'su - xilinx -c "cat /home/xilinx/jupyter_notebooks/KerrCat/bash_scripts/remotesignalcore.sh | ssh escher@192.168.1.123" '
    subprocess.call('rm ' + script, shell=True)
    out0 = subprocess.check_output(cmd0, shell=True)
    out1 = subprocess.check_output(cmd1, shell=True)
    out2 = subprocess.check_output(cmd2, shell=True)
    printf(out2)
    return