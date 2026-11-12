"""A crashed, hung or interrupted FMU run is reported like a native one and leaves nothing behind."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from mtools.errors import SimulationError, SimulationTimeout
from mtools.internal.omc import process, workdir
from tests.fmu.helpers import simulate_exported


def test_segfault_raises_crashed_with_sigsegv():
    with pytest.raises(SimulationError, match=r"^Simulation of 'FmuTests.Segfault' crashed with SIGSEGV:"):
        simulate_exported("FmuTests.Segfault")


def test_hang_times_out():
    simulate_exported("FmuTests.Hang", stop_time=0.1)  # export (a build, outside the timeout) into the module's cache

    started = time.monotonic()
    with pytest.raises(SimulationTimeout, match=r"timed out after 3 s"):
        simulate_exported("FmuTests.Hang", timeout=3)
    assert time.monotonic() - started < 15


def test_keep_runs_names_the_directory(monkeypatch):
    monkeypatch.setenv("MTOOLS_KEEP_RUNS", "1")
    with pytest.raises(SimulationError) as error:
        simulate_exported("FmuTests.Segfault")
    directory = Path(error.value.diagnostics.splitlines()[-1].removeprefix("Run directory: "))
    assert (directory / "fmu" / "modelDescription.xml").exists()


def test_interrupt_kills_the_child_and_removes_the_run_directory(monkeypatch):
    simulate_exported("FmuTests.Hang", stop_time=0.1)  # export first
    kept = set(workdir.runs_dir().iterdir())  # directories earlier tests kept
    children: list[subprocess.Popen[str]] = []
    communicate = subprocess.Popen.communicate

    def interrupting(self: subprocess.Popen[str], *args: object, **kwargs: object) -> tuple[str, str]:
        children.append(self)
        time.sleep(1)  # the child has started
        raise KeyboardInterrupt

    monkeypatch.setattr(process.subprocess.Popen, "communicate", interrupting)
    with pytest.raises(KeyboardInterrupt):
        simulate_exported("FmuTests.Hang")
    monkeypatch.setattr(process.subprocess.Popen, "communicate", communicate)

    [child] = children
    with pytest.raises(ProcessLookupError):
        os.killpg(child.pid, 0)
    assert set(workdir.runs_dir().iterdir()) == kept
