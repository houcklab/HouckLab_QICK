

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers

# import matplotlib; matplotlib.use('Qt5Agg')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND


class SweepExperiment2D_plots(SweepExperimentND):
    def _display_plot(self, data=None, fig_axs=None):
        if data is None:
            data = self.data
        fig, axs = fig_axs

        fig.suptitle(str(self.titlename), fontsize=16)

        y_key_name = SweepHelpers.key_savename(self.y_key)
        try:
            x_key_name = self.x_key
        except:
            x_key_name = self.loop_names[0]

        try:
            X, Y = data['data'][x_key_name], data['data'][y_key_name]
        except KeyError as ex:
            raise ValueError(f"\tkeys: {x_key_name}, {y_key_name}"
                           f"\ndata['data'].keys():, {data['data'].keys()}"
                           f"\nCommon cause of this error:"
                           f"\n\tIf you have a loop in your AveragerProgram, "
                             f" you need to define loop_pts and"
                  " have it return a tuple of arrays for this code to work (see my SpecSlice program)")
        X_step = X[1] - X[0]
        Y_step = Y[1] - Y[0]
        Z_mat = data['data'][self.z_value]


        if self.z_value == 'contrast':
            colorbar_label = 'IQ contrast (a.u.)'
        elif self.z_value == 'population':
            colorbar_label = 'Excited state population'
        elif self.z_value == 'population_corrected':
            colorbar_label = 'Excited state population (corrected)'
        else:
            colorbar_label = None

        readout_list = data['data']['readout_list']
        for ro_index, ro_ch in enumerate(readout_list):
            ax_im = axs[ro_index].imshow(
                Z_mat[ro_index],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none')
            axs[ro_index].set_ylabel(self.ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].set_title(f"Read: {ro_ch}")
            cbar = fig.colorbar(ax_im, ax=axs[ro_index], extend='both')
            cbar.set_label(colorbar_label, rotation=90)

        fig.show()

    def _update_fig(self, Z_mat, fig, axs):
        for ro_index in range(len(Z_mat)):
            # print(axs[ro_index].images[-1][-1])
            im = axs[ro_index].get_images()[-1],
            im = im[-1]
            cbar = im.colorbar
            im.set_data(Z_mat[ro_index])
            im.autoscale()
            cbar.update_normal()
