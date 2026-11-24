//! Validate existing exports without inventing their missing deployment settings.
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::Read,
    path::{Component, Path, PathBuf},
};

/// A model family the live detector can deploy.
pub struct Family {
    /// Bundle directory under the model root, and the model ID prefix.
    pub name: &'static str,
    /// Operator that must run on the GPU for a WebGPU session to be accepted.
    pub main_operator: &'static str,
}

/// Families with a live-compatible export: the default 120 Hz representation.
pub const FAMILIES: [Family; 4] = [
    Family {
        name: "cnn",
        main_operator: "Conv",
    },
    Family {
        name: "lstm",
        main_operator: "LSTM",
    },
    Family {
        name: "gru",
        main_operator: "GRU",
    },
    // Shared per-tone encoder with a temporal head; its export is mostly Conv.
    Family {
        name: "tonepool_tcn",
        main_operator: "Conv",
    },
];

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
    pub frames: usize,
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
        || manifest["input_layout"] != "batch,time,features"
        || manifest["output_name"] != "fall_logit"
    {
        return Err("unsupported model IO contract".into());
    }
    let mut exports = Vec::new();
    let mut ids = std::collections::BTreeSet::new();
    for row in manifest["exports"].as_array().ok_or("missing exports")? {
        let family = row["model"].as_str().ok_or("missing model family")?;
        let duration = row["duration_seconds"].as_u64().ok_or("missing duration")?;
        if !FAMILIES.iter().any(|known| known.name == family)
            || !DURATIONS_SECONDS.contains(&duration)
            || row["sample_rate_hz"] != 120
        {
            return Err("unsupported sequence export".into());
        }
        let frames = duration as usize * 120;
        if row["input_shape"] != serde_json::json!(["batch", frames, 1964]) {
            return Err("invalid sequence shape".into());
        }
        let id = format!("{family}-{duration}s");
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
            // tonepool_tcn publishes only its 4 s model so far.
            assert_eq!(
                exports.len(),
                if family.name == "tonepool_tcn" { 1 } else { 3 }
            );
        }
    }
    #[test]
    fn family_of_resolves_ids_including_underscored_names() {
        assert_eq!(family_of("tonepool_tcn-4s").unwrap().main_operator, "Conv");
        assert_eq!(family_of("gru-6s").unwrap().main_operator, "GRU");
        assert!(family_of("tonepool_tcn").is_none());
        assert!(family_of("unknown-4s").is_none());
        assert_eq!(MAX_MODELS, 12);
    }
}
