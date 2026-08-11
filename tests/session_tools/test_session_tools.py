import numpy as np
import pytest

from mtools.internal.session_tools import SessionBuilder


class TestConvertParameters:
    def test_scalar_passthrough(self):
        assert SessionBuilder._convert_parameters({"v_norm": 10.0, "phi": 0.1}) == {
            "v_norm": 10.0,
            "phi": 0.1,
        }

    def test_non_numeric_scalar_passthrough(self):
        assert SessionBuilder._convert_parameters({"flag": True, "label": "x"}) == {
            "flag": True,
            "label": "x",
        }

    def test_list_1d_indexed(self):
        assert SessionBuilder._convert_parameters({"vec": [1.0, 2.0, 3.0]}) == {
            "vec[1]": 1.0,
            "vec[2]": 2.0,
            "vec[3]": 3.0,
        }

    def test_tuple_1d_indexed(self):
        assert SessionBuilder._convert_parameters({"vec": (1.0, 2.0)}) == {
            "vec[1]": 1.0,
            "vec[2]": 2.0,
        }

    def test_numpy_1d_array_indexed(self):
        assert SessionBuilder._convert_parameters({"vec": np.array([1.0, 2.0])}) == {
            "vec[1]": np.float64(1.0),
            "vec[2]": np.float64(2.0),
        }

    def test_numpy_2d_array_row_major_indexed(self):
        assert SessionBuilder._convert_parameters({"mat": np.array([[1.0, 2.0], [3.0, 4.0]])}) == {
            "mat[1, 1]": np.float64(1.0),
            "mat[1, 2]": np.float64(2.0),
            "mat[2, 1]": np.float64(3.0),
            "mat[2, 2]": np.float64(4.0),
        }

    def test_nested_list_2d_row_major_indexed(self):
        assert SessionBuilder._convert_parameters({"mat": [[1.0, 2.0], [3.0, 4.0]]}) == {
            "mat[1, 1]": 1.0,
            "mat[1, 2]": 2.0,
            "mat[2, 1]": 3.0,
            "mat[2, 2]": 4.0,
        }

    def test_mixed_scalar_and_array(self):
        assert SessionBuilder._convert_parameters({"v_norm": 10.0, "vec": [1.0, 2.0]}) == {
            "v_norm": 10.0,
            "vec[1]": 1.0,
            "vec[2]": 2.0,
        }

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="vec"):
            SessionBuilder._convert_parameters({"vec": []})

    def test_empty_tuple_raises(self):
        with pytest.raises(ValueError, match="vec"):
            SessionBuilder._convert_parameters({"vec": ()})

    def test_empty_ndarray_raises(self):
        with pytest.raises(ValueError, match="vec"):
            SessionBuilder._convert_parameters({"vec": np.array([])})

    def test_dict_passthrough(self):
        assert SessionBuilder._convert_parameters({"meta": {"a": 1}}) == {"meta": {"a": 1}}

    def test_string_value_passthrough(self):
        assert SessionBuilder._convert_parameters({"path": "abc"}) == {"path": "abc"}
