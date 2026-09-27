import json

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.flux_predistortion import load_compensation_json


def test_qick_loader_accepts_measured_trace_candidate_schema(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({
        "enabled": True, "success": True, "multiplier_clipped": False,
        "method": "measured_trace_piecewise_set_dc_offset_correction",
        "segment_edges_ns": [0.0, 2000.0], "multipliers": [1.0, 1.02],
        "metadata": {"qubit": "q3", "flux_channel": 1,
                     "baseline_dc_offset": 10000, "dc_offset": 20000,
                     "intended_use": "measured_trace_set_dc_offset_tail_compensation",
                     "fit_ff_ramp_length_us": 0, "fit_dt_pulseplay_us": 2,
                     "fit_dt_pulsedef_us": 2},
    }))
    loaded = load_compensation_json(path, qubit="q3", baseline_dc_offset=10000,
                                    dc_offset=20000)
    assert loaded["multipliers"] == [1.0, 1.02]
