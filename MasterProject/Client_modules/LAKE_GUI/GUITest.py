# General imports
import json

import datetime
import importlib
import sys, os, inspect
import time
from time import sleep
import h5py
import numpy as np
from pathlib import Path

from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
soc, soccfg = makeProxy()

# Qt imports
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtCore import Qt, QRect, QMutex
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFileDialog,
    QErrorMessage,
    QMessageBox,
    QSplitter,
)
from PyQt5.QtGui import QIcon
from QDictEdit import QDictEdit
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure


# Custom widgets
from PlotWidget import PlotWidget

# RFSOC imports
from MasterProject.Client_modules.LAKE_GUI.ExperimentThread import ExperimentThread
from qick import RAveragerProgram, AveragerProgram

path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from MasterProject.Client_modules.Calib.initialize import BaseConfig

#############
#### this function should be moved elsewhere
def dictOverride(dict1, dict2):
    ### overrides elements in dict2 with elements from dict1 that overlap
    keys = list(dict2.keys())
    num_elements = len(keys)
    new_dict = {}
    for idx in range(num_elements):
        ### attempt to override the key
        try:
            new_dict[keys[idx]] = dict1[keys[idx]]
        except:
            new_dict[keys[idx]] = dict2[keys[idx]]
    return new_dict
#############

class Window(QMainWindow):
    """
    This class represents the main application window of the GUI.
    It includes all of the UI, as well as functions for running experiments and dealing with the data.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Connect to the RFSOC
        self.soc, self.soccfg = makeProxy()

        self.data = [] # The array that stores the currently-plotted data. The exact format of this may get changed.
        self.dataLock = QMutex() # This is an object used to make data access thread-safe. Not currently necessary
        self.setupUi() # Set up all of the UI


        self.experiment_type = '' # The name of the experiment type, e.g. RAverager
        self.experiment_instance = None # The actual experiment object
        self.experiment_name = '' # The name of the experiment class, e.g. SpecSlice_GUI

        #TODO at some point this needs to be set by the user
        self.outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF4\\"



    def setupUi(self):
        """ This function draws all of the UI elements and attaches signals to them. """
        self.setWindowTitle("RFSOC GUI")
        self.setWindowIcon(QIcon('lake_icon.png'))
        self.resize(2500, 1500)
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        # Set up the font
        font = self.font()
        font.setPointSize(16)
        self.setFont(font)

        # Create and connect widgets
        self.runExperimentButton = QPushButton("Run Experiment!", self)
        self.runExperimentButton.clicked.connect(self.runExperiment)
        self.plotWidget = PlotWidget(parent = self)
        loadExperimentDataButton = QPushButton(self)
        loadExperimentDataButton.setGeometry(QRect(30, 790, 75, 23))
        loadExperimentDataButton.setObjectName("loadExperimentDataButton")
        loadExperimentDataButton.setText("Load data")
        loadExperimentDataButton.clicked.connect(self.loadExperimentData)

        loadExperimentButton = QPushButton(self)
        loadExperimentButton.setObjectName("loadExperimentButton")
        loadExperimentButton.setText("Load experiment ")
        loadExperimentButton.clicked.connect(self.load_experiment_file_open)

        loadConfigButton = QPushButton(self)
        loadConfigButton.setObjectName("loadConfigButton")
        loadConfigButton.setText("Load Config ")
        loadConfigButton.clicked.connect(self.load_config_file_open)

        cancelButton = QPushButton(self)
        cancelButton.setObjectName("STOP")
        cancelButton.setText("STOP!")
        cancelButton.clicked.connect(self.stopExperiment)

        self.experimentNameLabel = QLabel(self)
        self.experimentNameLabel.setText('<html><b>Experiment: none</b></html>')

        # create the dictionary editor
        self.configUpdate = {"Experiment Config": {}, "Base Config": {}}
        self.configUpdate["Experiment Config"] = {
            "test element": 1,
        }
        self.configUpdate["Base Config"] = BaseConfig

        self.configEdit = QDictEdit(self.configUpdate)
        self.configEdit.resize(500, 500)

        # Set the layout
        layout = QVBoxLayout()
        # layout.addStretch()
        topButtonsLayout = QHBoxLayout()
        topButtonsLayout.addWidget(self.runExperimentButton)
        self.centralWidget.setLayout(layout)
        topButtonsLayout.addWidget(loadExperimentDataButton)
        topButtonsLayout.addWidget(loadExperimentButton)
        topButtonsLayout.addWidget(loadConfigButton)
        topButtonsLayout.addWidget(self.experimentNameLabel)
        topButtonsLayout.addWidget(cancelButton)
        layout.addLayout(topButtonsLayout)
        # layout.addWidget(self.plotWidget, 1)

        ### add splitter for plot and config to change size
        layout_plot = QHBoxLayout()
        plotSplitter = QSplitter()
        plotSplitter.addWidget(self.plotWidget)
        plotSplitter.addWidget(self.configEdit)
        ### adjust default size
        plotSplitter.setStretchFactor(0, 3)
        plotSplitter.setStretchFactor(1, 1)
        layout_plot.addWidget(plotSplitter)

        layout.addLayout(layout_plot)

        ### adjust the sizes, make plot 5x larger than labels
        layout.setStretch(0, 1)
        layout.setStretch(1, 5)

########################################################################################################################
#######################################  Signal functions for UI  ######################################################
########################################################################################################################

    def runExperiment(self): # runExperimentButton
        self.thread = QThread() # Thread object
        ### update the config
        UpdateConfig = self.configEdit.config["Experiment Config"]
        BaseConfig  = self.configEdit.config["Base Config"]
        self.config = BaseConfig | UpdateConfig

        ### create names and time stamps for the experiment
        # Dates/times for file names
        experiment_name = self.experiment_name
        date_time_now = datetime.datetime.now()
        date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        date_string = date_time_now.strftime("%Y_%m_%d")

        # Create directories if they don't already exist
        if not Path(self.outerFolder + experiment_name).is_dir():
            os.mkdir(self.outerFolder + experiment_name)
        if not Path(os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string)).is_dir():
            os.mkdir(os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string))

        # Define filenames
        self.data_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
                                     experiment_name + "_" + date_time_string + '.h5')
        self.config_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
                                       experiment_name + "_" + date_time_string + '.json')
        self.image_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
                                      experiment_name + "_" + date_time_string + '.png')

        ### create the experiment
        self.experiment = self.experiment_instance(soccfg, self.config)
        self.worker = ExperimentThread(self.config, soccfg = self.soccfg, exp = self.experiment, soc = self.soc)
        self.worker.moveToThread(self.thread) # Move the ExperimentThread onto the actual QThread from the main loop
        # Step 5: Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.updateData.connect(self.updateData)
        self.worker.RFSOC_error.connect(self.RFSOC_error)
        self.thread.start() # Start the thread

        # Final resets
        self.runExperimentButton.setEnabled(False)
        self.thread.finished.connect( # Connect finished signal to a slot with an in-line function to re-enable the button
            lambda: self.runExperimentButton.setEnabled(True)
        )

    def stopExperiment(self):
        print("STOP!!!!")
        self.worker.stop()
        print("stopped?")

    def loadExperimentData(self): # loadExperimentDataButton
        """
        This function loads the experiment data from an h5 file when the button is pressed.
        Side effects: updates the main window's data variable to what is read from the file, re-plots.
        :return: Nothing
        """
        fname = QFileDialog.getOpenFileName(self, 'Open file',
                                            r"Z:\TantalumFluxonium\Data\2023_07_20_BF2_cooldown_3",
                                            "H5 files (*.h5);;All files (*)")[0]
        if not fname:
            return  # User pressed 'cancel'

        with h5py.File(fname, "r") as f:
            #print(list(f['x_pts']))
            #print(f['avgi'][0][0])
            self.dataLock.lock()
            self.data = f # Update the data variable, might need mutex for safety
            self.dataLock.unlock()
            self._updateCanvas(list(f['x_pts']), f['avgi'][0][0], f['avgq'][0][0])

    def load_experiment_file_open(self): # loadExperimentButton
        """ Runs when the load experiment file button is pressed. """
        filename, ok = QFileDialog.getOpenFileName(self, "Select a File", "..\\", "python files (*.py)",)
        if filename:
            self.loadExperiment(filename)

    def load_config_file_open(self): # loadConfigButton
        """ Runs when the load config file button is pressed. """
        filename, ok = QFileDialog.getOpenFileName(self, "Select a File", "..\\", "json files (*.json)",)
        if filename:
            ### load the dictionary
            file = open(filename)
            newConfig = json.load(file)

            #### override config elements
            newConfigExp = dictOverride(newConfig, self.configEdit.config["Experiment Config"])
            newConfigBase = dictOverride(newConfig, self.configEdit.config["Base Config"])

            self.configEdit.config["Experiment Config"] = newConfigExp
            self.configEdit.config["Base Config"] = newConfigBase
            self.configEdit.set_config()

########################################################################################################################
#########################################  Data/threading functions  ###################################################
########################################################################################################################

    def updateData(self, data):
        """ This function updates the data object of the main window. We have to be careful when doing this with multiple
        threads, because we don't want to corrupt the data. Currently, this is only run by the main window, and thus
        should be thread-safe even without the mutex. """
        self.dataLock.lock() # Make sure no other thread is messing with the data!
        self.data = data
        self.dataLock.unlock() # Release the lock on the mutex

        ### check what set number is being run
        set_num = data['data']['set_num']
        print(set_num)
        if set_num == 0:
            self.data_cur = data
        elif set_num > 0:
            ### average together the data weighting the sets
            avgi = (self.data_cur['data']['avgi'][0][0]*(set_num) + data['data']['avgi'][0][0])/ (set_num+1)
            avgq = (self.data_cur['data']['avgq'][0][0] * (set_num) + data['data']['avgq'][0][0]) / (set_num+1)

            self.data_cur['data']['avgi'][0][0] = avgi
            self.data_cur['data']['avgq'][0][0] = avgq

        self.data['data']['avgi'][0][0] = self.data_cur['data']['avgi'][0][0]
        self.data['data']['avgq'][0][0] = self.data_cur['data']['avgq'][0][0]

        ### create a diction to feed into the plot widget for labels
        plot_labels = {
            "x label": self.experiment.cfg["x_pts_label"],
            "y label": self.experiment.cfg["y_pts_label"],
        }

        ### check for if the y label is none (for single varible sweep) and set the y label to I/Q or amp/phase
        if plot_labels["y label"] == None:
            plot_labels["y label 1"] = "I (a.u.)"
            plot_labels["y label 2"] = "Q (a.u.)"

        self._updateCanvas(data['data']['x_pts'], data['data']['avgi'][0][0], data['data']['avgq'][0][0], plot_labels)
        self.save_data(data, self.data_filename, self.config_filename, self.image_filename)


    def RFSOC_error(self, e):
        """
        Function to run when the RFSOC thread reports an error. Opens up an error box.
        :param e: Exception raised by RFSOC acquire code.
        :return: Nothing
        """
        msgBox = QErrorMessage()
        msgBox.setText("RFSOC error:", e)
        msgBox.setWindowTitle("RFSOC error!.")
        msgBox.exec()

########################################################################################################################
###########################################  Helper functions  #########################################################
########################################################################################################################


    def _updateCanvas(self, x, i, q, labels):
        """ Re-draw the canvas using the provided data. Likely will be changed in the future, including signature. """
        self.plotWidget.plot1(x, i, labels)
        self.plotWidget.plot2(x, q, labels)
        self.plotWidget.drawCanvas()


    def import_file(self, full_path_to_module):
        """
         Function used to import experiment files as module.
        :param full_path_to_module: string
        :return: module_obj: the object representing the imported module
         module_name: the name of the imported module
        """
        try:
            module_dir, module_file = os.path.split(full_path_to_module)
            module_name, module_ext = os.path.splitext(module_file)
            loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
            module_obj = loader.load_module()
            module_obj.__file__ = full_path_to_module
            globals()[module_name] = module_obj
        except Exception as e:
            raise ImportError(e)
        return module_obj, module_name


    def loadExperiment(self, filename):
        """
        This function loads the experiment located at filename. Still figuring out what exactly it will do,
        update comments then.
        :param filename: String from file chooser dialog representing absolute path of file.
        :return: Nothing, so far, uses side effects.
        """
        path = Path(filename)
        # self.filename_edit.setText(str(path))

        print('importing: ' + str(path))

        experiment, self.experiment_name = self.import_file(str(path))
        #print(experiment)
        #print(experiment_name)

        ### create an instance of the class from the file
        for name, obj, in inspect.getmembers(experiment):
            if name == self.experiment_name:
                if inspect.isclass(obj):
                    print("found class instance: " + name)

                    ### create instance of experiment
                    # self.experiment_instance = obj(soccfg, self.config)
                    self.experiment_instance = obj
                    ### reset the config
                    self.configEdit.config["Experiment Config"] = self.experiment_instance.config_template
                    self.configEdit.set_config()

                    ### check what kind of experiment class it is
                    ###
                    if issubclass(obj, AveragerProgram):
                        self.experiment_type = 'Averager'
                        print('RAverager program, good to go!')
                    elif issubclass(obj, RAveragerProgram):
                        self.experiment_type = 'RAverager'
                        print('RAverager program, good to go!')
                    # elif issubclass(obj, super2):
                    #     self.experiment_type = 'super2'
                    #     print('class type: super 2')
                    else:
                        msgBox = QMessageBox()
                        msgBox.setText("Error. Unrecognised class: " + self.experiment_name + ". Restart program.")
                        msgBox.setWindowTitle("Error -- unrecognised class.")
                        msgBox.exec()
                        return
        self.experimentNameLabel.setText('<html><b>Experiment: ' + self.experiment_name + "</b></html>")

    def save_data(self, data, data_filename, config_filename, image_filename):
        """
        This function saves the data passed to it using the experiment name passed to it.
        I am currently passing these as arguments so that they get copied and we don't have problems with multiple
        accesses of the actual class variables, but it may be faster/less memory-intensive to use those instead.
        Think about this more later.
        This program saves the data separately from the config. This is due to the difficulties associated with saving
        Python dictionaries in h5 format, and we can't afford to store the data in plaintext so serialising that way is out.
        Pickling in Python is also a bad option, since it's not general.
        :param data: dictionary containing the data (and config) to be saved.
        :param experiment_name: string containing name of the experiment
        :return: Nothing
        """
        # # Dates/times for file names
        # date_time_now = datetime.datetime.now()
        # date_time_string = date_time_now.strftime("%Y_%m_%d_%H_%M_%S")
        # date_string = date_time_now.strftime("%Y_%m_%d")
        #
        # # Create directories if they don't already exist
        # if not Path(self.outerFolder + experiment_name).is_dir():
        #     os.mkdir(self.outerFolder + experiment_name)
        # if not Path(os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string)).is_dir():
        #     os.mkdir(os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string))
        #
        # # Define filenames
        # data_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
        #                           experiment_name + "_" + date_time_string + '.h5')
        # config_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
        #                           experiment_name + "_" + date_time_string + '.json')
        # image_filename = os.path.join(self.outerFolder + experiment_name, experiment_name + "_" + date_string,
        #                           experiment_name + "_" + date_time_string + '.png')

        # Save data
        data_file = h5py.File(data_filename, 'w') # Create file if does not exist, truncate mode if exists
        data_file.flush() # Notsure what the point of flushing buffers is, inherited from old code
        for key, datum in data['data'].items():
            datum = np.array(datum)
            # I don't know what is the error that this is supposed to catch. I am leaving it here for now, and adding a print
            try:
                data_file.create_dataset(key, shape=datum.shape,
                                    maxshape=tuple([None] * len(datum.shape)),
                                    dtype=str(datum.astype(np.float64).dtype))
            except RuntimeError as e:
                print(e)
                del data_file[key]
                data_file.create_dataset(key, shape=datum.shape,
                                    maxshape=tuple([None] * len(datum.shape)),
                                    dtype=str(datum.astype(np.float64).dtype))
            data_file[key][...] = datum
        data_file.close()

        # Save config
        with open(config_filename, 'w') as config_file:
            json.dump(data['config'], config_file, cls=Window.NpEncoder), #TODO coul dump config directly from self

        #TODO save image
        self.plotWidget.save_fig(image_filename)

    class NpEncoder(json.JSONEncoder):
        """ Ensure json dump can handle np arrays """
        # I took this code from an old Experiment.py, I have no idea whether it's necessary
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super(Window.NpEncoder, self).default(obj)



app = QApplication(sys.argv)
win = Window()
win.show()
sys.exit(app.exec())
