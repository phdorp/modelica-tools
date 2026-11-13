"""The Modelica models the FMU tests export, and their parameter dataclasses."""

from dataclasses import dataclass
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "FmuTests.mo"


@dataclass
class DecayParameters:
    """Parameters of ``FmuTests.Decay``."""

    k: float = 1.0
    x0: float = 1.0


@dataclass
class DahlquistParameters:
    """Parameters of the Reference-FMU ``Dahlquist``."""

    k: float = 1.0
