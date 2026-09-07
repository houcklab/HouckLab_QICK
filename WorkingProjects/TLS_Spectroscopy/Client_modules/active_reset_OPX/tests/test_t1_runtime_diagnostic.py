import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.t1_runtime_diagnostic_q3 import (
    estimate_stream_overhead,
)


def test_stream_overhead_matches_two_bank_words_per_record():
    result = estimate_stream_overhead(
        dmem_words=4096,
        record_base=32,
        record_words=2,
        records=71000,
        measured_words=2032,
        measured_seconds=1.1,
    )

    assert result == {
        "bank_records": 1016,
        "bank_words": 2032,
        "bank_count": 70,
        "single_read_us_per_word": pytest.approx(541.3385826771654),
        "estimated_single_read_stream_s": pytest.approx(77.0),
    }


def test_stream_overhead_rejects_invalid_dimensions():
    with pytest.raises(ValueError, match="positive"):
        estimate_stream_overhead(
            dmem_words=4096,
            record_base=32,
            record_words=0,
            records=71000,
            measured_words=2032,
            measured_seconds=1.1,
        )
