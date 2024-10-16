"""
Created on 8th October 2024
@author: Parth Jatakia
v3.0
Code to measure temperature three different ways
1. Single Shot
2. State-to-State decoherence rate matrix
3. Hidden Markov Model
while ensuring the qubit is calibrated to a particular qubit frequency with the best measurement parameters.
A new way of document information is being implemented.
"""

# Importing packages
import numpy as np
import matplotlib.pyplot as plt

# Importing experiments
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_FullAnalysis import SingleShotFull

# Create class
class TemperatureScan():
    def __init__(self):
        print("-----------------------------")
        print("Initializing Temperature Scan")

