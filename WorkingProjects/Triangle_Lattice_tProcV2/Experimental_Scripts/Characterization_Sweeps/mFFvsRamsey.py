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
        pass
        # def fit(t, T2, A, y0, omega, phi):
        #     return A * np.exp(-t / T2) * np.cos(omega*t - phi) + y0
        #
        # omegas, FFgains = [], []
        # x_pts = data["data"]["delay_loop"]
        # Zmat = data["data"]["contrast"][0]
        # for row, FFgain in zip(Zmat, data["data"]["Gain_Pulse"]):
        #     p0_guess = [x_pts[-1], (np.max(row) - np.min(row))/2, row[-1], omega_guess(x_pts, row), 1e-2]
        #     try:
        #         (T2, A, y0, omega, phi), _ = scipy.optimize.curve_fit(fit, x_pts, row, p0=p0_guess)
        #         omegas.append(np.abs(omega))
        #         FFgains.append(FFgain)
        #     except:
        #         pass
        #
        # self.omegas_fit = omegas
        # self.gains_fit = FFgains





    # def display(self, *args, **kwargs):
    #     fig, axs = super().display(*args, **kwargs)
    #
    #     if 'omegas_fit' in self.__dict__:
    #         # Assume FF gain is linear to detuning
    #         def freq_fit(FF_gain, center_gain, k):
    #             return k * np.abs(FF_gain - center_gain)
    #
    #         quarter_periods = 2*np.pi/np.array(self.omegas_fit) / 4
    #         axs[0].plot(quarter_periods, self.gains_fit, 'o-', color='r', zorder=11)
    #         # (center_gain, k), _ = scipy.optimize.curve_fit(freq_fit, FFgains, omegas, p0=[np.mean(data["data"]["Gain_Pulse"]), (omegas[-1]-omegas[-2])/(FFgains[-1]-FFgains[-2])])
    #         # ax.plot(omegas, FFgains, '-o', color='red')
    #         # ax.plot(freq_fit(FFgains, center_gain, k), FFgains, '-', color='black')
    #         # ax.set_ylabel("FF gains")
    #         # ax.set_xlabel("Oscillation frequency (2pi * MHz)")
    #         # ax.axhline(center_gain, color='black', ls='--', label=center_gain)
    #         # ax.legend()
    #         fig.show()
    #         plt.show(block=True)
    #
    #     return fig, axs