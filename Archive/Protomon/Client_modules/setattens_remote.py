from ctypes import *
import os
import subprocess
import sys

def printf(format, *args):
    sys.stdout.write(format % args)
    
def setatten(atten=50, serial=27783):
    cmdstring = "python control_atten.py " + str(atten) + " " + str(serial)
    script = '/home/xilinx/jupyter_notebooks/KerrCat/bash_scripts/remoteatten.sh'
    cmd0 = ' echo "cd Documents\GitHub\pythonsandbox\PythonDrivers" >> ' + script
    cmd1 = ' echo "' + cmdstring + '" >> ' + script
    cmd2 = 'su - xilinx -c "cat /home/xilinx/jupyter_notebooks/KerrCat/bash_scripts/remoteatten.sh | ssh escher@192.168.1.123" '
    subprocess.call('rm ' + script, shell=True)
    out0 = subprocess.check_output(cmd0, shell=True)
    out1 = subprocess.check_output(cmd1, shell=True)
    out2 = subprocess.check_output(cmd2, shell=True)
    printf(out2)
    return