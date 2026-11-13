//! Shared gateway framing and CSI decoding without Python dependencies.
pub mod acceptance;
pub mod acquisition;
pub mod availability;
pub mod clock;
pub mod control;
pub mod framing;
pub mod journal;
pub mod quality;
pub mod receivers;
pub mod reference;
pub mod replay;
#[cfg(target_os = "linux")]
pub mod serial;
pub mod session;
pub mod startup;
pub mod wire;
