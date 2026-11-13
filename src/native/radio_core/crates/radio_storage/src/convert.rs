//! Convert a session's raw journals and events into `frames.parquet`.
use crate::error::{Error, Result};
use crate::schema::{DELTA_COLUMNS, HEADER_FIELDS, SCHEMA_VERSION, frames_schema};
use crate::source::{
    BatchEvent, CaptureEvents, PythonCapture, RunSource, SessionInfo, discover_runs, first_arrival,
    for_each_envelope, scan_events, session_info,
};
use crate::vfs::Vfs;
use arrow_array::builder::{
    BinaryBuilder, BooleanBuilder, FixedSizeBinaryBuilder, Float32Builder, Int8Builder,
    Int64Builder, StringBuilder, UInt8Builder, UInt16Builder, UInt32Builder, UInt64Builder,
};
use arrow_array::{ArrayRef, RecordBatch, StringArray, UInt16Array, UInt64Array};
use parquet::arrow::ArrowWriter;
use parquet::basic::{Compression, Encoding, ZstdLevel};
use parquet::file::metadata::KeyValue;
use parquet::file::properties::{EnabledStatistics, WriterProperties};
use parquet::schema::types::ColumnPath;
use radio_transport::wire::{RawBatch, mac};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;

/// Version of the converting code, recorded in every derived file.
pub const CONVERTER_VERSION: &str = concat!("radio-storage-", env!("CARGO_PKG_VERSION"));

/// Which journal frames the table contains.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameScope {
    /// Only frames captured inside an attempt window, matching what the
    /// collector wrote to per-attempt files. Sessions without attempts keep
    /// every frame.
    Attempts,
    /// Every journal frame, including time between attempts.
    All,
}

impl FrameScope {
    /// Name recorded in `conversion.json`.
    pub fn label(self) -> &'static str {
        match self {
            FrameScope::Attempts => "attempts",
            FrameScope::All => "all",
        }
    }
}

/// Tunable write parameters.
#[derive(Debug, Clone, Copy)]
pub struct ConvertOptions {
    /// Maximum rows per Parquet row group.
    pub row_group_rows: usize,
    /// Zstandard level for every column.
    pub zstd_level: i32,
    /// Which frames to keep.
    pub scope: FrameScope,
}

impl Default for ConvertOptions {
    fn default() -> Self {
        Self {
            row_group_rows: 10_000,
            zstd_level: 3,
            scope: FrameScope::Attempts,
        }
    }
}

/// Merged half-open capture-time windows `[start, end)`.
struct Windows(Vec<(i64, i64)>);

impl Windows {
    fn from_attempts(attempts: &[crate::annotate::Attempt]) -> Self {
        let mut spans: Vec<(i64, i64)> = attempts
            .iter()
            .map(|a| (a.start_ns, a.end_ns.unwrap_or(i64::MAX)))
            .collect();
        spans.sort_unstable();
        let mut merged: Vec<(i64, i64)> = Vec::new();
        for (start, end) in spans {
            match merged.last_mut() {
                Some(last) if start <= last.1 => last.1 = last.1.max(end),
                _ => merged.push((start, end)),
            }
        }
        Self(merged)
    }

    fn contains(&self, ns: i64) -> bool {
        let at = self.0.partition_point(|(start, _)| *start <= ns);
        at > 0 && ns < self.0[at - 1].1
    }
}

/// Journal era of one run, chosen by the capture events present.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Era {
    PythonEra,
    RustEra,
    NoCapture,
}

impl Era {
    fn label(self) -> &'static str {
        match self {
            Era::PythonEra => "journal_python_era",
            Era::RustEra => "journal_rust_era",
            Era::NoCapture => "journal_no_capture",
        }
    }
}

/// Per-run facts recorded in the conversion report.
#[derive(Debug, Clone)]
pub struct RunReport {
    pub run_index: Option<u16>,
    pub run_id: u64,
    pub era: Option<Era>,
    pub frames: u64,
    /// Journal frames left out by the frame scope.
    pub frames_excluded: u64,
    pub first_arrival_ns: Option<u64>,
    pub torn_journal: bool,
    pub torn_event_lines: u64,
    pub frames_without_capture: u64,
    pub capture_backward_steps: u64,
    pub arrival_decreases: u64,
    pub sequence_nonincreasing: u64,
}

/// Summary of one conversion.
#[derive(Debug, Clone)]
pub struct ConversionReport {
    pub session_id: String,
    pub protocol_hash: String,
    pub source_fingerprint: String,
    pub source_kind: String,
    pub payload_width: Option<i32>,
    /// Name of the frame scope used.
    pub frame_scope: String,
    pub frames: u64,
    /// Frames present in the journals, before the scope was applied.
    pub frames_in_journal: u64,
    pub receivers: BTreeMap<String, u64>,
    pub runs: Vec<RunReport>,
    pub unmapped_receivers: Vec<String>,
}

impl ConversionReport {
    /// Frames left out by the frame scope across all runs.
    pub fn frames_excluded_total(&self) -> u64 {
        self.runs.iter().map(|r| r.frames_excluded).sum()
    }

    /// Render the report as JSON for `conversion.json`.
    pub fn to_json(&self) -> Value {
        let runs: Vec<Value> = self
            .runs
            .iter()
            .map(|r| {
                json!({
                    "run_index": r.run_index,
                    "run_id": format!("{:016x}", r.run_id),
                    "era": r.era.map(Era::label),
                    "frames": r.frames,
                    "frames_excluded": r.frames_excluded,
                    "first_arrival_ns": r.first_arrival_ns,
                    "torn_journal": r.torn_journal,
                    "torn_event_lines": r.torn_event_lines,
                    "frames_without_capture": r.frames_without_capture,
                    "capture_backward_steps": r.capture_backward_steps,
                    "arrival_decreases": r.arrival_decreases,
                    "sequence_nonincreasing": r.sequence_nonincreasing,
                })
            })
            .collect();
        json!({
            "storage_schema_version": SCHEMA_VERSION,
            "converter_version": CONVERTER_VERSION,
            "session_id": self.session_id,
            "protocol_hash": self.protocol_hash,
            "source_fingerprint": self.source_fingerprint,
            "source_kind": self.source_kind,
            "payload_width": self.payload_width,
            "frame_scope": self.frame_scope,
            "frames": self.frames,
            "frames_in_journal": self.frames_in_journal,
            "receivers": self.receivers,
            "unmapped_receivers": self.unmapped_receivers,
            "runs": runs,
        })
    }
}

enum Payload {
    Fixed(FixedSizeBinaryBuilder),
    Variable(BinaryBuilder),
}

/// Column builders for the frames of one receiver within one run.
struct Columns {
    transmitter: StringBuilder,
    tx_boot: UInt32Builder,
    rx_boot: UInt32Builder,
    sequence: UInt32Builder,
    transport_sequence: UInt32Builder,
    capture: Int64Builder,
    uncertainty: Float32Builder,
    arrival: Int64Builder,
    rx_radio: UInt32Builder,
    tx_enqueue: UInt64Builder,
    rx_callback: UInt64Builder,
    rssi: Int8Builder,
    noise: Int8Builder,
    header: Vec<UInt8Builder>,
    sig_len: UInt16Builder,
    first_word: BooleanBuilder,
    timely: BooleanBuilder,
    payload: Payload,
    rows: usize,
    last_arrival: Option<i64>,
    last_sequence: Option<u32>,
    last_capture: Option<i64>,
}

impl Columns {
    fn new(width: Option<i32>) -> Self {
        Self {
            transmitter: StringBuilder::new(),
            tx_boot: UInt32Builder::new(),
            rx_boot: UInt32Builder::new(),
            sequence: UInt32Builder::new(),
            transport_sequence: UInt32Builder::new(),
            capture: Int64Builder::new(),
            uncertainty: Float32Builder::new(),
            arrival: Int64Builder::new(),
            rx_radio: UInt32Builder::new(),
            tx_enqueue: UInt64Builder::new(),
            rx_callback: UInt64Builder::new(),
            rssi: Int8Builder::new(),
            noise: Int8Builder::new(),
            header: (0..HEADER_FIELDS.len())
                .map(|_| UInt8Builder::new())
                .collect(),
            sig_len: UInt16Builder::new(),
            first_word: BooleanBuilder::new(),
            timely: BooleanBuilder::new(),
            payload: match width {
                Some(width) => Payload::Fixed(FixedSizeBinaryBuilder::new(width)),
                None => Payload::Variable(BinaryBuilder::new()),
            },
            rows: 0,
            last_arrival: None,
            last_sequence: None,
            last_capture: None,
        }
    }

    fn finish(
        &mut self,
        schema: &Arc<arrow_schema::Schema>,
        run_index: u16,
        receiver_id: &str,
        run_id: u64,
    ) -> Result<RecordBatch> {
        let rows = self.rows;
        let mut columns: Vec<ArrayRef> = vec![
            Arc::new(UInt16Array::from(vec![run_index; rows])),
            Arc::new(StringArray::from_iter_values(std::iter::repeat_n(
                receiver_id,
                rows,
            ))),
            Arc::new(self.transmitter.finish()),
            Arc::new(UInt64Array::from(vec![run_id; rows])),
            Arc::new(self.tx_boot.finish()),
            Arc::new(self.rx_boot.finish()),
            Arc::new(self.sequence.finish()),
            Arc::new(self.transport_sequence.finish()),
            Arc::new(self.capture.finish()),
            Arc::new(self.uncertainty.finish()),
            Arc::new(self.arrival.finish()),
            Arc::new(self.rx_radio.finish()),
            Arc::new(self.tx_enqueue.finish()),
            Arc::new(self.rx_callback.finish()),
            Arc::new(self.rssi.finish()),
            Arc::new(self.noise.finish()),
        ];
        for builder in &mut self.header {
            columns.push(Arc::new(builder.finish()));
        }
        columns.push(Arc::new(self.sig_len.finish()));
        columns.push(Arc::new(self.first_word.finish()));
        columns.push(Arc::new(self.timely.finish()));
        columns.push(match &mut self.payload {
            Payload::Fixed(builder) => Arc::new(builder.finish()),
            Payload::Variable(builder) => Arc::new(builder.finish()),
        });
        Ok(RecordBatch::try_new(schema.clone(), columns)?)
    }
}

/// Per-frame values taken from the capture events.
struct Capture {
    capture_ns: Option<i64>,
    uncertainty_us: Option<f32>,
    timely: Option<bool>,
}

struct Writer {
    inner: ArrowWriter<File>,
    schema: Arc<arrow_schema::Schema>,
    width: Option<i32>,
}

fn properties(options: &ConvertOptions) -> Result<WriterProperties> {
    let mut builder = WriterProperties::builder()
        .set_compression(Compression::ZSTD(ZstdLevel::try_new(options.zstd_level)?))
        .set_max_row_group_row_count(Some(options.row_group_rows))
        .set_statistics_enabled(EnabledStatistics::Chunk)
        .set_dictionary_enabled(false);
    for name in DELTA_COLUMNS {
        builder =
            builder.set_column_encoding(ColumnPath::from(name), Encoding::DELTA_BINARY_PACKED);
    }
    Ok(builder.build())
}

/// Convert a session source into `out_dir/frames.parquet`.
///
/// The output is a pure function of the source and the options. Frames are
/// written in journal order per receiver, run by run.
pub fn convert_frames(
    vfs: &dyn Vfs,
    out_dir: &Path,
    options: &ConvertOptions,
) -> Result<ConversionReport> {
    let info = session_info(vfs)?;
    let attempts = crate::annotate::read_attempts(vfs, &info)?;
    let windows = (options.scope == FrameScope::Attempts && !attempts.is_empty())
        .then(|| Windows::from_attempts(&attempts));
    let windows = windows.as_ref();
    match convert_with(vfs, out_dir, options, &info, windows, true) {
        Err(error) if error.0 == VARIABLE_PAYLOAD => {
            convert_with(vfs, out_dir, options, &info, windows, false)
        }
        other => other,
    }
}

const VARIABLE_PAYLOAD: &str = "payload length varies within the session";

fn convert_with(
    vfs: &dyn Vfs,
    out_dir: &Path,
    options: &ConvertOptions,
    info: &SessionInfo,
    windows: Option<&Windows>,
    prefer_fixed: bool,
) -> Result<ConversionReport> {
    let fingerprint = vfs.fingerprint()?;
    std::fs::create_dir_all(out_dir)?;
    let temporary = out_dir.join("frames.parquet.tmp");
    let target = out_dir.join("frames.parquet");

    // Order runs by their first journal arrival; empty journals are reported.
    let mut ordered = Vec::new();
    let mut reports: Vec<RunReport> = Vec::new();
    for run in discover_runs(vfs, info)? {
        match first_arrival(vfs, &run.envelopes)? {
            Some(arrival) => ordered.push((arrival, run)),
            None => reports.push(empty_report(&run)),
        }
    }
    ordered.sort_by_key(|(arrival, run)| (*arrival, run.run_id));

    let mut writer: Option<Writer> = None;
    let mut receivers: BTreeMap<String, u64> = BTreeMap::new();
    let mut unmapped: Vec<String> = Vec::new();
    let mut eras: Vec<Era> = Vec::new();
    let mut width: Option<i32> = None;
    for (index, (arrival, run)) in ordered.iter().enumerate() {
        let run_index = u16::try_from(index).map_err(|_| Error("more than 65535 runs".into()))?;
        let processed = process_run(
            vfs,
            info,
            run,
            run_index,
            *arrival,
            &mut width,
            prefer_fixed,
            windows,
            &mut unmapped,
        )?;
        let (mut report, chunks, era) = processed;
        if !chunks.is_empty() && writer.is_none() {
            let schema = frames_schema(width);
            let file = File::create(&temporary)?;
            writer = Some(Writer {
                inner: ArrowWriter::try_new(file, schema.clone(), Some(properties(options)?))?,
                schema,
                width,
            });
        }
        for (receiver_id, mut columns) in chunks {
            let w = writer.as_mut().expect("writer exists when chunks exist");
            let batch = columns.finish(&w.schema, run_index, &receiver_id, run.run_id)?;
            *receivers.entry(receiver_id).or_default() += batch.num_rows() as u64;
            w.inner.write(&batch)?;
            w.inner.flush()?;
        }
        eras.push(era);
        report.era = Some(era);
        reports.push(report);
    }

    if writer.is_none() {
        let schema = frames_schema(None);
        let file = File::create(&temporary)?;
        writer = Some(Writer {
            inner: ArrowWriter::try_new(file, schema.clone(), Some(properties(options)?))?,
            schema,
            width: None,
        });
    }
    let mut writer = writer.expect("writer created above");
    reports.sort_by_key(|r| (r.run_index.is_none(), r.run_index, r.run_id));
    let frames: u64 = receivers.values().sum();
    let source_kind = kind_of(&eras);
    let report = ConversionReport {
        session_id: info.session_id.clone(),
        protocol_hash: info.protocol_hash.clone(),
        source_fingerprint: fingerprint,
        source_kind,
        payload_width: writer.width,
        frame_scope: if windows.is_some() { "attempts" } else { "all" }.to_string(),
        frames,
        frames_in_journal: frames + reports.iter().map(|r| r.frames_excluded).sum::<u64>(),
        receivers,
        runs: reports,
        unmapped_receivers: unmapped,
    };
    let metadata = [
        ("storage_schema_version", SCHEMA_VERSION.to_string()),
        ("session_id", report.session_id.clone()),
        ("protocol_hash", report.protocol_hash.clone()),
        ("source_kind", report.source_kind.clone()),
        ("source_fingerprint", report.source_fingerprint.clone()),
        ("converter_version", CONVERTER_VERSION.to_string()),
        ("iq_order", "imag_real".to_string()),
        ("frame_scope", report.frame_scope.clone()),
        ("row_count", serde_json::to_string(&report.receivers)?),
    ];
    for (key, value) in metadata {
        writer
            .inner
            .append_key_value_metadata(KeyValue::new(key.to_string(), Some(value)));
    }
    writer.inner.close()?;
    File::open(&temporary)?.sync_all()?;
    std::fs::rename(&temporary, &target)?;
    Ok(report)
}

fn kind_of(eras: &[Era]) -> String {
    let mut labels: Vec<&str> = eras.iter().map(|e| e.label()).collect();
    labels.sort();
    labels.dedup();
    match labels.as_slice() {
        [] => "journal_empty".to_string(),
        [one] => (*one).to_string(),
        _ => "journal_mixed".to_string(),
    }
}

fn empty_report(run: &RunSource) -> RunReport {
    RunReport {
        run_index: None,
        run_id: run.run_id,
        era: None,
        frames: 0,
        frames_excluded: 0,
        first_arrival_ns: None,
        torn_journal: false,
        torn_event_lines: 0,
        frames_without_capture: 0,
        capture_backward_steps: 0,
        arrival_decreases: 0,
        sequence_nonincreasing: 0,
    }
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn process_run(
    vfs: &dyn Vfs,
    info: &SessionInfo,
    run: &RunSource,
    run_index: u16,
    first_arrival_ns: u64,
    width: &mut Option<i32>,
    prefer_fixed: bool,
    windows: Option<&Windows>,
    unmapped: &mut Vec<String>,
) -> Result<(RunReport, BTreeMap<String, Columns>, Era)> {
    let scan = match &run.events {
        Some(path) => scan_events(vfs, path)?,
        None => Default::default(),
    };
    let era = match scan.capture {
        CaptureEvents::None => Era::NoCapture,
        CaptureEvents::Python { .. } => Era::PythonEra,
        CaptureEvents::Rust(_) => Era::RustEra,
    };
    let mut report = RunReport {
        run_index: Some(run_index),
        first_arrival_ns: Some(first_arrival_ns),
        torn_event_lines: scan.torn_lines,
        ..empty_report(run)
    };
    let mut chunks: BTreeMap<String, Columns> = BTreeMap::new();
    let mut next_batch = 0usize;
    let mut batch_events: Option<&Vec<BatchEvent>> = None;
    if let CaptureEvents::Rust(events) = &scan.capture {
        batch_events = Some(events);
    }
    let tail = for_each_envelope(vfs, &run.envelopes, &mut |arrival, envelope| {
        let batch = RawBatch::parse(envelope).map_err(Error)?;
        if batch.run != run.run_id {
            return Err(Error(format!(
                "envelope run {:016x} differs from directory {:016x}",
                batch.run, run.run_id
            )));
        }
        let receiver_mac = mac(batch.receiver);
        let receiver_id = match info.receiver_ids.get(&receiver_mac) {
            Some(id) => id.clone(),
            None => {
                if !unmapped.contains(&receiver_mac) {
                    unmapped.push(receiver_mac.clone());
                }
                receiver_mac.clone()
            }
        };
        let event = match batch_events {
            Some(events) => {
                let event = events.get(next_batch);
                next_batch += 1;
                if let Some(event) = event {
                    check_event(event, &batch, &receiver_mac)?;
                }
                event
            }
            None => None,
        };
        for (position, record) in batch.records.iter().enumerate() {
            let capture = match (&scan.capture, event) {
                (CaptureEvents::Python { receivers, records }, _) => {
                    let found: Option<PythonCapture> = receivers
                        .get(&receiver_id)
                        .and_then(|slot| {
                            records.get(&(*slot, batch.rx_boot, batch.tx_boot, record.sequence()))
                        })
                        .copied();
                    found.map(|c| Capture {
                        capture_ns: c.capture_ns,
                        uncertainty_us: c.uncertainty_us,
                        timely: c.timely,
                    })
                }
                (CaptureEvents::Rust(_), Some(event)) => {
                    let (sequence, capture) = event.records[position];
                    if sequence != record.sequence() {
                        return Err(Error(
                            "batch_acceptance sequence differs from envelope".into(),
                        ));
                    }
                    Some(Capture {
                        capture_ns: capture,
                        uncertainty_us: event.uncertainty_us,
                        timely: None,
                    })
                }
                _ => None,
            };
            if let Some(windows) = windows
                && !capture
                    .as_ref()
                    .and_then(|c| c.capture_ns)
                    .is_some_and(|ns| windows.contains(ns))
            {
                report.frames_excluded += 1;
                continue;
            }
            let payload = record.payload();
            let columns = chunks.entry(receiver_id.clone()).or_insert_with(|| {
                Columns::new(match (prefer_fixed, *width) {
                    (true, Some(w)) => Some(w),
                    (true, None) => {
                        *width = Some(payload.len() as i32);
                        *width
                    }
                    (false, _) => None,
                })
            });
            append(
                columns,
                &batch,
                record,
                arrival as i64,
                capture,
                &mut report,
                prefer_fixed,
            )?;
        }
        Ok(())
    })?;
    report.torn_journal = tail.torn;
    report.frames = chunks.values().map(|c| c.rows as u64).sum();
    Ok((report, chunks, era))
}

fn check_event(event: &BatchEvent, batch: &RawBatch<'_>, receiver: &str) -> Result<()> {
    if event.run != batch.run
        || event.tx_boot != batch.tx_boot
        || event.rx_boot != batch.rx_boot
        || event.batch != batch.id
        || event.receiver != receiver
        || event.records.len() != batch.records.len()
    {
        return Err(Error(format!(
            "batch_acceptance does not match envelope (run {:016x}, batch {})",
            batch.run, batch.id
        )));
    }
    Ok(())
}

fn append(
    columns: &mut Columns,
    batch: &RawBatch<'_>,
    record: &radio_transport::wire::RawRecord<'_>,
    arrival_ns: i64,
    capture: Option<Capture>,
    report: &mut RunReport,
    prefer_fixed: bool,
) -> Result<()> {
    columns.transmitter.append_value(mac(record.transmitter()));
    columns.tx_boot.append_value(batch.tx_boot);
    columns.rx_boot.append_value(batch.rx_boot);
    columns.sequence.append_value(record.sequence());
    columns
        .transport_sequence
        .append_value(record.transport_sequence());
    let (capture_ns, uncertainty, timely) = match capture {
        Some(c) => (c.capture_ns, c.uncertainty_us, c.timely),
        None => (None, None, None),
    };
    if capture_ns.is_none() {
        report.frames_without_capture += 1;
    }
    if let (Some(now), Some(before)) = (capture_ns, columns.last_capture)
        && now < before
    {
        report.capture_backward_steps += 1;
    }
    if capture_ns.is_some() {
        columns.last_capture = capture_ns;
    }
    columns.capture.append_option(capture_ns);
    columns.uncertainty.append_option(uncertainty);
    columns.arrival.append_value(arrival_ns);
    if columns
        .last_arrival
        .is_some_and(|before| arrival_ns < before)
    {
        report.arrival_decreases += 1;
    }
    columns.last_arrival = Some(arrival_ns);
    if columns
        .last_sequence
        .is_some_and(|before| record.sequence() <= before)
    {
        report.sequence_nonincreasing += 1;
    }
    columns.last_sequence = Some(record.sequence());
    columns.rx_radio.append_value(record.rx_radio_us());
    columns.tx_enqueue.append_value(record.tx_enqueue_us());
    columns.rx_callback.append_value(record.rx_callback_us());
    columns.rssi.append_value(record.rssi());
    columns.noise.append_value(record.noise_floor());
    for (builder, value) in columns.header.iter_mut().zip(record.fields()) {
        builder.append_value(value);
    }
    columns.sig_len.append_value(record.sig_len());
    columns.first_word.append_value(record.flags() & 1 != 0);
    columns.timely.append_option(timely);
    match &mut columns.payload {
        Payload::Fixed(builder) => {
            if builder.append_value(record.payload()).is_err() {
                debug_assert!(prefer_fixed);
                return Err(Error(VARIABLE_PAYLOAD.to_string()));
            }
        }
        Payload::Variable(builder) => builder.append_value(record.payload()),
    }
    columns.rows += 1;
    Ok(())
}

/// Hash a file's contents as lowercase hexadecimal SHA-256.
pub fn sha256_file(path: &Path) -> Result<String> {
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = vec![0u8; 1 << 20];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

/// Convert a whole session into `frames`, `attempts` and `phases` tables.
///
/// Writes `frames.parquet`, `attempts.parquet`, `phases.parquet` and
/// `conversion.json` (source fingerprint, counts and output hashes) into
/// `out_dir`. Every file is written to a temporary name and renamed.
pub fn convert_session(
    vfs: &dyn Vfs,
    out_dir: &Path,
    options: &ConvertOptions,
) -> Result<ConversionReport> {
    let report = convert_frames(vfs, out_dir, options)?;
    let info = session_info(vfs)?;
    let attempts = crate::annotate::read_attempts(vfs, &info)?;
    let phases = crate::annotate::read_phases(vfs, &info, &attempts)?;
    crate::annotate::write_attempts(&out_dir.join("attempts.parquet"), &attempts)?;
    crate::annotate::write_phases(&out_dir.join("phases.parquet"), &attempts, &phases)?;
    let mut outputs = serde_json::Map::new();
    for name in ["frames.parquet", "attempts.parquet", "phases.parquet"] {
        let path = out_dir.join(name);
        outputs.insert(
            name.to_string(),
            json!({"sha256": sha256_file(&path)?, "bytes": std::fs::metadata(&path)?.len()}),
        );
    }
    let mut document = report.to_json();
    document["attempts"] = json!(attempts.len());
    document["phases"] = json!(phases.len());
    document["outputs"] = Value::Object(outputs);
    let temporary = out_dir.join("conversion.json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&document)?)?;
    File::open(&temporary)?.sync_all()?;
    std::fs::rename(&temporary, out_dir.join("conversion.json"))?;
    Ok(report)
}
