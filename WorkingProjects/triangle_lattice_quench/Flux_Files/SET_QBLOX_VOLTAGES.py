from triangle_lattice_quench.PythonDrivers.SPIRackvoltage import SPIRack, D5aModule
import numpy as np
import json

'''Running this file loads the voltages in PRESENT_CONFIG.JSON.
MODIFIES THE STATE OF THE QBLOX'''
#############################################################


set_unused_to_zero = True

# Running this file loads the voltages in PRESENT_CONFIG.JSON
PRESENT_CONFIG_PATH = r"C:\Users\houck\Documents\HouckLab_QICK\WorkingProjects\triangle_lattice_quench\Flux_Files\PRESENT_CONFIG.json"

with open(PRESENT_CONFIG_PATH) as fh:
    present_config = json.load(fh)
    DEFAULT_JSON_PATH = present_config["VOLTAGES_PATH"] 


##############################################################
def get_DACS_and_voltages_dicts(JSON_PATH):
    with open(JSON_PATH) as fh:
        jd = json.load(fh)
        DACs = jd['dac_map']
        voltages = jd['voltages']

    for qubit_name in voltages:
        assert qubit_name in DACs, f"Error: {qubit_name} given a voltage but is not in dac_map"

    return DACs, voltages

def reset_voltages(JSON_PATH):
    COM_speed = 1e6  # Baud rate, doesn't matter much
    timeout = 1  # In seconds
    port = 'COM3'
    spi_rack = SPIRack(port, COM_speed, timeout)
    D5a = D5aModule(spi_rack, module=2, reset_voltages=False, ramp_step=0.003, ramp_interval=0.01)

    # 0 to 4 Volt: range_4V_uni (span 0)
    # -4 to 4 Volt: range_4V_bi (span 2)
    # -2 to 2 Volt: range_2V_bi (span 4)
    span = D5a.range_4V_bi
    # span = D5a.range_8V_uni


    # Update span if needed
    for i in range(D5a._num_dacs):
        if not D5a.get_settings(i)[1] == span:
            current_settings = D5a.get_settings(i)
            D5a.change_span(i, span)
            D5a.set_voltage(i, current_settings[0])

    # print(spi_rack.get_temperature())
    # print(spi_rack.get_battery())
    # print(spi_rack.get_firmware_version())

    DACs, voltages = get_DACS_and_voltages_dicts(JSON_PATH)


    for qubit_name in DACs.keys():
        try:
            D5a.set_voltage_ramp(DACs[qubit_name], voltages[qubit_name])
        except KeyError as e:
            print(f"Warning: {qubit_name} is in dac_map but not in voltages, will -> 0 if set_unused_to_zero == True.")

    if set_unused_to_zero:
        for i in range(D5a._num_dacs):
            if i not in DACs.values():
                D5a.set_voltage(i, 0)

    for i in range(D5a._num_dacs):
        print(f'{i}: {np.round(D5a.get_settings(i)[0], 4)} V')
    spi_rack.close()

    print(JSON_PATH)

    try:
        with open(PRESENT_CONFIG_PATH, "w") as f:
            present_config["currently_set_voltages_path"] = JSON_PATH
            present_config["currently_set_voltages"] = voltages
            json.dump(present_config, f, indent=2)
    except Exception as e:
        print("Unable to update currently_set_voltages flag.", e)

    return DACs, voltages

if __name__ == '__main__':
    reset_voltages(DEFAULT_JSON_PATH)