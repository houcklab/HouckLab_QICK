from MasterProject.Client_modules.CoreLib.socProxy import makeProxy
from MasterProject.Client_modules.Desq_GUI.ExperimentsPlus.TesterExperiment import TesterExperiment
from MasterProject.Client_modules.Init.initialize import BaseConfig

config = {
    "test": 1000,
    "imported_cfg": BaseConfig,
}

experiment_instance = TesterExperiment("", "", config)