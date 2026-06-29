

import numpy as np

from WorkingProjects.triangle_lattice_quench.Helpers import SweepHelpers

# import matplotlib; matplotlib.use('Qt5Agg')

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperimentND import SweepExperimentND


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

        ### hard-coded fudge to allow easy collecting of shots data in an experiment already written for
        ### population, consider altering - Joshua 12/10/25
        if self.z_value == 'population_shots':
            Z_mat = data['data']['population_corrected']
        else:
            Z_mat = data['data'][self.z_value]


        if self.z_value == 'contrast':
            colorbar_label = 'IQ contrast (a.u.)'
        elif self.z_value == 'population':
            colorbar_label = 'Excited state population'
        elif self.z_value == 'population_corrected' or self.z_value == 'population_shots':
            colorbar_label = 'Excited state population (corrected)'
        else:
            colorbar_label = None

        readout_list = data['data']['readout_list']
        # Shared color scale across all readouts: same color == same population
        # everywhere, with a single colorbar for the whole figure.
        zs = [np.asarray(Z_mat[i], float) for i in range(len(readout_list))]
        fin = [z[np.isfinite(z)] for z in zs]
        fin = np.concatenate(fin) if any(f.size for f in fin) else np.array([0.0, 1.0])
        vmin, vmax = float(fin.min()), float(fin.max())
        if vmin == vmax:
            vmax = vmin + 1e-9
        ims = []
        for ro_index, ro_ch in enumerate(readout_list):
            ax_im = axs[ro_index].imshow(
                Z_mat[ro_index],
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
                vmin=vmin, vmax=vmax)
            axs[ro_index].set_ylabel(self.ylabel)
            axs[ro_index].set_xlabel(self.xlabel)
            axs[ro_index].set_title(f"Read: {ro_ch}")
            ims.append(ax_im)
        cbar = fig.colorbar(ims[-1], ax=[axs[i] for i in range(len(readout_list))],
                            extend='both')
        cbar.set_label(colorbar_label, rotation=90)
        self._shared_cbar_2d = cbar

        fig.show()
        return fig, axs

    def _update_fig(self, data, fig, axs):
        if self.z_value == 'population_shots':
            Z_mat = data['data']['population_corrected']
        else:
            Z_mat = data['data'][self.z_value]

        # Recompute one shared color scale across all readouts each update.
        zs = [np.asarray(Z_mat[i], float) for i in range(len(Z_mat))]
        fin = [z[np.isfinite(z)] for z in zs]
        fin = np.concatenate(fin) if any(f.size for f in fin) else np.array([0.0, 1.0])
        vmin, vmax = float(fin.min()), float(fin.max())
        if vmin == vmax:
            vmax = vmin + 1e-9
        for ro_index in range(len(Z_mat)):
            im = axs[ro_index].get_images()[-1]
            im.set_data(Z_mat[ro_index])
            im.set_clim(vmin, vmax)
        cbar = getattr(self, '_shared_cbar_2d', None)
        if cbar is not None:
            try:
                cbar.update_normal(axs[0].get_images()[-1])
            except Exception:
                pass
