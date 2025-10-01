

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers

# import matplotlib; matplotlib.use('Qt5Agg')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND

'''This class plots 1D data of multiple readouts all on the same plot, as opposed to 1D_plots which
creates a separate plot for each readout.'''
class SweepExperiment1D_lines(SweepExperimentND):

    '''Redefine display to only create one subplot'''
    def display(self, data=None, plotDisp=True, figNum=1, plotSave=True, block=True, fig_axs=None):
        # Create a new figure if you did not pass in your own fig and axs.
        if fig_axs is None:
            fig, axs = self._make_subplots(figNum, 1)
        else:
            fig, axs = fig_axs
        
        return super().display(data, plotDisp, figNum, plotSave, block, (fig, axs))

    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs
        ax = axs[-1]

        if self.z_value == 'IQ':
            ylabel = 'Transmission (a.u.)'
        elif self.z_value == 'population':
            ylabel = 'Excited state population'
        elif self.z_value == 'contrast':
            ylabel = 'IQ contrast (a.u.)'
        elif self.z_value == 'population_corrected':
            ylabel = 'Excited state population (corrected)'
        else:
            ylabel = None

        try:
            x_key_name = SweepHelpers.key_savename(self.x_key)
        except:
            x_key_name = self.loop_names[0]
        X = data['data'][x_key_name]
        self.X = X

        Z_mat = data['data'][self.z_value]

        fig.suptitle(str(self.titlename), fontsize=16)
        readout_list = data['data']['readout_list']
        for ro_index, ro_ch in enumerate(readout_list):
            ax.plot(X, Z_mat[ro_index], marker='o', label=f"Read: {ro_ch}")

        ax.set_ylabel(ylabel)
        ax.set_xlabel(self.xlabel)
        ax.legend()

        return fig, ax

    def _update_fig(self, data, fig, axs):
        Z_mat = data['data'][self.z_value]
        lines = axs[-1].lines
        for ro_index in range(len(Z_mat)):
            lines[ro_index].set_data(self.X, Z_mat[ro_index])
        axs[-1].relim()
        axs[-1].autoscale()