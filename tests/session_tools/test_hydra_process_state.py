"""Running Hydra through mtools leaves the calling process as it found it."""

import logging

import hydra_zen
import pytest
from hydra.core.config_store import ConfigStore
from hydra.errors import HydraException
from models.kinematic_vehicle import MODEL_PATH, run_default

import mtools.sim_tools as sim_tools
from mtools.hydra_registry import HydraZenRegistry

SWEEP = ["settings.parameters.v_norm=1.0,2.0", "build.target=C"]


def _logging_state() -> dict[str, tuple[int, list[logging.Handler], bool, bool]]:
    loggers = [logging.getLogger()] + [
        logger for logger in logging.root.manager.loggerDict.values() if isinstance(logger, logging.Logger)
    ]
    return {logger.name: (logger.level, list(logger.handlers), logger.propagate, logger.disabled) for logger in loggers}


def _store_entries() -> set[str]:
    """Every config path in Hydra's store, except Hydra's own lazily filled group."""

    def walk(node: dict, prefix: str) -> set[str]:
        paths = set()
        for key, value in node.items():
            path = f"{prefix}{key}"
            paths.add(path)
            if isinstance(value, dict):
                paths |= walk(value, f"{path}/")
        return paths

    return walk({key: value for key, value in ConfigStore.instance().repo.items() if key != "hydra"}, "")


def _registry(name: str) -> HydraZenRegistry:
    registry = HydraZenRegistry(store=hydra_zen.ZenStore())
    registry.create_run(model_name="KinematicVehicle", model_path=MODEL_PATH, name=name)
    return registry


@pytest.fixture
def user_logging():
    """A caller's own logging setup: a root handler and an app logger at DEBUG."""
    handler = logging.NullHandler()
    root, app = logging.getLogger(), logging.getLogger("user_app")
    root_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    app.setLevel(logging.DEBUG)
    yield
    root.removeHandler(handler)
    root.setLevel(root_level)
    app.setLevel(logging.NOTSET)


def test_a_sweep_leaves_the_logging_configuration_as_it_found_it(tmp_path, user_logging):
    before = _logging_state()

    sim_tools.simulate(run_default, overrides=SWEEP, multirun=True, sweep_dir=str(tmp_path))

    after = _logging_state()
    assert {name: after[name] for name in before} == before
    configured_by_the_sweep = {
        name: state for name, state in after.items() if name not in before and (state[0] != logging.NOTSET or state[1])
    }
    assert configured_by_the_sweep == {}


def test_a_sweep_writes_no_job_log_files_by_default(tmp_path):
    sim_tools.simulate(run_default, overrides=SWEEP, multirun=True, sweep_dir=str(tmp_path))

    assert list(tmp_path.glob("*/*.log")) == []


def test_a_caller_can_still_choose_hydra_job_logging(tmp_path):
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    try:
        sim_tools.simulate(
            run_default, overrides=[*SWEEP, "hydra/job_logging=default"], multirun=True, sweep_dir=str(tmp_path)
        )
    finally:
        root.setLevel(level)
        root.handlers[:] = handlers

    assert len(list(tmp_path.glob("*/*.log"))) == 2


def test_a_sweep_leaves_hydra_config_store_as_it_found_it(tmp_path):
    before = _store_entries()

    sim_tools.simulate(run_default, overrides=SWEEP, multirun=True, sweep_dir=str(tmp_path))

    assert _store_entries() == before


def test_compose_leaves_hydra_config_store_as_it_found_it():
    registry = _registry("only_here")
    before = _store_entries()

    registry.compose("only_here")

    assert _store_entries() == before


def test_compose_sees_only_its_own_registry():
    first = _registry("defined_by_first")
    first.compose("defined_by_first")
    second = _registry("defined_by_second")

    with pytest.raises(HydraException, match="defined_by_first"):
        second.compose("defined_by_first")
