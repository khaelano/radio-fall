//! Sequence preprocessing settings shared by the live window builder.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// Signal preprocessing applied before the exported models.
///
/// The values mirror `docs/amplitude-preprocessing.md` and the shared offline
/// kernels; ONNX exports take prepared inputs and do not embed these steps.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preprocessing {
    pub identity: String,
    pub sample_rate_hz: u32,
    pub alignment: String,
    pub duplicate_rule: String,
    pub timestamp_rule: String,
    pub receiver_order: [String; 4],
    pub subcarrier_order: Vec<i16>,
    pub hampel_window_seconds: f64,
    pub hampel_threshold: f64,
    pub hampel_mad_scale: f64,
    pub hampel_min_periods: usize,
    pub future_context_ns: u64,
    pub preceding_context_ns: u64,
    pub segment_gap_ns: u64,
    pub difference_boundary: String,
    pub transform_casts: String,
    pub tensor_layout: String,
}
impl Preprocessing {
    /// Settings used to build the current 120 Hz sequence exports.
    pub fn operational() -> Self {
        Self {
            identity: "operational-sequence-120hz-v1".into(),
            sample_rate_hz: 120,
            alignment: "exact-source-round".into(),
            duplicate_rule: "first".into(),
            timestamp_rule: "nominal-grid-median-origin".into(),
            receiver_order: std::array::from_fn(|i| format!("rx-{}", i + 1)),
            subcarrier_order: (-122..=122).collect(),
            hampel_window_seconds: 0.5,
            hampel_threshold: 3.0,
            hampel_mad_scale: 1.4826,
            hampel_min_periods: 5,
            future_context_ns: 250_000_000,
            preceding_context_ns: 258_333_334,
            segment_gap_ns: 1_000_000_000,
            difference_boundary: "missing-first".into(),
            transform_casts: "f64-hampel-difference-square-log1p-to-f32".into(),
            tensor_layout: "batch,time,980-signals,980-validity,4-presence".into(),
        }
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.identity.is_empty()
            || self.sample_rate_hz != 120
            || self.alignment != "exact-source-round"
            || self.duplicate_rule != "first"
            || self.timestamp_rule != "nominal-grid-median-origin"
            || self.tensor_layout != "batch,time,980-signals,980-validity,4-presence"
            || self.subcarrier_order != (-122..=122).collect::<Vec<_>>()
            || self.receiver_order.iter().any(String::is_empty)
            || self.receiver_order.iter().collect::<BTreeSet<_>>().len() != 4
        {
            return Err("unsupported sequence alignment/layout contract".into());
        }
        if !self.hampel_window_seconds.is_finite()
            || self.hampel_window_seconds <= 0.0
            || !self.hampel_threshold.is_finite()
            || self.hampel_threshold < 0.0
            || self.hampel_mad_scale != 1.4826
            || self.hampel_min_periods == 0
            || self.segment_gap_ns == 0
        {
            return Err("invalid or unsupported numerical preprocessing contract".into());
        }
        let half_ns = (self.hampel_window_seconds * 500_000_000.0).ceil();
        if half_ns >= u64::MAX as f64
            || self.future_context_ns < half_ns as u64
            || (half_ns as u64)
                .checked_add(8_333_334)
                .is_none_or(|required| self.preceding_context_ns < required)
        {
            return Err("insufficient centered-filter context".into());
        }
        if !["missing-first", "drop-first"].contains(&self.difference_boundary.as_str())
            || self.transform_casts != "f64-hampel-difference-square-log1p-to-f32"
        {
            return Err("unsupported difference boundary or numerical casts".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_operational_settings_validate_and_context_is_enforced() {
        let mut settings = Preprocessing::operational();
        settings.validate().unwrap();
        settings.future_context_ns = 100_000_000;
        assert!(settings.validate().is_err());
        assert!(
            serde_json::from_value::<Preprocessing>(serde_json::json!({"sample_rate_hz": 120}))
                .is_err()
        );
    }
}
