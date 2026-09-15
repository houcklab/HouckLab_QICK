"""Seven-condition matched-reference T1 scan for q3.

This keeps the established five-condition runner available while adding two
survival delays and alternating the survival-delay play order on reverse shots.
"""

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    FivePointApplesToApples as _five,
)


P6_7PT_APPLES_TO_APPLES = {
    **_five.P6_5PT_APPLES_TO_APPLES,
    "decay_delays_us": [40.0, 80.0, 120.0, 160.0, 200.0],
    "shots_per_condition": 180,
    "reverse_survival_order": True,
    "sync_session": "q3_q5_7pt_apples_20260915_v1",
    "sync_slot_s": 180.0,
}


def main():
    _five.P6_5PT_APPLES_TO_APPLES = dict(P6_7PT_APPLES_TO_APPLES)
    _five.main()


if __name__ == "__main__":
    main()
