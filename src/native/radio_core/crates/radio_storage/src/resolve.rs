//! Resolve a session's immutable recording together with its review.
//!
//! Layout under the repository root:
//!
//! ```text
//! data/raw/sessions/<id>.zip                      current archive (or a session directory)
//! data/old_raw/sessions/<id>.zip                  predecessor; checked when present
//! data/annotations/<id>/session_review.json       the mutable review
//! ```
//!
//! The review is looked up in `data/annotations` first and, for sessions that
//! carry their own, inside the source. Whichever is used is reported as the
//! review's origin.
use crate::annotate::read_attempts;
use crate::archive::archive_manifest;
use crate::error::{Error, Result};
use crate::review::{EffectiveAttempt, Review, attempt_key, effective_attempts};
use crate::source::session_info;
use crate::vfs::{self, Vfs};
use std::path::{Path, PathBuf};

/// Directory of reviews, relative to the repository root.
pub const ANNOTATIONS_DIR: &str = "data/annotations";
/// Review file name.
pub const REVIEW_FILE: &str = "session_review.json";

/// Where the review that was applied came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReviewOrigin {
    /// `data/annotations/<id>/session_review.json`.
    Annotations,
    /// A `session_review.json` stored inside the session directory or archive.
    Embedded,
}

impl ReviewOrigin {
    /// Stable name used in reports.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Annotations => "annotations",
            Self::Embedded => "embedded",
        }
    }
}

/// A review together with where it was found.
#[derive(Debug, Clone)]
pub struct OpenedReview {
    pub origin: ReviewOrigin,
    /// File path; `None` for a review read from inside an archive.
    pub path: Option<PathBuf>,
    pub review: Review,
}

/// An immutable recording with its review applied.
#[derive(Debug, Clone)]
pub struct OpenedSession {
    pub session_id: String,
    pub protocol_hash: String,
    pub source: PathBuf,
    /// Version of the archive manifest; `None` for a directory.
    pub archive_version: Option<u64>,
    /// Identity of the recording itself; reviews do not change it.
    pub source_fingerprint: String,
    pub review: Option<OpenedReview>,
    pub attempts: Vec<EffectiveAttempt>,
}

/// The annotations directory implied by a source's location.
///
/// A source in `<root>/data/raw/sessions` uses `<root>/data/annotations`; any
/// other source has no implied location and relies on a review stored inside
/// it.
pub fn annotations_dir_for(source: &Path) -> Option<PathBuf> {
    let source = source.canonicalize().ok()?;
    let sessions = source.parent()?;
    let raw = sessions.parent()?;
    if sessions.file_name()? == "sessions" && raw.file_name()? == "raw" {
        Some(raw.parent()?.join("annotations"))
    } else {
        None
    }
}

/// True for a single path component that cannot escape its directory.
pub fn valid_session_id(session_id: &str) -> bool {
    !session_id.is_empty()
        && session_id != "."
        && session_id != ".."
        && !session_id.contains(['/', '\\', '\0'])
}

fn checked_id(session_id: &str) -> Result<&str> {
    if valid_session_id(session_id) {
        Ok(session_id)
    } else {
        Err(Error("invalid session identifier".into()))
    }
}

/// Path of a session's review under `root`.
pub fn annotation_path(root: &Path, session_id: &str) -> Result<PathBuf> {
    Ok(root
        .join(ANNOTATIONS_DIR)
        .join(checked_id(session_id)?)
        .join(REVIEW_FILE))
}

/// Path of the current source of a session under `root`: the archive, or a
/// session directory with the same name.
pub fn source_path(root: &Path, session_id: &str) -> Result<PathBuf> {
    let base = root.join("data/raw/sessions");
    let archive = base.join(format!("{}.zip", checked_id(session_id)?));
    if archive.is_file() {
        return Ok(archive);
    }
    let directory = base.join(session_id);
    if directory.is_dir() {
        return Ok(directory);
    }
    Err(Error(format!(
        "no session {session_id:?} in {}",
        base.display()
    )))
}

fn archive_version(source: &Path) -> Option<u64> {
    if source.is_file() {
        archive_manifest(source).ok()?["version"].as_u64()
    } else {
        None
    }
}

fn load_review(
    source: &dyn Vfs,
    prefix: &str,
    session_id: &str,
    annotations_dir: Option<&Path>,
) -> Result<Option<OpenedReview>> {
    let annotated = match annotations_dir {
        Some(dir) => Some(dir.join(checked_id(session_id)?).join(REVIEW_FILE)),
        None => None,
    };
    if let Some(path) = annotated.filter(|path| path.is_file()) {
        let review = Review::parse(&std::fs::read(&path)?)
            .map_err(|error| Error(format!("{}: {error}", path.display())))?;
        return Ok(Some(OpenedReview {
            origin: ReviewOrigin::Annotations,
            path: Some(path),
            review,
        }));
    }
    let embedded = format!("{prefix}{REVIEW_FILE}");
    if source.exists(&embedded) {
        let review = Review::parse(&source.read_all(&embedded)?)
            .map_err(|error| Error(format!("embedded {REVIEW_FILE}: {error}")))?;
        return Ok(Some(OpenedReview {
            origin: ReviewOrigin::Embedded,
            path: None,
            review,
        }));
    }
    Ok(None)
}

/// Open a session directory or archive and apply its review.
///
/// Args:
///     source: Session directory or archive.
///     annotations_dir: Directory of reviews, one folder per session id; a
///         review found there is preferred over one inside the source.
///
/// A review that belongs to another session or names an unknown attempt is an
/// error rather than being ignored.
pub fn open_source(source: &Path, annotations_dir: Option<&Path>) -> Result<OpenedSession> {
    let archive_version = archive_version(source);
    let vfs = vfs::open(source)?;
    let info = session_info(vfs.as_ref())?;
    let session_id = if info.session_id.is_empty() {
        source
            .file_stem()
            .map(|stem| stem.to_string_lossy().into_owned())
            .unwrap_or_default()
    } else {
        info.session_id.clone()
    };
    let attempts = read_attempts(vfs.as_ref(), &info)?;
    let keys: Vec<String> = attempts
        .iter()
        .map(|attempt| attempt_key(attempt, info.prefix))
        .collect();
    let review = load_review(vfs.as_ref(), info.prefix, &session_id, annotations_dir)?;
    if let Some(opened) = &review {
        opened
            .review
            .validate_for(&session_id, &info.protocol_hash, &keys)
            .map_err(|error| Error(format!("{} review: {error}", opened.origin.as_str())))?;
    }
    Ok(OpenedSession {
        attempts: effective_attempts(&attempts, info.prefix, review.as_ref().map(|r| &r.review)),
        source_fingerprint: vfs.fingerprint()?,
        protocol_hash: info.protocol_hash,
        source: source.to_path_buf(),
        archive_version,
        session_id,
        review,
    })
}

/// Locate and check the source of `session_id` under the repository `root`,
/// without reading its review.
///
/// Returns the path and the archive manifest version (`None` for a directory).
/// A version-3 archive must belong to the session and, when its predecessor is
/// present in `data/old_raw`, record that predecessor's fingerprint.
pub fn resolve_source(root: &Path, session_id: &str) -> Result<(PathBuf, Option<u64>)> {
    let source = source_path(root, session_id)?;
    let version = archive_version(&source);
    if version == Some(3) {
        let manifest = archive_manifest(&source)?;
        if manifest["session_id"].as_str() != Some(session_id) {
            return Err(Error("version-3 session identity differs".into()));
        }
        let predecessor = root
            .join("data/old_raw/sessions")
            .join(format!("{session_id}.zip"));
        if predecessor.is_file() {
            let recorded = manifest["source"]["fingerprint"].as_str().unwrap_or("");
            if recorded != vfs::open(&predecessor)?.fingerprint()? {
                return Err(Error("version-3 session source differs".into()));
            }
        }
    }
    Ok((source, version))
}

/// Open the session `session_id` under the repository `root`.
///
/// Uses `data/raw/sessions/<id>` as the source (checked by [`resolve_source`])
/// and `data/annotations/<id>` for the review.
pub fn open_session(root: &Path, session_id: &str) -> Result<OpenedSession> {
    let (source, _) = resolve_source(root, session_id)?;
    open_source(&source, Some(&root.join(ANNOTATIONS_DIR)))
}
