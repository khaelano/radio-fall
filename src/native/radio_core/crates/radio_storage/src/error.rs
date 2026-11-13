//! Error type shared by the storage crate.
use std::fmt;

/// A storage failure with a human-readable message.
#[derive(Debug)]
pub struct Error(pub String);

/// Result alias for storage operations.
pub type Result<T> = std::result::Result<T, Error>;

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

macro_rules! from_error {
    ($($ty:ty),* $(,)?) => {$(
        impl From<$ty> for Error {
            fn from(error: $ty) -> Self {
                Error(error.to_string())
            }
        }
    )*};
}

from_error!(
    std::io::Error,
    serde_json::Error,
    parquet::errors::ParquetError,
    arrow_schema::ArrowError,
    zip::result::ZipError,
);

impl From<String> for Error {
    fn from(message: String) -> Self {
        Error(message)
    }
}

impl From<&str> for Error {
    fn from(message: &str) -> Self {
        Error(message.to_string())
    }
}
