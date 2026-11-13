//! Read-only access to a session stored as a directory or a ZIP archive.
//!
//! Paths are logical: relative to the session root, with `/` separators and
//! with a trailing `.zst` removed. Zstandard members are decoded transparently.
use crate::error::{Error, Result};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Read-only logical file system over one session.
pub trait Vfs: Send + Sync {
    /// Every logical file path, sorted.
    fn files(&self) -> &[String];
    /// Run `visit` on a decoded reader for `path`.
    fn read(&self, path: &str, visit: &mut dyn FnMut(&mut dyn Read) -> Result<()>) -> Result<()>;
    /// Cheap content identity of the whole source, stable across runs.
    fn fingerprint(&self) -> Result<String>;
    /// Size in bytes of the stored member or file behind `path`, before any
    /// Zstandard decoding.
    fn physical_size(&self, path: &str) -> Result<u64>;
    /// True when `path` exists.
    fn exists(&self, path: &str) -> bool {
        self.files()
            .binary_search_by(|f| f.as_str().cmp(path))
            .is_ok()
    }
    /// Read a whole file into memory.
    fn read_all(&self, path: &str) -> Result<Vec<u8>> {
        let mut out = Vec::new();
        self.read(path, &mut |reader| {
            reader.read_to_end(&mut out)?;
            Ok(())
        })?;
        Ok(out)
    }
}

fn logical(name: &str) -> (&str, bool) {
    match name.strip_suffix(".zst") {
        Some(stripped) => (stripped, true),
        None => (name, false),
    }
}

/// Open `path` as a session directory or a ZIP archive.
pub fn open(path: &Path) -> Result<Box<dyn Vfs>> {
    if path.is_dir() {
        Ok(Box::new(DirVfs::new(path)?))
    } else if path.is_file() {
        Ok(Box::new(ZipVfs::new(path)?))
    } else {
        Err(Error(format!("no such session: {}", path.display())))
    }
}

/// Session stored as a plain directory.
pub struct DirVfs {
    root: PathBuf,
    files: Vec<String>,
    actual: HashMap<String, (PathBuf, bool)>,
}

impl DirVfs {
    fn new(root: &Path) -> Result<Self> {
        let mut found = Vec::new();
        walk(root, root, &mut found)?;
        let mut actual = HashMap::new();
        for (relative, path) in found {
            let (name, compressed) = logical(&relative);
            actual.insert(name.to_string(), (path, compressed));
        }
        let mut files: Vec<String> = actual.keys().cloned().collect();
        files.sort();
        Ok(Self {
            root: root.to_path_buf(),
            files,
            actual,
        })
    }
}

fn walk(base: &Path, dir: &Path, out: &mut Vec<(String, PathBuf)>) -> Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if entry.file_type()?.is_dir() {
            walk(base, &path, out)?;
        } else {
            let relative = path
                .strip_prefix(base)
                .map_err(|e| Error(e.to_string()))?
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            out.push((relative, path));
        }
    }
    Ok(())
}

impl Vfs for DirVfs {
    fn files(&self) -> &[String] {
        &self.files
    }

    fn read(&self, path: &str, visit: &mut dyn FnMut(&mut dyn Read) -> Result<()>) -> Result<()> {
        let (actual, compressed) = self
            .actual
            .get(path)
            .ok_or_else(|| Error(format!("missing file {path} in {}", self.root.display())))?;
        let file = BufReader::with_capacity(1 << 20, File::open(actual)?);
        if *compressed {
            visit(&mut zstd::stream::read::Decoder::new(file)?)
        } else {
            let mut file = file;
            visit(&mut file)
        }
    }

    fn physical_size(&self, path: &str) -> Result<u64> {
        let (actual, _) = self
            .actual
            .get(path)
            .ok_or_else(|| Error(format!("missing file {path} in {}", self.root.display())))?;
        Ok(std::fs::metadata(actual)?.len())
    }

    fn fingerprint(&self) -> Result<String> {
        // Only inputs the converter reads: a mutable review overlay or a video
        // file must not invalidate the derived tables.
        let mut hash = Sha256::new();
        hash.update(b"dir\n");
        for name in &self.files {
            let relevant = name == "session.json"
                || name == "events.jsonl"
                || name.ends_with("/attempt.json")
                || name.starts_with("transport/");
            if !relevant {
                continue;
            }
            let (path, _) = &self.actual[name];
            let size = std::fs::metadata(path)?.len();
            hash.update(format!("{name}\t{size}\n"));
            if size <= 1 << 20 && !name.ends_with("envelopes.bin") {
                hash.update(std::fs::read(path)?);
            }
        }
        Ok(format!("{:x}", hash.finalize()))
    }
}

/// Session stored as a ZIP archive.
pub struct ZipVfs {
    archive: Mutex<zip::ZipArchive<BufReader<File>>>,
    files: Vec<String>,
    members: HashMap<String, (usize, bool)>,
    fingerprint: String,
}

impl ZipVfs {
    fn new(path: &Path) -> Result<Self> {
        let mut archive =
            zip::ZipArchive::new(BufReader::with_capacity(1 << 20, File::open(path)?))?;
        let mut members = HashMap::new();
        let mut hash = Sha256::new();
        hash.update(b"zip\n");
        let mut listing = Vec::new();
        for index in 0..archive.len() {
            let member = archive.by_index_raw(index)?;
            if member.is_dir() {
                continue;
            }
            let name = member.name()?.to_string();
            listing.push(format!("{name}\t{}\t{:08x}", member.size(), member.crc32()));
            let (logical_name, compressed) = logical(&name);
            members.insert(logical_name.to_string(), (index, compressed));
        }
        listing.sort();
        for line in &listing {
            hash.update(line);
            hash.update(b"\n");
        }
        let mut files: Vec<String> = members.keys().cloned().collect();
        files.sort();
        Ok(Self {
            archive: Mutex::new(archive),
            files,
            members,
            fingerprint: format!("{:x}", hash.finalize()),
        })
    }
}

impl Vfs for ZipVfs {
    fn files(&self) -> &[String] {
        &self.files
    }

    fn read(&self, path: &str, visit: &mut dyn FnMut(&mut dyn Read) -> Result<()>) -> Result<()> {
        let (index, compressed) = *self
            .members
            .get(path)
            .ok_or_else(|| Error(format!("missing member {path}")))?;
        let mut archive = self
            .archive
            .lock()
            .map_err(|_| Error("archive lock poisoned".into()))?;
        let member = archive.by_index(index)?;
        if compressed {
            visit(&mut zstd::stream::read::Decoder::new(member)?)
        } else {
            let mut member = member;
            visit(&mut member)
        }
    }

    fn physical_size(&self, path: &str) -> Result<u64> {
        let (index, _) = *self
            .members
            .get(path)
            .ok_or_else(|| Error(format!("missing member {path}")))?;
        let mut archive = self
            .archive
            .lock()
            .map_err(|_| Error("archive lock poisoned".into()))?;
        Ok(archive.by_index_raw(index)?.size())
    }

    fn fingerprint(&self) -> Result<String> {
        Ok(self.fingerprint.clone())
    }
}

/// Logical session root inside a source: archives wrap the session in `original/`.
pub fn session_prefix(vfs: &dyn Vfs) -> &'static str {
    if vfs.exists("original/session.json") {
        "original/"
    } else {
        ""
    }
}

/// Read a recording file as logical bytes, independent of disk compression.
///
/// `path` may name the plain file or the logical name of a `<path>.zst`
/// sibling. Concatenated independent Zstandard frames are decoded in order. A
/// truncated final frame is an error, so a crash mid-write is never mistaken
/// for a complete recording.
pub fn read_file(path: &Path) -> Result<Vec<u8>> {
    let (actual, compressed) = if path.exists() {
        let compressed = path.extension().is_some_and(|ext| ext == "zst");
        (path.to_path_buf(), compressed)
    } else {
        let mut name = path.as_os_str().to_os_string();
        name.push(".zst");
        (PathBuf::from(name), true)
    };
    let file = File::open(&actual)
        .map_err(|error| Error(format!("cannot read {}: {error}", actual.display())))?;
    let mut out = Vec::new();
    if compressed {
        zstd::stream::read::Decoder::new(BufReader::new(file))?
            .read_to_end(&mut out)
            .map_err(|error| Error(format!("{}: {error}", actual.display())))?;
    } else {
        BufReader::new(file).read_to_end(&mut out)?;
    }
    Ok(out)
}
