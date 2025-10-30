"""
Simplified ConfigManager for use in ConfigTreePanel.
Handles deep merging of multiple JSON configuration files.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional


class ConfigManager:
    """
    Manages multiple configuration layers with recency-based priority.

    When multiple configs define the same parameter, the most recently
    checked config takes precedence.
    """

    def __init__(self):
        # Ordered list of (identifier, config_dict) tuples
        # Order matters: later entries override earlier ones
        self._config_layers: List[tuple[str, Dict[str, Any]]] = []

        # Cache for the merged config (invalidated on changes)
        self._merged_cache: Optional[Dict[str, Any]] = None

    def check_config(self, identifier: str, config: Dict[str, Any]) -> None:
        """
        Check/enable a config, adding it to the layer stack.

        Args:
            identifier: Unique identifier for this config (e.g., filename)
            config: Dictionary containing the configuration
        """
        config_dict = deepcopy(config)

        # Remove existing layer with same identifier if present
        self._config_layers = [(id_, cfg) for id_, cfg in self._config_layers
                               if id_ != identifier]

        # Add to end (highest priority)
        self._config_layers.append((identifier, config_dict))

        # Invalidate cache
        self._merged_cache = None

    def uncheck_config(self, identifier: str) -> bool:
        """
        Uncheck/disable a config, removing it from the layer stack.

        Args:
            identifier: The identifier of the config to remove

        Returns:
            True if config was found and removed, False otherwise
        """
        original_length = len(self._config_layers)
        self._config_layers = [(id_, cfg) for id_, cfg in self._config_layers
                               if id_ != identifier]

        if len(self._config_layers) < original_length:
            self._merged_cache = None
            return True
        return False

    def get_config(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get the final merged configuration.

        Args:
            use_cache: Whether to use cached result if available

        Returns:
            Deep-merged dictionary of all checked configs
        """
        if use_cache and self._merged_cache is not None:
            return deepcopy(self._merged_cache)

        # Merge all layers in order
        result = {}
        for identifier, config in self._config_layers:
            result = self._deep_merge(result, config)

        self._merged_cache = result
        return deepcopy(result)

    def get_checked_configs(self) -> List[str]:
        """
        Get list of currently checked config identifiers in order.

        Returns:
            List of identifiers from lowest to highest priority
        """
        return [identifier for identifier, _ in self._config_layers]

    def clear(self) -> None:
        """Remove all checked configs."""
        self._config_layers.clear()
        self._merged_cache = None

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, with override taking precedence.

        - For dictionaries: recursively merge
        - For all other types: override wins
        """
        result = deepcopy(base)

        for key, value in override.items():
            if (key in result and
                    isinstance(result[key], dict) and
                    isinstance(value, dict)):
                # Both are dicts, merge recursively
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                # Override wins (includes lists, primitives, etc.)
                result[key] = deepcopy(value)

        return result