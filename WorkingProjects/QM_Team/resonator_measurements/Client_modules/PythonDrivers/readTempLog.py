import os
import datetime
import warnings

def readTempLog(filename):

    try:
        # read from the log file backwards looking for the last line
        with open(filename, 'rb') as f:
            try:  # catch OSError in case of a one line file
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
            lastLine = f.readline().decode()
        lastLineList = lastLine.strip("][").replace("'", '').split(', ')
    except FileNotFoundError:
        assert('Temperature log file cannot be found')
    except:
        assert('Error reading temperature log file')

    return datetime.datetime.strptime(lastLineList[0], '%y-%m-%d %H-%M-%S'), float(lastLineList[4])*1000