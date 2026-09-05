import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    build_t1_point_config,
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import (
    ClassifierCalibration,
    Zone,
    classify,
    fit_classifier,
    qua_thresholds,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.config import (
    OPXResetConfig,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    RECORD_WORDS,
    ShotRecord,
    TerminalStatus,
    decode_records,
    max_records,
)


def _separated_blobs(seed=4, n=4000):
    rng = np.random.default_rng(seed)
    gi = rng.normal(1000, 700, n).astype(np.int64)
    gq = rng.normal(-2000, 700, n).astype(np.int64)
    ei = rng.normal(-11000, 900, n).astype(np.int64)
    eq = rng.normal(17000, 900, n).astype(np.int64)
    return gi, gq, ei, eq


def test_fit_orients_projection_from_ground_toward_excited():
    gi, gq, ei, eq = _separated_blobs()
    cal = fit_classifier(gi, gq, ei, eq, context="payload")

    assert np.median(cal.project(ei, eq)) > np.median(cal.project(gi, gq))
    assert cal.ground_threshold < cal.excited_threshold
    assert cal.context == "payload"
    assert cal.holdout["false_ground_accept"] <= 0.02
    assert cal.holdout["false_pi"] <= 0.02


def test_qua_thresholds_use_first_confident_and_peak_fidelity_points():
    ground = np.repeat(np.arange(-9, 1), 4)
    excited = np.repeat(np.arange(0, 10), 4)

    thresholds = qua_thresholds(
        ground,
        excited,
        ground_confidence_fidelity=0.7,
        threshold_steps=7,
    )

    assert thresholds["ground"] == -3
    assert thresholds["excited"] == 0
    assert thresholds["peak_fidelity"] == pytest.approx(0.95)


def test_classifier_can_fit_the_qua_confidence_policy():
    ground_i = np.repeat(np.arange(-9, 1), 4)
    excited_i = np.repeat(np.arange(0, 10), 4)
    zeros = np.zeros(40, dtype=np.int64)

    calibration = fit_classifier(
        ground_i,
        zeros,
        excited_i,
        zeros,
        context="loop",
        ground_confidence_fidelity=0.7,
        qua_threshold_steps=7,
    )

    assert calibration.ground_threshold == -3 * calibration.c_int
    assert calibration.excited_threshold == 0
    assert calibration.holdout["ground_accept"] == pytest.approx(0.7)
    assert calibration.holdout["excited_fire"] == pytest.approx(0.9)


def test_q3_benchmark_settings_drive_measured_timing_and_qua_thresholds():
    settings = q3_benchmark_settings()
    reset = OPXResetConfig.from_mapping(settings.opx_overrides())
    ground_i = np.repeat(np.arange(-9, 1), 4)
    excited_i = np.repeat(np.arange(0, 10), 4)
    zeros = np.zeros(40, dtype=np.int64)
    calibration = fit_classifier(
        ground_i,
        zeros,
        excited_i,
        zeros,
        context="loop",
        **settings.calibration_options(),
    )

    assert reset.feedback_syncdelay_us == 8.0
    assert reset.loop_recovery_us == 25.0
    assert reset.inter_shot_delay_us == 200.0
    assert calibration.holdout["ground_accept"] == pytest.approx(0.5)
    assert calibration.holdout["excited_fire"] == pytest.approx(1.0)
    assert calibration.holdout["ground_confidence_fidelity"] == pytest.approx(0.7)
    assert calibration.holdout["threshold_steps"] == 100


def test_t1_point_config_applies_flux_excursion_without_changing_park():
    cfg = build_t1_point_config(
        {"ff_park_gain": -25790, "ff_gain": -25790},
        reset_scheme="opx_unbounded",
        inter_shot_delay_us=50.0,
        shots=250,
        delay_us=12.5,
        excursion_gain=-20000,
    )

    assert cfg["ff_park_gain"] == -25790
    assert cfg["ff_gain"] == -20000
    assert cfg["do_ff"] is True
    assert cfg["ff_hold"] == pytest.approx(12.5)
    assert cfg["t1_wait_us"] == pytest.approx(12.5)
    assert cfg["shots"] == 250
    assert cfg["reps"] == 250
    assert cfg["opx_reset_scheme"] == "opx_unbounded"
    assert cfg["opx_inter_shot_delay_us"] == pytest.approx(50.0)


def test_t1_point_config_leaves_park_t1_at_the_park_gain():
    cfg = build_t1_point_config(
        {"ff_park_gain": -25790},
        reset_scheme="none",
        inter_shot_delay_us=1000.0,
        shots=250,
        delay_us=100.0,
    )

    assert cfg["ff_gain"] == -25790
    assert cfg["do_ff"] is False


def test_classifier_uses_strict_three_zone_boundaries():
    cal = ClassifierCalibration(
        schema_version=1,
        context="loop",
        theta_rad=0.0,
        shift=0,
        c_int=1,
        s_int=0,
        ground_threshold=-10,
        excited_threshold=10,
        max_abs_raw=100,
        holdout={},
    )

    assert classify(-10, cal) is Zone.GROUND
    assert classify(-9, cal) is Zone.AMBIGUOUS
    assert classify(10, cal) is Zone.AMBIGUOUS
    assert classify(11, cal) is Zone.EXCITED


def test_classifier_json_round_trip_preserves_assembly_thresholds():
    gi, gq, ei, eq = _separated_blobs()
    original = fit_classifier(gi, gq, ei, eq, context="loop")
    restored = ClassifierCalibration.from_dict(original.to_dict())

    assert restored == original
    assert restored.assembly_plan() == original.assembly_plan()
    assert restored.assembly_thresholds() == original.assembly_thresholds()


def test_config_accepts_diagnostic_attempt_limits_and_rejects_more_than_32():
    cfg = OPXResetConfig.from_mapping({"opx_max_reset_attempts": 24})

    assert cfg.max_reset_attempts == 24
    with pytest.raises(ValueError, match="1..32"):
        OPXResetConfig.from_mapping({"opx_max_reset_attempts": 33})


def test_config_accepts_user_facing_prefixed_keys():
    cfg = OPXResetConfig.from_mapping({
        "opx_max_reset_attempts": 8,
        "opx_read_delay_us": 1.5,
        "opx_feedback_syncdelay_us": 3.0,
        "opx_loop_recovery_us": 25.0,
        "opx_verification_delay_us": 0.25,
        "opx_record_base": 40,
    })

    assert cfg.max_reset_attempts == 8
    assert cfg.read_delay_us == 1.5
    assert cfg.feedback_syncdelay_us == 3.0
    assert cfg.loop_recovery_us == 25.0
    assert cfg.verification_delay_us == 0.25
    assert cfg.record_base == 40


def test_config_rejects_negative_loop_recovery():
    with pytest.raises(ValueError, match="loop_recovery_us"):
        OPXResetConfig.from_mapping({"opx_loop_recovery_us": -0.01})


def test_record_round_trip_converts_unsigned_hardware_words_to_signed():
    record = ShotRecord(
        preparation=1,
        initial_z=-123,
        reset_attempts=2,
        pi_pulses=1,
        terminal_status=TerminalStatus.CONFIRMED_GROUND,
        final_i=-456,
        final_q=789,
        last_z=-12,
    )
    unsigned = np.asarray(record.to_words(), dtype=np.int64) & 0xFFFFFFFF

    assert decode_records(unsigned, expected_records=1) == [record]


def test_record_decoder_rejects_truncated_blocks():
    with pytest.raises(ValueError, match="multiple"):
        decode_records(np.zeros(RECORD_WORDS - 1, dtype=np.int64))


def test_capacity_arithmetic_never_overruns_dmem():
    assert max_records(dmem_words=4096, record_base=32) == (4096 - 32) // RECORD_WORDS
    assert 32 + max_records(4096, 32) * RECORD_WORDS <= 4096
    with pytest.raises(ValueError, match="record_base"):
        max_records(dmem_words=32, record_base=32)


def test_unbounded_reset_mode_is_feedback_without_heralding():
    assert "opx_unbounded" in active_reset.RESET_MODES
    assert active_reset.uses_feedback("opx_unbounded")
    assert active_reset.uses_opx_unbounded("opx_unbounded")
    assert not active_reset.heralds("opx_unbounded")
    with pytest.raises(RuntimeError, match="no fixed readout count"):
        active_reset.active_reset_readouts({"reset_mode": "opx_unbounded"})
