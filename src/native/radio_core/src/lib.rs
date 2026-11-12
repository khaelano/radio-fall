#[path = "low_level/bindings.rs"]
mod bindings;
#[path = "preprocessing/detector.rs"]
mod detector;
#[path = "low_level/framing.rs"]
mod framing;
#[cfg(unix)]
#[path = "low_level/pipeline.rs"]
mod pipeline;
#[path = "low_level/recording.rs"]
mod recording;
#[path = "low_level/wire.rs"]
mod wire;
use pyo3::prelude::*;
use radio_preprocessing::{amplitude, hampel};

#[pymodule]
fn _radio_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BACKEND_VERSION", 1)?;
    #[cfg(unix)]
    {
        m.add_class::<pipeline::Pipeline>()?;
        m.add_class::<pipeline::ProcessedFrame>()?;
    }
    m.add_class::<bindings::NativeRecord>()?;
    m.add_class::<detector::CnnPreprocessor>()?;
    m.add_class::<detector::CnnWindow>()?;
    m.add_function(wrap_pyfunction!(detector::decode_cnn_record, m)?)?;
    m.add_class::<bindings::NativeBatch>()?;
    m.add_class::<framing::FrameDecoder>()?;
    m.add_function(wrap_pyfunction!(framing::encode_frame, m)?)?;
    m.add_class::<recording::RecordingWriter>()?;
    m.add_class::<recording::RecordingStream>()?;
    m.add_function(wrap_pyfunction!(bindings::decode_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::simd_kernel, m)?)?;
    m.add_function(wrap_pyfunction!(hampel::hampel_filter, m)?)?;
    m.add_function(wrap_pyfunction!(amplitude::prepare_amplitude, m)?)?;
    m.add_function(wrap_pyfunction!(amplitude::prepare_magnitude, m)?)?;
    Ok(())
}
