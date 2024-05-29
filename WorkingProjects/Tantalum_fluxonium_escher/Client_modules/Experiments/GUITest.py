# https://realpython.com/python-pyqt-qthread/
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import sys
from time import sleep

from PyQt5.QtCore import Qt, QRect, QMutex
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure
import h5py
import numpy as np

### Experiment stuff
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mQubit_ef_spectroscopy_GUI import Qubit_ef_spectroscopy_GUI as Qubit_ef_spectroscopy
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_07_20_BF2_cooldown_3\\TF3SC1\\"
soc, soccfg = makeProxy()
###


# A thread that is used to run the RFSOC experiment when the button is pressed.
# This needs to happen on a separate thread since it takes potentially a very long time, don't want to lock up the ui.
class ExperimentThread(QObject):
    finished = pyqtSignal()
    updateData = pyqtSignal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.clicksCount = 0
        self.config = config

    def run(self):
        """Long-running task."""
        yoko1.SetVoltage(self.config["yokoVoltage"])
        # #
        Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy",
                                                               outerFolder=outerFolder, cfg=self.config, soc=soc,
                                                               soccfg=soccfg, progress=True)
        data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
        Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
        Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
        self.updateData.emit(data_Qubit_ef_spectroscopy)
        # Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, self.fig, data_Qubit_ef_spectroscopy, plotDisp=True)
        self.finished.emit()


class Window(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clicksCount = 0
        self.data = [] # The array that stores the currently-plotted data. The exact format of this may get changed.
        self.dataLock = QMutex()
        self.setupUi()
        ### Experiment stuff
        UpdateConfig = {
            ##### define attenuators
            "yokoVoltage": 0.815,
            ###### cavity
            "read_pulse_style": "const",  # --Fixed
            "read_length": 8,  # us
            "read_pulse_gain": 12000,  # [DAC units]
            "read_pulse_freq": 5988.33,
            # g-e parameters
            "qubit_ge_freq": 1715.6,  # MHz
            "qubit_ge_gain": 20000,  # Gain for pi pulse in DAC units
            ##### spec parameters for finding the qubit frequency
            "qubit_ef_freq_start": 1200,  # 1167-10
            "qubit_ef_freq_step": 0.5,
            "SpecNumPoints": 41,  ### number of points
            "qubit_pulse_style": "arb",
            "qubit_length": 1,  # us, changes experiment time but is necessary for "const" style
            "sigma": 0.300,  ### units us, define a 20ns sigma
            # "qubit_length": 1, ### units us, doesnt really get used though
            # "flat_top_length": 0.025, ### in us
            "relax_delay": 500,  ### turned into us inside the run function
            "qubit_gain": 20000,  # Constant gain to use
            # "qubit_gain_start": 18500, # shouldn't need this...
            "reps": 100,  # number of averages of every experiment
        }
        self.config = BaseConfig | UpdateConfig

    def setupUi(self):
        self.setWindowTitle("Freezing GUI")
        self.resize(1500, 1000)
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        # Create and connect widgets
        self.clicksLabel = QLabel("Counting: 0 clicks", self)
        self.clicksLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.stepLabel = QLabel("Long-Running Step: 0")
        self.stepLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.countBtn = QPushButton("Click me!", self)
        self.countBtn.clicked.connect(self.countClicks)
        self.longRunningBtn = QPushButton("Long-Running Task!", self)
        self.longRunningBtn.clicked.connect(self.runLongTask)
        self.dynamic_canvas = FigureCanvas(Figure(figsize=(5, 3)))
        t = np.linspace(0, 10, 101)
        # Set up a Line2D.
        self._dynamic_ax = self.dynamic_canvas.figure.subplots()
        self._line, = self._dynamic_ax.plot(t, np.sin(t))
        getFileButton = QPushButton(self)
        getFileButton.setGeometry(QRect(30, 790, 75, 23))
        getFileButton.setObjectName("getFileButton")
        getFileButton.setText("Choose a file")
        getFileButton.clicked.connect(self.getfile)
        # Set the layout
        layout = QVBoxLayout()
        layout.addWidget(self.clicksLabel)
        layout.addWidget(self.countBtn)
        layout.addStretch()
        layout.addWidget(self.stepLabel)
        layout.addWidget(self.longRunningBtn)
        self.centralWidget.setLayout(layout)
        layout.addWidget(self.dynamic_canvas)
        layout.addWidget(NavigationToolbar(self.dynamic_canvas, self))
        layout.addWidget(getFileButton)

    def countClicks(self):
        self.clicksCount += 1
        self.clicksLabel.setText(f"Counting: {self.clicksCount} clicks")

    # Be careful!
    def updateData(self, data):
        #self.stepLabel.setText(f"Long-Running Step: {n}")
        print(data)
        self.dataLock.lock()
        print('please?')
        self.data = data
        self.dataLock.unlock()
        print('ok...')
        self._update_canvas(data['data']['x_pts'], data['data']['avgi'][0][0], data['data']['avgq'][0][0])

    def runLongTask(self):
        # Step 2: Create a QThread object
        self.thread = QThread()
        # Step 3: Create a worker object
        self.worker = ExperimentThread(self.config)
        # Step 4: Move worker to the thread
        self.worker.moveToThread(self.thread)
        # Step 5: Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.updateData.connect(self.updateData)
        # Step 6: Start the thread
        self.thread.start()

        # Final resets
        self.longRunningBtn.setEnabled(False)
        self.thread.finished.connect(
            lambda: self.longRunningBtn.setEnabled(True)
        )
        self.thread.finished.connect(
            lambda: self.stepLabel.setText("Long-Running Step: 0")
        )

    def getfile(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file',
                                            r"Z:\TantalumFluxonium\Data\2023_07_20_BF2_cooldown_3\TF3SC1\dataTempSweeps_T1_PS\dataTempSweeps_T1_PS_2023_08_16",
                                            "H5 files (*.h5);;All files (*)")[0]
        if not fname:
            return  # User pressed 'cancel'

        with h5py.File(fname, "r") as f:
            self._update_canvas(list(f['i_0_arr'])[0])

    def _update_canvas(self, x, i, q):
        self._line.set_data(x, i)
        print('got somewhere')
        self._line.figure.canvas.draw()
        print(x)
        print(i)




app = QApplication(sys.argv)
win = Window()
win.show()
sys.exit(app.exec())
