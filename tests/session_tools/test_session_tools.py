"""Array parameters in a parameter dataclass reach the model as indexed names, set from configs."""

import dataclasses
from pathlib import Path

import hydra_zen
import pytest

from mtools.session_config import Build, RunSettings, SimulationRun
from mtools.sim_tools import simulate

MODEL_PATH = Path(__file__).parent.joinpath("models", "arrays.mo").resolve()


@dataclasses.dataclass
class ArrayParameters:
    y: list[float] = dataclasses.field(default_factory=lambda: [1.0, 2.0])
    m: list[list[float]] = dataclasses.field(default_factory=lambda: [[1.0, 2.0], [3.0, 4.0]])


run_arrays = hydra_zen.make_config(
    bases=(SimulationRun,),
    hydra_defaults=["_self_"],
    build=Build(model_path=MODEL_PATH, model_name="Arrays"),
    settings=RunSettings(parameters=ArrayParameters(), stop_time=1.0),
)


def _final(tmp_path, overrides):
    job = hydra_zen.launch(
        run_arrays,
        simulate,
        [*overrides, f"hydra.run.dir={tmp_path}", "hydra.job.chdir=False"],
        with_log_configuration=False,
        version_base=None,
    )
    return job.return_value["Arrays"].iloc[-1]


@pytest.mark.parametrize("target", ["C", "Cpp"])
def test_array_parameters_are_set_element_by_element(tmp_path, target):
    final = _final(
        tmp_path,
        [f"build.target={target}", "settings.parameters.y=[3.0,4.0]", "settings.parameters.m=[[1.0,5.0],[6.0,4.0]]"],
    )

    assert final["s"] == pytest.approx(3.0 + 10 * 4.0)
    assert final["t"] == pytest.approx(5.0 + 10 * 6.0)


def test_array_defaults_from_the_dataclass_are_applied(tmp_path):
    final = _final(tmp_path, [])

    assert final["s"] == pytest.approx(1.0 + 10 * 2.0)
    assert final["t"] == pytest.approx(2.0 + 10 * 3.0)


def test_empty_array_parameter_raises_value_error():
    run = SimulationRun(
        build=Build(model_path=MODEL_PATH, model_name="Arrays"),
        settings=RunSettings(parameters=ArrayParameters(y=[])),
    )

    with pytest.raises(ValueError, match="y"):
        simulate(run)
