#[cfg(target_os = "linux")]
mod acquisition_bindings;
#[path = "low_level/bindings.rs"]
mod bindings;
mod detection_bindings;
#[path = "low_level/framing.rs"]
mod framing;
mod preprocessing_bindings;
#[path = "low_level/recording.rs"]
mod recording;
mod storage_bindings;
#[path = "low_level/wire.rs"]
mod wire;
use pyo3::prelude::*;

#[pymodule]
fn _radio_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BACKEND_VERSION", 1)?;
    m.add_class::<detection_bindings::NativeDetector>()?;
    #[cfg(target_os = "linux")]
    m.add_class::<acquisition_bindings::NativeAcquisition>()?;
    m.add_class::<bindings::NativeRecord>()?;
    m.add_class::<bindings::NativeBatch>()?;
    m.add_class::<framing::FrameDecoder>()?;
    m.add_function(wrap_pyfunction!(framing::encode_frame, m)?)?;
    m.add_class::<recording::RecordingWriter>()?;
    m.add_class::<recording::RecordingStream>()?;
    m.add_function(wrap_pyfunction!(bindings::decode_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::simd_kernel, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::read_envelopes, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::fit_clock, m)?)?;
    m.add_class::<bindings::ClockFit>()?;
    m.add_function(wrap_pyfunction!(bindings::ltf_layouts, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::phase_block, m)?)?;
    storage_bindings::register(m)?;
    m.add_function(wrap_pyfunction!(preprocessing_bindings::hampel_filter, m)?)?;
    m.add_function(wrap_pyfunction!(
        preprocessing_bindings::prepare_amplitude,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        preprocessing_bindings::prepare_magnitude,
        m
    )?)?;
    Ok(())
}
