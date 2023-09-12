from PyQt5.QtWidgets import QWidget, QVBoxLayout
import matplotlib
matplotlib.use('GTK4Agg') ### this helps plot faster for sets
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar)


class PlotWidget(QWidget):
    """ This class represents a widget that contains the main axes for plotting data, as well as the navigation bar """
    def __init__(self, parent = None, width = 5, height = 3, dpi = 100):
        super().__init__()

        # Create two maptlotlib FigureCanvas objects for the top and bottom plots
        self.canvas1 = FigureCanvas(Figure(figsize = (width, height), dpi = dpi))
        #self.canvas2 = FigureCanvas(Figure(figsize = (width, height), dpi = dpi))

        self.ax1, self.ax2 = self.canvas1.figure.subplots(2, 1)
        # Create toolbars for the figures:
        toolbar1 = NavigationToolbar(self.canvas1, self)
        #toolbar2 = NavigationToolbar(self.canvas2, self)

        # Define and apply widget layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(toolbar1)
        layout.addWidget(self.canvas1)
        #layout.addWidget(self.canvas2)
       # layout.addWidget(toolbar2)
        self.setLayout(layout)

    def plot1(self, x, y, labels, clear = True):
        """ Plot the data x, y on axes 1 (the top one). """
        if clear:
            self.ax1.clear()
        self.ax1.plot(x, y)
        ### set the plot labels
        self.ax1.set_xlabel(labels["x label"])
        if labels["y label"] == None:
            self.ax1.set_ylabel(labels["y label 1"])
        else:
            self.ax1.set_ylabel(labels["y label"])


    def plot2(self, x, y, labels, clear = True):
        """ Plot the data x, y on axes 2 (the bottom one). """
        if clear:
            self.ax2.clear()
        self.ax2.plot(x, y)
        ### set the plot labels
        self.ax2.set_xlabel(labels["x label"])
        if labels["y label"] == None:
            self.ax2.set_ylabel(labels["y label 2"])
        else:
            self.ax2.set_ylabel(labels["y label"])

    def drawCanvas(self):
        #### note that using cavas.draw() is a very slow process and this should be changed to improve plotting speed
        self.canvas1.draw()


    def save_fig(self, full_path_filename):
        self.canvas1.figure.savefig(full_path_filename)