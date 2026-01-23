"""
================
ConfigManager.py
================

Simplified ConfigManager for use in ConfigTreePanel.

Handles deep merging of multiple JSON configuration files with recency-based
priority ordering. When multiple configs define the same parameter, the most
recently checked config takes precedence.

:var ConfigManager: Main class for managing configuration layers.

.. note::
    This module is designed for use with the ConfigTreePanel GUI component
    and supports deep merging of nested dictionary structures.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


class ConfigManager:
    """
    Manages multiple configuration layers with recency-based priority.

    When multiple configs define the same parameter, the most recently
    checked config takes precedence. Configs are stored as an ordered list
    of (identifier, config_dict) tuples where later entries override earlier ones.

    :ivar _config_layers: Ordered list of (identifier, config_dict) tuples.
        Order matters: later entries override earlier ones during merge.
    :vartype _config_layers: List[Tuple[str, Dict[str, Any]]]
    :ivar _merged_cache: Cache for the merged config result. Invalidated
        whenever configs are checked or unchecked.
    :vartype _merged_cache: Optional[Dict[str, Any]]

    .. note::
        The merge cache is automatically invalidated when configs are added
        or removed. Use ``use_cache=False`` in :meth:`get_config` to force
        recalculation if needed.

    Example usage::

        manager = ConfigManager()
        manager.check_config("base", {"param1": 1, "nested": {"a": 1}})
        manager.check_config("override", {"param1": 2, "nested": {"b": 2}})
        config = manager.get_config()
        # Result: {"param1": 2, "nested": {"a": 1, "b": 2}}
    """

    def __init__(self) -> None:
        """
        Initialize the ConfigManager with empty configuration layers.

        Creates an empty layer stack and initializes the merge cache to None.
        """
        # Ordered list of (identifier, config_dict) tuples
        # Order matters: later entries override earlier ones
        self._config_layers: List[Tuple[str, Dict[str, Any]]] = []

        # Cache for the merged config (invalidated on changes)
        self._merged_cache: Optional[Dict[str, Any]] = None

    def check_config(self, identifier: str, config: Dict[str, Any]) -> None:
        """
        Check/enable a config, adding it to the layer stack.

        If a config with the same identifier already exists, it is removed
        from its current position and re-added at the end (highest priority).
        The config is deep-copied to prevent external modifications from
        affecting the stored configuration.

        :param identifier: Unique identifier for this config (e.g., filename).
        :type identifier: str
        :param config: Dictionary containing the configuration to add.
        :type config: Dict[str, Any]
        :returns: None
        :rtype: None

        .. note::
            This method invalidates the merge cache, forcing recalculation
            on the next call to :meth:`get_config`.
        """
        # Deep copy to prevent external modifications from affecting stored config
        config_dict = deepcopy(config)

        # Remove existing layer with same identifier if present
        # This ensures the config moves to the highest priority position
        self._config_layers = [(id_, cfg) for id_, cfg in self._config_layers
                               if id_ != identifier]

        # Add to end (highest priority)
        self._config_layers.append((identifier, config_dict))

        # Invalidate cache since layer stack has changed
        self._merged_cache = None

    def uncheck_config(self, identifier: str) -> bool:
        """
        Uncheck/disable a config, removing it from the layer stack.

        :param identifier: The identifier of the config to remove.
        :type identifier: str
        :returns: True if config was found and removed, False otherwise.
        :rtype: bool

        .. note::
            This method invalidates the merge cache if a config was removed.
        """
        original_length = len(self._config_layers)

        # Filter out the config with the matching identifier
        self._config_layers = [(id_, cfg) for id_, cfg in self._config_layers
                               if id_ != identifier]

        # Check if anything was actually removed
        if len(self._config_layers) < original_length:
            # Invalidate cache since layer stack has changed
            self._merged_cache = None
            return True
        return False

    def get_config(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get the final merged configuration.

        Merges all checked configs in priority order (earliest to latest)
        and returns a deep copy of the result.

        :param use_cache: Whether to use cached result if available.
            Set to False to force recalculation.
        :type use_cache: bool
        :returns: Deep-merged dictionary of all checked configs. Returns
            a deep copy to prevent external modifications.
        :rtype: Dict[str, Any]

        .. seealso::
            :meth:`_deep_merge` for details on how dictionaries are merged.
        """
        # Return cached result if available and caching is enabled
        if use_cache and self._merged_cache is not None:
            return deepcopy(self._merged_cache)

        # Merge all layers in priority order (earliest to latest)
        result: Dict[str, Any] = {}
        for identifier, config in self._config_layers:
            result = self._deep_merge(result, config)

        # Update cache with the merged result
        self._merged_cache = result

        # Return deep copy to prevent external modifications
        return deepcopy(result)

    def get_checked_configs(self) -> List[str]:
        """
        Get list of currently checked config identifiers in order.

        :returns: List of identifiers from lowest to highest priority.
            The last element has the highest priority in the merge.
        :rtype: List[str]
        """
        return [identifier for identifier, _ in self._config_layers]

    def clear(self) -> None:
        """
        Remove all checked configs.

        Clears the layer stack and invalidates the merge cache.

        :returns: None
        :rtype: None
        """
        self._config_layers.clear()
        self._merged_cache = None

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, with override taking precedence.

        Merge rules:
            - For dictionaries: recursively merge nested keys
            - For all other types (lists, primitives, etc.): override wins

        :param base: The base dictionary to merge into.
        :type base: Dict[str, Any]
        :param override: The dictionary whose values take precedence.
        :type override: Dict[str, Any]
        :returns: A new dictionary containing the merged result.
        :rtype: Dict[str, Any]

        .. note::
            Both input dictionaries are deep-copied, so the originals
            are not modified.

        .. note::
            Lists are NOT merged - the override list completely replaces
            the base list. This is intentional behavior for configuration
            management where list replacement is typically desired.
        """
        # Start with a deep copy of the base dictionary
        result = deepcopy(base)

        for key, value in override.items():
            if (key in result and
                    isinstance(result[key], dict) and
                    isinstance(value, dict)):
                # Both values are dicts: merge recursively
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                # Override wins for all non-dict types (includes lists, primitives, None)
                result[key] = deepcopy(value)

        return result