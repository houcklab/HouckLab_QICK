#~~~~~~~~~~~~~~~~~~~~~~~~~ Qubit 1 and 2 on resonance ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~:
# yoko69.SetVoltage(-0.229)
# yoko70.SetVoltage(-0.1415)
# yoko71.SetVoltage(-0.062)
# yoko72.SetVoltage(-0.058)
#
#
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.68, 'Gain': 8000}, 'Qubit': {'Frequency': 4598, 'Gain': 1450}},
#     '2': {'Readout': {'Frequency': 7055.94, 'Gain': 6000}, 'Qubit': {'Frequency': 4807, 'Gain': 990}},
#     '3': {'Readout': {'Frequency': 7117.55, 'Gain': 6000}, 'Qubit': {'Frequency': 5255, 'Gain': 840}},
#     '4': {'Readout': {'Frequency': 7200, 'Gain': 6000}, 'Qubit': {'Frequency': 4470, 'Gain': 2630}}
#     }

# Readout
# FF_gain1 = 0  # 8000
# FF_gain2 = 7000
# FF_gain3 = 0
# FF_gain4 = 0
# # expt
# FF_gain1_expt = 0  # 8000
# FF_gain2_expt = 7000
# FF_gain3_expt = 0
# FF_gain4_expt = 0

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~ End Qubit 1 and 2 on Resonance~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Start 4 Qubits on Resonance at Sweet spot~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# yoko69.SetVoltage(-0.061)
# yoko70.SetVoltage(-0.279)
# yoko71.SetVoltage(-0.358)
# yoko72.SetVoltage(0.340)
#
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.87, 'Gain': 8000}, 'Qubit': {'Frequency': 4597.6, 'Gain': 1670},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7056.08, 'Gain': 6000}, 'Qubit': {'Frequency': 4609.2, 'Gain': 1820},
#           'Pulse_FF': [0, 10000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.02, 'Gain': 6000}, 'Qubit': {'Frequency': 4599.5, 'Gain': 2600},
#           'Pulse_FF': [0, 0, 10000, 0]},
#     '4': {'Readout': {'Frequency': 7249.89, 'Gain': 6000}, 'Qubit': {'Frequency': 4571.4, 'Gain': 1160},
#           'Pulse_FF': [0, 0, 0, -14000]}
#     }
# # Readout
# FF_gain1 = -15000  # 8000
# FF_gain2 = 20000
# FF_gain3 = 0
# FF_gain4 = -16000
# # expt
# FF_gain1_expt = -150  # 8000
# FF_gain2_expt = -250
# FF_gain3_expt = 0
# FF_gain4_expt = 0




#~~~~~~~~~~~~~~~~~~~~~~~~~~~~End 4 qubits on Resonance at sweet spot ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#~~~~~~~~~~~~~~~~~~~~~~~~ 4 Qubits on Resonance ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~:
# yoko69.SetVoltage(-0.3355)
# yoko70.SetVoltage(-0.0426)
# yoko71.SetVoltage(-0.1153)
# yoko72.SetVoltage(-0.0051)

# Qubit 1 (Left)
# resonator_frequency_center = 6952.6 #6953.0
# cavity_gain = 8000#8
# qubit_frequency_center = 4502.5 #4802 - 300
# qubit_gain = 770

# Qubit 2 (Top)
# resonator_frequency_center = 7056.3 #7055.95
# cavity_gain = 6000#8
# qubit_frequency_center = 5031
# qubit_gain = 810

# Qubit 3 (Bottom)
# resonator_frequency_center = 7117.55
# cavity_gain = 6000#8
# qubit_frequency_center = 4809.2
# qubit_gain = 840

# Qubit 4 (Right)
# resonator_frequency_center = 7249.95 #7250.15
# cavity_gain = 6000#8
# qubit_frequency_center = 4617.85
# qubit_gain = 2630

# FF_gain1_expt = -180  # 8000
# FF_gain2_expt = 60
# FF_gain3_expt = 0
# FF_gain4_expt = 100
# # Readout
# FF_gain1 = 11000  # 8000
# FF_gain2 = 7500
# FF_gain3 = 0
# FF_gain4 = 7500
# # expt
# FF_gain1_expt = 11000  # 8000
# FF_gain2_expt = 7500
# FF_gain3_expt = 0
# FF_gain4_expt = 7500

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~End 4 qubits on resonance~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~:



#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~4 qubits on resonance OLD NO GOOD~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~:
# yoko69.SetVoltage(-0.435)
# yoko70.SetVoltage(0.05)
# yoko71.SetVoltage(-0.025)
# yoko72.SetVoltage(-0.12)

#Qubit 1 (Left)
# resonator_frequency_center = 453.1
# cavity_attenuation = 15#8
# qubit_frequency_center = 4665.7
# qubit_gain = 1240

#Qubit 2 (Top)
# resonator_frequency_center = 556.9
# cavity_attenuation = 20 #12
# qubit_frequency_center = 5217.4
# qubit_gain = 1600

#Qubit 3 (Bottom)
# resonator_frequency_center = 618.05
# cavity_attenuation = 20
# qubit_frequency_center = 5007.8
# qubit_gain = 780

#Qubit 4 (Right)
# resonator_frequency_center = 750.2
# cavity_attenuation = 18
# qubit_frequency_center = 4809.6
# qubit_gain = 940
#
# 50 ns sigma

# #Readout
# FF_gain1 = 11000
# FF_gain2 = 7500
# FF_gain3 = 0
# FF_gain4 = 7500
#
# FF_gain1_pulse = -400  #Left Qubit
# FF_gain2_pulse = 300  #Middle Qubit
# FF_gain3_pulse = 0  #Middle Qubit
# FF_gain4_pulse = 0 #Middle Qubit
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~4 qubits on resonance~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~:

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Left and bottom qubit on resonance~~~~~~~~~~~~~~~~~~:
# yoko69.SetVoltage(-0.23)
# yoko70.SetVoltage(0)
# yoko71.SetVoltage(-0.215)
# yoko72.SetVoltage(0)
#
#
#
# #Qubit 1 (Left)
# resonator_frequency_center = 452.5 + 6500
# cavity_gain = 10000#8
# qubit_frequency_center = 4421.5 #4423.9
# qubit_gain = 1150

#Qubit 3 (Bottom)
# resonator_frequency_center = 618.5
# cavity_attenuation = 20
# qubit_frequency_center = 5253.3
# qubit_gain = 1300

# #Readout
# FF_gain1 = 8000#8000
# FF_gain2 = 8000
# FF_gain3 = 0
# FF_gain4 = -8000
# #experiment(pulse)
# FF_gain1_pulse = -750 #8000  #Left Qubit
# FF_gain2_pulse = 8000  #Top Qubit
# FF_gain3_pulse = 0  #Bottom Qubit
# FF_gain4_pulse = -8000  #Right Qubit
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Left and bottom qubit on resonance~~~~~~~~~~~~~~~~~~:

#~~~~~~~~~~~~~~~~~~~~4 qubits on resonance (OLD BEFORE CALIBRATION BAD)~~~~~~~~~~~~~:
# yoko69.SetVoltage(-0.41)
# yoko70.SetVoltage(0.1)
# yoko71.SetVoltage(0.03)
# yoko72.SetVoltage(-0.062)

#Qubit 1 (Left)
# resonator_frequency_center = 453.35
# cavity_attenuation = 15#8
# qubit_frequency_center = 4772.5
# qubit_gain = 670

#Qubit 2 (Top)
# resonator_frequency_center = 556.75
# cavity_attenuation = 20 #12
# qubit_frequency_center = 5119.8
# qubit_gain = 720

#Qubit 3 (Bottom)
# resonator_frequency_center = 618.5
# cavity_attenuation = 20
# qubit_frequency_center = 5253.3
# qubit_gain = 1300

#Qubit 4 (Right)
# resonator_frequency_center = 750.3
# cavity_attenuation = 18
# qubit_frequency_center = 4904.7
# qubit_gain = 2310

# 50 ns sigma


#Readout
FF_gain1 = 8000
FF_gain2 = 4000
FF_gain3 = 8000
FF_gain4 = 4000

FF_gain1_pulse = 0  #Left Qubit
FF_gain2_pulse = 150  #Middle Qubit
FF_gain3_pulse = -100  #Middle Qubit
FF_gain4_pulse = -200  #Middle Qubit
#~~~~~~~~~~~~~~~~~~~~4 qubits on resonance (OLD BEFORE CALIBRATION BAD)~~~~~~~~~~~~~:

