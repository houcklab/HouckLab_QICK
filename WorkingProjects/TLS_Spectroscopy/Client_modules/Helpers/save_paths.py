import datetime
import os

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder


def data_path(suffix, qubit="q4", short_directory_names=False):
    now = datetime.datetime.now()
    time_string = now.strftime('%H_%M_%S')
    date_string = now.strftime('%Y_%m_%d')
    subdir = date_string if short_directory_names else (qubit + "_" + date_string)
    data_dir = os.path.join(str(outerFolder), qubit, subdir)
    os.makedirs(data_dir, exist_ok=True)
    stem = (time_string if short_directory_names else qubit + "_" + time_string) + "_" + suffix
    return os.path.join(data_dir, stem)
