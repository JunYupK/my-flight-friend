# tests/test_types.py

import json

from flight_friend.types import Preferences


def test_preferences_json_roundtrip_restores_tuples():
    prefs = Preferences(
        out_dep_window=("06:00", "12:00"),
        in_dep_window=("14:00", "20:00"),
        nonstop_only=True,
        include_airlines=["TW"],
        exclude_airlines=["OZ"],
        max_price=300_000,
        max_duration_min=180,
    )

    restored = Preferences.from_dict(json.loads(json.dumps(prefs.to_dict())))

    assert restored == prefs
    assert restored.out_dep_window == ("06:00", "12:00")
    assert isinstance(restored.out_dep_window, tuple)
    assert restored.in_dep_window == ("14:00", "20:00")
    assert isinstance(restored.in_dep_window, tuple)


def test_preferences_from_empty_dict_equals_default():
    assert Preferences.from_dict({}) == Preferences()
