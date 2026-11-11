"""Plain helpers for the FMU tests: the vendored Reference-FMUs and given-FMU runs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from omegaconf import OmegaConf

from mtools import sim_tools
from mtools.hydra_registry import HydraZenRegistry
from mtools.internal.fmu.request import RunRequest
from mtools.session_config import RunSettings

REFERENCE_FMUS = Path(__file__).parent / "reference_fmus"


def reference_fmu(name: str, fmi_version: str = "2.0") -> Path:
    """Return the vendored Reference-FMU ``name`` for ``fmi_version``."""
    return REFERENCE_FMUS / fmi_version / f"{name}.fmu"


def simulate_given(
    fmu_path: Path,
    *,
    model_name: str | None = None,
    fmu_type: str | None = None,
    name_map: dict[str, str] | None = None,
    parameters: Any = None,
    **settings: Any,
) -> dict[str, pd.DataFrame]:
    """Run the given FMU at ``fmu_path`` through ``sim_tools.simulate``."""
    values: Any = parameters or {}
    run = HydraZenRegistry().create_fmu_run(
        fmu_path=fmu_path,
        model_name=model_name,
        fmu_type=fmu_type,
        name_map=name_map,
        settings=RunSettings(parameters=values, **settings),
    )
    return sim_tools.simulate(OmegaConf.structured(run))


def capture_request(monkeypatch: pytest.MonkeyPatch, fmu_path: Path, **kwargs: Any) -> RunRequest:
    """Run ``simulate_given(fmu_path, **kwargs)`` and return the request the run wrote."""
    written: list[RunRequest] = []
    write = RunRequest.write

    def recording_write(request: RunRequest, directory: Path) -> None:
        written.append(request)
        write(request, directory)

    monkeypatch.setattr(RunRequest, "write", recording_write)
    simulate_given(fmu_path, **kwargs)
    [request] = written
    return request


def write(path: Path, content: bytes) -> Path:
    """Write ``content`` to ``path`` and return the path."""
    path.write_bytes(content)
    return path


def zip_without(fmu_path: Path, directory: Path, prefix: str) -> Path:
    """Copy ``fmu_path`` into ``directory`` without the archive entries starting with ``prefix``."""
    copy = directory / fmu_path.name
    with zipfile.ZipFile(fmu_path) as source, zipfile.ZipFile(copy, "w") as target:
        for entry in source.infolist():
            if not entry.filename.startswith(prefix):
                target.writestr(entry, source.read(entry))
    return copy


def edited_fmu(source: Path, directory: Path, edit: Callable[[ET.Element], None]) -> Path:
    """Copy ``source`` into ``directory`` with ``edit`` applied to its ``modelDescription.xml``."""
    copy = directory / source.name
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(copy, "w") as target:
        for entry in original.infolist():
            content = original.read(entry)
            if entry.filename == "modelDescription.xml":
                root = ET.fromstring(content)
                edit(root)
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(entry, content)
    return copy


def remove_element(tag: str) -> Callable[[ET.Element], None]:
    """Return an edit that removes every direct child of the root called ``tag``."""

    def edit(root: ET.Element) -> None:
        for element in root.findall(tag):
            root.remove(element)

    return edit


def set_attribute(tag: str, name: str, value: str) -> Callable[[ET.Element], None]:
    """Return an edit that sets attribute ``name`` of the first ``tag`` element, anywhere in the tree."""

    def edit(root: ET.Element) -> None:
        element = root if root.tag == tag else root.find(f".//{tag}")
        assert element is not None, f"no <{tag}> in the model description"
        element.set(name, value)

    return edit
