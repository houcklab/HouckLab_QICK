######################################################################On qick.qick_asm:
def sync_all(self, t=0, dac_t0=None):
    """Aligns and syncs all channels with additional time t.
    Accounts for both generator pulses and readout windows.
    This does not pause the tProc.

    Parameters
    ----------
    t : int, optional
        The time offset in tProc cycles
    """
    # if dac_t0 == None:
    #     print('None')
    # print(self._dac_ts)

    # print('Before', self._dac_ts)
    time_offset_dac = [0] * len(self._dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
    dac_ts_copy = np.copy(self._dac_ts)
    self._dac_ts = [max(time - offset, 0) for time, offset in zip(dac_ts_copy, time_offset_dac)]
    # print('after', self._dac_ts)
    max_t = max(self._dac_ts + self._adc_ts)
    if max_t + t > 0:
        self.synci(int(max_t + t))
        self._dac_ts = [0] * len(self._dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
        self._adc_ts = [0] * len(self._adc_ts)
    elif dac_t0:
        self._dac_ts = list(np.copy(dac_t0))

        #
        # print('final', self._dac_ts)

        # max_t = max(self._dac_ts+self._adc_ts)
        # if max_t+t > 0:
        #     self.synci(int(max_t+t))
        #     self._dac_ts = [0]*len(self._dac_ts)
        #     self._adc_ts = [0]*len(self._adc_ts)


# <<<<<<< Updated upstream
#         max_t = max(self._dac_ts+self._adc_ts)
#         if max_t+t > 0:
#             self.synci(int(max_t+t))
#             self._dac_ts = [0]*len(self._dac_ts)
#             self._adc_ts = [0]*len(self._adc_ts)
# =======
#         time_offset_dac = [0] * len(self.dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
#         dac_ts_copy = np.copy(self.dac_ts)
#         self.dac_ts = [max(time - offset, 0) for time, offset in zip(dac_ts_copy, time_offset_dac)]
#         max_t = max(self.dac_ts+self.adc_ts)
#         # print(self.dac_ts)
#         if max_t+t > 0:
#             self.synci(int(max_t+t))
#             self.dac_ts = [0]*len(self.dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
#             self.adc_ts = [0]*len(self.adc_ts)
#         elif dac_t0:
#             self.dac_ts = list(np.copy(dac_t0))
# >>>>>>> Stashed changes

    def sync_all(self, t=0, dac_t0=None):
        """Aligns and syncs all channels with additional time t.
        Accounts for both generator pulses and readout windows.
        This does not pause the tProc.

        Parameters
        ----------
        t : int, optional
            The time offset in tProc cycles
        """
        time_offset_dac = [0] * len(self._dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
        dac_ts_copy = np.copy(self._dac_ts)
        self._dac_ts = [max(time - offset, 0) for time, offset in zip(dac_ts_copy, time_offset_dac)]
        # print('after', self._dac_ts)
        max_t = max(self._dac_ts+self._adc_ts)
        if max_t+t > 0:
            self.synci(int(max_t+t))
            self._dac_ts = [0]*len(self._dac_ts) if dac_t0 is None else list(np.copy(dac_t0))
            self._adc_ts = [0]*len(self._adc_ts)
        elif dac_t0:
            self._dac_ts = list(np.copy(dac_t0))


data[:, i] = np.round(d.astype(float))
# Replaces
# data[:,i] = np.round(d)
# in line 717 as part of     def add_pulse(self, name, idata, qdata): in class AbsGenManager(AbsRegisterManager):



Additionally,

mcode |= (int(args[field[0]]) << field[1])
# replaces mcode |= (args[field[0]] << field[1]) in line 2129  in def compile_instruction(self, inst, labels, debug=False): within QickProgram

######################################################################On qick.averager_program:


# <<<<<<< Updated upstream
#         d_buf, avg_d, shots = super().acquire(soc, reads_per_rep=readouts_per_experiment, load_pulses=load_pulses, start_src=start_src, progress=progress, debug=debug)
# =======
#         # Configure signal generators
#         self.config_gens(soc)
#
#         # Configure the readout down converters
#         self.config_readouts(soc)
#         self.config_bufs(soc, enable_avg=True, enable_buf=False)
#
#         # load this program into the soc's tproc
#         self.load_program(soc, debug=debug)
#
#         # configure tproc for internal/external start
#         soc.start_src(start_src)
#
#         reps = self.cfg['reps']
#         total_count = reps*readouts_per_experiment
#         count = 0
#         n_ro = len(self.ro_chs)
#
#         d_buf = np.zeros((n_ro, 2, total_count))
#         self.stats = []
#
#         with tqdm(total=total_count, position=2, disable=not progress) as pbar:
#             soc.start_readout(total_count, counter_addr=1,
#                                    ch_list=list(self.ro_chs), reads_per_count=readouts_per_experiment)
#             while count<total_count:
#                 new_data = soc.poll_data()
#                 for d, s in new_data:
#                     new_points = d.shape[2]
#                     d_buf[:, :, count:count+new_points] = d
#                     count += new_points
#                     self.stats.append(s)
#                     pbar.update(new_points)
# >>>>>>> Stashed changes



# <<<<<<< Updated upstream
# =======
#     def acquire(self, soc, threshold=None, angle=None, readouts_per_experiment=1, save_experiments=None, load_pulses=True, start_src="internal", progress=False, debug=False):
#         """
#         This method optionally loads pulses on to the SoC, configures the ADC readouts, loads the machine code representation of the AveragerProgram onto the SoC, starts the program and streams the data into the Python, returning it as a set of numpy arrays.
#         config requirements:
#         "reps" = number of repetitions;
#
#         :param soc: Qick object
#         :type soc: Qick object
#         :param threshold: threshold
#         :type threshold: int
#         :param angle: rotation angle
#         :type angle: list
#         :param readouts_per_experiment: readouts per experiment
#         :type readouts_per_experiment: int
#         :param save_experiments: saved readouts (by default, save all readouts)
#         :type save_experiments: list
#         :param load_pulses: If true, loads pulses into the tProc
#         :type load_pulses: bool
#         :param start_src: "internal" (tProc starts immediately) or "external" (each round waits for an external trigger)
#         :type start_src: string
#         :param progress: If true, displays progress bar
#         :type progress: bool
#         :param debug: If true, displays assembly code for tProc program
#         :type debug: bool
#         :returns:
#             - expt_pts (:py:class:`list`) - list of experiment points
#             - avg_di (:py:class:`list`) - list of lists of averaged accumulated I data for ADCs 0 and 1
#             - avg_dq (:py:class:`list`) - list of lists of averaged accumulated Q data for ADCs 0 and 1
#         """
#
#         if angle is None:
#             angle = [0, 0]
#         if save_experiments is None:
#             save_experiments = range(readouts_per_experiment)
#         if "rounds" not in self.cfg or self.cfg["rounds"] == 1:
#             return self.acquire_round(soc, threshold=threshold, angle=angle, readouts_per_experiment=readouts_per_experiment, save_experiments=save_experiments, start_src=start_src, load_pulses=load_pulses, progress=progress, debug=debug)
#
#         avg_di = None
#         for ii in tqdm(range(self.cfg["rounds"]), position=1, disable=not progress):
#             avg_di0, avg_dq0 = self.acquire_round(
#                 soc, threshold=threshold, angle=angle, readouts_per_experiment=readouts_per_experiment, save_experiments=save_experiments, start_src=start_src, load_pulses=load_pulses, progress=False, debug=debug)
#
#             if avg_di is None:
#                 avg_di, avg_dq = avg_di0, avg_dq0
#             else:
#                 avg_di += avg_di0
#                 avg_dq += avg_dq0
#
#         return avg_di/self.cfg["rounds"], avg_dq/self.cfg["rounds"]
#
#     def get_single_shots(self, di, dq, threshold, angle=None):
#         """
#         This method converts the raw I/Q data to single shots according to the threshold and rotation angle
#
#         :param di: Raw I data
#         :type di: list
#         :param dq: Raw Q data
#         :type dq: list
#         :param threshold: threshold
#         :type threshold: int
#         :param angle: rotation angle
#         :type angle: list
#
#         :returns:
#             - single_shot_array (:py:class:`array`) - Numpy array of single shot data
#
#         """
#
#         if angle is None:
#             angle = [0, 0]
#         if isinstance(threshold, int):
#             threshold = [threshold, threshold]
#         return np.array([np.heaviside((di[i]*np.cos(angle[i]) - dq[i]*np.sin(angle[i]))/self.ro_chs[ch].length-threshold[i], 0) for i, ch in enumerate(self.ro_chs)])
# >>>>>>> Stashed changes


#
# <<<<<<< Updated upstream
#         d_buf, avg_d, shots = super().acquire(soc, reads_per_rep=readouts_per_experiment, load_pulses=load_pulses, start_src=start_src, progress=progress, debug=debug)
# =======
#         # Configure signal generators
#         self.config_gens(soc)
#
#         # Configure the readout down converters
#         self.config_readouts(soc)
#         self.config_bufs(soc, enable_avg=True, enable_buf=False)
#
#         # load this program into the soc's tproc
#         self.load_program(soc, debug=debug)
#
#         # configure tproc for internal/external start
#         soc.start_src(start_src)
#
#         reps, expts = self.cfg['reps'], self.cfg['expts']
#
#         total_count = reps*expts*readouts_per_experiment
#         count = 0
#         n_ro = len(self.ro_chs)
#         d_buf = np.zeros((n_ro, 2, total_count))
#         self.stats = []
#
#         with tqdm(total=total_count, position=2, disable=not progress) as pbar:
#             soc.start_readout(total_count, counter_addr=1, ch_list=list(
#                 self.ro_chs), reads_per_count=readouts_per_experiment)
#             while count<total_count:
#                 new_data = soc.poll_data()
#                 for d, s in new_data:
#                     new_points = d.shape[2]
#                     d_buf[:, :, count:count+new_points] = d
#                     count += new_points
#                     self.stats.append(s)
#                     pbar.update(new_points)
# >>>>>>> Stashed changes

# <<<<<<< Updated upstream
#         # avg_d calculated in QickProgram.acquire() assumes a different data shape, here we will recalculate based on
#         # the d_buf returned.
#         d_buf, avg_d, shots = super().acquire(soc, reads_per_rep=readouts_per_experiment, load_pulses=load_pulses,
#                                               start_src=start_src, progress=progress, debug=debug)
# =======
#         avg_di = None
#         for ii in tqdm(range(self.cfg["rounds"]), position=1, disable=not progress):
#             expt_pts, avg_di0, avg_dq0 = self.acquire_round(soc, threshold=threshold, angle=angle, readouts_per_experiment=readouts_per_experiment,
#                                                             save_experiments=save_experiments, load_pulses=load_pulses, start_src=start_src, progress=False, debug=debug)
# >>>>>>> Stashed changes