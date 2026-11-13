"""The CSI record type and the Espressif-compatible CSV row serialization.

``CsiRecord`` is the single Python-visible CSI measurement. It wraps one Rust
record, which owns the samples, the I/Q means, the calibrated HE-LTF phase
block and the CSV line. The record is built either from a record the Rust
session accepted (:meth:`CsiRecord.from_native`, the live and collector path)
or from Python values (the constructor, used by the session inspector and
tests); both produce the same derived values. Array views and per-block phase
data are created lazily and cached on the wrapper, and session metadata that
the native record does not carry (run and boot identifiers, capture time) is
held beside it.

The native record stores each CSI component as the signed byte the radio
reported, so constructor values must be integers in ``[-128, 127]``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .phase import LtfBlock, decode_ltf_blocks

CSI_HEADER = (
    "type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,"
    "aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,"
    "secondary_channel,local_timestamp,ant,sig_len,rx_state,len,first_word,data"
)

# Session metadata held beside the native record rather than inside it.
CONTEXT_FIELDS = (
    "run_id",
    "transmitter_boot_id",
    "receiver_boot_id",
    "capture_host_monotonic_ns",
    "capture_clock_uncertainty_us",
    "transport",
    "native_processed_ns",
)
_CONTEXT_DEFAULTS: dict[str, Any] = {
    "run_id": None,
    "transmitter_boot_id": None,
    "receiver_boot_id": None,
    "capture_host_monotonic_ns": None,
    "capture_clock_uncertainty_us": None,
    "transport": "",
}
_CONSTRUCTOR_CONTEXT = frozenset(_CONTEXT_DEFAULTS)
# Scalar properties the native record exposes under the constructor's names.
_NATIVE_FIELDS = (
    "sequence",
    "mac",
    "rssi",
    "noise_floor",
    "timestamp_us",
    "receiver_mac",
    "transport_sequence",
    "tx_timestamp_us",
    "rx_callback_timestamp_us",
    "first_word_invalid",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "ampdu_count",
    "channel",
    "secondary_channel",
    "antenna",
    "sig_len",
    "rx_state",
    "profile_fingerprint",
)


class NativePhaseBlock:
    """Calibrated HE-LTF block prepared by the native processing worker."""

    __slots__ = (
        "_record",
        "amplitudes",
        "calibrated_phases",
        "name",
        "raw_phases",
        "subcarrier_indices",
    )

    def __init__(
        self, record: Any, indices: Any, amplitude: Any, raw: Any, cal: Any
    ) -> None:
        self.name = "HE-LTF"
        self.subcarrier_indices = tuple(indices)
        self.amplitudes = np.frombuffer(amplitude, dtype="=f8")
        self.raw_phases = np.frombuffer(raw, dtype="=f8")
        self.calibrated_phases = np.frombuffer(cal, dtype="=f8")
        self._record = record

    @property
    def csi(self) -> tuple[complex, ...]:
        """Return the block's raw complex samples; HE layouts cover the record."""
        return self._record.raw_csi


class CsiRecord:
    """One immutable CSI measurement backed by a Rust record.

    Args:
        sequence: Transmitter sequence number (32 bit).
        mac: Transmitter MAC address text.
        rssi: Received signal strength in dBm (signed byte).
        noise_floor: Noise floor in dBm (signed byte).
        timestamp_us: Receiver radio timestamp in microseconds (32 bit).
        csi: Complex CSI exactly as the radio reported it; every component is
            an integer in ``[-128, 127]``. With ``first_word_invalid`` the
            ``csi`` view masks the first two values as NaN while ``raw_csi``
            keeps them.
        run_id: Receiver run identifier, when known.
        transmitter_boot_id: Transmitter boot identifier, when known.
        receiver_boot_id: Receiver boot identifier, when known.
        capture_host_monotonic_ns: Host capture time estimate, when known.
        capture_clock_uncertainty_us: Uncertainty of that estimate.
        transport: Transport name; empty when unknown.
        **native_fields: Remaining native fields: ``receiver_mac``,
            ``transport_sequence``, ``tx_timestamp_us``,
            ``rx_callback_timestamp_us``, ``first_word_invalid``, PHY fields
            (``rate``, ``sig_mode``, ``mcs``, ``bandwidth``, ``smoothing``,
            ``not_sounding``, ``aggregation``, ``stbc``, ``fec_coding``,
            ``sgi``, ``ampdu_count``, ``channel``, ``secondary_channel``,
            ``antenna``, ``sig_len``, ``rx_state``) and
            ``profile_fingerprint``. Passing only one of the two timestamps
            stores the other as zero.

    Raises:
        ValueError: If a CSI component is not an integer byte value.
    """

    __slots__ = ("_block", "_context", "_ltf", "_native", "_views")

    def __init__(
        self,
        sequence: int,
        mac: str,
        rssi: int,
        noise_floor: int,
        timestamp_us: int,
        csi: Any,
        *,
        run_id: int | None = None,
        transmitter_boot_id: int | None = None,
        receiver_boot_id: int | None = None,
        capture_host_monotonic_ns: int | None = None,
        capture_clock_uncertainty_us: float | None = None,
        transport: str = "",
        **native_fields: Any,
    ) -> None:
        from .native import require_native

        self._context = {
            "run_id": run_id,
            "transmitter_boot_id": transmitter_boot_id,
            "receiver_boot_id": receiver_boot_id,
            "capture_host_monotonic_ns": capture_host_monotonic_ns,
            "capture_clock_uncertainty_us": capture_clock_uncertainty_us,
            "transport": transport,
        }
        self._native = require_native().NativeRecord(
            sequence, mac, rssi, noise_floor, timestamp_us, tuple(csi), **native_fields
        )
        self._block = ...
        self._ltf = None
        self._views = None

    @classmethod
    def from_native(
        cls, native: Any, context: dict[str, Any] | None = None
    ) -> CsiRecord:
        """Wrap a record accepted by the Rust session without copying samples.

        Args:
            native: Record from ``_radio_native`` decoding or polling.
            context: Session metadata keyed by ``CONTEXT_FIELDS`` names.

        Returns:
            The wrapped record.
        """
        record = object.__new__(cls)
        record._context = context or {}
        record._native = native
        record._block = ...
        record._ltf = None
        record._views = None
        return record

    def __getattr__(self, name: str) -> Any:
        # Reached only for names that are not slots or methods. Special names
        # and unassigned slots (an instance that ``copy`` or ``pickle`` has
        # allocated but not filled) must fail here; looking them up through
        # ``self._context`` would recurse.
        if name.startswith("__") or name in CsiRecord.__slots__:
            raise AttributeError(name)
        context = self._context
        if name in context:
            return context[name]
        if name in _CONTEXT_DEFAULTS:
            return _CONTEXT_DEFAULTS[name]
        return getattr(self._native, name)

    def __reduce__(self) -> tuple[Any, tuple[dict[str, Any], dict[str, Any]]]:
        # The Rust record cannot be pickled. Rebuilding from the stored fields
        # keeps pickle, copy and deepcopy working as they did for the former
        # dataclass; the derived values are recomputed identically, and the
        # wire bytes, which nothing in Python reads, are not carried.
        return _restore_record, (self._native_fields(), dict(self._context))

    def _native_fields(self) -> dict[str, Any]:
        fields = {name: getattr(self._native, name) for name in _NATIVE_FIELDS}
        fields["csi"] = self._native.raw_csi
        return fields

    def __repr__(self) -> str:
        return (
            f"CsiRecord(sequence={self.sequence}, mac={self.mac!r}, "
            f"receiver_mac={self.receiver_mac!r}, samples={self.sample_count})"
        )

    def _identity(self) -> tuple[Any, ...]:
        native = self._native
        context = {**_CONTEXT_DEFAULTS, **self._context}
        return (
            tuple(getattr(native, name) for name in _NATIVE_FIELDS),
            native.raw_csi,
            tuple(sorted(context.items())),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CsiRecord):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())

    def with_context(self, updates: dict[str, Any]) -> CsiRecord:
        """Share native samples and prepared phase while adding session metadata."""
        return CsiRecord.from_native(self._native, {**self._context, **updates})

    def replace(self, **changes: Any) -> CsiRecord:
        """Return a copy with some fields changed.

        Metadata fields (``CONTEXT_FIELDS``) are changed without touching the
        native record. Any other field rebuilds the native record from the
        current values; ``csi`` then names the values as reported.

        Args:
            **changes: Constructor field names and their new values.

        Returns:
            The changed record.
        """
        context = {key: changes.pop(key) for key in CONTEXT_FIELDS if key in changes}
        if not changes:
            return self.with_context(context)
        return _restore_record(
            {**self._native_fields(), **changes}, {**self._context, **context}
        )

    @property
    def phase_views_ready(self) -> bool:
        """Return whether phase blocks exist without triggering preparation."""
        return self._ltf is not None or self._native.has_phase

    def _decoded_blocks(self) -> tuple[LtfBlock, ...]:
        blocks = self._ltf
        if blocks is None:
            blocks = decode_ltf_blocks(
                self._native.raw_csi,
                sig_mode=self._native.sig_mode,
                bandwidth=self._native.bandwidth,
                stbc=self._native.stbc,
                first_word_invalid=self._native.first_word_invalid,
            )
            self._ltf = blocks
        return blocks

    @property
    def channel_estimate_block(self) -> NativePhaseBlock | LtfBlock | None:
        """Return the HE- or HT-LTF block used by the calibrated phase path."""
        if self._block is ...:
            values = self._native.phase_bytes()
            if values is not None:
                self._block = NativePhaseBlock(self, *values)
            else:
                self._block = next(
                    (
                        block
                        for name in ("HE-LTF", "HT-LTF")
                        for block in self._decoded_blocks()
                        if block.name == name
                    ),
                    None,
                )
        return self._block

    @property
    def ltf_blocks(self) -> tuple[NativePhaseBlock | LtfBlock, ...]:
        """Return decoded CSI LTF blocks, or empty for unsupported layouts."""
        if self._native.has_phase:
            return (self.channel_estimate_block,)
        return self._decoded_blocks()

    @property
    def htltf_block(self) -> LtfBlock | None:
        """Return the HT-LTF block used by the calibrated phase path."""
        return next(
            (block for block in self.ltf_blocks if block.name == "HT-LTF"), None
        )

    def _view(self, index: int) -> np.ndarray:
        if self._views is None:
            self._views = tuple(
                np.frombuffer(b, dtype="=f8") for b in self._native.views_bytes()
            )
        return self._views[index]

    real = property(lambda self: self._view(0), doc="In-phase value per subcarrier.")
    imaginary = property(
        lambda self: self._view(1), doc="Quadrature value per subcarrier."
    )
    amplitudes = property(lambda self: self._view(2), doc="Magnitude per subcarrier.")
    phases = property(
        lambda self: self._view(3), doc="Phase in radians per subcarrier."
    )


def _restore_record(fields: dict[str, Any], context: dict[str, Any]) -> CsiRecord:
    """Build a record from native fields and session metadata.

    Metadata the constructor does not accept (``native_processed_ns``) is
    attached afterwards without rebuilding the native record.
    """
    extras = {k: v for k, v in context.items() if k not in _CONSTRUCTOR_CONTEXT}
    accepted = {k: v for k, v in context.items() if k in _CONSTRUCTOR_CONTEXT}
    record = CsiRecord(**fields, **accepted)
    return record.with_context(extras) if extras else record


def format_csi_record(record: CsiRecord) -> str:
    """Serialize a record using the existing Espressif CSV schema."""
    return record.csv_line
