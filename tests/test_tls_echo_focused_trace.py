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


def test_single_point_schedule_reverses_four_blocks_at_4284():
    assert focused.SINGLE_SITE_GHZ == 4.284
    assert focused.SINGLE_DELAYS_US[0] < .15
    assert focused.SINGLE_DELAYS_US[-1] >= 4.
    first = focused.schedule(0, sites=(4.284,),
                             delays=focused.SINGLE_DELAYS_US)
    last = focused.schedule(3, sites=(4.284,),
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
    assert plan["sites_ghz"] == [4.284]
    assert plan["reversed_blocks"] == 4
    assert plan["t1_scans"] is None


def test_single_point_source_requires_two_valid_4284_blocks():
    site = {"frequency_ghz": 4.284, "status": "valid_controls",
            "rabi_gate": {"valid": True}, "control_gate": {"valid": True},
            "trace": {"rate_per_us": .5}}
    source = {"schema": "q3.echo-focused-trace.v1", "status": "complete",
              "session_id": focused.SINGLE_SOURCE_SESSION,
              "code_commit": "f7c12262" + "0" * 32,
              "correction_sha256": focused.localizer.CORRECTION_SHA256,
              "blocks": [{"sites": [site]}, {"sites": [site]}]}
    focused.validate_single_point_source(source)
    source["blocks"][1] = {"sites": [{**site, "status": "unresolved_local_control"}]}
    with pytest.raises(ValueError):
        focused.validate_single_point_source(source)


def test_single_point_assessment_requires_repeated_consistent_echo():
    blocks = [{"sites": [{"status": "valid_controls",
                          "trace": {"status": "fit", "rate_per_us": rate,
                                    "log_fit_rms": .1, "revival_count": 0}}]}
              for rate in (.45, .49, .47, .46)]
    assert focused.assess_single_point(blocks)["repeatable"]
    blocks[2]["sites"][0]["trace"]["rate_per_us"] = 1.4
    assert not focused.assess_single_point(blocks)["repeatable"]


def test_one_over_e_crossing_accepts_repeatable_nonexponential_decay():
    delays = (.08, .5, 1.2, 1.8, 2.6, 4.)
    values = (1., .9, .84, .66, .39, .1)
    report = focused.one_over_e_crossing(dict(zip(delays, values)))
    assert report["valid"]
    assert 2.6 < report["time_us"] < 2.8
    rebound = focused.one_over_e_crossing(dict(zip(delays,
                                                 (1., .9, .3, .7, .2, .1))))
    assert not rebound["valid"]
    assert not focused.one_over_e_crossing(dict(zip(
        delays, (1., .9, .8, .7, .6, .5))))["valid"]


def test_local_map_plan_stays_small_and_brackets_validated_sites():
    plan = focused.plan(local_map=True)
    assert plan["sites_ghz"] == [4.280, 4.284, 4.288, 4.292, 4.296]
    assert plan["reversed_blocks"] == 3
    assert plan["t1_scans"] is None
    assert plan["metric"] == "interpolated 1/e echo visibility crossing"


def test_local_map_assessment_uses_crossings_not_exponential_fit():
    sites = focused.LOCAL_MAP_SITES_GHZ
    blocks = []
    for index, crossing in enumerate((2.5, 2.7, 2.6)):
        blocks.append({"index": index, "sites": [
            {"frequency_ghz": frequency, "status": "valid_controls",
             "trace": {"one_over_e": {"valid": True, "time_us": crossing},
                       "log_fit_rms": .4}}
            for frequency in sites]})
    report = focused.assess_local_map(blocks)
    assert report["resolved_sites"] == len(sites)
    assert report["sites"]["4.288"]["mean_crossing_us"] == pytest.approx(2.6)
    blocks[0]["sites"][2]["status"] = "unresolved_local_control"
    blocks[1]["sites"][2]["status"] = "unresolved_local_control"
    assert focused.assess_local_map(blocks)["sites"]["4.288"]["status"] == "unresolved"
    blocks[0]["sites"][2]["status"] = "valid_controls"
    blocks[1]["sites"][2]["status"] = "valid_controls"
    blocks[2]["sites"][2]["trace"]["one_over_e"]["time_us"] = 3.9
    assert focused.assess_local_map(blocks)["sites"]["4.288"]["status"] == "unresolved"
