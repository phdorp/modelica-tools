"""Read the variable list OMC writes to a build's ``<prefix>_init.xml``."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Variable:
    """One ``ScalarVariable`` of a build.

    Attributes:
        name: OMC's variable name, e.g. ``sub.k`` or ``m[1,2]``.
        type: Modelica type from the child element: ``Real``, ``Integer``,
            ``Boolean``, ``String`` or ``Enumeration``.
        variability: ``parameter``, ``discrete``, ``continuous`` or ``constant``.
        causality: ``parameter``, ``calculatedParameter``, ``local``, ...; the copy a
            Cpp-exported FMU carries marks every variable ``internal``.
        changeable: Whether a run can set its value (``isValueChangeable``).
        protected: Whether the variable is protected.
        alias: ``noAlias``, ``alias`` or ``negatedAlias``.
        value_reference: Index of the value the variable is stored in, per type. On
            Cpp an alias shares the value reference of the variable it aliases.
    """

    name: str
    type: str
    variability: str
    causality: str
    changeable: bool
    protected: bool
    alias: str = "noAlias"
    value_reference: str = ""


def read_variables(path: Path) -> dict[str, Variable]:
    """Return the build's variables by name."""
    variables: dict[str, Variable] = {}
    for element in ET.parse(path).getroot().iter("ScalarVariable"):
        name = element.attrib["name"]
        variables[name] = Variable(
            name=name,
            type=element[0].tag,
            variability=element.attrib.get("variability", ""),
            causality=element.attrib.get("causality", ""),
            changeable=element.attrib.get("isValueChangeable") == "true",
            protected=element.attrib.get("isProtected") == "true",
            alias=element.attrib.get("alias", "noAlias"),
            value_reference=element.attrib.get("valueReference", ""),
        )
    return variables
