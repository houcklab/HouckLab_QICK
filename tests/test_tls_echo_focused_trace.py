import math

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSEchoFocusedTrace as focused,
)


def test_sites_bracket_old_4212_peak_and_include_two_controls():
    assert {4.204, 4.208, 4.212, 4.216}.issubset(focused.SITES_GHZ)
    assert {4.232, 4.284}.issubset(focused.SITES_GHZ)
    assert len(focused.DELAYS_US) >= 6
    assert min(focused.DELAYS_US) < .3
    assert max(focused.DELAYS_US) > 1.8


def test_reverse_block_changes_site_delay_and_phase_order():
    first = focused.schedule(0)
    second = focused.schedule(1)
    assert first[0]["frequency_ghz"] == min(focused.SITES_GHZ)
    assert second[0]["frequency_ghz"] == max(focused.SITES_GHZ)
    assert first[0]["echo_arms"][0] == (min(focused.DELAYS_US), 0)
    assert second[0]["echo_arms"][0] == (max(focused.DELAYS_US), 270)


def test_local_one_pulse_turnover_gate_requires_half_and_twice_pi():
    assert focused.rabi_gate(.46, .04)["valid"]
    assert not focused.rabi_gate(.85, .04)["valid"]
    assert not focused.rabi_gate(.46, .7)["valid"]


def test_trace_report_fits_decay_but_flags_revival():
    delays = focused.DELAYS_US
    cycles = {delay: {0: .5 + .4 * math.exp(-delay),
                      90: .5, 180: .5 - .4 * math.exp(-delay),
                      270: .5} for delay in delays}
    report = focused.trace_report(cycles)
    assert report["rate_per_us"] == pytest.approx(1.)
    assert report["revival_count"] == 0
    cycles[delays[-1]] = {0: .8, 90: .5, 180: .2, 270: .5}
    assert focused.trace_report(cycles)["revival_count"] >= 1


def test_single_point_schedule_reverses_four_blocks_at_4288():
    assert focused.SINGLE_SITE_GHZ == 4.288
    assert focused.SINGLE_DELAYS_US[0] < .15
    assert focused.SINGLE_DELAYS_US[-1] >= 4.
    first = focused.schedule(0, sites=(4.288,),
                             delays=focused.SINGLE_DELAYS_US)
    last = focused.schedule(3, sites=(4.288,),
                            delays=focused.SINGLE_DELAYS_US)
    assert first[0]["echo_arms"][0] == (focused.SINGLE_DELAYS_US[0], 0)
    assert last[0]["echo_arms"][0] == (focused.SINGLE_DELAYS_US[-1], 270)


def test_short_echo_sentinel_requires_repeatable_visibility_and_phase():
    first = {0: .9, 90: .5, 180: .1, 270: .5}
    repeat = {0: .87, 90: .5, 180: .13, 270: .5}
    wrong = {0: .1, 90: .5, 180: .9, 270: .5}
    assert focused.short_echo_gate(first, repeat)["valid"]
    assert not focused.short_echo_gate(first, wrong)["valid"]


def test_single_point_plan_has_no_t1_scout_and_four_repeats():
    plan = focused.plan(single_point=True)
    assert plan["sites_ghz"] == [4.288]
    assert plan["reversed_blocks"] == 4
    assert plan["t1_scans"] is None


def test_single_point_assessment_requires_repeated_consistent_echo():
    blocks = [{"sites": [{"status": "valid_controls",
                          "trace": {"status": "fit", "rate_per_us": rate,
                                    "log_fit_rms": .1, "revival_count": 0}}]}
              for rate in (.45, .49, .47, .46)]
    assert focused.assess_single_point(blocks)["repeatable"]
    blocks[2]["sites"][0]["trace"]["rate_per_us"] = 1.4
    assert not focused.assess_single_point(blocks)["repeatable"]
