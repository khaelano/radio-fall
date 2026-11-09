"""Exercise interrupted-run recovery without physical USB devices."""

from collections import deque
import json
from threading import Event

import pytest

from fall_detection.radio.acquisition.gateway_journal import GatewayJournal
from fall_detection.radio.acquisition.gateway_reader import GatewayReceiverManager
from fall_detection.radio.acquisition.recovery import can_recover, recover_gateway
from fall_detection.radio.acquisition.serial_framing import (
    decode_serial_frame,
    encode_serial_frame,
)
from fall_detection.radio.live import LiveRadio
from fall_detection.radio.visualization.app import _parser


@pytest.mark.parametrize(
    "reason, expected",
    [
        ("transmitter restarted; start a new run", True),
        ("gateway restarted; start a new run", True),
        (
            "gateway ingestion failed: wireless transmitter reference failed: peer_timeout",
            True,
        ),
        ("could not open port: No such file or directory", True),
        ("gateway ingestion failed: CRC mismatch", False),
        ("gateway USB receive failed: gateway USB receive buffer age exceeded", True),
        ("gateway ingestion failed: gateway USB receive buffer overflow", False),
        ("No space left on device", False),
        ("transmitter identity/profile mismatch", False),
        ("transmitter reference framing error", True),
        ("gateway ingestion failed: gateway USB framing error", True),
    ],
)
def test_recovery_preserves_terminal_failures(reason, expected):
    assert can_recover(reason) is expected


@pytest.mark.parametrize("reason", [
    "transmitter restarted; start a new run",
    "gateway ingestion failed: gateway USB receive buffer age exceeded",
])
def test_live_recovery_replaces_run_clock_and_buffers_after_retiring_worker(tmp_path, reason):
    managers = []
    resumed = Event()
    interruptions = []
    calls = []

    class OfflineManager(GatewayReceiverManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            managers.append(self)

        def start(self):
            calls.append((self.run_id, "start"))
            if len(managers) == 2:
                resumed.set()

        def stop(self):
            calls.append((self.run_id, "stop"))

    def repair(old):
        assert (old.run_id, "stop") in calls
        calls.append((old.run_id, "repair"))

    args = _parser().parse_args(
        ["--output-dir", str(tmp_path), "--receiver-id", "rx-3"]
    )
    radio = LiveRadio(
        args,
        manager_factory=OfflineManager,
        repair_link=repair,
        on_interruption=interruptions.append,
    )
    radio._recovery_delay_s = 0
    old = radio.manager
    old.journal = GatewayJournal(tmp_path, old.run_id, {})
    old_buffer = radio.state.buffer
    try:
        radio.start()
        old._fail(reason)
        assert resumed.wait(2)
        assert radio.manager.run_id != old.run_id
        assert radio.manager.reference is None and not radio.manager.clock_sync_ready
        assert radio.manager.recovery_context["previous_run_id"] == str(old.run_id)
        assert radio.state.buffer is not old_buffer
        assert radio.state.selected_receiver_id == "rx-3"
        assert interruptions == [reason]
        events = [
            json.loads(s)
            for s in (old.journal.root / "events.jsonl").read_text().splitlines()
        ]
        assert events[-1]["kind"] == "run_interrupted"
    finally:
        radio.stop()
        old.journal.close()
    assert calls.count((old.run_id, "stop")) == 1
    assert calls.count((radio.manager.run_id, "stop")) == 1


def test_closing_live_radio_cancels_recovery_backoff():
    retired = Event()

    class OfflineManager(GatewayReceiverManager):
        def start(self):
            pass

        def stop(self):
            retired.set()

    radio = LiveRadio(
        _parser().parse_args([]),
        manager_factory=OfflineManager,
        repair_link=lambda old: pytest.fail("must not recover after close"),
    )
    radio._recovery_delay_s = 30
    radio.start()
    radio.manager._fail("transmitter restarted; start a new run")
    assert retired.wait(2)
    radio.stop()
    assert not radio._recovery_thread.is_alive()


@pytest.mark.parametrize(
    "configured, ready, fault, expected_types",
    [
        (True, True, False, [5, 20, 31]),
        (False, False, True, [5, 31]),
        (False, False, False, [5]),
        (False, True, False, [5]),
    ],
)
def test_recovery_stops_old_run_and_restarts_only_when_needed(
    monkeypatch, configured, ready, fault, expected_types
):
    radio = LiveRadio(_parser().parse_args([]))
    frames = deque()
    sent = []
    status = dict(
        role="gateway",
        target="esp32c6",
        mac=radio.settings.inventory.gateway.mac,
        relay_recovery_version=1,
        configured=configured,
        run_id="123",
        relay_ready=ready,
        relay_fault=fault,
    )

    class Connection:
        in_waiting = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def write(self, data):
            frame = decode_serial_frame(data.strip(b"\0"))
            sent.append(frame.type)
            frames.append(
                encode_serial_frame(6, json.dumps(status).encode())
                if frame.type == 5
                else encode_serial_frame(21, b"ok")
            )
            return len(data)

        def read(self, n):
            return frames.popleft() if frames else b""

    monkeypatch.setattr("serial.Serial", lambda *a, **kw: Connection())
    recover_gateway(radio.manager)
    assert sent == expected_types
