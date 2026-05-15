import hydra_zen

from hydraRegistry import HydraZenRegistry


def test_register_group_option_creates_store_entry():
    """Ensure registering a group option stores the config in the group's ZenStore.

    Verifies the stored entry contains the expected package and name metadata.
    """

    store = hydra_zen.ZenStore()
    registry = HydraZenRegistry(store=store)

    group_id = registry.register_group_name("pkg.sub", group_name="pkg/sub")
    registry.register_group_option(group_id=group_id, name="opt1", config={"x": 1})

    # The underlying ZenStore for the group stores the entry
    group_store = registry._group_stores["pkg.sub"]
    assert (group_id, "opt1") in group_store._internal_repo
    entry = group_store._internal_repo[(group_id, "opt1")]
    assert entry["package"] == "pkg.sub"
    assert entry["name"] == "opt1"


def test_build_run_config_registers_root_entry():
    """Ensure build_run_config registers a run config under the registry root.

    The created run config should be present in the registry's root ZenStore
    keyed by (None, name).
    """

    store = hydra_zen.ZenStore()
    registry = HydraZenRegistry(store=store)

    # Create minimal base and session config types
    BaseConf = hydra_zen.make_config("a")
    SessionConf = hydra_zen.make_config("s")

    registry.build_run_config(
        base=BaseConf, model_name="modelX", session=SessionConf, selections=None, name="runA"
    )

    # The run config should be registered at the registry's root store
    assert (None, "runA") in registry.store._internal_repo
    entry = registry.store._internal_repo[(None, "runA")]
    assert entry["name"] == "runA"


def test_register_experiment_creates_experiment_group_entry():
    """Ensure register_experiment places an experiment config in the experiment group.

    Confirms the entry is added under group 'experiment' with package '_global_'
    and the expected name.
    """

    store = hydra_zen.ZenStore()
    registry = HydraZenRegistry(store=store)

    BaseConf = hydra_zen.make_config("a")
    SessionConf = hydra_zen.make_config("s")

    # create a run config to use as base
    run_cfg = registry.build_run_config(base=BaseConf, model_name="m", session=SessionConf)

    registry.register_experiment(name="exp1", base_run_config=run_cfg, selections={"pkg.sub": "opt1"})

    assert ("experiment", "exp1") in registry.store._internal_repo
    entry = registry.store._internal_repo[("experiment", "exp1")]
    assert entry["package"] == "_global_"
    assert entry["name"] == "exp1"
