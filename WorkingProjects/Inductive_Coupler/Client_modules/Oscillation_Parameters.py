##################### Qubit 1 and 2 on resonance, Put qubit 2 away, second excited state pi pulse
####################

# yoko69.rampstep = 0.0005
# yoko70.rampstep = 0.0005
# yoko71.rampstep = 0.0005
# yoko72.rampstep = 0.0005
#
# yoko69.SetVoltage(-0.1656)
# yoko70.SetVoltage(-0.1978)
# yoko71.SetVoltage(-0.0586)
# yoko72.SetVoltage(-0.0564)
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.61 + 1, 'Gain': 8000}, 'Qubit01': {'Frequency': 4499.7, 'Gain': 790},
#           'Qubit12': {'Frequency': 4343.6, 'Gain': 1830},
#           'Pulse_FF': [0, 5000, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.44, 'Gain': 6000}, 'Qubit01': {'Frequency': 4389.73, 'Gain': 1650},
#           'Qubit12': {'Frequency': 4231.8, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit01': {'Frequency': 4387.0, 'Gain': 2100},
#           'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '4': {'Readout': {'Frequency': 7249.71, 'Gain': 6000}, 'Qubit01': {'Frequency': 4390.46, 'Gain': 2000},
#           'Qubit12': {'Frequency': 4232.49, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, 0]}
#     }
#
# # Readout
# FF_gain1 = 0  # 8000
# FF_gain2 = 5000
# FF_gain3 = 0
# FF_gain4 = 0
#
# # expt
# FF_gain1_expt = 0  # 8000
# FF_gain2_expt = 0
# FF_gain3_expt = 0
# FF_gain4_expt = 0
#
# Qubit_Readout = 1
# Qubit_Pulse = 1
#
# config["sigma"] = 0.05
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#~~~~~~~~~~~~~~~~~~~ Start oscillations between qubits 1 and 2 and 2 and 4
# yoko69.SetVoltage(-0.0887)
# yoko70.SetVoltage(-0.2419)
# yoko71.SetVoltage(-0.0012)
# yoko72.SetVoltage(0.2829)
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.61 + 1, 'Gain': 8000}, 'Qubit01': {'Frequency': 4499.7, 'Gain': 790},
#           'Qubit12': {'Frequency': 4343.6, 'Gain': 1830},
#           'Pulse_FF': [0, 5000, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.39, 'Gain': 8500}, 'Qubit01': {'Frequency': 4418.85, 'Gain': 1120},
#           'Qubit12': {'Frequency': 4263.3 , 'Gain': 1740},
#           'Pulse_FF': [-7000, 0, 0, -8000]},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit01': {'Frequency': 4387.0, 'Gain': 2100},
#           'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '4': {'Readout': {'Frequency': 7249.71, 'Gain': 6000}, 'Qubit01': {'Frequency': 4390.46, 'Gain': 2000},
#           'Qubit12': {'Frequency': 4232.49, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, 0]}
#     }
#
# Qubit_Readout = 2
# Qubit_Pulse = 2
# # Readout
# FF_gain1 = -7000  # 8000
# FF_gain2 = 0
# FF_gain3 = 0
# FF_gain4 = -8000
#
# # expt
# FF_gain1_expt = -7000  # 8000
# FF_gain2_expt = 0
# FF_gain3_expt = 0
# FF_gain4_expt = -8000
#
# Qubit1_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit1_n_exp_Final.p', 'rb'))
# Qubit2_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit2_n_exp_Final.p', 'rb'))
# Qubit4_ = pickle.load(open('Z:/Jeronimo/Qubit_Calibration_FF_Params/Qubit4_n_exp_Final.p', 'rb'))
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 2 photon All 4 qubits close to 4.42 Ghz ##############################
# yoko69.SetVoltage(-0.0928)
# yoko70.SetVoltage(-0.2451)
# yoko71.SetVoltage(-0.315)
#
# yoko72.SetVoltage(0.2793)
#
# #Readout Qubit Params
#
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.5, 'Gain': 11500, "FF_Gains": [-11000, 0, 0, 0]},
#           'Qubit01': {'Frequency': 4664.1, 'Gain': 1380},
#           'Qubit12': {'Frequency': 4510.7, 'Gain': 640},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.6, 'Gain': 8000, "FF_Gains": [0, 11000, 0, 0]},
#           'Qubit01': {'Frequency': 4693, 'Gain': 1000},
#           'Qubit12': {'Frequency': 4538.2 , 'Gain': 790},
#           'Pulse_FF': [0, 11000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.1, 'Gain': 8000, "FF_Gains": [0, 0, 11000, 0]},
#           'Qubit01': {'Frequency': 4692.7, 'Gain': 1330},
#           'Qubit12': {'Frequency': 4538.4, 'Gain': 680},
#           'Pulse_FF': [0, 0, 11000, 0]},
#     '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500, "FF_Gains": [0, 0, 0, -14000]},
#           'Qubit01': {'Frequency': 4670.5, 'Gain': 1500},
#           'Qubit12': {'Frequency': 4516.3, 'Gain': 820},
#           'Pulse_FF': [0, 0, 0, -14000] }
#     }
#
# # expt
# FF_gain1_expt = -90  # 8000
# FF_gain2_expt = 65
# FF_gain3_expt = 0
# FF_gain4_expt = -245
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ End 2 photon 4 qubit ~~~~~~~~~~~~~~~~~~~~~~~~~

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 2 photon All 4 qubits close to 4.395 GHz ##############################
# yoko69.SetVoltage(-0.0622)
# yoko70.SetVoltage(-0.2662)
# yoko71.SetVoltage(-0.3391)
# yoko72.SetVoltage(0.328)

#
#Readout Qubit Params 01 distinguish
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-20000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency':  4610.4, 'Gain': 1750},
#           'Qubit12': {'Frequency': 4458.8, 'Gain': 800 * 0},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.8, 'Gain': 7000, "FF_Gains": [0, 17000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency': 4648.5, 'Gain': 1800},
#           'Qubit12': {'Frequency': 4494.4, 'Gain': 750 * 0},
#           'Pulse_FF': [0, 11000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.4, 'Gain': 8000, "FF_Gains": [0, 0, 17000, 0]},
#           'Qubit01': {'Frequency': 4643.0, 'Gain': 2200},
#           'Qubit12': {'Frequency': 4489.8, 'Gain': 1150 * 0},
#           'Pulse_FF': [0, 0, 11000, 0]},
#     '4': {'Readout': {'Frequency': 7249.7, 'Gain': 8000, "FF_Gains": [0, 0, 0, -23000]},
#           'Qubit01': {'Frequency': 4616.7, 'Gain': 2280},
#           'Qubit12': {'Frequency': 4463.5, 'Gain': 710 * 0},
#           'Pulse_FF': [0, 0, 0, -15000]}
#     }

#Readout parameters for 12 discrimination
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.5, 'Gain': 9500, "FF_Gains": [-20000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency':  4610.4, 'Gain': 1750},
#           'Qubit12': {'Frequency': 4458.8, 'Gain': 800},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.3, 'Gain': 6500, "FF_Gains": [0, 17000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency': 4648.5, 'Gain': 1800},
#           'Qubit12': {'Frequency': 4494.4, 'Gain': 750},
#           'Pulse_FF': [0, 11000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7116.8, 'Gain': 11000, "FF_Gains": [0, 0, 17000, 0]},
#           'Qubit01': {'Frequency': 4643.0, 'Gain': 2200},
#           'Qubit12': {'Frequency': 4489.8, 'Gain': 1150},
#           'Pulse_FF': [0, 0, 11000, 0]},
#     '4': {'Readout': {'Frequency': 7249.5, 'Gain': 8000, "FF_Gains": [0, 0, 0, -23000]},
#           'Qubit01': {'Frequency': 4616.7, 'Gain': 2280},
#           'Qubit12': {'Frequency': 4463.5, 'Gain': 710},
#           'Pulse_FF': [0, 0, 0, -15000]}
#     }
#
# # expt
# FF_gain1_expt = -90  # 8000
# FF_gain2_expt = 65
# FF_gain3_expt = 0
# FF_gain4_expt = -245
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ End 2 photon 4 qubit 4.395 GHz~~~~~~~~~~~~~~~~~~~~~~~~~



#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Start 1 photon 4 qubit ~~~~~~~~~~~~~~~~~~~~~~~
# yoko69.SetVoltage(-0.0928)
# yoko70.SetVoltage(-0.2451)
# yoko71.SetVoltage(-0.315)
# yoko72.SetVoltage(0.2793)
#
# #Readout Qubit Params
#
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.5, 'Gain': 11500, "FF_Gains": [-11000, 0, 0, 0]},
#           'Qubit01': {'Frequency': 4664.1, 'Gain': 1380},
#           'Qubit12': {'Frequency': 4510.7, 'Gain': 640 * 0},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.6, 'Gain': 8000, "FF_Gains": [0, 11000, 0, 0]},
#           'Qubit01': {'Frequency': 4693, 'Gain': 1000},
#           'Qubit12': {'Frequency': 4538.2 , 'Gain': 790 * 0},
#           'Pulse_FF': [0, 11000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.1, 'Gain': 8000, "FF_Gains": [0, 0, 11000, 0]},
#           'Qubit01': {'Frequency': 4692.7, 'Gain': 1330},
#           'Qubit12': {'Frequency': 4538.4, 'Gain': 680 * 0},
#           'Pulse_FF': [0, 0, 11000, 0]},
#     '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500, "FF_Gains": [0, 0, 0, -14000]},
#           'Qubit01': {'Frequency': 4670.5, 'Gain': 1500},
#           'Qubit12': {'Frequency': 4516.3, 'Gain': 820 * 0},
#           'Pulse_FF': [0, 0, 0, -14000] }
#     }
#
# Qubit_Readout = 4
# Qubit_Pulse = 1
# # Readout
#
# # expt
# FF_gain1_expt = -90  # 8000
# FF_gain2_expt = 125
# FF_gain3_expt = 0
# FF_gain4_expt = -150
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ End 1 photon 4 qubit ~~~~~~~~~~~~~~~~~~~~~~~~~~