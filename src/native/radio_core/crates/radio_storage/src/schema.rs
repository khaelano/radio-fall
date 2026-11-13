//! Arrow schema of `frames.parquet`.
use arrow_schema::{DataType, Field, Schema};
use std::sync::Arc;

/// Version of the table layout written by this crate.
pub const SCHEMA_VERSION: u32 = 3;

/// Names of the fifteen verbatim header bytes, in wire order.
pub const HEADER_FIELDS: [&str; 15] = [
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
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "ant",
    "rx_state",
];

/// Integer columns that are nearly monotone and use delta encoding.
pub const DELTA_COLUMNS: [&str; 7] = [
    "sequence",
    "transport_sequence",
    "capture_time_ns",
    "host_arrival_ns",
    "rx_radio_us",
    "tx_enqueue_us",
    "rx_callback_us",
];

/// Build the frames schema. `payload_width` of `None` stores variable-length bytes.
pub fn frames_schema(payload_width: Option<i32>) -> Arc<Schema> {
    let mut fields = vec![
        Field::new("run_index", DataType::UInt16, false),
        Field::new("receiver_id", DataType::Utf8, false),
        Field::new("transmitter_mac", DataType::Utf8, false),
        Field::new("run_id", DataType::UInt64, false),
        Field::new("tx_boot_id", DataType::UInt32, false),
        Field::new("rx_boot_id", DataType::UInt32, false),
        Field::new("sequence", DataType::UInt32, false),
        Field::new("transport_sequence", DataType::UInt32, false),
        Field::new("capture_time_ns", DataType::Int64, true),
        Field::new("capture_uncertainty_us", DataType::Float32, true),
        Field::new("host_arrival_ns", DataType::Int64, false),
        Field::new("rx_radio_us", DataType::UInt32, false),
        Field::new("tx_enqueue_us", DataType::UInt64, false),
        Field::new("rx_callback_us", DataType::UInt64, false),
        Field::new("rssi", DataType::Int8, false),
        Field::new("noise_floor", DataType::Int8, false),
    ];
    fields.extend(
        HEADER_FIELDS
            .iter()
            .map(|name| Field::new(*name, DataType::UInt8, false)),
    );
    fields.push(Field::new("sig_len", DataType::UInt16, false));
    fields.push(Field::new("first_word_invalid", DataType::Boolean, false));
    fields.push(Field::new("timely", DataType::Boolean, true));
    fields.push(Field::new(
        "csi",
        match payload_width {
            Some(width) => DataType::FixedSizeBinary(width),
            None => DataType::Binary,
        },
        false,
    ));
    Arc::new(Schema::new(fields))
}
