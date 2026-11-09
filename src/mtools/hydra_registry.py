from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TypeAlias, cast

import hydra
import hydra_zen
from hydra.core.global_hydra import GlobalHydra
from hydra_zen import MISSING, ZenStore
from hydra_zen.typing._implementations import DefaultsList
from omegaconf import DictConfig

import mtools.session_config as session_config

if TYPE_CHECKING:
    from hydra_zen.typing._implementations import DataClass

#: Hydra group under which experiments are registered.
EXPERIMENT_GROUP = "experiment"

#: A run config: the Hydra config *type* created by :meth:`HydraZenRegistry.create_run`,
#: :meth:`HydraZenRegistry.build_run_config`, or an equivalent ``hydra_zen.make_config`` call.
RunConfig: TypeAlias = type[session_config.SimulationRun]


def _run_config_defaults(run_config: object) -> list | None:
    """Best-effort extraction of the Hydra defaults list from a run config.

    Args:
        run_config: Run config type or instance to inspect.

    Returns:
        The defaults list, or ``None`` when the config shape is not
        introspectable (non-dataclass or no ``defaults`` field).
    """
    try:
        if isinstance(run_config, type) and dataclasses.is_dataclass(run_config):
            field = run_config.__dataclass_fields__.get("defaults")
            if field is None:
                return None
            if field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                return list(field.default_factory())  # type: ignore[operator]
            if isinstance(field.default, list):
                return list(field.default)
            return None
        if dataclasses.is_dataclass(run_config) and not isinstance(run_config, type):
            defaults = getattr(run_config, "defaults", None)
            return list(defaults) if isinstance(defaults, list) else None
    except Exception:
        return None
    return None


def _defaults_include_group(defaults: list, group: str) -> bool:
    """Check whether a Hydra defaults list references ``group``.

    Handles plain entries (``{"experiment": None}``, ``"experiment"``) and
    override entries (``{"override /experiment": ...}``).

    Args:
        defaults: Hydra defaults list to inspect.
        group: Group name to look for (e.g. ``"experiment"``).

    Returns:
        Whether any entry references the group.
    """
    candidates = {group, group.replace(".", "/")}
    for entry in defaults:
        if isinstance(entry, dict):
            keys = {key.removeprefix("override /") for key in entry}
            normalized = {key.replace(".", "/") for key in keys} | keys
            if candidates & normalized:
                return True
        elif isinstance(entry, str) and entry != "_self_":
            if entry in candidates or entry.replace(".", "/") in candidates:
                return True
    return False


@dataclasses.dataclass(frozen=True)
class ExperimentSpec:
    """Declarative definition of one experiment.

    A spec can be registered against any number of registries via
    :meth:`HydraZenRegistry.register_experiments`, so the same experiment set
    can be replayed for a candidate model and a reference model.

    Attributes:
        name: Experiment name registered under the ``experiment`` group.
        overrides: Mapping of hierarchy path to config instance, replacing the
            selected group's default.
        selections: Mapping of hierarchy path to group option name.
    """

    #: Experiment name registered under the ``experiment`` group.
    name: str
    #: Mapping of hierarchy path to config instance.
    overrides: Mapping[str, DataClass] | None = None
    #: Mapping of hierarchy path to group option name.
    selections: Mapping[str, str] | None = None


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
        self._hydra_defaults: dict[str, str] = {}
        # Map from registered run config name to the run config type, so
        # callers (e.g. multirun sweeps) can retrieve it without keeping
        # their own reference.
        self._run_configs: dict[str, RunConfig] = {}
        # Map from experiment name to the tuple of run configs it binds to
        # (every registered run config whose defaults include the experiment
        # group). Immutable tuples so callers cannot mutate the binding.
        self._experiment_bases: dict[str, tuple[RunConfig, ...]] = {}
        # Default run config per experiment, used when compose_experiment /
        # get_experiment_run_config are called without an explicit run config.
        self._experiment_default_run_config: dict[str, RunConfig] = {}
        # Pre-built Hydra defaults list per experiment, reused on every rebind.
        self._experiment_defaults: dict[str, list] = {}

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
        if group_id in self._group_names:
            raise ValueError(f"Hydra group name '{group_id}' is already registered")

        if normalized_path in self._package_to_group:
            raise ValueError(f"Hydra package name '{package}' is already registered")

        # Record the two-way mapping.
        self._group_names[group_id] = normalized_path
        self._package_to_group[normalized_path] = group_id
        return group_id


    def register_group_option(
        self, group_id: str, name: str, config: DataClass | type[DataClass], default: bool = False
    ):
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
            default: Adds option to the hydra default list.
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

        if default:
            if canonical_group in self._hydra_defaults:
                raise ValueError(f"The `group_id` {canonical_group} is already present in the defaults list.")
            else:
                self._hydra_defaults[canonical_group] = name

    def register_group_options(
        self,
        group_id: str,
        options: Mapping[str, DataClass | type[DataClass]],
        default: Optional[str] = None,
    ) -> None:
        """Register several named options under one hierarchical group.

        This is a batch convenience wrapper around ``register_group_option``
        for the common case where a package exposes a set of interchangeable
        options and one of them is the default.

        Args:
            group_id: Either the Hydra group identifier or the package path
                corresponding to a previously-registered group.
            options: Mapping of option name to config object or factory.
            default: Name of the option to add to the Hydra defaults list.
                When ``None`` (the default), no option is selected.

        Raises:
            ValueError: If ``default`` is not one of the provided ``options``.
        """
        if default is not None and default not in options:
            raise ValueError(
                f"default option {default!r} is not among the registered options {sorted(options)}"
            )

        for name, config in options.items():
            self.register_group_option(group_id, name=name, config=config, default=(name == default))

    def _build_hydra_defaults(
        self, selections: Mapping[str, str] | None = None, include_self: bool = True, override: bool = False
    ) -> DefaultsList:
        """Build a Hydra defaults list from group selections.

        Args:
            selections: Mapping from hierarchy path to selected option name.
            include_self: Whether to prepend ``"_self_"`` to defaults.
            override: Whether each selection should use Hydra override syntax.

        Returns:
            A Hydra defaults list containing ``"_self_"`` (optional) and
            selection mappings.
        """
        defaults: DefaultsList = ["_self_"] if include_self else []
        if not selections:
            return defaults

        # Sort group names for packages so parameter overrides are not caused by order of group option registration.
        # Group options with packages deeper in the hierarchy could be overridden by options higher in hierarchiy otherwise.
        sorted_groups = dict(sorted(self._group_names.items(), key=lambda x: str(x[1])))

        for hierarchy_path in sorted_groups.keys():
            group = self._group_name(hierarchy_path)
            key = f"override /{group}" if override else group
            if hierarchy_path in selections:
                defaults.append({key: selections[hierarchy_path]})
        return defaults

    def build_run_config(
        self,
        *,
        base: type[DataClass],
        build: session_config.Build | type[DataClass],
        settings: session_config.RunSettings | type[DataClass],
        selections: Mapping[str, str] | None = None,
        include_experiment_group: bool = False,
        name: Optional[str] = None,
    ) -> RunConfig:
        """Create a run config type with Hydra defaults.

        Args:
            base: Base config class to inherit from, usually
                :class:`mtools.session_config.SimulationRun`.
            build: Build config for the generated config.
            settings: Run settings for the generated config; a group default for
                ``settings`` or ``settings/parameters`` replaces the parts it sets.
            selections: Optional mapping of hierarchy path to selected option.
            include_experiment_group: Whether to include ``{"experiment": None}``
                in defaults to allow experiment overrides.
            name: Optional name to register the created run config under the
                root store. If provided, the config is registered via
                ``register_run_config`` before being returned.

        Returns:
            A config type created by ``hydra_zen.make_config``.
        """
        selected_defaults = self._hydra_defaults
        if selections:
            selected_defaults.update(selections)
        default = self._build_hydra_defaults(selections=selected_defaults)

        if include_experiment_group:
            default.append({"experiment": None})

        run_config = hydra_zen.make_config(
            bases=(base,),
            build=build,
            settings=settings,
            hydra_defaults=default,
        )

        # ``hydra_zen.make_config`` is typed as returning ``type[DataClass]`` although
        # it derives from ``bases``; narrow it back to the run config type it builds.
        run_config_type = cast(RunConfig, run_config)

        # If a name is provided, register the created run config in the
        # root store so callers can create-and-register in one call.
        if name is not None:
            self.register_run_config(name=name, run_config=run_config_type)

        return run_config_type

    def create_run(
        self,
        *,
        model_name: str,
        model_path: Path,
        target: session_config.Target = "C",
        extra_sources: Sequence[Path] = (),
        libraries: Sequence[session_config.Library] = (),
        omc_flags: Mapping[str, str | None] | None = None,
        settings: session_config.RunSettings | None = None,
        selections: Mapping[str, str] | None = None,
        include_experiment_group: bool = False,
        name: Optional[str] = None,
    ) -> RunConfig:
        """Create and register a run config from the build fields and run settings.

        This is a convenience wrapper around ``build_run_config`` that assembles the
        :class:`~mtools.session_config.Build` config from individual inputs.

        Args:
            model_name: Fully qualified name of the model class; results are keyed by it.
            model_path: Modelica source file holding the model.
            target: Simulation target, ``"C"`` or ``"Cpp"``.
            extra_sources: Source files or packages loaded before ``model_path``.
            libraries: Libraries loaded before the sources.
            omc_flags: Extra OMC flags; the target is set with ``target`` only.
            settings: Run settings. Defaults to settings whose parameters come from the
                ``settings/parameters`` group and whose other values come from the
                model's experiment annotation; a ``settings`` group default replaces it.
            selections: Optional mapping of hierarchy path to selected option.
            include_experiment_group: Whether to include ``{"experiment": None}``
                in defaults to allow experiment overrides.
            name: Optional name to register the created run config under the
                root store. If provided, the config is registered via
                ``register_run_config`` before being returned.

        Returns:
            A config type created by ``hydra_zen.make_config``.
        """
        build = session_config.Build(
            model_path=model_path,
            model_name=model_name,
            target=target,
            extra_sources=list(extra_sources),
            libraries=list(libraries),
            omc_flags=dict(omc_flags or {}),
        )
        return self.build_run_config(
            base=session_config.SimulationRun,
            build=build,
            settings=settings if settings is not None else session_config.RunSettings(parameters=MISSING),
            selections=selections,
            include_experiment_group=include_experiment_group,
            name=name,
        )

    def register_run_config(self, name: str, run_config: RunConfig):
        """Register a run config in the root store.

        Args:
            name: Registered config name.
            run_config: Run config type to register.
        """
        self._store(run_config, name=name)
        self._run_configs[name] = run_config
        defaults = _run_config_defaults(run_config)
        if defaults is not None and _defaults_include_group(defaults, EXPERIMENT_GROUP):
            for experiment_name in list(self._experiment_defaults):
                self._rebind_experiment(experiment_name)

    def get_run_config(self, name: str) -> RunConfig:
        """Return the run config registered under ``name``.

        Args:
            name: Registered config name.

        Returns:
            The run config type registered via ``register_run_config`` (also
            called implicitly by ``build_run_config``/``create_run`` when
            ``name`` is given).

        Raises:
            KeyError: If no run config is registered under ``name``.
        """
        try:
            return self._run_configs[name]
        except KeyError:
            raise KeyError(f"unknown run config '{name}'") from None

    def _find_run_config_name(self, run_config: object) -> str | None:
        """Return the registered name for a run config type, if any.

        Args:
            run_config: Object to look up by identity.

        Returns:
            The registered name, or ``None`` if the config is not registered.
        """
        return next((name for name, registered in self._run_configs.items() if registered is run_config), None)

    def _resolve_run_config_name(self, run_config: RunConfig | str) -> str:
        """Resolve a run config name or type to its registered name.

        Args:
            run_config: Registered run config name or run config type.

        Returns:
            The registered name of the run config.

        Raises:
            KeyError: If ``run_config`` is a name that is not registered.
            ValueError: If ``run_config`` is an object that is not registered.
        """
        if isinstance(run_config, str):
            if run_config not in self._run_configs:
                raise KeyError(f"unknown run config '{run_config}'")
            return run_config
        name = self._find_run_config_name(run_config)
        if name is None:
            raise ValueError(
                "run config is not a registered run config; register it with a name first via "
                "'register_run_config' or 'create_run'."
            )
        return name

    def _experiment_targets(self) -> list[RunConfig]:
        """Run configs whose defaults include the experiment group, in registration order."""
        targets: list[RunConfig] = []
        for run_config in self._run_configs.values():
            defaults = _run_config_defaults(run_config)
            if defaults is not None and _defaults_include_group(defaults, EXPERIMENT_GROUP):
                targets.append(run_config)
        return targets

    def _rebind_experiment(self, name: str) -> None:
        """Re-register experiment ``name`` as a subclass of every experiment target."""
        bases = tuple(self._experiment_targets())
        try:
            del self._store[(EXPERIMENT_GROUP, name)]
        except KeyError:
            pass
        self._experiment_bases[name] = bases
        self._store(group=EXPERIMENT_GROUP, package="_global_")(
            hydra_zen.make_config(
                bases=bases,
                build=MISSING,
                settings=MISSING,
                hydra_defaults=self._experiment_defaults[name],
            ),
            name=name,
        )

    def get_experiment_run_config(
        self, name: str, run_config: RunConfig | str | None = None
    ) -> RunConfig:
        """Return the base run config used to sweep experiment ``name``.

        Args:
            name: Experiment name registered via ``register_experiment``.
            run_config: Registered run config name or run config type.
                Optional; when omitted the run config the experiment was
                registered with is returned.

        Returns:
            The run config type, suitable as multirun base for sweeps over
            this experiment.

        Raises:
            KeyError: If no experiment is registered under ``name``, or if
                ``run_config`` names an unknown run config.
            ValueError: If ``run_config`` is not bound to this experiment.
        """
        try:
            bases = self._experiment_bases[name]
        except KeyError:
            raise KeyError(f"unknown experiment '{name}'") from None

        if run_config is None:
            return self._experiment_default_run_config[name]

        requested = self._resolve_run_config_name(run_config)
        for base in bases:
            if self._find_run_config_name(base) == requested:
                return base
        raise ValueError(
            f"run config '{requested}' is not one of the run configs bound to experiment '{name}'"
        )

    def compose_experiment(
        self,
        name: str,
        run_config: RunConfig | str | None = None,
        overrides: list[str] | None = None,
    ) -> DictConfig:
        """Compose the config for experiment ``name``.

        Args:
            name: Experiment name registered via ``register_experiment``.
            run_config: Registered run config name or run config type.
                Optional; defaults to the run config the experiment was
                registered with.
            overrides: Optional additional Hydra override strings.

        Returns:
            The composed configuration as a DictConfig.

        Raises:
            KeyError: If no experiment is registered under ``name``.
            ValueError: If the target run config is not registered or not bound.
        """
        base_run_config = self.get_experiment_run_config(name, run_config)
        primary = self._find_run_config_name(base_run_config)
        if primary is None:
            raise ValueError(
                f"base run config for experiment '{name}' is not a registered run config; "
                "register it with a name first via 'register_run_config' or 'create_run'."
            )
        return self.compose(primary, overrides=[f"{EXPERIMENT_GROUP}={name}", *(overrides or [])])

    def _get_default_groups(self, hydra_defaults: DefaultsList) -> set[str]:
        """Extract group paths that already have entries in ``hydra_defaults``.

        Scans each entry in the defaults list and collects the normalized
        hierarchy path for both plain string entries (e.g. ``"group/subgroup"``)
        and dict-style override entries (e.g. ``{"override /group/subgroup": "name"}``).

        Args:
            hydra_defaults: A Hydra defaults list to inspect.

        Returns:
            A set of normalized dot-delimited group paths found in the list.
        """
        existing_groups = set()
        for entry in hydra_defaults:
            if isinstance(entry, dict):
                key = next(iter(entry.keys()))
                if key.startswith("override /"):
                    existing_groups.add(self._normalize_path(key[len("override /"):]))
            else:
                existing_groups.add(self._normalize_path(str(entry)))

        return existing_groups

    def _register_overrides(
        self, name: str, overrides: Mapping[str, DataClass], hydra_defaults: DefaultsList
    ) -> None:
        """Register override configs as group options and append to defaults.

        Args:
            name: Experiment name used to derive internal option names.
            overrides: Mapping of hierarchy path to config instances.
            hydra_defaults: Defaults list to append override entries to.

        Note:
            If a hierarchy path in ``overrides`` already has an entry in
            ``hydra_defaults``, the existing defaults entry takes precedence
            and no duplicate is added. The override config is still registered
            under its group so it can be selected by other defaults entries.
        """
        existing_groups = self._get_default_groups(hydra_defaults)

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
        base_run_config: RunConfig,
        selections: Mapping[str, str] | None = None,
        overrides: Mapping[str, DataClass] | None = None,
    ) -> None:
        """Register an experiment config under the ``experiment`` group.

        The experiment config derives from ``base_run_config`` and overrides
        selected groups using Hydra's ``override /group`` defaults syntax.
        The experiment is automatically bound to every run config currently
        registered that includes the ``experiment`` group, and to any such run
        config registered later. One experiment definition can be reused
        across multiple registries by partially applying the unbound method,
        e.g. ``partial(HydraZenRegistry.register_experiment, name="standstill")``;
        calling the result as ``register_experiment(registry, base_run_config=...)``
        binds ``self`` as the first positional argument.

        Args:
            name: Experiment name to register.
            base_run_config: Base run config type to extend. Must be a run config
                previously registered with a name (via ``register_run_config``
                or ``create_run`` with ``name``), so the experiment stays
                connected to it. It defaults for ``compose_experiment`` /
                ``get_experiment_run_config`` when no run config is given.
            selections: Mapping of hierarchy path to selected option names.
            overrides: Mapping of hierarchy path to dataclass config instances
                to use as override targets.

        Raises:
            ValueError: If ``base_run_config`` is not a registered run config,
                or if it does not include the ``experiment`` group (create it
                with ``include_experiment_group=True``).
        """
        targets = self._experiment_targets()
        if self._find_run_config_name(base_run_config) is None:
            raise ValueError(
                f"base_run_config for experiment '{name}' is not a registered run config; "
                "register it with a name first via 'register_run_config' or 'create_run'."
            )
        if not any(target is base_run_config for target in targets):
            raise ValueError(
                f"base_run_config for experiment '{name}' does not include the "
                f"'{EXPERIMENT_GROUP}' group; create it with "
                "'include_experiment_group=True' so 'compose_experiment' and sweeps can select the experiment."
            )
        hydra_defaults = self._build_hydra_defaults(selections=selections, override=True)
        if overrides:
            self._register_overrides(name, overrides, hydra_defaults)
        self._experiment_defaults[name] = hydra_defaults
        self._experiment_default_run_config[name] = base_run_config
        self._rebind_experiment(name)

    def register_experiments(
        self, experiments: Iterable[ExperimentSpec], *, base_run_config: RunConfig
    ) -> None:
        """Register several experiments defined as ``ExperimentSpec`` values.

        This is a batch convenience wrapper around the
        ``register_experiment`` method, allowing one experiment set to be
        applied to multiple registries (for example a candidate and a
        reference model) with a single call per registry. Each experiment is
        automatically bound to every run config in the registry that includes
        the ``experiment`` group, now and in the future.

        Args:
            experiments: Experiment specs to register.
            base_run_config: Base run config type the experiments derive from.
                It must already be registered in this registry and include the
                ``experiment`` group. It is the default run config for
                ``compose_experiment`` / ``get_experiment_run_config`` when no
                run config is given.
        """
        for experiment in experiments:
            self.register_experiment(
                name=experiment.name,
                base_run_config=base_run_config,
                selections=experiment.selections,
                overrides=experiment.overrides,
            )

    def add_to_hydra_store(self, overwrite_ok: bool | None = None):
        """Add all registered entries to Hydra's global config store.

        When ``overwrite_ok`` is True, re-enqueues every registered entry first
        so the same registry can be activated repeatedly. This lets multiple
        registries that reuse config and experiment names overwrite each other
        immediately before composing or launching their own runs. Without
        ``overwrite_ok``, a repeated call is a no-op after the first add.

        Args:
            overwrite_ok: If True, existing entries in Hydra's config store
                may be overwritten. Defaults to the store's setting.
        """
        if overwrite_ok:
            self._store.enqueue_all()
        self._store.add_to_hydra_store(overwrite_ok=overwrite_ok)

    def compose(
        self, config_name: str, overrides: list[str] | None = None
    ) -> DictConfig:
        """Compose a config from the local store using Hydra's compose.

        This method adds all stored entries to Hydra's global config store,
        overwriting entries from other registries with the same names,
        initializes Hydra, composes the requested config, and returns the
        composed result.

        Args:
            config_name: Name of the primary config to compose.
            overrides: Optional list of Hydra override strings.

        Returns:
            The composed configuration as a DictConfig.
        """
        self.add_to_hydra_store(overwrite_ok=True)
        GlobalHydra.instance().clear()
        with hydra.initialize(version_base=None, config_path=None):
            return hydra.compose(config_name=config_name, overrides=overrides)
