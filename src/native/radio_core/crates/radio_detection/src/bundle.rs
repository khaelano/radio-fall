//! Validate existing exports without inventing their missing deployment settings.
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::Read,
    path::{Component, Path, PathBuf},
};

/// The transformed signal a family's normalizer and model read.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Representation {
    /// `log1p((A[t] - A[t - 1])^2)`, the default.
    SquaredDifference,
    /// `A[t] - A[t - 1]` of the Hampel-filtered amplitude.
    SignedDifference,
}

impl Representation {
    /// Name used in bundle manifests and in `03_training`.
    pub fn name(self) -> &'static str {
        match self {
            Representation::SquaredDifference => "log1p_squared_difference",
            Representation::SignedDifference => "signed_difference",
        }
    }
}

/// A model family the live detector can deploy.
pub struct Family {
    /// Bundle directory under the model root, and the model ID prefix.
    pub name: &'static str,
    /// Operator that must run on the GPU for a WebGPU session to be accepted.
    pub main_operator: &'static str,
    /// Signal its exports read.
    pub representation: Representation,
    /// Whether the window passes through the principal-component spectrum
    /// front end (`radio_signal::pc_spectrum`) before ONNX, which then holds
    /// only the head and takes `[batch, stft_frames, 65]`.
    pub front_end: bool,
}

/// Families with a live-compatible 120 Hz export.
pub const FAMILIES: [Family; 6] = [
    Family {
        name: "cnn",
        main_operator: "Conv",
        representation: Representation::SquaredDifference,
        front_end: false,
    },
    Family {
        name: "lstm",
        main_operator: "LSTM",
        representation: Representation::SquaredDifference,
        front_end: false,
    },
    Family {
        name: "gru",
        main_operator: "GRU",
        representation: Representation::SquaredDifference,
        front_end: false,
    },
    // Shared per-tone encoder with a temporal head; its export is mostly Conv.
    Family {
        name: "tonepool_tcn",
        main_operator: "Conv",
        representation: Representation::SquaredDifference,
        front_end: false,
    },
    // Tone- and receiver-averaged motion energy with a small temporal network.
    Family {
        name: "tiny_tcn1",
        main_operator: "Conv",
        representation: Representation::SquaredDifference,
        front_end: false,
    },
    // Per-window principal components and their STFT power (computed by the
    // Rust front end), then a GRU; the export is the head only.
    Family {
        name: "pcspec_gru",
        main_operator: "GRU",
        representation: Representation::SignedDifference,
        front_end: true,
    },
];

/// The `front_end` block a front-end export must declare: the definition the
/// Rust front end implements, so a bundle trained on another one is refused.
pub fn front_end_specification() -> serde_json::Value {
    use radio_signal::pc_spectrum as pc;
    serde_json::json!({
        "kind": "pc_spectrum",
        "version": pc::VERSION,
        "components": pc::COMPONENTS,
        "window": pc::WINDOW,
        "hop": pc::HOP,
        "bins": pc::BINS,
        "minimum_tones": 0.9,
        "minimum_valid": 0.6,
        "interior": pc::RUNS.map(|(low, high)| [low, high]),
        "log_floor": 1e-6,
    })
}

/// Window durations, in seconds, that an export can use.
pub const DURATIONS_SECONDS: [u64; 3] = [2, 4, 6];

/// Every family at every duration; bounds the number of resident models.
pub const MAX_MODELS: usize = FAMILIES.len() * DURATIONS_SECONDS.len();

/// Family of a `<family>-<seconds>s` model ID.
pub fn family_of(id: &str) -> Option<&'static Family> {
    let (name, _) = id.rsplit_once('-')?;
    FAMILIES.iter().find(|family| family.name == name)
}

/// Hash a potentially large artifact with bounded scratch memory.
pub fn sha256(path: &Path) -> Result<String, Box<dyn std::error::Error>> {
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

/// Verified weights and normalizer, still requiring supplementary deployment metadata.
#[derive(Debug)]
pub struct Export {
    pub id: String,
    pub model: PathBuf,
    pub normalizer: PathBuf,
    /// Samples per window.
    pub frames: usize,
    /// Signal the normalizer and model read.
    pub representation: Representation,
    /// Whether the principal-component spectrum front end precedes ONNX.
    pub front_end: bool,
    /// ONNX input `[steps, features]` after the batch dimension.
    pub input: [usize; 2],
    pub model_hash: String,
    pub normalizer_hash: String,
}

fn artifact(
    root: &Path,
    row: &serde_json::Value,
    key: &str,
    hash_key: &str,
) -> Result<(PathBuf, String), Box<dyn std::error::Error>> {
    let name = row[key].as_str().ok_or("missing artifact filename")?;
    if Path::new(name).components().count() != 1
        || !matches!(
            Path::new(name).components().next(),
            Some(Component::Normal(_))
        )
    {
        return Err("artifact must be a local filename".into());
    }
    let root = root.canonicalize()?;
    let path = root.join(name).canonicalize()?;
    if !path.starts_with(&root) {
        return Err("artifact escapes bundle directory".into());
    }
    let expected = row[hash_key].as_str().ok_or("missing artifact hash")?;
    let actual = sha256(&path)?;
    if actual != expected {
        return Err(format!("artifact checksum mismatch: {name}").into());
    }
    Ok((path, actual))
}

/// Verify all current 120 Hz exports and normalizers before constructing sessions.
pub fn inspect_exports(root: &Path) -> Result<Vec<Export>, Box<dyn std::error::Error>> {
    let manifest: serde_json::Value =
        serde_json::from_reader(File::open(root.join("manifest.json"))?)?;
    if manifest["input_name"] != "input"
        || manifest["input_dtype"] != "float32"
        || manifest["output_name"] != "fall_logit"
    {
        return Err("unsupported model IO contract".into());
    }
    let mut exports = Vec::new();
    let mut ids = std::collections::BTreeSet::new();
    for row in manifest["exports"].as_array().ok_or("missing exports")? {
        let name = row["model"].as_str().ok_or("missing model family")?;
        let duration = row["duration_seconds"].as_u64().ok_or("missing duration")?;
        let family = FAMILIES
            .iter()
            .find(|known| known.name == name)
            .ok_or("unsupported sequence export")?;
        if !DURATIONS_SECONDS.contains(&duration) || row["sample_rate_hz"] != 120 {
            return Err("unsupported sequence export".into());
        }
        let frames = duration as usize * 120;
        // Bundles from before representations were recorded read the default.
        let representation = row["representation"]
            .as_str()
            .unwrap_or(Representation::SquaredDifference.name());
        if representation != family.representation.name() {
            return Err("export representation does not match its family".into());
        }
        let (layout, input) = if family.front_end {
            if row["front_end"] != front_end_specification() {
                return Err("export front end differs from the native one".into());
            }
            let steps = radio_signal::pc_spectrum::stft_frames(frames);
            (
                "batch,frames,features",
                [steps, radio_signal::pc_spectrum::OUTPUTS],
            )
        } else {
            if !row["front_end"].is_null() {
                return Err("front end declared for a family without one".into());
            }
            ("batch,time,features", [frames, crate::sequence::FEATURES])
        };
        if manifest["input_layout"] != layout
            || row["input_shape"] != serde_json::json!(["batch", input[0], input[1]])
        {
            return Err("invalid sequence shape".into());
        }
        let id = format!("{name}-{duration}s");
        if !ids.insert(id.clone()) {
            return Err("duplicate model ID".into());
        }
        let (model, model_hash) = artifact(root, row, "file", "sha256")?;
        let (normalizer, normalizer_hash) = artifact(root, row, "normalizer", "normalizer_sha256")?;
        crate::sequence::Normalizer::load(&normalizer)?;
        exports.push(Export {
            id,
            model,
            normalizer,
            frames,
            representation: family.representation,
            front_end: family.front_end,
            input,
            model_hash,
            normalizer_hash,
        });
    }
    if exports.is_empty() {
        return Err("empty export bundle".into());
    }
    Ok(exports)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires DVC model artifacts"]
    fn verifies_all_current_export_artifacts() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../artifacts/model");
        for family in FAMILIES {
            let exports = inspect_exports(&root.join(family.name)).unwrap();
            // Newer families publish only their 4 s models so far.
            assert_eq!(
                exports.len(),
                if ["tonepool_tcn", "tiny_tcn1", "pcspec_gru"].contains(&family.name) {
                    1
                } else {
                    3
                }
            );
        }
    }
    #[test]
    fn family_of_resolves_ids_including_underscored_names() {
        assert_eq!(family_of("tonepool_tcn-4s").unwrap().main_operator, "Conv");
        assert_eq!(family_of("tiny_tcn1-4s").unwrap().main_operator, "Conv");
        assert_eq!(family_of("gru-6s").unwrap().main_operator, "GRU");
        let pcspec = family_of("pcspec_gru-4s").unwrap();
        assert!(pcspec.front_end);
        assert_eq!(pcspec.representation, Representation::SignedDifference);
        assert!(family_of("tonepool_tcn").is_none());
        assert!(family_of("unknown-4s").is_none());
        assert_eq!(MAX_MODELS, 18);
    }

    #[test]
    fn front_end_specification_matches_the_native_constants() {
        use radio_signal::pc_spectrum as pc;
        let spec = front_end_specification();
        assert_eq!(
            spec["minimum_tones"].as_f64().unwrap() as f32,
            pc::MINIMUM_TONES
        );
        assert_eq!(
            spec["minimum_valid"].as_f64().unwrap() as f32,
            pc::MINIMUM_VALID
        );
        assert_eq!(spec["log_floor"].as_f64().unwrap() as f32, pc::LOG_FLOOR);
        // As 03_training writes it (Python's json module).
        let written: serde_json::Value = serde_json::from_str(
            r#"{"kind": "pc_spectrum", "version": 1, "components": 5, "window": 64,
                "hop": 8, "bins": 32, "minimum_tones": 0.9, "minimum_valid": 0.6,
                "interior": [[2, 121], [124, 243]], "log_floor": 1e-06}"#,
        )
        .unwrap();
        assert_eq!(spec, written);
    }
}
