//! Session storage: read raw journals and write typed tables.
pub use arrow_array;
pub use arrow_schema;

pub mod annotate;
pub mod archive;
pub mod convert;
pub mod error;
pub mod read;
pub mod resolve;
pub mod review;
pub mod schema;
pub mod source;
pub mod store;
pub mod verify;
pub mod vfs;

pub use archive::{
    ArchiveOptions, MigrateOptions, MigrationReport, archive_manifest, extract_archive,
    migrate_archive, tables_differences, verify_archive, write_archive,
};
pub use convert::{ConversionReport, ConvertOptions, FrameScope, convert_frames, convert_session};
pub use error::{Error, Result};
pub use read::{FrameQuery, frame_counts, read_frames, read_frames_with_schema};
pub use resolve::{
    ANNOTATIONS_DIR, OpenedReview, OpenedSession, ReviewOrigin, annotation_path,
    annotations_dir_for, open_session, open_source, resolve_source, source_path,
};
pub use review::{AttemptReview, EffectiveAttempt, Review, effective_attempts};
pub use source::{extract_session_file, read_session_file, session_files};
pub use store::{EnsureStage, FrameStore, Table, ensure_frames, tables_current};
pub use verify::{VerifyReport, verify_against_source, verify_dir};
