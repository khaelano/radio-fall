"""Drive the Rust acquisition session against a fake gateway on a pseudo-terminal.

The fake C6 gateway and its relayed C5 transmitter answer the real startup
transactions, then stream authoritative rounds, receiver status, gateway status
and CSI envelopes. No radio hardware or network access is used.
"""

import json
import os
import select
import struct
import threading
import time
import zlib

import pytest
from envelope_reference import Envelope
from test_gateway import inventory, profile
from transport_config import transport_config
from wire_encoder import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)

from fall_detection import _radio_native as core
from fall_detection.radio.profile import profile_fingerprint
from fall_detection.radio.provisioning import encode_serial_frame
from fall_detection.radio.records import CsiRecord

pytestmark = pytest.mark.skipif(
    not hasattr(core, "NativeAcquisition"), reason="native acquisition is Linux-only"
)

ROUND = struct.Struct("!4sQIIQQIII3B")
TRANSMITTER_BOOT = 11
RECEIVER_BOOT = 21


def now_us():
    return time.monotonic_ns() // 1000


class FakeGateway:
    """Answer gateway and relayed transmitter requests; stream data after CGGO."""

    def __init__(
        self,
        master,
        *,
        gateway_mac=None,
        status_period=0.3,
        radio_inventory=None,
        radio_profile=None,
    ):
        self.master = master
        self.inventory = radio_inventory or inventory()
        self.profile = radio_profile or profile()
        self.gateway_mac = gateway_mac or self.inventory.gateway.mac
        self.fingerprint = profile_fingerprint(self.profile, self.inventory)
        self.status_period = status_period
        self.configured = False
        self.run = None
        self.streaming = False
        self.silent = False
        self.sequence = 0
        self.acks, self.commands, self.relay_commands = [], [], []
        self.batches = 0
        self.decoder = core.FrameDecoder()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def send(self, kind, payload):
        frame = encode_serial_frame(kind, payload)
        with self.lock:
            os.write(self.master, frame)

    def relay(self, kind, payload):
        self.send(27, bytes([kind]) + payload)

    def gateway_status(self):
        return {
            "role": "gateway",
            "target": "esp32c6",
            "mac": self.gateway_mac,
            "protocol_version": 3,
            "csi_transport": "espnow_gateway",
            "transport_config_max_version": 7,
            "boot_id": 99,
            "ready": True,
            "configured": self.configured,
            "run_id": str(self.run or 0),
            "relay_version": 1,
            "relay_recovery_version": 1,
            "relay_transport": "espnow_uart",
            "relay_paired": True,
            "relay_ready": True,
            "relay_fault": False,
            "received": self.batches,
            "forwarded": self.batches,
        }

    def _serve(self):
        last_status = last_data = 0.0
        while not self.stop.is_set():
            readable, _, _ = select.select([self.master], [], [], 0.02)
            if readable:
                try:
                    data = os.read(self.master, 4096)
                except OSError:
                    return
                for kind, payload in self.decoder.feed(data):
                    self._handle(kind, bytes(payload))
            now = time.monotonic()
            if self.streaming:
                if now - last_status >= self.status_period:
                    last_status = now
                    if not self.silent:
                        self.send(6, json.dumps(self.gateway_status()).encode())
                    for slot in range(4):
                        self.relay(23, self._receiver_status(slot))
                if now - last_data >= 0.05:
                    last_data = now
                    enqueue = now_us()
                    self.relay(
                        22,
                        ROUND.pack(
                            b"CGRD",
                            self.run,
                            TRANSMITTER_BOOT,
                            self.sequence,
                            enqueue,
                            enqueue,
                            1_000_000 // self.profile.nominal_rate_hz,
                            15,
                            0,
                            0,
                            1,
                            2,
                        ),
                    )
                    for slot in range(4):
                        self.send(24, self._envelope(slot, self.sequence, enqueue))
                    self.sequence += 1

    def _handle(self, kind, payload):
        if kind == 5:
            self.send(6, json.dumps(self.gateway_status()).encode())
        elif kind == 20:
            self.commands.append(payload[:4])
            if payload[:4] == b"CGCF":
                self.configured, self.run = (
                    True,
                    struct.unpack_from("!Q", payload, 8)[0],
                )
            elif payload[:4] == b"CGSP":
                self.configured = self.streaming = False
            self.send(21, b"ok")
        elif kind == 25:
            self.acks.append(payload)
        elif kind == 26:
            relayed, body = payload[0], payload[1:]
            if relayed == 5:
                status = {
                    "role": "transmitter",
                    "target": "esp32c5",
                    "mac": self.inventory.transmitter.mac,
                    "protocol_version": 3,
                    "ready": True,
                    "profile_fingerprint": self.fingerprint,
                    "sensing_phy": "he20",
                    "sensing_version": 4,
                    "transport_config_max_version": 7,
                }
                self.relay(6, json.dumps(status).encode())
            elif relayed == 20:
                self.relay_commands.append(body[:4])
                if body[:4] == b"CGHC":
                    stamp = now_us()
                    response = body[:16] + struct.pack(
                        "!QQII", stamp, stamp, TRANSMITTER_BOOT, 0
                    )
                    self.relay(21, response)
                else:
                    self.relay(21, b"ok")
                    if body[:4] == b"CGGO":
                        # Each run's authoritative round log starts at zero.
                        self.sequence = 0
                        self.streaming = True

    def _receiver_status(self, slot):
        status = bytearray(96)
        status[:4] = b"CGST"
        status[4:8] = bytes((1, slot, 0, 0))
        struct.pack_into("!QII", status, 8, self.run, TRANSMITTER_BOOT, RECEIVER_BOOT)
        struct.pack_into("!IIIHHI", status, 72, 900, 0, 0, 3, 8, 0)
        struct.pack_into("!I", status, 92, zlib.crc32(status[:92]))
        return bytes(status)

    def _envelope(self, slot, sequence, enqueue):
        mac = self.inventory.receivers[slot].mac
        record = CsiRecord(
            sequence,
            self.inventory.transmitter.mac,
            -40,
            -95,
            100 + sequence,
            (complex(20, 30),) * 245,
            receiver_mac=mac,
            tx_timestamp_us=enqueue,
            rx_callback_timestamp_us=enqueue + 10,
            sig_mode=4,
            channel=self.profile.channel,
            profile_fingerprint=self.fingerprint,
        )
        # The radio usually captures each frame twice; the host keeps the first.
        datagrams = (
            DecodedCsiDatagram(record, mac, 2 * sequence),
            DecodedCsiDatagram(record, mac, 2 * sequence + 1),
        )
        payload = encode_csi_batch(
            datagrams,
            boot_id=RECEIVER_BOOT,
            batch_sequence=sequence,
            receiver_stats=ReceiverStats(*([0] * 10)),
        )
        self.batches += 1
        return Envelope(
            self.run, TRANSMITTER_BOOT, RECEIVER_BOOT, sequence, mac, payload
        ).encode()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


@pytest.fixture
def pty_gateway():
    master, slave = os.openpty()
    gateways = []

    def make(**options):
        gateway = FakeGateway(master, **options)
        gateways.append(gateway)
        return gateway, os.ttyname(slave)

    yield make
    for gateway in gateways:
        gateway.close()
    os.close(slave)
    os.close(master)


def acquisition(path, journal_root, **policy):
    config = transport_config().encode(123, inventory(), profile())
    return core.NativeAcquisition(
        json.dumps(
            {
                "serial_path": path,
                "radio_config": list(config),
                "journal_root": str(journal_root),
                "metadata": {"source": "pty-test"},
                "bin_hz": 50,
                "delivery_grace_ms": 500,
                "restart_delay_ms": 100,
                "maximum_restart_delay_ms": 200,
                "relay_ready_timeout_ms": 1000,
                **policy,
            }
        )
    )


def wait_for(condition, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("condition not reached")


def test_session_accepts_journals_acknowledges_and_deduplicates(tmp_path, pty_gateway):
    gateway, path = pty_gateway()
    native = acquisition(path, tmp_path)
    native.start()
    records = []
    try:
        wait_for(lambda: records.extend(native.poll(4096)) or len(records) >= 40)
        health = wait_for(
            lambda: (h := json.loads(native.health()))["session"].get("clock") and h
        )
        snapshot = wait_for(native.availability)
    finally:
        native.stop(5.0)
    records.extend(native.poll(4096))
    health = json.loads(native.health())
    assert health["failure"] is None and not health["fatal"]
    assert health["session"]["state"] == "running"
    assert health["session"]["clock"]["ready"]
    assert all(r["status"]["captured"] == 900 for r in health["session"]["receivers"])
    totals = health["totals"]
    # Every batch carries the same capture twice; exactly one is delivered.
    assert totals["records"] == len(records) == totals["duplicates"]
    assert totals["batches"] == len(records)
    for (
        native_record,
        slot,
        run,
        tx_boot,
        rx_boot,
        _,
        capture,
        arrival,
        available,
        _,
    ) in records:
        assert native_record.receiver_mac == inventory().receivers[slot].mac
        assert (run, tx_boot, rx_boot) == (gateway.run, TRANSMITTER_BOOT, RECEIVER_BOOT)
        assert abs(capture / 1000 - native_record.tx_timestamp_us) < 50_000
        assert available >= arrival
    assert json.loads(snapshot)["receivers"] == [d.mac for d in inventory().receivers]
    wait_for(lambda: len(gateway.acks) == totals["batches"], timeout=2)
    assert b"CGSP" in gateway.commands and b"CGGO" in gateway.relay_commands
    (journal,) = (tmp_path / "transport/gateway").iterdir()
    assert journal.name == f"{gateway.run:016x}"
    manifest = json.loads((journal / "manifest.json").read_text())
    assert manifest["source"] == "pty-test" and manifest["recovery"] is None
    assert len(core.read_envelopes(journal / "envelopes.bin")) == totals["batches"]
    kinds = {
        json.loads(line)["kind"]
        for line in (journal / "events.jsonl").read_text().splitlines()
    }
    assert {"reference_initial", "batch_acceptance", "round", "gateway_status"} <= kinds
    acceptances = [
        event
        for event in map(
            json.loads, (journal / "events.jsonl").read_text().splitlines()
        )
        if event["kind"] == "batch_acceptance"
    ]
    assert len(acceptances) == totals["batches"]
    for event in acceptances:
        # The clock-mapping uncertainty is journaled once per accepted batch.
        assert "clock_uncertainty_us" in event
        uncertainty = event["clock_uncertainty_us"]
        assert uncertainty is None or uncertainty >= 0
        assert all("capture_ns" in record for record in event["records"])
    assert (journal / "availability.jsonl").read_text().strip()


def test_lost_gateway_status_restarts_a_fresh_run(tmp_path, pty_gateway):
    gateway, path = pty_gateway()
    native = acquisition(path, tmp_path)
    native.start()
    try:
        wait_for(lambda: native.poll(4096))
        first = gateway.run
        gateway.silent = True
        wait_for(lambda: json.loads(native.health())["restarts"] >= 1)
        gateway.silent = False
        health = wait_for(
            lambda: (
                (h := json.loads(native.health()))["runs"] >= 2
                and h["session"].get("state") == "running"
                and h
            )
        )
        assert health["failure"] is None
        assert gateway.run != first
    finally:
        native.stop(5.0)
    journals = sorted((tmp_path / "transport/gateway").iterdir())
    assert len(journals) >= 2
    interrupted = [
        json.loads(line)
        for line in (journals[0] / "events.jsonl").read_text().splitlines()
        if '"run_interrupted"' in line
    ]
    assert interrupted[0]["reason"] == "gateway status timed out"
    resumed = json.loads((journals[-1] / "manifest.json").read_text())["recovery"]
    assert resumed["previous_run_id"] == str(first)
    assert "gateway status timed out" in resumed["reason"]


def test_identity_mismatch_stops_without_retrying(tmp_path, pty_gateway):
    gateway, path = pty_gateway(gateway_mac="02:00:00:00:00:99")
    native = acquisition(path, tmp_path)
    native.start()
    try:
        health = wait_for(lambda: (h := json.loads(native.health()))["finished"] and h)
    finally:
        native.stop(5.0)
    assert health["fatal"] and "mismatch" in health["failure"]
    assert health["runs"] == 0 and health["restarts"] == 0
    assert not gateway.streaming


def test_live_radio_delivers_native_records_to_the_host(tmp_path, pty_gateway):
    from fall_detection.apps.live.app import parser as _parser
    from fall_detection.radio.live import LiveRadio
    from fall_detection.radio.settings import RadioSettings

    settings = RadioSettings.load()
    gateway, path = pty_gateway(
        radio_inventory=settings.inventory, radio_profile=settings.profile
    )
    delivered = []
    args = _parser().parse_args(["--output-dir", str(tmp_path), "--gateway-port", path])
    radio = LiveRadio(args, record_sink=lambda r, t: delivered.append((r, t)))
    radio.start()
    try:
        wait_for(lambda: radio.preflight_ready)
        assert radio.failure is None and radio.availability(1.0) is not None
        diagnostics = radio.diagnostics()
        assert all(r.online and r.captured == 900 for r in diagnostics.receivers)
    finally:
        radio.stop()
    assert delivered
    receivers = {r.receiver_mac for r, _ in delivered}
    assert receivers == {d.mac for d in settings.inventory.receivers}
    record, arrival = delivered[-1]
    assert record.run_id == gateway.run and record.transport == "espnow_gateway"
    assert record.capture_host_monotonic_ns is not None and arrival > 0
    assert record.csv_line.startswith(f"CSI_DATA,{record.sequence},")
    telemetry = radio.telemetry_snapshot()
    assert telemetry.records == len(delivered) == telemetry.batches
    assert (tmp_path / "transport/gateway").is_dir()
