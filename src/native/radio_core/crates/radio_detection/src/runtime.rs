//! Native sessions. GPU initialization fails rather than selecting a CPU device.

use ort::{environment::Environment, memory::DeviceType, session::Session, value::TensorRef};
use std::path::Path;

/// PCI device IDs of AMD GPUs exposed through DRM. ORT can report an empty
/// vendor string for the WebGPU adapter, so the PCI identity disambiguates it.
fn amd_drm_devices() -> std::collections::BTreeSet<u32> {
    let mut devices = std::collections::BTreeSet::new();
    let Ok(entries) = std::fs::read_dir("/sys/class/drm") else {
        return devices;
    };
    for entry in entries.flatten() {
        let path = entry.path().join("device");
        let read_hex = |name: &str| {
            std::fs::read_to_string(path.join(name))
                .ok()
                .and_then(|v| u32::from_str_radix(v.trim().trim_start_matches("0x"), 16).ok())
        };
        if read_hex("vendor") == Some(0x1002)
            && let Some(device) = read_hex("device")
        {
            devices.insert(device);
        }
    }
    devices
}

/// Threads of one CPU session: the 4 s model takes about 5 ms with four, against 4 ms
/// with eight and 3 ms with the default, and a window arrives every 250 ms.
const CPU_INTRA_THREADS: usize = 4;

/// Explicitly selected execution backend.
pub enum Backend<'a> {
    CpuDiagnostic,
    /// WebGPU on an AMD GPU through Dawn/Vulkan. `device_id` is the PCI device
    /// ID; `None` selects the only AMD WebGPU adapter and fails if ambiguous.
    AmdVulkan {
        plugin: &'a Path,
        device_id: Option<u32>,
    },
}

/// Own the native environment and keep model sessions resident.
pub struct Runtime {
    environment: Environment,
    sessions: Vec<Session>,
    gpu: bool,
    selected_device: Option<u32>,
}

impl Runtime {
    /// Validate the selected resident sessions before starting the submission thread.
    pub fn validate_sessions(
        &self,
        sessions: &std::collections::BTreeMap<String, usize>,
    ) -> Result<(), String> {
        if sessions.is_empty()
            || sessions.len() > crate::bundle::MAX_MODELS
            || sessions.keys().any(String::is_empty)
            || sessions.values().any(|&index| index >= self.sessions.len())
            || sessions
                .values()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != sessions.len()
        {
            return Err("model selection must identify distinct loaded sessions".into());
        }
        Ok(())
    }

    /// Provider identity reported on results; GPU selection never changes to CPU.
    pub fn provider_name(&self) -> &'static str {
        if self.gpu {
            "WebGPU/Vulkan"
        } else {
            "CPU diagnostic"
        }
    }
    /// Create explicit CPU diagnostic sessions within the same native environment.
    pub fn cpu_diagnostic_peer(&self) -> Self {
        Self {
            environment: self.environment.clone(),
            sessions: Vec::new(),
            gpu: false,
            selected_device: None,
        }
    }
    /// Load the supplied core runtime and optionally register the WebGPU plugin.
    pub fn new(core: &Path, backend: Backend<'_>) -> Result<Self, Box<dyn std::error::Error>> {
        let environment = ort::init_from(core)?.with_telemetry(false).build()?;
        let gpu = matches!(backend, Backend::AmdVulkan { .. });
        if let Backend::AmdVulkan { plugin, .. } = backend {
            environment.register_ep_library("webgpu", plugin)?;
        }
        let mut runtime = Self {
            environment,
            sessions: Vec::new(),
            gpu,
            selected_device: None,
        };
        // Store selection separately through session creation; never rely on EP ordering.
        if let Backend::AmdVulkan { device_id, .. } = backend {
            let drm = amd_drm_devices();
            let candidates: std::collections::BTreeSet<u32> = runtime
                .environment
                .devices()
                .filter(|device| {
                    let hardware = device.hardware_device();
                    device
                        .ep()
                        .is_ok_and(|ep| ep.eq_ignore_ascii_case("WebGpuExecutionProvider"))
                        && hardware.ty() == DeviceType::GPU
                        && hardware.vendor().is_ok_and(|v| {
                            let v = v.to_ascii_lowercase();
                            v.contains("amd")
                                || v.contains("advanced micro devices")
                                || (v.is_empty() && drm.contains(&hardware.id()))
                        })
                })
                .map(|device| device.hardware_device().id())
                .collect();
            let selected = match device_id {
                Some(id) if candidates.contains(&id) => id,
                Some(id) => {
                    return Err(format!("AMD WebGPU adapter {id:#06x} is unavailable").into());
                }
                None if candidates.len() == 1 => *candidates.first().unwrap(),
                None if candidates.is_empty() => {
                    return Err("no AMD WebGPU adapter is available".into());
                }
                None => {
                    return Err(format!(
                        "several AMD WebGPU adapters {candidates:?}; select one explicitly"
                    )
                    .into());
                }
            };
            runtime.selected_device = Some(selected);
        }
        Ok(runtime)
    }

    /// Load a model and enable placement profiling before running it.
    pub fn load(
        &mut self,
        model: &Path,
        profile: &Path,
    ) -> Result<usize, Box<dyn std::error::Error>> {
        self.load_session(model, Some(profile))
    }

    /// Load without profiling to measure ordinary submissions independently.
    pub fn load_unprofiled(&mut self, model: &Path) -> Result<usize, Box<dyn std::error::Error>> {
        self.load_session(model, None)
    }

    fn load_session(
        &mut self,
        model: &Path,
        profile: Option<&Path>,
    ) -> Result<usize, Box<dyn std::error::Error>> {
        let mut builder = Session::builder(&self.environment)?;
        if let Some(profile) = profile {
            builder = builder.with_profiling(profile)?;
        }
        if self.gpu {
            let options = vec![(
                "WebGpuExecutionProvider.dawnBackendType".into(),
                "Vulkan".into(),
            )];
            builder = builder.with_devices(
                self.environment.devices().filter(|d| {
                    d.ep()
                        .is_ok_and(|ep| ep.eq_ignore_ascii_case("WebGpuExecutionProvider"))
                        && Some(d.hardware_device().id()) == self.selected_device
                        && d.hardware_device().ty() == DeviceType::GPU
                }),
                Some(&options),
            )?;
        } else {
            // The default pool spins a thread on every physical core between calls, which
            // keeps the whole machine busy for a few milliseconds of work per window.
            let threads = std::thread::available_parallelism()
                .map_or(1, std::num::NonZeroUsize::get)
                .min(CPU_INTRA_THREADS);
            builder = builder
                .with_intra_threads(threads)?
                .with_config_entry("session.intra_op.allow_spinning", "0")?;
            builder = builder.with_devices(
                self.environment.devices().filter(|d| {
                    d.ep().is_ok_and(|ep| ep == "CPUExecutionProvider")
                        && d.hardware_device().ty() == DeviceType::CPU
                }),
                None,
            )?;
        }
        let session = builder.commit_from_file(model)?;
        if session.inputs().len() != 1
            || session.inputs()[0].name() != "input"
            || session.outputs().len() != 1
            || session.outputs()[0].name() != "fall_logit"
        {
            return Err("model must expose input and fall_logit tensor names".into());
        }
        self.sessions.push(session);
        Ok(self.sessions.len() - 1)
    }

    /// Submit a prepared batch-one tensor; preprocessing remains outside this module.
    pub fn infer(
        &mut self,
        model: usize,
        frames: usize,
        input: Vec<f32>,
    ) -> Result<f32, Box<dyn std::error::Error>> {
        self.infer_view(model, frames, &input)
    }

    /// Borrow immutable prepared storage for one synchronous native submission.
    pub fn infer_view(
        &mut self,
        model: usize,
        frames: usize,
        input: &[f32],
    ) -> Result<f32, Box<dyn std::error::Error>> {
        if input.len() != frames.checked_mul(1964).ok_or("input size overflow")? {
            return Err("input must have shape [1,time,1964]".into());
        }
        let session = self
            .sessions
            .get_mut(model)
            .ok_or("unknown model session")?;
        let tensor = TensorRef::from_array_view(([1, frames, 1964], input))?;
        let outputs = session.run(ort::inputs!["input" => tensor])?;
        let (_, values) = outputs
            .get("fall_logit")
            .ok_or("model omitted fall_logit")?
            .try_extract_tensor::<f32>()?;
        if values.len() != 1 || !values[0].is_finite() {
            return Err("invalid model logit".into());
        }
        Ok(values[0])
    }

    /// Flush the runtime profile for independent placement auditing.
    pub fn finish_profile(&mut self, model: usize) -> Result<String, Box<dyn std::error::Error>> {
        Ok(self
            .sessions
            .get_mut(model)
            .ok_or("unknown model session")?
            .end_profiling()?)
    }
}
