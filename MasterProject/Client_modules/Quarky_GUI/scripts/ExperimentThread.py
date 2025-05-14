"""
===================
ExperimentThread.py
===================
The experiment thread is a QObject (not a thread itself) that is used to execute RFSoC experiments. The intended usage
is for an ExterimentThread object to be created, moved to a new QThread, then run. Initialization is very important
by defining the experiment instance and configuration.

It will then communicate with the main program via signals, as intended in Qt, making it thread-safe.
"""

import time
from PyQt5.QtCore import QObject, pyqtSignal, qWarning, qDebug
from qick import AveragerProgram, RAveragerProgram

class ExperimentThread(QObject):
    """
    This class is used to run an RFSOC experiment, meant to be used on a separate QThread than the main loop.
    Communicates to the main GUI thread via signals and emitting data.

    **Important Attributes:**

        * config (dict): The dictionary containing the configuration for the experiment
        * experiment_instance (Class ExperimentClass): The experiment instance
        * soc (Proxy): The RFSoC connection proxy
    """

    finished = pyqtSignal()
    """
    The Signal to send upon experiment execution completion.
    """

    updateData = pyqtSignal(object, object)
    """
    Signal to send when receiving new data, including the new data dictionary

    :param data: The data object.
    :type data: object
    :param exp_instance: The experiment instance object.
    :type exp_instance: object
    """

    intermediateData = pyqtSignal(object, object)
    """
    Signal to send when receiving intermediate data, meaning from within a set, rather than at the end of a set.

    :param data: The data object.
    :type data: object
    :param exp_instance: The experiment instance object.
    :type exp_instance: object
    """

    updateProgress = pyqtSignal(int)
    """
    Signal to send when finishing a set to update the setsComplete bar

    :param sets_completed: The number of sets completed
    :type sets_completed: int
    """

    updateRuntime = pyqtSignal(float, int)
    """
    Signal to send when finishing a set to update the runtime estimations
    
    :param runtime_delta: The runtime delta of the experiment
    :type runtime_delta: float
    :param sets_completed: The number of sets completed
    :type sets_completed: int
    """

    RFSOC_error = pyqtSignal(Exception)
    """
    Signal to send when the RFSoC encounters an error

    :param error: The exception raised by the RFSoC
    :type error: Exception
    """

    def __init__(self, config, soccfg, exp, soc, parent = None):
        """
        Initializes an ExperimentThread object with the actual experiment instance, configuration, and soc connection.
        """

        super().__init__(parent)
        self.config = config # The config file used to run the experiment
        self.parent = parent # We don't actually want to give it the parent window, that can cause blocking
        self.experiment_instance = exp # The object representing an instance of a QickProgram subclass to be run
        self.soc = soc # The RFSOC!

        # ### create the experiment instance (not needed anymore since instance is passed
        # self.experiment_instance = exp(soccfg, self.config)

        if not exp:
            qDebug('Warning: None experiment. Going to crash in 3, 2, 1...')

        # Connecting intermediate data signal if experiment uses it
        if hasattr(self.experiment_instance, 'intermediateData'):
            self.experiment_instance.intermediateData.connect(self.intermediate_data_handler)

    def run(self):
        """
        Run the RFSOC experiment. Each set execution is done with a simple while loop for now. Future implementations
        can change configuration variables at each set iteration. Sends appropriate signals at each set execution to
        update the data and progress bar.
        """

        #yoko1.SetVoltage(self.config["yokoVoltage"]) # this needs to go somewhere else

        self.running = True
        idx_set = 0
        prev_time = time.perf_counter()

        ### loop over all the sets for the data taking
        while self.running and idx_set < self.config["sets"]:

            try:
                data = self.experiment_instance.acquire()
                data['data']['set_num'] = idx_set
            except Exception as e:
                self.RFSOC_error.emit(e)
                self.finished.emit()
                return # Do not want to update data -- no new data was recorded!

            # Emit the signal with new data and update the progress bar with additional set complete
            # Each set clears and recreates the plot (inefficient)
            self.updateData.emit(data, self.experiment_instance)

            idx_set += 1
            curr_time = time.perf_counter()
            time_delta = curr_time - prev_time
            prev_time = curr_time

            self.updateRuntime.emit(time_delta, idx_set)
            self.updateProgress.emit(idx_set)

        self.finished.emit()

    def intermediate_data_handler(self, data):
        """
        The function that handles an intermediate_data signal from the experiment instance. 

        :param data: The data dictionary.
        :type data: dict
        """

        self.intermediateData.emit(data, self.experiment_instance)

    def stop(self):
        """
        Stops an experiment.
        """

        self.running = False
        if hasattr(self.experiment_instance, 'stop_flag'): # if a stop_flag exists
            self.experiment_instance.stop_flag = True

        qDebug("Stopping the thread at the next set iteration...")