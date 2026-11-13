//! Sequence input assembly matching `analysis/sequence_training_data.py`.

pub const SIGNALS: usize = 980;
pub const FEATURES: usize = 1964;

/// Saved training statistics; construction never estimates live statistics.
pub struct Normalizer {
    mean: Vec<f32>,
    scale: Vec<f32>,
}

impl Normalizer {
    /// Read the existing uncompressed NumPy sidecar without Python or pickle.
    /// Artifact hashes must be verified by the deployment loader before use.
    pub fn load(path: &std::path::Path) -> Result<Self, Box<dyn std::error::Error>> {
        let mut archive = ndarray_npy::NpzReader::new(std::fs::File::open(path)?)?;
        let mean: ndarray::Array1<f32> = archive.by_name("mean")?;
        let scale: ndarray::Array1<f32> = archive.by_name("scale")?;
        let count: ndarray::Array1<i64> = archive.by_name("count")?;
        if count.len() != SIGNALS || count.iter().any(|&v| v < 0) {
            return Err("invalid normalizer training counts".into());
        }
        Ok(Self::new(mean.to_vec(), scale.to_vec())?)
    }

    /// Validate already decoded saved statistics in receiver/subcarrier order.
    pub fn new(mean: Vec<f32>, scale: Vec<f32>) -> Result<Self, String> {
        if mean.len() != SIGNALS
            || scale.len() != SIGNALS
            || mean.iter().any(|v| !v.is_finite())
            || scale.iter().any(|v| !v.is_finite() || *v <= 0.0)
        {
            return Err("normalizer must contain 980 finite means and positive scales".into());
        }
        Ok(Self { mean, scale })
    }

    /// Assemble normalized signals, validity flags, and receiver presence.
    ///
    /// Input signals have already undergone the exported transformation and
    /// float32 cast. NaNs are missing. Coverage is finite time/tone support,
    /// independently for each receiver. The caller can reuse output allocation.
    pub fn assemble(
        &self,
        signal: &[f32],
        presence: &[[bool; 4]],
        output: &mut Vec<f32>,
    ) -> Result<[f32; 4], String> {
        let frames = presence.len();
        if frames == 0
            || frames.checked_mul(SIGNALS) != Some(signal.len())
            || signal.iter().any(|v| v.is_infinite())
        {
            return Err("invalid transformed signal shape or infinity".into());
        }
        let size = frames.checked_mul(FEATURES).ok_or("input size overflow")?;
        output.clear();
        output.resize(size, 0.0);
        let mut counts = [0usize; 4];
        for (time, row) in signal.chunks_exact(SIGNALS).enumerate() {
            let target = &mut output[time * FEATURES..(time + 1) * FEATURES];
            for (feature, &value) in row.iter().enumerate() {
                if value.is_finite() {
                    target[feature] = (value - self.mean[feature]) / self.scale[feature];
                    if !target[feature].is_finite() {
                        return Err("normalization overflow".into());
                    }
                    target[SIGNALS + feature] = 1.0;
                    counts[feature / 245] += 1;
                }
            }
            for receiver in 0..4 {
                target[2 * SIGNALS + receiver] = f32::from(presence[time][receiver]);
            }
        }
        Ok(counts.map(|n| n as f32 / (frames * 245) as f32))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires local DVC model artifacts"]
    fn load_current_export_normalizers() {
        let root =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../../artifacts/model");
        for model in ["cnn", "lstm", "gru"] {
            for duration in [2, 4, 6] {
                let path = root.join(model).join(format!("normalizer-{duration}s.npz"));
                Normalizer::load(&path)
                    .unwrap_or_else(|error| panic!("{}: {error}", path.display()));
            }
        }
    }
    #[test]
    fn ordering_missingness_and_receiver_coverage() {
        let n = Normalizer::new(vec![1.0; SIGNALS], vec![2.0; SIGNALS]).unwrap();
        let mut signal = vec![3.0; SIGNALS * 2];
        signal[245..490].fill(f32::NAN);
        let mut output = Vec::new();
        let coverage = n
            .assemble(
                &signal,
                &[[true, true, false, true], [true; 4]],
                &mut output,
            )
            .unwrap();
        assert_eq!(coverage, [1.0, 0.5, 1.0, 1.0]);
        assert_eq!(output[0], 1.0);
        assert_eq!(output[245], 0.0);
        assert_eq!(output[980], 1.0);
        assert_eq!(output[980 + 245], 0.0);
        assert_eq!(&output[1960..1964], &[1.0, 1.0, 0.0, 1.0]);
        assert_eq!(output.len(), 3928);
    }
}
