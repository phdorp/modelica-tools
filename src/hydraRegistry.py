from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import hydra_zen
from hydra_zen import MISSING, ZenStore


class HydraZenRegistry:
    """Wrapper around ZenStore for hierarchical config and experiment registration."""

    def __init__(self, store: ZenStore | None = None):
        self._store = store or hydra_zen.ZenStore()
        self._group_stores: dict[str, Any] = {}

    @property
    def store(self) -> ZenStore:
        return self._store

    @staticmethod
    def _normalize_path(hierarchy_path: str) -> str:
        normalized = hierarchy_path.strip().replace("/", ".").strip(".")
        parts = [part for part in normalized.split(".") if part]
        if not parts:
            raise ValueError("hierarchy_path must contain at least one non-empty segment")
        return ".".join(parts)

    def group_name(self, hierarchy_path: str) -> str:
        return self._normalize_path(hierarchy_path).replace(".", "/")

    def register_group_option(self, hierarchy_path: str, name: str, config: Any):
        normalized_path = self._normalize_path(hierarchy_path)
        group_store = self._group_stores.get(normalized_path)
        if group_store is None:
            group_store = self._store(group=self.group_name(normalized_path), package=normalized_path)
            self._group_stores[normalized_path] = group_store
        group_store(config, name=name)

    def build_hydra_defaults(
        self, selections: Mapping[str, str] | None = None, include_self: bool = True, override: bool = False
    ) -> list[Any]:
        defaults: list[Any] = ["_self_"] if include_self else []
        if not selections:
            return defaults

        for hierarchy_path, choice in selections.items():
            group = self.group_name(hierarchy_path)
            key = f"override /{group}" if override else group
            defaults.append({key: choice})
        return defaults

    def build_run_config(
        self,
        *,
        base: type[Any],
        model_name: str,
        session: Any,
        selections: Mapping[str, str] | None = None,
        include_experiment_group: bool = False,
    ):
        defaults = self.build_hydra_defaults(selections=selections)
        if include_experiment_group:
            defaults.append({"experiment": None})

        return hydra_zen.make_config(
            bases=(base,),
            model_name=model_name,
            session=session,
            hydra_defaults=defaults,
        )

    def register_run_config(self, name: str, run_config: Any):
        self._store(run_config, name=name)

    def register_experiment(self, *, name: str, base_run_config: Any, selections: Mapping[str, str]):
        experiment_store = self._store(group="experiment", package="_global_")
        experiment_store(
            hydra_zen.make_config(
                bases=(base_run_config,),
                model_name=MISSING,
                session=MISSING,
                hydra_defaults=self.build_hydra_defaults(selections=selections, override=True),
            ),
            name=name,
        )

    def add_to_hydra_store(self):
        self._store.add_to_hydra_store()
