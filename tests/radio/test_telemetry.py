import pytest

from fall_detection.radio.acquisition.telemetry import (
    GatewayTelemetry,
    ReceiverTelemetry,
    TransmitterTelemetry,
    parse_gateway_telemetry,
    parse_receiver_telemetry,
    parse_telemetry_line,
    parse_transmitter_telemetry,
)
from fall_detection.radio.acquisition.wire import ReceiverStats


def test_receiver_telemetry_parses_stable_counter_order():
    parsed = parse_receiver_telemetry(
        "CSI_RX_STATS,udp-active,1234,99,100,2,3,4,5,6,7,8,9,10"
    )

    assert parsed == ReceiverTelemetry(
        mode="udp-active",
        uptime_ms=1234,
        boot_id=99,
        stats=ReceiverStats(100, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    )


def test_transmitter_telemetry_parses_stable_counter_order():
    parsed = parse_transmitter_telemetry("CSI_TX_STATS,1234,100,1,98,1")

    assert parsed == TransmitterTelemetry(1234, 100, 1, 98, 1)


def test_gateway_telemetry_parses_stable_counter_order():
    parsed = parse_gateway_telemetry("CSI_GATEWAY_STATS,1234,100,1,2,97,3")

    assert parsed == GatewayTelemetry(1234, 100, 1, 2, 97, 3)


def test_telemetry_dispatch_ignores_unrelated_firmware_output():
    assert parse_telemetry_line("I (10) csi_rx: ready") is None


@pytest.mark.parametrize(
    "line",
    [
        "CSI_RX_STATS,unknown,1,2,3,4,5,6,7,8,9,10,11,12",
        "CSI_RX_STATS,udp-active,1,2,3",
        "CSI_RX_STATS,udp-active,1,2,-1,4,5,6,7,8,9,10,11,12",
        "CSI_TX_STATS,1,2,3",
        "CSI_TX_STATS,1,2,3,nope,5",
        "CSI_GATEWAY_STATS,1,2,3",
        "CSI_GATEWAY_STATS,1,2,3,4,nope,6",
    ],
)
def test_telemetry_rejects_malformed_records(line):
    with pytest.raises(ValueError):
        parse_telemetry_line(line)
