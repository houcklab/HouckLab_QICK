import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment1D_lines import \
    SweepExperiment1D_lines
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import \
    SweepExperiment2D_plots
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mSweepXPhase import SweepXPhase
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.quench_experiments.mMottQuench import \
    MottQuenchBasicProgram, MottQuenchBase
from WorkingProjects.triangle_lattice_quench.Helpers.Beamsplitter_Fit import fit_beamsplitter_offset
from WorkingProjects.triangle_lattice_quench.Helpers import SweepHelpers
from WorkingProjects.triangle_lattice_quench.Helpers import FF_Crosstalk_Helper
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF


# Variant (A): bare two-pi/2 phase sweep (pi/2 sanity / pulse-pair phase reference)
class SweepPi2Phase(SweepXPhase):
    '''
    Two sequential pi/2 pulses, sweeping the phase of the second pulse on swept_qubit.
    Reuses fit_beamsplitter_offset (sine + optional exp decay, multi-start) from the chevron pipeline.
    Per-qubit gains default to qubit_gains/2 from the JSON (matches mMottQuench's pi/2 convention).
    swept_qubit is 0-based throughout this file (consistent with pi2_init_index).
    '''
    def init_sweep_vars(self):
        # default the gain matrix to JSON-derived pi/2 = qubit_gains/2; user can still override via cfg.
        # Done AFTER super so we use super's else-branch fallback (which tiles qubit_gains across pulses)
        # and avoid the parent's broadcast branch at mSweepXPhase.py:108-110 that references cfg['qubit_pulse'].
        user_supplied = 'qubit_gains_matrix' in self.cfg
        super().init_sweep_vars()
        if not user_supplied:
            self.cfg['qubit_gains_matrix'] = np.asarray(self.cfg['qubit_gains_matrix'], dtype=float) / 2.0
        # Override the parent's 1-based x_key (it does swept_qubit-1) with the 0-based convention
        # used uniformly inside mSweeppi2Phase.
        self.x_key = ('qubit_phases_matrix', int(self.cfg['swept_qubit']), 1)

    def analyze(self, data):
        data_dict = data['data']
        Z = np.asarray(data_dict[self.z_value], float)[..., None]  # (R, O=phase, T=1)
        phases = np.asarray(data_dict[SweepHelpers.key_savename(self.x_key)], float)  # (O,) deg
        wait_times = np.array([0.0])  # no dynamics axis in variant A

        self.fit_params = fit_beamsplitter_offset(Z, phases, wait_times)
        data_dict.update(self.fit_params)
        data_dict['swept_qubit'] = self.cfg['swept_qubit']  # which qubit was swept


# Variant (B): two-qubit William-Oliver-style phase calibration. Single pi/2 on the seed,
# FF swap with one partner (other qubits held detuned by the Ramp_State / Dynamics_Point JSON
# entries), single pi/2 on the partner with swept phase, then readout. Per-qubit
# measurement_pi2_phases array replaces the original scalar measurement_pi2_phase.
class MottQuenchPi2PhaseProgram(MottQuenchBasicProgram):
    '''
    Two-qubit phase-calibration program (William-Oliver scheme). Sequence:
        1. FF up at Pulse_FF -- each qubit at its own drive frequency.
        2. Single pi/2 on the seed qubit at index pi2_init_index (phase 0).
        3. FF jump to Expt_FF -- seed + partner come into resonance; non-paired qubits
           held detuned by the Ramp_State + Dynamics_Point JSON entries.
        4. Hold expt_samples -> partial iSWAP-like swap evolution between seed and partner.
        5. FF jump back to Pulse_FF -- qubits separate again, each at own drive freq.
        6. Single pi/2 on the partner at index swept_qubit (0-based), with phase
           cfg['measurement_pi2_phases'][swept_qubit] -- swept by the sweep engine.
        7. FF jump to Readout_FF, ADC trigger + res pulse.
    Inherits _initialize from this class (per-qubit measurement phase) and the FF
    cleanup tail from the parent. swept_qubit and pi2_init_index are BOTH 0-based
    indices into Qubit_Pulse, and normally point at DIFFERENT qubits (the seed and
    its partner).
    '''
    def _initialize(self, cfg):

        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])

        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])

        FF.FFDefinitions(self)

        # William-Oliver common-frequency scheme (Karamlou et al. S4C): BOTH pi/2 pulses fire at
        # the common interaction frequency f_int = meas_pi2_freq, with the SPECTATOR qubit detuned
        # during each pulse so only one qubit is resonant at f_int at a time. (Empirically required:
        # two pi/2 at DIFFERENT frequencies do not produce a fringe on this hardware.) Build the two
        # asymmetric FF geometries (mirror of each other) from the per-qubit Expt/Pulse gains, then
        # crosstalk-correct (same convention as FFDefinitions). Gated on the flag + a set f_int.
        self._wo = bool(self.cfg.get('second_pulse_at_dynamics')) and self.cfg.get('meas_pi2_freq') is not None
        if self._wo:
            qp = self.cfg.get('Qubit_Pulse') or self.cfg.get('_Qubit_Pulse_list')
            seed_chip = str(qp[int(self.cfg['pi2_init_index'])])
            partner_chip = str(qp[int(self.cfg['swept_qubit'])])
            # FFSeed: all at Expt, but PARTNER returned to idle -> seed qubit alone at f_int (SEED pi/2).
            raw_seed = [self.cfg["FF_Qubits"][q]["Gain_Expt"] for q in self.FFQubits]
            raw_seed[self.FFQubits.index(partner_chip)] = self.cfg["FF_Qubits"][partner_chip]["Gain_Pulse"]
            self.FFSeed = FF_Crosstalk_Helper.correct(np.array(raw_seed))
            # FFSecond: all at Expt, but SEED returned to idle -> partner alone at f_int (MEASURE pi/2).
            raw_second = [self.cfg["FF_Qubits"][q]["Gain_Expt"] for q in self.FFQubits]
            raw_second[self.FFQubits.index(seed_chip)] = self.cfg["FF_Qubits"][seed_chip]["Gain_Pulse"]
            self.FFSecond = FF_Crosstalk_Helper.correct(np.array(raw_second))

        # qubit init pulses (one Gaussian envelope per pulse)
        for i in range(len(cfg["qubit_gains"])):
            gain = cfg["qubit_gains"][i]
            self.add_gauss(ch=cfg["qubit_ch"], name=f"qubit{i}", sigma=cfg["sigma"][i], length=4 * cfg["sigma"][i])
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_drive_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=0,
                           gain=gain)
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_pi2_{i}', style="arb", envelope=f"qubit{i}",
                           freq=cfg["qubit_freqs"][i],
                           phase=0,
                           gain=gain/2)
            # measurement pi/2 (swept phase). Own frequency, EXCEPT in second-pulse-at-dynamics
            # mode the swept qubit is parked at the seed's Expt_FF frequency at the swapped
            # dynamics point, so drive its measurement pi/2 there. The swap point passes that
            # absolute frequency as cfg['meas_pi2_freq'] (from the dynamics entry); convert to
            # the generator IF by subtracting the qubit LO. Fall back to the seed's drive freq.
            meas_freq = cfg["qubit_freqs"][i]
            meas_gain = gain / 2                      # normalized default (qubit_gains[i]/2)
            if self.cfg.get('second_pulse_at_dynamics') and i == int(self.cfg['swept_qubit']):
                if self.cfg.get('meas_pi2_freq') is not None:
                    meas_freq = float(self.cfg['meas_pi2_freq']) - cfg['qubit_LO']
                else:
                    meas_freq = cfg["qubit_freqs"][int(self.cfg['pi2_init_index'])]
                # 2nd-pi/2 GAIN override (DAC units in cfg, consistent with the JSON Gain
                # field / chevron); convert to the normalized pulse gain (DAC/32766).
                if self.cfg.get('meas_pi2_gain') is not None:
                    meas_gain = float(self.cfg['meas_pi2_gain']) / 32766.0
            self.add_pulse(ch=cfg["qubit_ch"], name=f'qubit_measurement_pi2_{i}', style="arb", envelope=f"qubit{i}",
                           freq=meas_freq,
                           phase=self.cfg["measurement_pi2_phases"][i],  # per-qubit measurement pi/2 phase
                           gain=meas_gain)

        # INIT pi/2 pulse on the seed qubit AT the common interaction frequency f_int (= meas_pi2_freq).
        # This is what makes the init & measurement pi/2 share one frequency (the empirical fringe condition).
        if self._wo:
            init_idx = int(self.cfg['pi2_init_index'])
            # INIT pi/2 GAIN: at the interaction flux the drive coupling differs from idle, so the
            # idle pi/2 gain (qubit_gains/2) over-/under-rotates. Prefer an explicit interaction-flux
            # init-pi/2 gain (pi2_init_gain, DAC -- calibrate it with the gain x freq cal run on the
            # init qubit); else fall back to the measurement pi/2 gain (meas_pi2_gain, a better
            # estimate than idle); else the idle pi/2.
            if self.cfg.get('pi2_init_gain') is not None:
                seed_gain = float(self.cfg['pi2_init_gain']) / 32766.0
            elif self.cfg.get('meas_pi2_gain') is not None:
                seed_gain = float(self.cfg['meas_pi2_gain']) / 32766.0
            else:
                seed_gain = cfg["qubit_gains"][init_idx] / 2
            self.add_pulse(ch=cfg["qubit_ch"], name='qubit_init_pi2', style="arb", envelope=f"qubit{init_idx}",
                           freq=float(self.cfg['meas_pi2_freq']) - cfg['qubit_LO'],
                           phase=0,
                           gain=seed_gain)  # init pi/2 at f_int

        self.qubit_total_length_us = 4 * sum(cfg["sigma"])

    def _body(self, cfg):
        FF_Delay_time = 0.2
        Second_FFPulse_delay = 0.2
        init_idx = int(self.cfg['pi2_init_index'])  # 0-based index into Qubit_Pulse
        meas_idx = int(self.cfg['swept_qubit'])     # 0-based index into Qubit_Pulse

        if getattr(self, '_wo', False):
            ### William-Oliver common-frequency scheme: both pi/2 at f_int, spectator detuned.
            # 1. Init: seed qubit at Expt(f_int), partner detuned (FFSeed) -> INIT pi/2 @ f_int.
            self.FFPulses(self.FFSeed, self.qubit_total_length_us + FF_Delay_time)
            self.pulse(ch=self.cfg["qubit_ch"], name='qubit_init_pi2', t=FF_Delay_time)
            self.delay_auto()
            # 2. Dwell: partner steps idle->Expt (FFSeed -> FFExpts), both resonant -> iSWAP.
            self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples"],
                                 self.FFSeed, IQPulseArray=self.cfg["IQArray_wo"], waveform_label='FFDynamics')
            self.delay_auto()
            # 3. Measure: partner at Expt(f_int), seed detuned (FFSecond) -> MEASURE pi/2 @ f_int (swept phase).
            self.FFPulses(self.FFSecond, self.qubit_total_length_us + Second_FFPulse_delay)
            self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_measurement_pi2_{meas_idx}', t=Second_FFPulse_delay)
            self.delay_auto()
            ### Readout
            self.FFPulses(self.FFReadouts, self.cfg["res_length"])
            for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
                self.trigger(ros=[ro_ch], t=adc_trig_delay)
            self.pulse(cfg["res_ch"], name='res_drive')
            self.wait_auto()
            self.delay_auto(10)  # us
            ### FF cleanup -- mirror the unwinds with the W-O geometries
            self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
            self.FFPulses(-1 * self.FFSeed, self.qubit_total_length_us + FF_Delay_time)
            self.FFPulses(-1 * self.FFSecond, self.qubit_total_length_us + Second_FFPulse_delay)
            self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples"],
                                 -1 * self.FFSeed, IQPulseArray=[-arr for arr in self.cfg["IQArray_wo"]],
                                 waveform_label='FFDynamicsInverse')
            self.delay_auto()
            return

        ### Init: pi/2 on the seed qubit only (no pulses on the other qubits)
        self.FFPulses(self.FFPulse, self.qubit_total_length_us + FF_Delay_time)
        self.pulse(ch=self.cfg["qubit_ch"], name=f'qubit_pi2_{init_idx}', t=FF_Delay_time)
        self.delay_auto()

        ### Dynamics: jump to Expt_FF (seed + partner resonant; others held detuned by Ramp_State)
        self.FFPulses_direct(self.FFExpts, self.cfg["expt_samples"],
                             self.FFPulse, IQPulseArray=self.cfg["IQArray"], waveform_label='FFDynamics')
        self.delay_auto()

        ### Measurement: jump to the 2nd-pulse FF point, pi/2 on the swept qubit with swept phase
        use_dyn = bool(self.cfg.get('second_pulse_at_dynamics'))
        # use_dyn (legacy, no meas_pi2_freq): park at the swapped-frequency dynamics point (FFBS);
        # else: original behaviour (jump back to Pulse_FF, drive at the swept qubit's own freq).
        second_FF = self.FFBS if use_dyn else self.FFPulse
        meas_pulse = f'qubit_measurement_pi2_{meas_idx}'  # freq set in _initialize
        self.FFPulses(second_FF, self.qubit_total_length_us + Second_FFPulse_delay)
        self.pulse(ch=self.cfg["qubit_ch"], name=meas_pulse, t=Second_FFPulse_delay)
        self.delay_auto()

        ### Readout
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us


        ### FF cleanup -- mirror the parent's negative-pulse unwinds so state returns to baseline
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_total_length_us + FF_Delay_time)
        self.FFPulses(-1 * second_FF, self.qubit_total_length_us + Second_FFPulse_delay)
        self.FFPulses_direct(-1 * self.FFExpts, self.cfg["expt_samples"],
                             -1 * self.FFPulse, IQPulseArray=[-arr for arr in self.cfg["IQArray"]],
                             waveform_label='FFDynamicsInverse')

        self.delay_auto()


class MottQuenchPi2Phase(MottQuenchBase, SweepExperiment1D_lines):
    '''
    Two-qubit William-Oliver phase calibration at a fixed expt_samples: pi/2 on the seed
    (pi2_init_index), FF swap with the partner, pi/2 on the partner (swept_qubit) with the
    swept phase, readout. Captures the dynamical/swap-accumulated phase of the partner pulse.
    Reuses fit_beamsplitter_offset.
    '''
    def init_sweep_vars(self):

        super().init_sweep_vars()

        self.Program = MottQuenchPi2PhaseProgram
        self.z_value = 'population_corrected'

        number_of_qubits = len(self.cfg['qubit_gains'])
        # ensure a per-qubit mutable phase array exists before the first set_nested_item
        if 'measurement_pi2_phases' not in self.cfg:
            self.cfg['measurement_pi2_phases'] = np.zeros(number_of_qubits)

        self.x_key = ('measurement_pi2_phases', int(self.cfg['swept_qubit']))
        self.x_points = np.linspace(self.cfg['phase_start'], self.cfg['phase_end'],
                                    self.cfg['phase_num_points'])
        self.xlabel = 'measurement pi/2 phase (deg)'  # for plotting

    def analyze(self, data):
        data_dict = data['data']
        Z = np.asarray(data_dict[self.z_value], float)[..., None]  # (R, O=phase, T=1)
        phases = np.asarray(data_dict[SweepHelpers.key_savename(self.x_key)], float)  # (O,) deg
        wait_times = np.array([float(self.cfg.get('expt_samples', 0))])  # fixed dynamics duration

        self.fit_params = fit_beamsplitter_offset(Z, phases, wait_times)
        data_dict.update(self.fit_params)
        data_dict['swept_qubit'] = self.cfg['swept_qubit']  # which qubit was swept


class MottQuenchPi2FreqCal(MottQuenchBase, SweepExperiment1D_lines):
    '''
    In-situ calibration of the 2nd (measurement) pi/2 DRIVE FREQUENCY at the swap
    dynamics point. Runs the full MottQuenchPi2PhaseProgram sequence UNCHANGED but
    sweeps cfg['meas_pi2_freq'] (the absolute 2nd-pi/2 frequency, used by the program
    in second-pulse-at-dynamics mode) instead of the phase. The swept qubit's
    population shows an extremum at the qubit's true frequency at the swap point;
    analyze() reports it as data['data']['meas_pi2_freq_cal'] (absolute MHz) -- the
    value to load into measurement_pi2_freq for the real run.
    Requires second_pulse_at_dynamics=True and a Dynamics_Point (swap point).
    '''
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.Program = MottQuenchPi2PhaseProgram
        self.z_value = 'population_corrected'
        number_of_qubits = len(self.cfg['qubit_gains'])
        if 'measurement_pi2_phases' not in self.cfg:
            self.cfg['measurement_pi2_phases'] = np.zeros(number_of_qubits)
        self.cfg['second_pulse_at_dynamics'] = True   # only meaningful in dynamics mode
        self.x_key = 'meas_pi2_freq'                   # scalar cfg key the program bakes the 2nd pi/2 freq from
        self.x_points = np.linspace(self.cfg['freq_start'], self.cfg['freq_end'],
                                    int(self.cfg['freq_num_points']))
        self.xlabel = '2nd pi/2 frequency (MHz)'

    def analyze(self, data):
        data_dict = data['data']
        x = np.asarray(data_dict[SweepHelpers.key_savename(self.x_key)], float)  # freqs (MHz)
        # swept qubit's readout trace. Map the swept (0-based) position -> chip qubit ->
        # readout index, normalizing BOTH sides to str (Qubit_Readout_List / Qubit_Pulse
        # are string chip labels from build_config / _build_cfg). Mirror _on_finished's
        # str(Qubit_Pulse[sq]) vs string-Qubit_Readout comparison so swept!=0 maps right.
        sw = int(self.cfg['swept_qubit'])
        chip = None
        if 'Qubit_Pulse' in self.cfg and 0 <= sw < len(self.cfg['Qubit_Pulse']):
            chip = str(self.cfg['Qubit_Pulse'][sw])
        ro_list = [str(q) for q in self.cfg.get('Qubit_Readout_List', [])]
        ro_idx = ro_list.index(chip) if (chip is not None and chip in ro_list) else 0
        Z = np.asarray(data_dict[self.z_value][ro_idx], float)  # population vs freq
        # resonance = frequency of max deviation from the off-resonant baseline (median).
        # Robust to dip-vs-peak; refine with a local parabola around the extremum.
        base = np.median(Z)
        k = int(np.argmax(np.abs(Z - base)))
        f_res = float(x[k])
        # local parabolic refine (3-pt) if interior
        if 0 < k < len(x) - 1:
            y0, y1, y2 = Z[k-1]-base, Z[k]-base, Z[k+1]-base
            denom = (y0 - 2*y1 + y2)
            if denom != 0:
                shift = 0.5 * (y0 - y2) / denom
                if abs(shift) <= 1:
                    f_res = float(x[k] + shift * (x[1]-x[0]))
        data_dict['meas_pi2_freq_cal'] = f_res
        data_dict['meas_pi2_freq_cal_ro_idx'] = ro_idx


class MottQuenchPi2GainFreqCal(MottQuenchBase, SweepExperiment2D_plots):
    '''
    In-situ 2D calibration of the 2nd (measurement) pi/2 pulse: x = drive frequency
    (cfg['meas_pi2_freq'], abs MHz), y = drive gain (cfg['meas_pi2_gain'], DAC). Runs
    the full MottQuenchPi2PhaseProgram sequence unchanged; only the 2nd pi/2's freq+gain
    sweep. The swept qubit's population is a gain x freq chevron. analyze() reports
    data['data']['meas_pi2_freq_cal'] (abs MHz) and ['meas_pi2_gain_cal'] (DAC) -- the
    values the real run loads into measurement_pi2_freq / measurement_pi2_gain.
    Requires second_pulse_at_dynamics=True and a Dynamics_Point.
    '''
    def init_sweep_vars(self):
        super().init_sweep_vars()
        self.Program = MottQuenchPi2PhaseProgram
        self.z_value = 'population_corrected'
        n = len(self.cfg['qubit_gains'])
        if 'measurement_pi2_phases' not in self.cfg:
            self.cfg['measurement_pi2_phases'] = np.zeros(n)
        self.cfg['second_pulse_at_dynamics'] = True
        self.x_key = 'meas_pi2_freq'
        self.x_points = np.linspace(self.cfg['freq_start'], self.cfg['freq_end'], int(self.cfg['freq_num_points']))
        self.xlabel = '2nd pi/2 frequency (MHz)'
        self.y_key = 'meas_pi2_gain'
        self.y_points = np.linspace(self.cfg['gain_start'], self.cfg['gain_end'], int(self.cfg['gain_num_points']))
        self.ylabel = '2nd pi/2 gain (DAC)'

    def analyze(self, data):
        # Fully defensive: never throw (a calibration plot is still useful even if the
        # extremum extraction degenerates). Best-effort freq + pi/2 gain estimate.
        try:
            dd = data['data']
            x = np.asarray(dd[SweepHelpers.key_savename(self.x_key)], float)  # freqs
            y = np.asarray(dd[SweepHelpers.key_savename(self.y_key)], float)  # gains
            # swept qubit's readout trace, indexed Z[ro][y=gain, x=freq] (engine order:
            # y outer, x inner -- see SweepExperimentND.keys = (y_key, x_key)).
            sw = int(self.cfg['swept_qubit'])
            chip = str(self.cfg['Qubit_Pulse'][sw]) if 'Qubit_Pulse' in self.cfg else None
            ro_list = [str(q) for q in self.cfg.get('Qubit_Readout_List', [])]
            ro_idx = ro_list.index(chip) if (chip in ro_list) else 0
            Z = np.asarray(dd[self.z_value][ro_idx], float)   # shape (len(y), len(x))
            base = np.median(Z)
            # resonance frequency: column (freq) of max total response across gains
            # (robust to dip/peak).
            col_dev = np.sum(np.abs(Z - base), axis=0)        # over gain axis -> per-freq
            fk = int(np.argmax(col_dev)); f_res = float(x[fk])
            # pi/2 gain at the resonance column: gain of FIRST maximum |response| (= pi
            # pulse / full flip), halved (rotation angle ~ linear in gain, so pi/2 gain ~
            # pi gain / 2). Best-effort -- see class/known-risks notes.
            col = np.abs(Z[:, fk] - base)
            gk = int(np.argmax(col)); g_pi = float(y[gk]); g_pi2 = g_pi / 2.0
            dd['meas_pi2_freq_cal'] = f_res
            dd['meas_pi2_gain_cal'] = g_pi2
            dd['meas_pi2_cal_ro_idx'] = ro_idx
        except Exception:
            pass


class MottQuenchPi2Phase2D(MottQuenchBase, SweepExperiment2D_plots):
    '''
    Two-qubit William-Oliver phase calibration mapped over (dynamics_time, phase):
    x_key = dynamics samples (the FF dwell time when seed + partner are resonant),
    y_key = measurement pi/2 phase of the partner (swept_qubit). Traces phi0(t) and the
    coherence-decay envelope of the partner under the iSWAP-like drive.
    '''
    def init_sweep_vars(self):

        super().init_sweep_vars()

        self.Program = MottQuenchPi2PhaseProgram
        self.z_value = 'population_corrected'

        number_of_qubits = len(self.cfg['qubit_gains'])
        # ensure a per-qubit mutable phase array exists before the first set_nested_item
        if 'measurement_pi2_phases' not in self.cfg:
            self.cfg['measurement_pi2_phases'] = np.zeros(number_of_qubits)

        self.x_key = 'expt_samples'
        self.x_points = np.linspace(self.cfg['samples_start'], self.cfg['samples_end'],
                                    self.cfg['samples_num_points'])
        self.xlabel = 'Samples (4.65/16 ns)'  # for plotting

        self.y_key = ('measurement_pi2_phases', int(self.cfg['swept_qubit']))
        self.y_points = np.linspace(self.cfg['phase_start'], self.cfg['phase_end'],
                                    self.cfg['phase_num_points'])
        self.ylabel = 'measurement pi/2 phase (deg)'  # for plotting

    def analyze(self, data):
        data_dict = data['data']
        Z = np.asarray(data_dict[self.z_value], float)  # (R, O=phase, T=samples)
        phases = np.asarray(data_dict[SweepHelpers.key_savename(self.y_key)], float)  # (O,) deg
        wait_times = np.asarray(data_dict[self.x_key], float)  # (T,)

        self.fit_params = fit_beamsplitter_offset(Z, phases, wait_times)
        data_dict.update(self.fit_params)
        data_dict['swept_qubit'] = self.cfg['swept_qubit']  # which qubit was swept
