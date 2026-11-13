import pytest

from fall_detection.radio.profile import (
    RadioInventory,
    RadioProfile,
    RadioProfileError,
    profile_fingerprint,
    validate_inventory_for_profile,
)


def inventory(*, target: str = "esp32c5") -> RadioInventory:
    return RadioInventory.from_mapping(
        {
            "schema_version": 2,
            "transmitter": {
                "id": "tx",
                "role": "transmitter",
                "target": target,
                "mac": "1a:00:00:00:00:00",
            },
            "receivers": [
                {
                    "id": "rx-1",
                    "role": "receiver",
                    "target": target,
                    "mac": "1a:00:00:00:00:01",
                }
            ],
            "gateway": {
                "id": "gw",
                "role": "gateway",
                "target": "esp32c6",
                "mac": "1a:00:00:00:00:02",
            },
        }
    )


def profile_mapping(**changes) -> dict:
    return {
        "schema_version": 2,
        "profile_id": "test",
        "country_code": "ID",
        "band": "5ghz",
        "channel": 44,
        "bandwidth_mhz": 20,
        "nominal_rate_hz": 100,
        **changes,
    }


def profile(*, channel: int = 44) -> RadioProfile:
    return RadioProfile.from_mapping(profile_mapping(channel=channel))


def test_profile_fingerprint_is_deterministic_and_changes_with_channel():
    inv = inventory()
    assert profile_fingerprint(profile(), inv) == profile_fingerprint(profile(), inv)
    assert profile_fingerprint(profile(), inv) != profile_fingerprint(
        profile(channel=36), inv
    )


def test_5ghz_rejects_c6_sensing_devices():
    with pytest.raises(RadioProfileError, match="ESP32-C5"):
        validate_inventory_for_profile(inventory(target="esp32c6"), profile())


def test_5ghz_accepts_all_c5_inventory():
    validate_inventory_for_profile(inventory(), profile())


def test_dfs_channels_are_rejected():
    with pytest.raises(RadioProfileError, match="non-DFS"):
        profile(channel=52)


def test_profile_requires_fixed_collection_shape():
    with pytest.raises(RadioProfileError, match="20 MHz"):
        RadioProfile.from_mapping(profile_mapping(bandwidth_mhz=40))


@pytest.mark.parametrize(
    "changes",
    [{"schema_version": 1}, {"band": "2.4ghz", "channel": 6}, {"nominal_rate_hz": 121}],
)
def test_retired_profile_forms_are_rejected(changes):
    with pytest.raises(RadioProfileError):
        RadioProfile.from_mapping(profile_mapping(**changes))


def test_inventory_requires_schema_two_and_a_c6_gateway():
    value = inventory().as_dict()
    assert RadioInventory.from_mapping(value) == inventory()
    with pytest.raises(RadioProfileError, match="schema_version must be 2"):
        RadioInventory.from_mapping({**value, "schema_version": 1})
    with pytest.raises(RadioProfileError, match="C6 gateway"):
        RadioInventory.from_mapping({k: v for k, v in value.items() if k != "gateway"})
