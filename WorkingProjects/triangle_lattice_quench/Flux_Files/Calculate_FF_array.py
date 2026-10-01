import json
import matplotlib.pyplot as plt
from Device_calib.VoltageConfiguration import VoltageConfiguration
from triangle_lattice_quench.Flux_Files.Device_calib.helper_Triladder_plotting import \
    plot_dressed_triladder

with open("PRESENT_CONFIG.json") as f:
    data = json.load(f)
    DEVICE_PATH = data["DEVICE_PATH"]
    VOLTAGES_PATH = data["VOLTAGES_PATH"]

frequencies = {
    'Q1': 3900,
    'Q2': 4200,
    'Q3': 3500,
    'Q4': 3800,
    'Q5': 4100,
    'Q6': 3550,
    'Q7': 3850,
    'Q8': 4150,
}



vc = VoltageConfiguration.from_json(DEVICE_PATH, VOLTAGES_PATH)

gains = vc.desired_freqs_to_fast_flux(frequencies)

import pprint
import textwrap
def pretty_dict_str(label, d):
    body = pprint.pformat(d, sort_dicts=False)[1:-1]  # strip outer braces
    s = f"{label}:{{\n " + textwrap.indent(body, " " * 4) + "\n}"
    return s
print(pretty_dict_str("Gains", gains))
print([gains[key] for key in vc.device.ff_lines])

plot_dressed_triladder(vc.get_dressed_frequencies_dict(gains), vc.get_all_dressed_couplings_dict(gains))
plt.show(block=True)