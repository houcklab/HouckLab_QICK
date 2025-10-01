import numpy as np
import scipy

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import omega_guess
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class FFvsRamsey(SweepExperiment2D_plots):

    def init_sweep_vars(self):
        self.cfg.setdefault('qubit_drive_freq', self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift",0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)

        print("Drive frequency at:", self.cfg['qubit_drive_freq'])
        if "phase_shift_cycles" in self.cfg:
            print("Caution: Adding additional cycles to FFvsRamsey. Did you intend to do this?")
        # else:
        #     self.cfg["phase_shift_cycles"] = 0

        self.Program = T2RProgram

        self.y_key = ("FF_Qubits", str(self.cfg["qubit_FF_index"]), "Gain_Pulse")
        self.y_points = np.linspace(self.cfg["FF_gain_start"], self.cfg["FF_gain_stop"], self.cfg["FF_gain_steps"],
                                    dtype=int)

        self.x_name = "delay_loop"

        self.z_value = 'population' if self.cfg['populations'] else 'contrast' # contrast or population
        self.ylabel = f'Fast flux gain index {self.cfg["qubit_FF_index"]}'  # for plotting
        self.xlabel = 'Delay (us)'  # for plotting

    def analyze(self, data, **kwargs):
        def fit(t, T2, A, y0, omega, phi):
            return A * np.exp(-t / T2) * np.cos(omega*t - phi) + y0

        omegas, FFgains = [], []
        x_pts = data["data"][self.loop_names[0]]
        Zmat = data["data"]["contrast"][0]
        for row, FFgain in zip(Zmat, data["data"]["Gain_Pulse"]):
            w_guess = omega_guess(x_pts, row)
            period_guess = 2*np.pi/w_guess
            if period_guess > 2/3 * x_pts[-1] or period_guess < 1/10 * x_pts[-1]:
                continue
            p0_guess = [x_pts[-1], (np.max(row) - np.min(row))/2, row[-1], w_guess, 1e-2]
            try:
                (T2, A, y0, omega, phi), _ = scipy.optimize.curve_fit(fit, x_pts, row, p0=p0_guess)
                omegas.append(np.abs(omega))
                FFgains.append(FFgain)
            except:
                pass

        self.omegas_fit = omegas
        self.gains_fit = FFgains


    def _display_plot(self, data=None, fig_axs=None):
        fig, axs = super()._display_plot(data, fig_axs)

        if 'omegas_fit' in self.__dict__:
            # Assume FF gain is linear to detuning
            def freq_fit(FF_gain, center_gain, k):
                return k * np.abs(FF_gain - center_gain)

            half_periods = 2*np.pi/np.array(self.omegas_fit) / 2
            axs[0].scatter(half_periods, self.gains_fit, color='r', zorder=11)

            omegas = self.omegas_fit
            FFgains = self.gains_fit
            ax = axs[0]

            try:
                (center_gain, k), _ = scipy.optimize.curve_fit(freq_fit, FFgains, omegas, p0=[np.mean(data["data"]["Gain_Pulse"]), (omegas[-1]-omegas[-2])/(FFgains[-1]-FFgains[-2])])
                y_pts = data["data"]["Gain_Pulse"]
                y_spacing = np.abs(y_pts[1] - y_pts[0])
                gains_up = np.linspace(np.max(y_pts)+y_spacing, center_gain,  num=50,endpoint=False,)
                gains_lo = np.linspace(np.min(y_pts) - y_spacing, center_gain,  num=50,endpoint=False,)
                print(gains_up, gains_lo)
                fig.canvas.draw()
                ax.autoscale(False)
                ax.plot(2*np.pi/freq_fit(gains_up, center_gain, k)/2, gains_up, '--', color='red',zorder=10,lw=3)
                ax.plot(2 * np.pi / freq_fit(gains_lo, center_gain, k)/2, gains_lo, '--', color='red',zorder=10,lw=3)


                ax.axhline(center_gain, color='red', ls='--', label=f'FF Gain = {center_gain:.1f}', lw=3)
                ax.legend(prop={'size': 14})
            except:
                print("Fitting failed.")


        return fig, axs