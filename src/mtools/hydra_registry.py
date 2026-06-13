from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Optional

import hydra_zen
from hydra_zen import MISSING, ZenStore

if TYPE_CHECKING:
    from hydra_zen.typing._implementations import DataClass


class HydraZenRegistry:
    """Registry for hierarchical Hydra configuration and experiment definitions.

    This class wraps a ``hydra_zen.ZenStore`` and provides helpers for:

    1. Registering config options under hierarchical group paths.
    2. Building Hydra defaults lists from selected group options.
    3. Creating and registering run and experiment configurations.
    """

    def __init__(self, store: ZenStore | None = None):
        """Initialize the registry.

        Args:
            store: Optional pre-configured ``ZenStore``. If omitted, a new
                ``hydra_zen.ZenStore`` instance is created.
        """
        self._store = store or hydra_zen.ZenStore()
        self._group_stores: dict[str, hydra_zen.ZenStore] = {}
        # Map from Hydra group identifier -> normalized package path. This
        # enables detecting when the same Hydra group name is attempted to
        # be reused for a different package, which would cause collisions in
        # Hydra's config store. We enforce uniqueness of group identifiers
        # across packages below in `register_group_option`.
        self._group_names: dict[str, str] = {}
        # Map from normalized package path -> Hydra group identifier. This
        # must be populated in advance via `register_group_name` so that
        # options can later be attached to the package using the registered
        # group identifier as an alias.
        self._package_to_group: dict[str, str] = {}

    @property
    def store(self) -> ZenStore:
        """Return the underlying ``ZenStore`` instance.

        Returns:
            The wrapped ``ZenStore``.
        """
        return self._store

    @staticmethod
    def _normalize_path(hierarchy_path: str) -> str:
        """Normalize a hierarchy path to dot notation.

        Slashes are converted to dots, surrounding dots and whitespace are
        removed, and empty segments are discarded.

        Args:
            hierarchy_path: Hierarchy path to normalize.

        Returns:
            The normalized dot-delimited path.

        Raises:
            ValueError: If the input does not contain any non-empty segments.
        """
        normalized = hierarchy_path.strip().replace("/", ".").strip(".")
        parts = [part for part in normalized.split(".") if part]
        if not parts:
            raise ValueError("hierarchy_path must contain at least one non-empty segment")
        return ".".join(parts)

    def _group_name(self, hierarchy_path: str) -> str:
        """Convert a hierarchy path to Hydra group notation.

        Args:
            hierarchy_path: Hierarchy path in slash or dot notation.

        Returns:
            The normalized group path using slash separators.
        """
        return self._normalize_path(hierarchy_path).replace(".", "/")

    def register_group_name(self, package: str, group_name: Optional[str] = None) -> str:
        """Register an explicit Hydra group identifier for a package.

        This method binds a normalized `package` path to a single Hydra
        group identifier. The mapping must be created before registering
        options for that package via `register_group_option`.

        Args:
            package: Package path in slash or dot notation to register.
            group_name: Optional explicit Hydra group identifier to use. If
                omitted, the normalized package path is used as the group
                identifier.

        Returns:
            The normalized group identifier that was registered.

        Raises:
            ValueError: If the chosen `group_name` is already registered to a
                different package, or if the `package` is already registered
                to a different group identifier.
        """
        normalized_path = self._normalize_path(package)
        group_id = group_name or self._group_name(normalized_path)

        # Check for conflicts: group_id -> package and package -> group_id
        existing_pkg = self._group_names.get(group_id)
        if existing_pkg is not None and existing_pkg != normalized_path:
            raise ValueError(f"Hydra group name '{group_id}' is already registered for package '{existing_pkg}'")

        existing_group = self._package_to_group.get(normalized_path)
        if existing_group is not None and existing_group != group_id:
            raise ValueError(f"Package '{normalized_path}' is already registered to group '{existing_group}'")

        # Record the two-way mapping.
        self._group_names[group_id] = normalized_path
        self._package_to_group[normalized_path] = group_id
        return group_id


    def register_group_option(self, group_id: str, name: str, config: Any):
        """Register a named option under a hierarchical config group.

        The ``group_id`` argument may be either:
        - a previously-registered Hydra group identifier (as returned by
          ``register_group_name``), or
        - a package path (slash or dot notation) that was previously bound
          to a group identifier via ``register_group_name``.

        The method resolves ``group_id`` to the normalized package path and
        the canonical group identifier. If the provided ``group_id`` cannot
        be resolved to a registered mapping, ``ValueError`` is raised and
        the caller should first call ``register_group_name``.

        Args:
            group_id: Either the Hydra group identifier or the package path
                corresponding to a previously-registered group.
            name: Name of the option to register within the group.
            config: Config object or factory to register in the group's
                ``ZenStore``.
        """

        # Prefer interpreting `group_id` as an explicit registered group
        # identifier. If present, look up the associated package path.
        if group_id in self._group_names:
            normalized_path = self._group_names[group_id]
            canonical_group = group_id
        else:
            normalized_path = self._normalize_path(group_id)
            if normalized_path not in self._package_to_group:
                self.register_group_name(package=normalized_path, group_name=self._group_name(normalized_path))
            canonical_group = self._package_to_group[normalized_path]

        # Reuse or create the ZenStore for this package's normalized path.
        group_store = self._group_stores.get(normalized_path)
        if group_store is None:
            group_store = self._store(group=canonical_group, package=normalized_path)
            self._group_stores[normalized_path] = group_store

        group_store(config, name=name)

    def _build_hydra_defaults(
        self, selections: Mapping[str, str] | None = None, include_self: bool = True, override: bool = False
    ) -> list[Any]:
        """Build a Hydra defaults list from group selections.

        Args:
            selections: Mapping from hierarchy path to selected option name.
            include_self: Whether to prepend ``"_self_"`` to defaults.
            override: Whether each selection should use Hydra override syntax.

        Returns:
            A Hydra defaults list containing ``"_self_"`` (optional) and
            selection mappings.
        """
        defaults: list[Any] = ["_self_"] if include_self else []
        if not selections:
            return defaults

        for hierarchy_path, choice in selections.items():
            group = self._group_name(hierarchy_path)
            key = f"override /{group}" if override else group
            defaults.append({key: choice})
        return defaults

    def build_run_config(
        self,
        *,
        base: type[Any],
        model_name: str,
        session: type[DataClass],
        selections: Mapping[str, str] | None = None,
        include_experiment_group: bool = False,
        name: Optional[str] = None,
    ):
        """Create a run config type with Hydra defaults.

        Args:
            base: Base config class to inherit from.
            model_name: Model name value for the generated config.
            session: Session dataclass type for the generated config.
            selections: Optional mapping of hierarchy path to selected option.
            include_experiment_group: Whether to include ``{"experiment": None}``
                in defaults to allow experiment overrides.
            name: Optional name to register the created run config under the
                root store. If provided, the config is registered via
                ``register_run_config`` before being returned.

        Returns:
            A config type created by ``hydra_zen.make_config``.
        """
        defaults = self._build_hydra_defaults(selections=selections)
        if include_experiment_group:
            defaults.append({"experiment": None})

        run_config = hydra_zen.make_config(
            bases=(base,),
            model_name=model_name,
            session=session,
            hydra_defaults=defaults,
        )

        # If a name is provided, register the created run config in the
        # root store so callers can create-and-register in one call.
        if name is not None:
            self.register_run_config(name=name, run_config=run_config)

        return run_config

    def register_run_config(self, name: str, run_config: Any):
        """Register a run config in the root store.

        Args:
            name: Registered config name.
            run_config: Config object or type to register.
        """
        self._store(run_config, name=name)

    def _register_overrides(
        self, name: str, overrides: Mapping[str, DataClass], hydra_defaults: list[Any]
    ) -> None:
        """Register override configs as group options and append to defaults.

        Args:
            name: Experiment name used to derive internal option names.
            overrides: Mapping of hierarchy path to config instances.
            hydra_defaults: Defaults list to append override entries to.
        """
        existing_groups = set()
        for entry in hydra_defaults:
            if isinstance(entry, dict):
                key = next(iter(entry.keys()))
                if key.startswith("override /"):
                    existing_groups.add(self._normalize_path(key[len("override /"):]))
            else:
                existing_groups.add(self._normalize_path(str(entry)))

        for hierarchy_path, config_instance in overrides.items():
            canonical_group = self._normalize_path(hierarchy_path).replace(".", "/")
            internal_name = f"_{name}_{self._normalize_path(hierarchy_path).replace('.', '_')}"
            self.register_group_option(
                group_id=hierarchy_path,
                name=internal_name,
                config=config_instance,
            )
            if canonical_group not in existing_groups:
                existing_groups.add(canonical_group)
                hydra_defaults.append({f"override /{canonical_group}": internal_name})

    def register_experiment(
        self,
        *,
        name: str,
        base_run_config: Any,
        selections: Mapping[str, str] | None = None,
        overrides: Mapping[str, DataClass] | None = None,
    ):
        """Register an experiment config under the ``experiment`` group.

        The experiment config derives from ``base_run_config`` and overrides
        selected groups using Hydra's ``override /group`` defaults syntax.

        Args:
            name: Experiment name to register.
            base_run_config: Base run config to extend.
            selections: Mapping of hierarchy path to selected option names.
            overrides: Mapping of hierarchy path to dataclass config instances
                to use as override targets.
        """
        hydra_defaults = self._build_hydra_defaults(selections=selections, override=True)
        if overrides:
            self._register_overrides(name, overrides, hydra_defaults)

        experiment_store = self._store(group="experiment", package="_global_")
        experiment_store(
            hydra_zen.make_config(
                bases=(base_run_config,),
                model_name=MISSING,
                session=MISSING,
                hydra_defaults=hydra_defaults,
            ),
            name=name,
        )

    def add_to_hydra_store(self):
        """Add all registered entries to Hydra's global config store."""
        self._store.add_to_hydra_store()
