//! Read frames back with row-group pruning and row filtering.
use crate::error::{Error, Result};
use arrow_arith::boolean::and;
use arrow_array::{BooleanArray, Int64Array, RecordBatch, StringArray};
use arrow_ord::cmp::{eq, gt_eq, lt};
use arrow_schema::SchemaRef;
use arrow_select::filter::filter_record_batch;
use parquet::arrow::ProjectionMask;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::file::metadata::RowGroupMetaData;
use parquet::file::statistics::Statistics;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;

/// Filters and projection for [`read_frames`].
#[derive(Debug, Clone, Default)]
pub struct FrameQuery {
    /// Keep only this receiver.
    pub receiver_id: Option<String>,
    /// Keep frames with `capture_time_ns >= start` (frames without capture are dropped).
    pub capture_start_ns: Option<i64>,
    /// Keep frames with `capture_time_ns < end`.
    pub capture_end_ns: Option<i64>,
    /// Columns to return, or all when `None`.
    pub columns: Option<Vec<String>>,
}

fn int64_bounds(group: &RowGroupMetaData, column: usize) -> Option<(i64, i64)> {
    match group.column(column).statistics()? {
        Statistics::Int64(stats) => Some((*stats.min_opt()?, *stats.max_opt()?)),
        _ => None,
    }
}

fn receiver_bounds(group: &RowGroupMetaData, column: usize) -> Option<(Vec<u8>, Vec<u8>)> {
    match group.column(column).statistics()? {
        Statistics::ByteArray(stats) => Some((
            stats.min_opt()?.data().to_vec(),
            stats.max_opt()?.data().to_vec(),
        )),
        _ => None,
    }
}

/// Read frames matching `query`; returns the batches in file order.
///
/// Row groups whose statistics rule out a match are skipped. Because capture
/// time is only nearly monotone, the row filter is always applied as well.
pub fn read_frames(path: &Path, query: &FrameQuery) -> Result<Vec<RecordBatch>> {
    Ok(read_frames_with_schema(path, query)?.1)
}

/// Like [`read_frames`] but also returns the projected schema, which exists
/// even when no row matches.
pub fn read_frames_with_schema(
    path: &Path,
    query: &FrameQuery,
) -> Result<(SchemaRef, Vec<RecordBatch>)> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path)?)?;
    let schema = builder.schema().clone();
    let position = |name: &str| {
        schema
            .index_of(name)
            .map_err(|_| Error(format!("frames table has no column {name}")))
    };
    let capture_column = position("capture_time_ns")?;
    let receiver_column = position("receiver_id")?;
    let selected: Vec<usize> = builder
        .metadata()
        .row_groups()
        .iter()
        .enumerate()
        .filter(|(_, group)| {
            if let Some(id) = &query.receiver_id
                && let Some((low, high)) = receiver_bounds(group, receiver_column)
                && (id.as_bytes() < low.as_slice() || id.as_bytes() > high.as_slice())
            {
                return false;
            }
            if let Some((low, high)) = int64_bounds(group, capture_column) {
                if query.capture_start_ns.is_some_and(|start| high < start) {
                    return false;
                }
                if query.capture_end_ns.is_some_and(|end| low >= end) {
                    return false;
                }
            }
            true
        })
        .map(|(index, _)| index)
        .collect();

    let mut wanted: Vec<usize> = match &query.columns {
        Some(names) => names.iter().map(|n| position(n)).collect::<Result<_>>()?,
        None => (0..schema.fields().len()).collect(),
    };
    let requested = wanted.clone();
    for (needed, column) in [
        (query.receiver_id.is_some(), receiver_column),
        (
            query.capture_start_ns.is_some() || query.capture_end_ns.is_some(),
            capture_column,
        ),
    ] {
        if needed && !wanted.contains(&column) {
            wanted.push(column);
        }
    }
    let mask = ProjectionMask::roots(builder.parquet_schema(), wanted.iter().copied());
    let reader = builder
        .with_row_groups(selected)
        .with_projection(mask)
        .build()?;
    let mut sorted_wanted = wanted.clone();
    sorted_wanted.sort_unstable();
    let local = |column: usize| sorted_wanted.iter().position(|c| *c == column).unwrap();
    let keep: Vec<usize> = requested.iter().map(|c| local(*c)).collect();
    let output_schema: SchemaRef = Arc::new(schema.project(&requested)?);

    let mut out = Vec::new();
    for batch in reader {
        let mut batch = batch?;
        let mut mask: Option<BooleanArray> = None;
        let mut combine = |next: BooleanArray| -> Result<()> {
            mask = Some(match mask.take() {
                Some(previous) => and(&previous, &next)?,
                None => next,
            });
            Ok(())
        };
        if let Some(id) = &query.receiver_id {
            let column = batch.column(local(receiver_column));
            combine(eq(column, &StringArray::new_scalar(id.as_str()))?)?;
        }
        if query.capture_start_ns.is_some() || query.capture_end_ns.is_some() {
            let column = batch.column(local(capture_column));
            if let Some(start) = query.capture_start_ns {
                combine(gt_eq(column, &Int64Array::new_scalar(start))?)?;
            }
            if let Some(end) = query.capture_end_ns {
                combine(lt(column, &Int64Array::new_scalar(end))?)?;
            }
        }
        if let Some(mask) = mask {
            batch = filter_record_batch(&batch, &mask)?;
        }
        if batch.num_rows() > 0 {
            out.push(batch.project(&keep)?);
        }
    }
    Ok((output_schema, out))
}

/// Total rows and row-group count, for quick inspection.
pub fn frame_counts(path: &Path) -> Result<(i64, usize)> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path)?)?;
    let meta = builder.metadata();
    Ok((meta.file_metadata().num_rows(), meta.num_row_groups()))
}
