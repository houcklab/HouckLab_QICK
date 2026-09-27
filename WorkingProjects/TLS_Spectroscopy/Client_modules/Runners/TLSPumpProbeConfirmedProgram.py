"""Experiment-only saturation program using the checked half-gain reset policy."""

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.control_flow import (
    emit_unbounded_reset_state_machine,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetTLSSaturationProgram,
)


class ConfirmedPumpProbeProgram(OPXResetTLSSaturationProgram):
    """Require a loop decision in each reset; read the final probe at full gain."""

    def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
        gain = cfg.get("opx_diagnostic_probe_readout_gain")
        if type(gain) is not int or not 1 <= gain <= 32767:
            raise ValueError("diagnostic probe readout gain must be a positive signed-16-bit integer")
        if type(cfg.get("read_pulse_gain")) is not int or not 1 <= cfg["read_pulse_gain"] < gain:
            raise ValueError("diagnostic decision gain must be positive and below probe gain")
        if bool(cfg.get("ro_mode_periodic", False)):
            raise ValueError("diagnostic gain switching requires pulsed readout")
        super().__init__(soccfg, cfg, payload_calibration, loop_calibration)

    def _reset_saturation_qubit(self, label):
        self._set_reset_pulse()
        self._measure_project(self.payload_calibration, "payload")
        emit_unbounded_reset_state_machine(
            self,
            page=self.reset_page,
            regs=self.reset_regs,
            payload_calibration=self.payload_calibration,
            loop_calibration=self.loop_calibration,
            measure_next=lambda: self._measure_project(self.loop_calibration, "loop"),
            play_pi=lambda: self.pulse(ch=self.cfg["qubit_ch"]),
            label_prefix=label,
            wait_reset_ringdown=self._wait_reset_ringdown,
            require_loop_readout=True,
        )
        # Preserve the parent saturation sequence's post-readout timing guard.
        self._saturation_reset_guard_us = max(
            float(self.reset_config.read_delay_us) + 10.0,
            float(self.reset_config.loop_recovery_us),
            float(self.reset_config.feedback_syncdelay_us),
        )
        self.sync_all(self.us2cycles(self._saturation_reset_guard_us))

    def _wait_saturation_probe(self):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse

        super()._wait_saturation_probe()
        set_readout_pulse(self, gain=int(self.cfg["opx_diagnostic_probe_readout_gain"]))
        self._diagnostic_final_readout_pending = True

    def _measure_project(self, calibration, context):
        if not getattr(self, "_diagnostic_final_readout_pending", False):
            return super()._measure_project(calibration, context)
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import set_readout_pulse

        try:
            # The recorded probe needs only I/Q. Projecting it through the
            # half-gain feedback coefficients would have no consumer and may
            # exceed their calibrated arithmetic range at full readout gain.
            return self._measure_raw()
        finally:
            set_readout_pulse(self)
            self._diagnostic_final_readout_pending = False
