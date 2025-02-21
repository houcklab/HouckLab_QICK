from PyQt5.QtCore import QObject, pyqtSignal, qWarning, qDebug
from qick import AveragerProgram, RAveragerProgram

class ExperimentThread(QObject):
    """
    This class is used to run an RFSOC experiment, meant to be used on a separate QThread than the main loop.
    The point is that running an RFSOC experiment will take a very long time, and we don't want to lock up the UI while
    that's going on. The intended usage is for an ExterimentThread object to be created, moved to a new QThread, then run.
    It will then communicate with the main program via signals, as intended in Qt, making it thread-safe.
    """
    finished = pyqtSignal() # Signal to send when done running
    updateData = pyqtSignal(object) # Signal to send when receiving new data, including the new data dictionary
    updateProgress = pyqtSignal(int) # Signal to send when finishing a set to update the setsComplete bar
    RFSOC_error = pyqtSignal(Exception) # Signal to send when the RFSOC encounters an error

    def __init__(self, config, soccfg, exp, soc, parent = None):
        super().__init__(parent)
        self.config = config # The config file used to run the experiment
        self.parent = parent # We don't actually want to give it the parent window, that can cause blocking
        self.experiment_instance = exp # The object representing an instance of a QickProgram subclass to be run
        self.soc = soc # The RFSOC!

        # ### create the experiment instance
        # self.experiment_instance = exp(soccfg, self.config)

        if not exp:
            qDebug('Warning: None experiment. Going to crash in 3, 2, 1...')

    def run(self):
        """ Run the RFSOC experiment. """
        #yoko1.SetVoltage(self.config["yokoVoltage"]) # this needs to go somewhere else

        self.running = True
        idx_set = 0

        ### loop over all the sets for the data taking
        while self.running and idx_set < self.config["sets"]:

            #### check what kind of experiment it is
            if issubclass(type(self.experiment_instance), AveragerProgram):
                qWarning("I can't handle AveragerProgram yet!")
                return
                ### if Averager class, need to loop over variables
            elif issubclass(type(self.experiment_instance), RAveragerProgram):

                try:
                    x_pts, avgi, avgq = self.experiment_instance.acquire(self.soc)
                except Exception as e:
                    self.RFSOC_error.emit(e)
                    self.finished.emit()
                    return # Do not want to update data -- no new data was recorded!
                data = {'config': self.config, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'set_num': idx_set}}

            # Emit the signal with new data
            self.updateData.emit(data)
            # Update the setsComplete bar
            self.updateProgress.emit(idx_set + 1, self.config['reps'], self.config['sets'])
            self.finished.emit()

            idx_set += 1

    def stop(self):
        self.running = False
        qDebug("trying to stop the thread...")