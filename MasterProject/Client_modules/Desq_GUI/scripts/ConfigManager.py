"""
ConfigManager.py

Centralized config manager for all three config components: base, global, and experiment.
"""

class ConfigManager:

    def __init__(
        self,
        base_config: dict = None,
        global_config: dict = None,
        experiment_config: dict = None,
        dataset_config: dict = None,
    ):
        self.base_config = base_config
        self.global_config = global_config
        self.experiment_config = experiment_config
        self.dataset_config = dataset_config

    def update_config(
        self,
        base_config: dict = None,
        global_config: dict = None,
        experiment_config: dict = None,
        dataset_config: dict = None,
    ):
        if base_config:
            self.base_config.update(base_config)
        if global_config:
            self.global_config.update(global_config)
        if experiment_config:
            self.experiment_config.update(experiment_config)
        if dataset_config:
            self.dataset_config.update(dataset_config)

    def get_config(self):
        """
        Combines all configs with the priority of experiment, global, then base
        """
        return self.base_config | self.global_config | self.experiment_config | self.dataset_config
