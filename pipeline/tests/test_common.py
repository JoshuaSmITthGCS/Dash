import math

from common import _json_safe


def test_json_safe_replaces_non_finite_values_recursively():
    payload = {
        "valid": 12.5,
        "nested": [math.inf, {"negative": -math.inf, "unknown": math.nan}],
    }

    assert _json_safe(payload) == {
        "valid": 12.5,
        "nested": [None, {"negative": None, "unknown": None}],
    }
