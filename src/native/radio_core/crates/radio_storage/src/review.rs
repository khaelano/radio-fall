//! Review overlays: human corrections kept apart from the immutable recording.
//!
//! A review (`session_review.json`) never changes the journal or `attempt.json`.
//! It is joined to the recorded attempts at read time, so one implementation
//! decides every consumer's effective label, inclusion and quality.
use crate::annotate::Attempt;
use crate::error::{Error, Result};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

/// The only review schema version this library reads.
pub const REVIEW_SCHEMA_VERSION: u64 = 1;
/// Allowed `inclusion` values.
pub const INCLUSION_VALUES: [&str; 3] = ["unreviewed", "include", "exclude"];
/// Allowed `quality` values.
pub const QUALITY_VALUES: [&str; 4] = ["unreviewed", "good", "questionable", "bad"];
/// Metadata fields a review may override.
pub const METADATA_FIELDS: [&str; 4] = ["participant_id", "operator", "location", "notes"];

const DOCUMENT_FIELDS: [&str; 8] = [
    "schema_version",
    "session_id",
    "protocol_hash",
    "revision",
    "updated_at_utc",
    "metadata",
    "attempts",
    "history",
];
const ATTEMPT_FIELDS: [&str; 4] = ["activity_label", "inclusion", "quality", "notes"];

/// The curated fields of one attempt.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AttemptReview {
    /// Corrected label; `None` keeps the acquisition label.
    pub activity_label: Option<String>,
    pub inclusion: String,
    pub quality: String,
    pub notes: String,
}

impl Default for AttemptReview {
    fn default() -> Self {
        Self {
            activity_label: None,
            inclusion: "unreviewed".into(),
            quality: "unreviewed".into(),
            notes: String::new(),
        }
    }
}

/// A validated review document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Review {
    pub session_id: String,
    pub protocol_hash: String,
    pub revision: u64,
    pub updated_at_utc: Option<String>,
    pub metadata: BTreeMap<String, String>,
    /// Keyed by the attempt's relative directory, for example
    /// `trials/001_walk/attempt_01`.
    pub attempts: BTreeMap<String, AttemptReview>,
    /// SHA-256 of the file's bytes; changes whenever the file does.
    pub content_sha256: String,
}

fn fail<T>(message: impl Into<String>) -> Result<T> {
    Err(Error(message.into()))
}

fn object<'a>(value: &'a Value, what: &str) -> Result<&'a Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| Error(format!("{what} must be an object")))
}

fn reject_unknown(map: &Map<String, Value>, allowed: &[&str], what: &str) -> Result<()> {
    let mut unknown: Vec<&str> = map
        .keys()
        .map(String::as_str)
        .filter(|key| !allowed.contains(key))
        .collect();
    unknown.sort_unstable();
    if unknown.is_empty() {
        Ok(())
    } else {
        fail(format!("{what}: unknown field(s): {}", unknown.join(", ")))
    }
}

fn parse_attempt(key: &str, value: &Value) -> Result<AttemptReview> {
    let what = format!("review.attempts[{key:?}]");
    let map = value
        .as_object()
        .ok_or_else(|| Error("review.attempts must map paths to objects".into()))?;
    reject_unknown(map, &ATTEMPT_FIELDS, &what)?;
    let activity_label = match map.get("activity_label") {
        None | Some(Value::Null) => None,
        Some(Value::String(label)) if !label.trim().is_empty() => Some(label.trim().to_string()),
        Some(_) => return fail("corrected activity label must be non-empty"),
    };
    let choice = |field: &str, allowed: &[&str]| -> Result<String> {
        match map.get(field) {
            None => Ok("unreviewed".into()),
            Some(Value::String(text)) if allowed.contains(&text.as_str()) => Ok(text.clone()),
            Some(other) => fail(format!("invalid {field} value: {other}")),
        }
    };
    let notes = match map.get("notes") {
        None => String::new(),
        Some(Value::String(text)) => text.clone(),
        Some(_) => return fail("attempt review notes must be text"),
    };
    Ok(AttemptReview {
        activity_label,
        inclusion: choice("inclusion", &INCLUSION_VALUES)?,
        quality: choice("quality", &QUALITY_VALUES)?,
        notes,
    })
}

fn valid_attempt_key(key: &str) -> bool {
    !key.starts_with('/') && key.starts_with("trials/") && !key.split('/').any(|part| part == "..")
}

impl Review {
    /// Parse and validate the bytes of a `session_review.json`.
    ///
    /// The checks mirror the inspector's: unknown fields are errors, so a typo
    /// cannot silently drop a decision.
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        let value: Value = serde_json::from_slice(bytes)
            .map_err(|error| Error(format!("invalid review document: {error}")))?;
        let document = value
            .as_object()
            .ok_or_else(|| Error("review document must contain an object".into()))?;
        reject_unknown(document, &DOCUMENT_FIELDS, "review")?;
        if document.get("schema_version").and_then(Value::as_u64) != Some(REVIEW_SCHEMA_VERSION) {
            return fail("review: only schema version 1 is supported");
        }
        let text = |field: &str| -> String {
            document
                .get(field)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string()
        };
        let session_id = text("session_id");
        if session_id.is_empty() {
            return fail("session_id must be non-empty");
        }
        let revision = match document.get("revision") {
            None => 0,
            Some(value) => value
                .as_u64()
                .ok_or_else(|| Error("revision must be a non-negative integer".into()))?,
        };
        let updated_at_utc = match document.get("updated_at_utc") {
            None | Some(Value::Null) => None,
            Some(Value::String(stamp)) => Some(stamp.clone()),
            Some(_) => return fail("updated_at_utc must be text or null"),
        };
        let mut metadata = BTreeMap::new();
        if let Some(raw) = document.get("metadata") {
            let raw = object(raw, "review.metadata")?;
            reject_unknown(raw, &METADATA_FIELDS, "metadata")?;
            for (field, value) in raw {
                let Some(value) = value.as_str() else {
                    return fail("metadata overrides must be text");
                };
                metadata.insert(field.clone(), value.to_string());
            }
        }
        let mut attempts = BTreeMap::new();
        if let Some(raw) = document.get("attempts") {
            for (key, value) in object(raw, "review.attempts")? {
                if !valid_attempt_key(key) {
                    return fail(format!("invalid attempt key: {key:?}"));
                }
                attempts.insert(key.clone(), parse_attempt(key, value)?);
            }
        }
        if let Some(history) = document.get("history")
            && !history
                .as_array()
                .is_some_and(|items| items.iter().all(Value::is_object))
        {
            return fail("history must be an array of objects");
        }
        Ok(Self {
            session_id,
            protocol_hash: text("protocol_hash"),
            revision,
            updated_at_utc,
            metadata,
            attempts,
            content_sha256: hex(&Sha256::digest(bytes)),
        })
    }

    /// Check that this review belongs to the session and names only its attempts.
    ///
    /// Binding by session id and protocol hash prevents a review from being
    /// applied to the wrong recording.
    pub fn validate_for(
        &self,
        session_id: &str,
        protocol_hash: &str,
        attempt_keys: &[String],
    ) -> Result<()> {
        if self.session_id != session_id {
            return fail(format!(
                "review belongs to session {:?}, not {session_id:?}",
                self.session_id
            ));
        }
        if self.protocol_hash != protocol_hash {
            return fail("review protocol hash does not match the session");
        }
        if let Some(unknown) = self.attempts.keys().find(|key| !attempt_keys.contains(key)) {
            return fail(format!("review references unknown attempt: {unknown}"));
        }
        Ok(())
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// One attempt after the review is applied.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EffectiveAttempt {
    /// Relative directory of the attempt, the key reviews use.
    pub attempt_key: String,
    pub trial_ordinal: u32,
    pub attempt: u32,
    /// The reviewed label when one was set, otherwise the acquisition label.
    pub activity_label: String,
    /// The label recorded at acquisition.
    pub original_activity_label: String,
    pub status: Option<String>,
    pub inclusion: String,
    pub quality: String,
    pub notes: String,
    /// `0` when no review exists.
    pub review_revision: u64,
}

/// Relative directory of an attempt, without the archive's `original/` prefix.
pub fn attempt_key(attempt: &Attempt, prefix: &str) -> String {
    attempt
        .directory
        .strip_prefix(prefix)
        .unwrap_or(&attempt.directory)
        .to_string()
}

/// Apply `review` to recorded attempts; unreviewed attempts keep their values.
pub fn effective_attempts(
    attempts: &[Attempt],
    prefix: &str,
    review: Option<&Review>,
) -> Vec<EffectiveAttempt> {
    attempts
        .iter()
        .map(|attempt| {
            let key = attempt_key(attempt, prefix);
            let decision = review.and_then(|review| review.attempts.get(&key));
            let fallback = AttemptReview::default();
            let decision = decision.unwrap_or(&fallback);
            EffectiveAttempt {
                activity_label: decision
                    .activity_label
                    .clone()
                    .unwrap_or_else(|| attempt.activity_label.clone()),
                original_activity_label: attempt.activity_label.clone(),
                status: attempt.status.clone(),
                inclusion: decision.inclusion.clone(),
                quality: decision.quality.clone(),
                notes: decision.notes.clone(),
                review_revision: review.map_or(0, |review| review.revision),
                trial_ordinal: attempt.trial_ordinal,
                attempt: attempt.attempt,
                attempt_key: key,
            }
        })
        .collect()
}
