# This class is meant to provide the infrastructure needed to interact with the temperature control computer at BFG.

# Import statements:
import numpy as np
import datetime as dt
import time
import os
import PythonDrivers.readTempLog as tempLog

class tempController():
    def __init__(self):
        self.today = dt.date.today()
        self.fridgeTempLogFile = 'Z:/t1Team/logFiles/' + self.today.strftime('%y-%m-%d') + '_BFGTemps_automatedControl.txt'
        self.fridgeControlFile = 'Z:/t1Team/logFiles/fridgeControlFile.txt'
        self.fridgeTempFile = 'Z:/t1Team/logFiles/fridgeTempFile.txt'

    # Define function to write to the heater current percent file:
    def changeHeaterCurrentPercent(self, heaterCurrentPercent):
        # Function expects heaterCurrentPercent to be an integer.
        f = open(self.fridgeControlFile, "w")
        f.write(str(heaterCurrentPercent))
        f.close()

    def setTemp(self, temp):
        # Function expects temperature to be in K (1 mK = 0.001 K)
        f = open(self.fridgeTempFile, "w")
        f.write(str(temp))
        f.close()

    def getLatestLog(self):
        try:
            # read from the log file backwards looking for the last line
            with open(self.fridgeTempLogFile, 'rb') as f:
                try:  # catch OSError in case of a one line file
                    f.seek(-2, os.SEEK_END)
                    while f.read(1) != b'\n':
                        f.seek(-2, os.SEEK_CUR)
                except OSError:
                    f.seek(0)
                lastLine = f.readline().decode()
            lastLineList = lastLine.strip("][").replace("'", '').split(', ')
        except FileNotFoundError:
            assert ('Temperature log file cannot be found')
        except:
            assert ('Error reading temperature log file')
        return lastLineList

    # Define function to read in the fridge data over a given time range:
    def readFridgeTempGeneral(self):  
        logTime, logTemp = tempLog.readTempLog(self.fridgeTempLogFile)
        minutesOld = (dt.datetime.now() - logTime).total_seconds() / 60
        if minutesOld > 30:
            warnings.warn(
                'Temperature log is {0:0.01f} minutes out of date. Make sure you are outputting the log file from the temperature PC'.format(
                    minutesOld))

        return logTemp
    
    def checkIfFridgeStable(self):
        flag = self.getLatestLog()[-1][0]
        return int(flag) == 1

    def waitUntilFridgeStableAfterHeaterChange(self):
        # only run this function after changing the heater current:
        # after changing current percentage, last line of log
        # will still say fridge is stable until the next line comes in
        # this waits until a log line claims the fridge is unstable
        t_end_fast = time.time()+(10*60)
        t_end = time.time()+(60*60)
        wait = True

        # only wait for first unstable log for 10 minutes in case
        # heater wasn't actually changed
        while wait and time.time()<t_end_fast:
            if not self.checkIfFridgeStable():
                wait = False
            time.sleep(1)

        # now wait for a log that claims the fridge is stable
        wait = True
        while wait and time.time()<t_end:
            if self.checkIfFridgeStable():
                wait = False
            time.sleep(1)
        if time.time()<t_end:
            print('Fridge says stable, waiting another 5 minutes')
            time.sleep(5*60)
        else:
            print('Wait function timed out after 1 hour')

        return None

        
        