###
# This file contains an NDAveragerProgram and ExperimentClass
# for ramping and then holding for some time and then ramping back down
# Parth, Sept 2025: create file.
###

import sys
from tqdm import tqdm
import matplotlib
from qick import NDAveragerProgram
from qick.averager_program import QickSweep
from MasterProject.Client_modules.CoreLib.Experiment import ExperimentClass
import numpy as np
import matplotlib.pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Helpers import PulseFunctions
import time

class mFFTransmission(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channels
        self.declare_gen(ch=self.cfg["res_ch"], nqz=self.cfg["nqz"])  # Readout
        self.declare_gen(ch=self.cfg["ff_ch"], nqz=self.cfg["ff_nqz"])  # Fast flux

        # Declare readout
        for ch in self.cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(self.cfg["read_length"], ro_ch=self.cfg["res_ch"]),
                                 freq=self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"])

        # Readout pulse
        self.set_pulse_registers(ch=self.cfg["res_ch"], style=self.cfg["read_pulse_style"],
                                 freq=self.freq2reg(self.cfg["read_pulse_freq"], gen_ch=self.cfg["res_ch"],
                                                    ro_ch=self.cfg["ro_chs"][0]), phase=0,
                                 gain=self.cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"], gen_ch=self.cfg["ro_chs"][0]))

        # Define the fast flux ramp. For now, just linear ramp is supported
        if self.cfg["ff_ramp_style"] == "linear":
            PulseFunctions.create_ff_ramp(self, reversed = False)
            PulseFunctions.create_ff_ramp(self, reversed = True)
        else:
            print("Need an ff_ramp_style! only \"linear\" supported at the moment.")

        self.adc_trig_offset_cycles = self.us2cycles(self.cfg["adc_trig_offset"])  # Do NOT include channel, it's wrong!
        # Give tprocessor time to execute all initialisation instructions before we expect any pulses to happen
        self.sync_all(self.us2cycles(1))

    def body(self):

        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel = 'last',
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"], t = 'auto')

        self.sync_all(self.us2cycles(self.cfg['pre_meas_delay'])) # Manually setting the value to be 1. Make sure it is greater than 238ns.
        # There is some weird delay in the FF channel

        # trigger measurement, play measurement pulse, wait for relax_delay_2. Once per experiment.
        self.measure(pulse_ch=self.cfg["res_ch"], adcs=self.cfg["ro_chs"], adc_trig_offset=self.adc_trig_offset_cycles,
                     wait=True,
                     syncdelay=self.us2cycles(1)) # Waiting for 1us for safety

        # play reversed fast flux ramp, return to original spot
        self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                 gain = self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
        self.pulse(ch = self.cfg["ff_ch"], t ='auto')


        if self.cfg['negative_pulse'] :
            self.sync_all(self.us2cycles(1))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0, stdysel='last',
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')
            self.sync_all(self.us2cycles(self.cfg['read_length']))
            self.set_pulse_registers(ch=self.cfg["ff_ch"], freq=0, style='arb', phase=0,
                                     gain=-self.soccfg['gens'][0]['maxv'], waveform="ramp_reversed", outsel="input")
            self.pulse(ch=self.cfg["ff_ch"], t='auto')

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    # Override acquire such that we can collect the single-shot data


class FFTransmission(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        if 'pre_meas_delay' not in self.cfg.keys():
            self.cfg['pre_meas_delay'] = 1
        else:
            print(f"Pre Meas Delay = {self.cfg['pre_meas_delay']}")

        if 'negative_pulse' in self.cfg.keys():
            if self.cfg['negative_pulse']:
                print(f"Playing negative pulses for integration to be zero")
            else:
                print("Not playing negative pulses")
        else:
            self.cfg['negative_pulse'] = False
            print("Not playing negative pulses")


        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"]-1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts):
            self.cfg["read_pulse_freq"] = f
            prog = mFFTransmission(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True,progress=False))
            # time.sleep(0.01) # Added to wait for the RFSOC to send all data
        if debug:
            print(f'Time: {time.time() - start}')

        #### find the frequency corresponding to the peak
        avgi = np.array([elem[1] for elem in results])[:,0,0]
        avgq = np.array([elem[2] for elem in results])[:,0,0]
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq = fpts[peak_loc]

        self.cfg["read_pulse_freq"] = expt_cfg["center"] # reset to original value
        data={'config': self.cfg, 'data': {'fpts':fpts, 'peak_freq':self.peakFreq,
                                           'amp0':avgamp0, 'avgi': avgi, 'avgq': avgq}}
        self.data=data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        avgamp0 = data['data']['amp0']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        plt.plot(x_pts, avgi,label="I")
        plt.plot(x_pts, avgq,label="Q")
        plt.plot(x_pts, avgamp0, label="Magnitude")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.legend()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show()

        else:
            fig.clf(True)
            plt.close(fig)

    def acquire_2d(self,
                   sweep_key: str,
                   sweep_values,
                   live_plot: bool = True,
                   plot_what: str = "mag",  # "mag", "I", or "Q" for the live image
                   progress: bool = False,
                   debug: bool = False):
        """
        Sweep transmission vs. readout frequency and one extra config parameter.

        Parameters
        ----------
        sweep_key : str
            Name of the key in self.cfg to vary (e.g., "ff_amp", "read_pulse_gain", etc.).
        sweep_values : array-like
            Values to assign to self.cfg[sweep_key] for each outer slice.
        live_plot : bool
            If True, draws/updates a live 2D image after each slice.
        plot_what : {"mag","I","Q"}
            Which quantity to visualize live. Data always saved for all three.
        progress : bool
            Passed through to `acquire()` per slice.
        debug : bool
            Passed through to `acquire()` per slice.

        Returns
        -------
        data2d : dict
            {
              "config": <final cfg snapshot>,
              "axes": {
                  "sweep_key": <name>,
                  "sweep_values": np.array([...]),
                  "fpts": np.array([...]),  # in MHz (as in acquire)
                  "x_ghz": np.array([...])  # GHz axis used in plots
              },
              "data": {
                  "I": 2D np.array [n_slices, n_freq],
                  "Q": 2D np.array [n_slices, n_freq],
                  "mag": 2D np.array [n_slices, n_freq],
                  "peak_freqs": 1D np.array [n_slices],  # MHz
              }
            }
        """

        import numpy as np
        import matplotlib.pyplot as plt
        import time

        # Validate plot_what
        plot_what = plot_what.lower()
        if plot_what not in ("mag", "i", "q"):
            plot_what = "mag"

        # Preserve original value to restore at the end
        _had_key = sweep_key in self.cfg
        _orig_val = self.cfg.get(sweep_key, None)

        sweep_values = np.array(list(sweep_values))
        n_slices = len(sweep_values)

        # Run the first slice to discover frequency grid size and set up arrays/plot.
        self.cfg[sweep_key] = sweep_values[0]
        first = self.acquire(progress=progress, debug=debug)
        fpts = np.array(first["data"]["fpts"])                      # MHz
        x_ghz = (fpts + self.cfg.get("cavity_LO", 0.0)/1e6) / 1e3   # GHz, matching your display()
        n_freq = fpts.size

        # Allocate 2D arrays
        I2d   = np.zeros((n_slices, n_freq), dtype=float)
        Q2d   = np.zeros((n_slices, n_freq), dtype=float)
        Mag2d = np.zeros((n_slices, n_freq), dtype=float)
        peaks = np.zeros((n_slices,), dtype=float)

        # Fill row 0 from the first slice
        I2d[0, :]   = np.array(first["data"]["avgi"])
        Q2d[0, :]   = np.array(first["data"]["avgq"])
        Mag2d[0, :] = np.array(first["data"]["amp0"])
        peaks[0]    = float(first["data"]["peak_freq"])

        # Set up live plot
        fig, ax, im, cbar = None, None, None, None
        if live_plot:
            plt.ion()
            fig, ax = plt.subplots()
            ax.set_xlabel("Cavity Frequency (GHz)")
            ax.set_ylabel(sweep_key)
            # ax.set_yticks(np.arange(n_slices))
            # ax.set_yticklabels([f"{v}" for v in sweep_values])
            ax.set_title(f"Live transmission vs freq × {sweep_key}  (Averages={self.cfg.get('reps','?')})")

            def _pick_field():
                return {"mag": Mag2d, "i": I2d, "q": Q2d}[plot_what]

            data_for_plot = _pick_field()
            # Use extent so the x-axis is in GHz and y is slice index (we label ticks with sweep_values)
            im = ax.imshow(data_for_plot,
                           aspect="auto",
                           origin="lower",
                           extent=(x_ghz.min(), x_ghz.max(), sweep_values[0], sweep_values[-1]),)
            cbar = fig.colorbar(im, ax=ax, label={"mag": "|IQ| (a.u.)", "i": "I (a.u.)", "q": "Q (a.u.)"}[plot_what])
            fig.tight_layout()
            fig.canvas.draw(); fig.canvas.flush_events()

        # Process remaining slices
        for i in range(1, n_slices):
            self.cfg[sweep_key] = sweep_values[i]
            d = self.acquire(progress=progress, debug=debug)

            I2d[i, :]   = np.array(d["data"]["avgi"])
            Q2d[i, :]   = np.array(d["data"]["avgq"])
            Mag2d[i, :] = np.array(d["data"]["amp0"])
            peaks[i]    = float(d["data"]["peak_freq"])

            if live_plot:
                # Update the displayed matrix only up to the current row (optional but visually clearer)
                if plot_what == "mag":
                    current = Mag2d.copy()
                elif plot_what == "i":
                    current = I2d.copy()
                else:
                    current = Q2d.copy()

                # Optionally mask unfilled rows to keep color scale sane
                if i < n_slices - 1:
                    current[i+1:, :] = np.nan

                im.set_data(current)
                # Autoscale color limits on the filled portion to keep contrast decent
                finite_vals = current[np.isfinite(current)]
                if finite_vals.size:
                    im.set_clim(np.nanpercentile(finite_vals, 2), np.nanpercentile(finite_vals, 98))
                fig.canvas.draw(); fig.canvas.flush_events()
                time.sleep(0.02)

        # Build return object (and stash on self)
        data2d = {
            "config": dict(self.cfg),
            "axes": {
                "sweep_key": sweep_key,
                "sweep_values": sweep_values,
                "fpts": fpts,
                "x_ghz": x_ghz
            },
            "data": {
                "I": I2d,
                "Q": Q2d,
                "mag": Mag2d,
                "peak_freqs": peaks
            }
        }
        self.data2d = data2d

        # Restore original cfg value for cleanliness
        if _had_key:
            self.cfg[sweep_key] = _orig_val
        else:
            self.cfg.pop(sweep_key, None)

        return data2d


    def save_data(self, data=None):
        # print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



