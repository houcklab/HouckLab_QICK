import json
import pprint
import textwrap
from Device_calib.VoltageConfiguration import VoltageConfiguration
from Device_calib.DeviceInterface import DeviceInterface

'''This file modifies the flux offsets ("zero voltage fluxes")
stored in the device information, with the device path given in PRESENT_CONFIG.
It also generates a .prev file for easy reversion.
MODIFIES THE STATE OF THE DEVICE'''


with open("PRESENT_CONFIG.json") as f:
    data = json.load(f)
    DEVICE_PATH = data["DEVICE_PATH"]
    VOLTAGES_PATH = data["VOLTAGES_PATH"]

found_qubits = [
                # ['Q3', 0, 4010]
]
# qubit, expected freq, found freq

########################################
VC = VoltageConfiguration.from_json(DEVICE_PATH, VOLTAGES_PATH)
device_data = VC.device.ddata
device_data.to_json(DEVICE_PATH + ".previous")

old_zero_voltage_fluxes = device_data.zero_voltage_fluxes
new_zero_voltage_fluxes = old_zero_voltage_fluxes.copy()

for found_qubit in found_qubits:
    qubit, expected, found = found_qubit
    if expected > 10: # frequency passed
        expected_flux = VC.dressed_freq_to_flux(qubit, expected)
        print(f"{qubit} frequency {expected} MHz converted to {expected_flux} flux - verify correct sign")
    else: # flux passed directly
        expected_flux = expected

    if found > 10: # frequency passed
        found_flux = VC.dressed_freq_to_flux(qubit, found)
        print(f"{qubit} frequency {found} MHz converted to {found_flux} flux - verify correct sign")
    else: # flux passed directly
        found_flux = found

    new_zero_voltage_fluxes[qubit] += (found_flux - expected_flux)


device_data.zero_voltage_fluxes = new_zero_voltage_fluxes

device_data.to_json(DEVICE_PATH)

def pretty_dict_str(label, d):
    body = pprint.pformat(d, sort_dicts=False)[1:-1]  # strip outer braces
    s = f"{label}:{{\n " + textwrap.indent(body, " " * 4) + "\n}"
    return s

print(pretty_dict_str("Old values", old_zero_voltage_fluxes))
print(pretty_dict_str("New values", new_zero_voltage_fluxes))
print(f"{DEVICE_PATH} updated. Also generated .prev file if revert desired.")

