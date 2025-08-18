

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers

# import matplotlib; matplotlib.use('Qt5Agg')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND


class SweepExperiment1D_plots(SweepExperimentND):
    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

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

        fig.suptitle(str(self.titlename), fontsize=16)
        try:
            x_key_name = SweepHelpers.key_savename(self.x_key)
        except:
            x_key_name = self.loop_names[0]

        X = data['data'][x_key_name]
        self.X = X

        Z_mat = data['data'][self.z_value]

        readout_list = data['data']['readout_list']
        for ro_index, ro_ch in enumerate(readout_list):
            axs[ro_index].plot(X, Z_mat[ro_index], marker='o', label=f"Read: {ro_ch}")

            axs[ro_index].set_ylabel(ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].legend()

    def _update_fig(self, Z_mat, fig, axs):
        for ro_index in range(len(Z_mat)):
            line = axs[ro_index].lines[-1]
            line.set_data(self.X, Z_mat[ro_index])
            axs[ro_index].relim()
            axs[ro_index].autoscale()