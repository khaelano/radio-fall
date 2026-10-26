import pytest

from fall_detection.radio.profile import (
    RadioInventory,
    RadioProfile,
    RadioProfileError,
    profile_fingerprint,
    validate_inventory_for_profile,
)


def inventory(*, target: str = "esp32c6") -> RadioInventory:
    return RadioInventory.from_mapping(
        {
            "schema_version": 1,
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
        }
    )


def profile(*, band: str = "2.4ghz", channel: int = 6) -> RadioProfile:
    return RadioProfile.from_mapping(
        {
            "schema_version": 1,
            "profile_id": "test",
            "country_code": "ID",
            "band": band,
            "channel": channel,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 100,
        }
    )


def test_profile_fingerprint_is_deterministic_and_changes_with_channel():
    inv = inventory()
    assert profile_fingerprint(profile(), inv) == profile_fingerprint(profile(), inv)
    assert profile_fingerprint(profile(), inv) != profile_fingerprint(
        profile(channel=11), inv
    )


def test_5ghz_rejects_c6_inventory():
    with pytest.raises(RadioProfileError, match="ESP32-C5"):
        validate_inventory_for_profile(inventory(), profile(band="5ghz", channel=36))


def test_5ghz_accepts_all_c5_inventory():
    validate_inventory_for_profile(
        inventory(target="esp32c5"), profile(band="5ghz", channel=36)
    )


def test_dfs_channels_are_rejected():
    with pytest.raises(RadioProfileError, match="non-DFS"):
        profile(band="5ghz", channel=52)


def test_profile_requires_fixed_collection_shape():
    with pytest.raises(RadioProfileError, match="20 MHz"):
        RadioProfile.from_mapping(
            {
                "schema_version": 1,
                "profile_id": "bad",
                "country_code": "ID",
                "band": "2.4ghz",
                "channel": 6,
                "bandwidth_mhz": 40,
                "nominal_rate_hz": 100,
            }
        )
