import json
import matplotlib.pyplot as plt
from Device_calib.helper_Triladder_plotting import plot_bare_triladder, plot_dressed_triladder
import pprint
import textwrap
from Device_calib.VoltageConfiguration import VoltageConfiguration

with open("PRESENT_CONFIG.json") as f:
    data = json.load(f)
    DEVICE_PATH = data["DEVICE_PATH"]

#########

SAVE_VOLTAGES_PATH = None#r"Voltage_jsons/8QV1_Q0V/scratchwork.json"

configuration = {
    # "Q1": 3800,
    # "Q2": 3800,
    # "Q3": 3800,
    # "Q4": 3800,
    # "Q5": 3800,
    # "Q6": 3800,
    # "Q7": 3800,
    # "Q8": 3800,
    "C1": 0,
    "C2": 0,
    "C3": 0,
    "C4": 0,
    "C5": 0,
    "C6": 0,
}

plot_bare_system = True
plot_effective_system = True

dac_map = {
    # "Q1": 1,
    # "Q2": 2,
    # "Q3": 3,
    # "Q4": 4,
    # "Q5": 5,
    # "Q6": 6,
    # "Q7": 7,
    # "Q8": 8,
    "C1": 9,
    "C2": 10,
    "C3": 11,
    "C4": 12,
    "C5": 13,
    "C6": 14
}


########################

if __name__ == "__main__":
    from Device_calib.DeviceData import DeviceData
    from Device_calib.DeviceInterface import DeviceInterface

    device = DeviceInterface.from_json(DEVICE_PATH)
    vc = VoltageConfiguration(device, configuration)
    voltages = vc.get_voltages_dict()
    bare_freqs = vc.get_bare_frequencies_dict()

    rounded_voltages = {k: round(float(voltages[k]), 4) for k in device.dc_lines}
    rounded_freqs = {k: round(float(bare_freqs[k]), 1) for k in device.ordered_all_transmons}

    if SAVE_VOLTAGES_PATH is not None:
        savedict = {"voltages":rounded_voltages, "frequencies_comment":rounded_freqs, "dac_map":dac_map}
        with open(SAVE_VOLTAGES_PATH, "w") as f:
            json.dump(savedict, f, indent=2)

    ### Printing and Plotting

    def pretty_dict_str(label, d):
        body = pprint.pformat(d, sort_dicts=False)[1:-1]  # strip outer braces
        s = f"{label}:{{\n " + textwrap.indent(body, " " * 4) + "\n}"
        return s
    print(pretty_dict_str("Frequencies", rounded_freqs))
    print(pretty_dict_str("Voltages", rounded_voltages))
    print(f"Saved to {SAVE_VOLTAGES_PATH}")

    if plot_bare_system:
        plot_bare_triladder(bare_freqs, vc.get_all_bare_couplings_dict())

    if plot_effective_system:
        plot_dressed_triladder(vc.get_dressed_frequencies_dict(), vc.get_all_dressed_couplings_dict())

    plt.show(block=True)


