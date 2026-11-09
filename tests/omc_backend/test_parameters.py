"""Flattening and array expansion of run-setting parameters, without OMC.

Array elements use OMC's variable names (``m[1,2]``, no space): that is how the
build's ``_init.xml`` and the C runtime's override file name them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from mtools.internal.omc.parameters import (expand_parameters,
                                            flatten_parameters)


@dataclass
class Inner:
    px: float = 0.0
    py: float = 1.0


@dataclass
class Outer:
    v_norm: float = 10.0
    state_0: Inner = field(default_factory=Inner)


class TestFlattenParameters:
    def test_nested_dataclass_becomes_dotted_names(self):
        assert flatten_parameters(Outer()) == {"v_norm": 10.0, "state_0.px": 0.0, "state_0.py": 1.0}

    def test_nested_mapping_becomes_dotted_names(self):
        assert flatten_parameters({"a": 1, "sub": {"b": 2, "deeper": {"c": 3}}}) == {
            "a": 1,
            "sub.b": 2,
            "sub.deeper.c": 3,
        }

    def test_array_values_are_kept_whole(self):
        assert flatten_parameters({"vec": [1.0, 2.0]}) == {"vec": [1.0, 2.0]}


class TestExpandParameters:
    def test_scalar_passthrough(self):
        assert expand_parameters({"v_norm": 10.0, "phi": 0.1}) == {"v_norm": 10.0, "phi": 0.1}

    def test_non_numeric_scalar_passthrough(self):
        assert expand_parameters({"flag": True, "label": "x"}) == {"flag": True, "label": "x"}

    def test_list_1d_indexed(self):
        assert expand_parameters({"vec": [1.0, 2.0, 3.0]}) == {"vec[1]": 1.0, "vec[2]": 2.0, "vec[3]": 3.0}

    def test_tuple_1d_indexed(self):
        assert expand_parameters({"vec": (1.0, 2.0)}) == {"vec[1]": 1.0, "vec[2]": 2.0}

    def test_numpy_1d_array_indexed(self):
        assert expand_parameters({"vec": np.array([1.0, 2.0])}) == {"vec[1]": 1.0, "vec[2]": 2.0}

    def test_numpy_2d_array_row_major_indexed(self):
        assert expand_parameters({"mat": np.array([[1.0, 2.0], [3.0, 4.0]])}) == {
            "mat[1,1]": 1.0,
            "mat[1,2]": 2.0,
            "mat[2,1]": 3.0,
            "mat[2,2]": 4.0,
        }

    def test_nested_list_2d_row_major_indexed(self):
        assert expand_parameters({"mat": [[1.0, 2.0], [3.0, 4.0]]}) == {
            "mat[1,1]": 1.0,
            "mat[1,2]": 2.0,
            "mat[2,1]": 3.0,
            "mat[2,2]": 4.0,
        }

    def test_mixed_scalar_and_array(self):
        assert expand_parameters({"v_norm": 10.0, "vec": [1.0, 2.0]}) == {
            "v_norm": 10.0,
            "vec[1]": 1.0,
            "vec[2]": 2.0,
        }

    @pytest.mark.parametrize("empty", [[], (), np.array([])], ids=["list", "tuple", "ndarray"])
    def test_empty_array_raises(self, empty):
        with pytest.raises(ValueError, match="vec"):
            expand_parameters({"vec": empty})

    def test_string_value_passthrough(self):
        assert expand_parameters({"path": "abc"}) == {"path": "abc"}
