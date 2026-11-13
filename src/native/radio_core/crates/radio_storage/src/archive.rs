//! Version-3 session archives and migration from older archives.
//!
//! A version-3 archive keeps the lossless raw record of a session and drops
//! what can be derived from it: the per-receiver CSV sidecars and the
//! string-typed `tables/` copies. Journals and event logs are re-encoded as
//! stored Zstandard frames in members named `<path>.zst`, the convention
//! shared with the collector's compressed streams. Every member's logical
//! content is hashed in `manifest.json`.
use crate::convert::{ConvertOptions, FrameScope, convert_session};
use crate::error::{Error, Result};
use crate::vfs;
use arrow_array::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufReader, Read, Write};
use std::path::Path;
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, ZipArchive, ZipWriter};

/// Format name and version recorded in the archive manifest.
pub const ARCHIVE_FORMAT: &str = "fall-detection-session-archive";
/// Archive layout written by this module.
pub const ARCHIVE_VERSION: u32 = 3;

/// Parameters of a migration.
#[derive(Debug, Clone, Copy)]
pub struct MigrateOptions {
    /// Zstandard level for journals and event logs.
    pub zstd_level: i32,
}

impl Default for MigrateOptions {
    fn default() -> Self {
        Self { zstd_level: 9 }
    }
}

/// Outcome of a migration.
#[derive(Debug, Clone)]
pub struct MigrationReport {
    pub session_id: String,
    pub source_bytes: u64,
    pub destination_bytes: u64,
    pub kept_members: usize,
    /// Dropped member count by file name (`csi.csv`, `csi.parquet`, ...).
    pub dropped: BTreeMap<String, usize>,
    pub dropped_logical_bytes: u64,
    /// Differences between tables converted from the source and the result.
    pub table_differences: Vec<String>,
}

impl MigrationReport {
    /// Render as JSON.
    pub fn to_json(&self) -> Value {
        json!({
            "session_id": self.session_id,
            "source_bytes": self.source_bytes,
            "destination_bytes": self.destination_bytes,
            "kept_members": self.kept_members,
            "dropped": self.dropped,
            "dropped_logical_bytes": self.dropped_logical_bytes,
            "table_differences": self.table_differences,
        })
    }
}

/// True for members that the raw journal and events fully determine.
fn derived_member(name: &str) -> bool {
    if name.starts_with("tables/") {
        return true;
    }
    let logical = name.strip_suffix(".zst").unwrap_or(name);
    let mut parts = logical.rsplit('/');
    let file = parts.next().unwrap_or_default();
    let parent_is_receiver = parts.nth(1).is_some_and(|dir| dir == "receivers");
    parent_is_receiver
        && matches!(
            file,
            "csi.csv" | "radio_timing.csv" | "usb_clock_sync.csv" | "gateway_timing.jsonl"
        )
}

/// True for large text-or-binary logs that benefit from Zstandard.
fn recompress_member(name: &str) -> bool {
    let logical = name.strip_suffix(".zst").unwrap_or(name);
    logical.contains("/transport/gateway/")
        && (logical.ends_with("/envelopes.bin")
            || logical.ends_with("/events.jsonl")
            || logical.ends_with("/availability.jsonl"))
}

/// Counts the bytes that reach an inner writer.
struct CountingSink<'a, W: Write> {
    inner: &'a mut W,
    bytes: u64,
}

impl<W: Write> Write for CountingSink<'_, W> {
    fn write(&mut self, data: &[u8]) -> std::io::Result<usize> {
        let n = self.inner.write(data)?;
        self.bytes += n as u64;
        Ok(n)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        self.inner.flush()
    }
}

fn copy_hashed(reader: &mut dyn Read, hash: &mut Sha256) -> Result<u64> {
    let mut buffer = vec![0u8; 1 << 20];
    let mut total = 0u64;
    loop {
        let n = reader.read(&mut buffer)?;
        if n == 0 {
            return Ok(total);
        }
        hash.update(&buffer[..n]);
        total += n as u64;
    }
}

/// Read a member's decoded content, undoing a `.zst` suffix.
fn decoded<'a>(
    archive: &'a mut ZipArchive<BufReader<File>>,
    index: usize,
    compressed: bool,
) -> Result<Box<dyn Read + 'a>> {
    let member = archive.by_index(index)?;
    if compressed {
        Ok(Box::new(zstd::stream::read::Decoder::new(member)?))
    } else {
        Ok(Box::new(member))
    }
}

/// Parameters of writing an archive.
#[derive(Debug, Clone, Copy)]
pub struct ArchiveOptions {
    /// Zstandard level for journals, event logs and receiver sidecars.
    pub zstd_level: i32,
    /// Leave out the per-receiver CSV, timing and `tables/` members, which the
    /// raw journal fully determines. Keep them until the journal conversion of
    /// that kind of session is validated against real data.
    pub drop_derived: bool,
}

impl Default for ArchiveOptions {
    fn default() -> Self {
        Self {
            zstd_level: 9,
            drop_derived: false,
        }
    }
}

/// True for per-receiver sidecars that benefit from Zstandard when kept.
fn recompress_sidecar(logical: &str) -> bool {
    logical.contains("/receivers/") && (logical.ends_with(".csv") || logical.ends_with(".jsonl"))
}

/// Compression of a stored member that is not re-encoded: already-compressed
/// media stay stored, text is deflated.
fn method_by_extension(name: &str) -> CompressionMethod {
    const STORED: [&str; 6] = [".mp4", ".zst", ".zip", ".png", ".jpg", ".mkv"];
    if STORED.iter().any(|extension| name.ends_with(extension)) {
        CompressionMethod::Stored
    } else {
        CompressionMethod::Deflated
    }
}

/// Write one logical member into `writer`; returns its manifest entry.
fn write_member(
    source: &dyn vfs::Vfs,
    logical: &str,
    target: &str,
    recompress: bool,
    method: CompressionMethod,
    level: i32,
    writer: &mut ZipWriter<File>,
) -> Result<Value> {
    let stored = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Stored)
        .large_file(true);
    let mut hash = Sha256::new();
    let mut logical_bytes = 0u64;
    let mut stored_bytes = 0u64;
    let name = if recompress {
        format!("{target}.zst")
    } else {
        target.to_string()
    };
    if recompress {
        writer.start_file(&name, stored)?;
    } else {
        writer.start_file(
            &name,
            SimpleFileOptions::default()
                .compression_method(method)
                .large_file(true),
        )?;
    }
    source.read(logical, &mut |reader| {
        let mut buffer = vec![0u8; 1 << 20];
        if recompress {
            let mut sink = CountingSink {
                inner: &mut *writer,
                bytes: 0,
            };
            // Hash the logical content, not the encoded bytes.
            let mut encoder = zstd::stream::write::Encoder::new(&mut sink, level)?;
            loop {
                let n = reader.read(&mut buffer)?;
                if n == 0 {
                    break;
                }
                hash.update(&buffer[..n]);
                encoder.write_all(&buffer[..n])?;
                logical_bytes += n as u64;
            }
            encoder.finish()?;
            stored_bytes = sink.bytes;
        } else {
            // Rewrite with explicit ZIP64 headers; raw-copying produced archives
            // whose members beyond 4 GiB the zip crate could not read back.
            loop {
                let n = reader.read(&mut buffer)?;
                if n == 0 {
                    break;
                }
                hash.update(&buffer[..n]);
                writer.write_all(&buffer[..n])?;
                logical_bytes += n as u64;
            }
        }
        Ok(())
    })?;
    let digest = format!("{:x}", hash.finalize());
    Ok(if recompress {
        json!({
            "name": name, "logical": target, "encoding": "zstd",
            "bytes": stored_bytes, "logical_bytes": logical_bytes, "sha256": digest,
        })
    } else {
        json!({
            "name": name, "logical": target, "encoding": "plain",
            "logical_bytes": logical_bytes, "sha256": digest,
        })
    })
}

/// Write `destination` from a session directory or archive, then prove the
/// tables unchanged.
///
/// The destination is written to a temporary name and renamed only after the
/// tables converted from it equal those converted from the source. Sessions
/// without journals have no tables and skip that check. The source is never
/// modified.
pub fn write_archive(
    source: &Path,
    destination: &Path,
    options: &ArchiveOptions,
) -> Result<MigrationReport> {
    if destination.exists() {
        return Err(Error(format!(
            "refusing to overwrite {}",
            destination.display()
        )));
    }
    let source_vfs = vfs::open(source)?;
    let source_fingerprint = source_vfs.fingerprint()?;
    let info = crate::source::session_info(source_vfs.as_ref())?;
    // Directory sessions are wrapped in `original/`; archives already are.
    let wrap = if crate::vfs::session_prefix(source_vfs.as_ref()).is_empty() {
        "original/"
    } else {
        ""
    };
    // Members keep the compression they had in an archive source.
    let source_methods: BTreeMap<String, CompressionMethod> = if source.is_file() {
        let mut archive = ZipArchive::new(BufReader::new(File::open(source)?))?;
        let mut methods = BTreeMap::new();
        for index in 0..archive.len() {
            let member = archive.by_index_raw(index)?;
            if let Ok(name) = member.name() {
                let logical = name.strip_suffix(".zst").unwrap_or(&name).to_string();
                methods.insert(logical, member.compression());
            }
        }
        methods
    } else {
        BTreeMap::new()
    };

    let temporary = destination.with_extension("zip.tmp");
    if let Some(parent) = temporary.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut writer = ZipWriter::new(File::create(&temporary)?);
    let mut members = Vec::new();
    let mut dropped: BTreeMap<String, usize> = BTreeMap::new();
    let mut dropped_bytes = 0u64;
    let mut journals = false;
    for logical in source_vfs.files() {
        if logical == "manifest.json" {
            continue; // the old manifest is replaced by the version-3 manifest
        }
        journals |= logical.ends_with("/envelopes.bin") || logical == "envelopes.bin";
        if options.drop_derived && derived_member(logical) {
            let file = logical.rsplit('/').next().unwrap_or(logical).to_string();
            *dropped.entry(file).or_default() += 1;
            dropped_bytes += source_vfs.physical_size(logical)?;
            continue;
        }
        let target = format!("{wrap}{logical}");
        let recompress = recompress_member(&target) || recompress_sidecar(&target);
        let method = source_methods
            .get(logical)
            .copied()
            .map(|method| match method {
                CompressionMethod::Stored => CompressionMethod::Stored,
                _ => CompressionMethod::Deflated,
            })
            .unwrap_or_else(|| method_by_extension(&target));
        members.push(write_member(
            source_vfs.as_ref(),
            logical,
            &target,
            recompress,
            method,
            options.zstd_level,
            &mut writer,
        )?);
    }
    let manifest = json!({
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "session_id": info.session_id,
        "converter_version": crate::convert::CONVERTER_VERSION,
        "source": {"fingerprint": source_fingerprint},
        "dropped": dropped,
        "members": members,
    });
    writer.start_file(
        "manifest.json",
        SimpleFileOptions::default().compression_method(CompressionMethod::Deflated),
    )?;
    writer.write_all(&serde_json::to_vec_pretty(&manifest)?)?;
    writer.finish()?.sync_all()?;
    drop(source_vfs);

    // Gate: tables derived from the new archive must equal those from the source.
    let differences = if journals {
        let scratch = destination.with_extension("migrate-check");
        let _ = std::fs::remove_dir_all(&scratch);
        let outcome = (|| -> Result<Vec<String>> {
            let convert = ConvertOptions {
                scope: FrameScope::Attempts,
                ..ConvertOptions::default()
            };
            let from_source = scratch.join("source");
            let from_result = scratch.join("result");
            convert_session(vfs::open(source)?.as_ref(), &from_source, &convert)?;
            convert_session(vfs::open(&temporary)?.as_ref(), &from_result, &convert)?;
            tables_differences(&from_source, &from_result)
        })();
        let _ = std::fs::remove_dir_all(&scratch);
        outcome?
    } else {
        Vec::new()
    };
    if !differences.is_empty() {
        let _ = std::fs::remove_file(&temporary);
        return Err(Error(format!(
            "archive changes the derived tables: {}",
            differences.join("; ")
        )));
    }
    std::fs::rename(&temporary, destination)?;
    Ok(MigrationReport {
        session_id: info.session_id,
        source_bytes: source_size(source)?,
        destination_bytes: std::fs::metadata(destination)?.len(),
        kept_members: members.len(),
        dropped,
        dropped_logical_bytes: dropped_bytes,
        table_differences: differences,
    })
}

fn source_size(source: &Path) -> Result<u64> {
    if source.is_file() {
        return Ok(std::fs::metadata(source)?.len());
    }
    let mut total = 0u64;
    let mut stack = vec![source.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                stack.push(entry.path());
            } else {
                total += entry.metadata()?.len();
            }
        }
    }
    Ok(total)
}

/// Write a version-3 archive from an older archive and prove the tables
/// unchanged. The per-receiver sidecars and `tables/` copies are dropped.
pub fn migrate_archive(
    source: &Path,
    destination: &Path,
    options: &MigrateOptions,
) -> Result<MigrationReport> {
    write_archive(
        source,
        destination,
        &ArchiveOptions {
            zstd_level: options.zstd_level,
            drop_derived: true,
        },
    )
}

/// Verify a version-3 archive and write its members as a session directory.
///
/// Members keep their stored form, so Zstandard logs stay `<name>.zst`; every
/// reader in this crate decodes them. `destination` must not exist, and is only
/// created once every member has been written. Returns the member count.
pub fn extract_archive(archive: &Path, destination: &Path) -> Result<usize> {
    if destination.exists() {
        return Err(Error(format!(
            "refusing to overwrite {}",
            destination.display()
        )));
    }
    let problems = verify_archive(archive)?;
    if !problems.is_empty() {
        return Err(Error(format!(
            "archive failed verification: {}",
            problems.join("; ")
        )));
    }
    let manifest = archive_manifest(archive)?;
    let mut zip = ZipArchive::new(BufReader::with_capacity(1 << 20, File::open(archive)?))?;
    let partial = destination.with_extension("extracting");
    let _ = std::fs::remove_dir_all(&partial);
    let result = (|| -> Result<usize> {
        let mut count = 0;
        for member in manifest["members"].as_array().into_iter().flatten() {
            let name = member["name"].as_str().unwrap_or_default();
            let Some(relative) = name.strip_prefix("original/") else {
                continue;
            };
            if relative.is_empty()
                || relative.starts_with('/')
                || relative
                    .split('/')
                    .any(|part| part == ".." || part.is_empty())
            {
                return Err(Error(format!("unsafe member name {name:?}")));
            }
            let target = partial.join(relative);
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let mut entry = zip.by_name(name)?;
            let mut out = File::create(&target)?;
            std::io::copy(&mut entry, &mut out)?;
            count += 1;
        }
        Ok(count)
    })();
    match result {
        Ok(count) => {
            std::fs::rename(&partial, destination)?;
            Ok(count)
        }
        Err(error) => {
            let _ = std::fs::remove_dir_all(&partial);
            Err(error)
        }
    }
}

/// Read the version-3 manifest of an archive.
pub fn archive_manifest(path: &Path) -> Result<Value> {
    let mut archive = ZipArchive::new(BufReader::new(File::open(path)?))?;
    let mut text = String::new();
    archive
        .by_name("manifest.json")
        .map_err(|_| Error("archive has no manifest.json".into()))?
        .read_to_string(&mut text)?;
    Ok(serde_json::from_str(&text)?)
}

/// Check every member of a version-3 archive against its manifest.
///
/// Returns the problems found; an empty list means the archive is intact.
pub fn verify_archive(path: &Path) -> Result<Vec<String>> {
    let manifest = archive_manifest(path)?;
    let mut problems = Vec::new();
    if manifest["format"] != ARCHIVE_FORMAT || manifest["version"] != ARCHIVE_VERSION {
        problems.push("manifest is not a version-3 session archive".into());
        return Ok(problems);
    }
    let mut archive = ZipArchive::new(BufReader::with_capacity(1 << 20, File::open(path)?))?;
    let mut by_name: BTreeMap<String, usize> = BTreeMap::new();
    for index in 0..archive.len() {
        let member = archive.by_index_raw(index)?;
        if !member.is_dir() {
            by_name.insert(member.name()?.to_string(), index);
        }
    }
    let listed = manifest["members"].as_array().cloned().unwrap_or_default();
    for entry in &listed {
        let name = entry["name"].as_str().unwrap_or_default();
        let Some(&index) = by_name.get(name) else {
            problems.push(format!("{name}: missing from archive"));
            continue;
        };
        let compressed = name.ends_with(".zst");
        let mut hash = Sha256::new();
        let logical_bytes = copy_hashed(
            decoded(&mut archive, index, compressed)?.as_mut(),
            &mut hash,
        )?;
        if format!("{:x}", hash.finalize()) != entry["sha256"].as_str().unwrap_or_default()
            || Some(logical_bytes) != entry["logical_bytes"].as_u64()
        {
            problems.push(format!("{name}: content differs from manifest"));
        }
    }
    for name in by_name.keys() {
        if name != "manifest.json" && !listed.iter().any(|e| e["name"] == name.as_str()) {
            problems.push(format!("{name}: not listed in manifest"));
        }
    }
    Ok(problems)
}

/// Compare the logical content of two converted directories.
///
/// Parquet metadata (source fingerprints) is ignored; rows and values are
/// compared. Returns human-readable differences.
pub fn tables_differences(left: &Path, right: &Path) -> Result<Vec<String>> {
    let mut differences = Vec::new();
    for name in ["frames.parquet", "attempts.parquet", "phases.parquet"] {
        let open = |dir: &Path| {
            ParquetRecordBatchReaderBuilder::try_new(File::open(dir.join(name))?)
                .map(|b| b.with_batch_size(65_536))
                .map_err(Error::from)
        };
        let mut a = open(left)?.build()?;
        let mut b = open(right)?.build()?;
        let mut position = 0usize;
        loop {
            let (x, y): (Option<RecordBatch>, Option<RecordBatch>) =
                (a.next().transpose()?, b.next().transpose()?);
            match (x, y) {
                (None, None) => break,
                (Some(x), Some(y)) => {
                    if x != y {
                        differences.push(format!("{name}: rows differ near {position}"));
                        break;
                    }
                    position += x.num_rows();
                }
                _ => {
                    differences.push(format!("{name}: row counts differ"));
                    break;
                }
            }
        }
    }
    Ok(differences)
}
