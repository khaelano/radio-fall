//! Build model inputs from buffered aligned magnitudes.
use crate::{
    preprocessing::Preprocessing,
    sequence::{Normalizer, SIGNALS},
    stream::Snapshot,
};
use std::ops::Range;

/// Segment boundaries must be known; a rolling-buffer edge is not a segment edge.
#[derive(Clone, Copy)]
pub struct SegmentEdges {
    pub start: bool,
    pub end: bool,
}

/// Inspection stages for qualification; only model_input goes to native inference.
pub struct Prepared {
    pub generation: u64,
    pub frames: usize,
    pub filtered: Vec<f64>,
    pub replacements: Vec<u8>,
    pub transformed: Vec<f32>,
    pub model_input: Vec<f32>,
    pub coverage: [f32; 4],
}

impl Prepared {
    /// Transfer a finalized input to scheduling without copying its tensor.
    pub fn into_job(
        self,
        model_id: String,
        timing: &crate::stream::WindowTiming,
        finalized_ns: u64,
        hop_ns: u64,
    ) -> Result<crate::scheduler::Job, String> {
        let duration = timing
            .end_ns
            .checked_sub(timing.start_ns)
            .ok_or("invalid capture window")?;
        if model_id.is_empty()
            || hop_ns == 0
            || ![240, 480, 720].contains(&self.frames)
            || duration as u128 * 120 != self.frames as u128 * 1_000_000_000
            || self.model_input.len() != self.frames * 1964
            || finalized_ns < timing.finalize_after_ns
        {
            return Err("model input/window/finalization contract mismatch".into());
        }
        let deadline = hop_ns
            .checked_mul(2)
            .and_then(|extra| timing.finalize_after_ns.checked_add(extra))
            .ok_or("publication deadline overflow")?;
        if finalized_ns > deadline {
            return Err("window already stale at finalization".into());
        }
        Ok(crate::scheduler::Job {
            model_id,
            generation: self.generation,
            start_ns: timing.start_ns,
            end_ns: timing.end_ns,
            finalized_ns,
            deadline_ns: deadline,
            coverage: self.coverage,
            frames: self.frames,
            input: self.model_input.into(),
        })
    }
}

/// Build an immutable window with explicit context/segment-edge semantics.
pub fn prepare(
    snapshot: &Snapshot,
    times: &[f64],
    window: Range<usize>,
    edges: SegmentEdges,
    contract: &Preprocessing,
    normalizer: &Normalizer,
) -> Result<Prepared, String> {
    contract.validate()?;
    let rows = snapshot.presence.len();
    if window.is_empty()
        || window.end > rows
        || times.len() != rows
        || snapshot.capture_ns.len() != rows
        || times.iter().any(|t| !t.is_finite())
        || times.windows(2).any(|t| t[1] <= t[0])
    {
        return Err("invalid window/grid bounds".into());
    }
    if window.start == 0 && (!edges.start || contract.difference_boundary == "drop-first") {
        return Err("preceding difference sample unavailable".into());
    }
    let earliest = window.start.saturating_sub(1);
    let half = contract.hampel_window_seconds / 2.0;
    if (!edges.start && times[earliest] - half < times[0])
        || (!edges.end && times[window.end - 1] + half > times[rows - 1])
    {
        return Err("centered Hampel context unavailable".into());
    }
    let (filtered, replacements) = snapshot.filter(
        times,
        contract.hampel_window_seconds,
        contract.hampel_min_periods,
        contract.hampel_threshold,
    )?;
    let frames = window.len();
    let mut transformed =
        vec![f32::NAN; frames.checked_mul(SIGNALS).ok_or("window size overflow")?];
    for (target, row) in window.clone().enumerate() {
        if row == 0 {
            continue;
        }
        for feature in 0..SIGNALS {
            let current = filtered[row * SIGNALS + feature];
            let previous = filtered[(row - 1) * SIGNALS + feature];
            if current.is_finite() && previous.is_finite() {
                let difference = current - previous;
                let value = (difference * difference).ln_1p() as f32;
                if !value.is_finite() {
                    return Err("signal transformation overflow".into());
                }
                transformed[target * SIGNALS + feature] = value;
            }
        }
    }
    let mut model_input = Vec::new();
    let coverage =
        normalizer.assemble(&transformed, &snapshot.presence[window], &mut model_input)?;
    Ok(Prepared {
        generation: snapshot.generation,
        frames,
        filtered,
        replacements,
        transformed,
        model_input,
        coverage,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn contract() -> Preprocessing {
        // Short synthetic filter span so a seven-frame fixture has full context.
        serde_json::from_value(serde_json::json!({"identity":"synthetic-window-test","sample_rate_hz":120,
            "alignment":"exact-source-round","duplicate_rule":"first","timestamp_rule":"nominal-grid-median-origin",
            "receiver_order":["rx-1","rx-2","rx-3","rx-4"],"subcarrier_order":(-122..=122).collect::<Vec<_>>(),
            "hampel_window_seconds":0.02,"hampel_threshold":100.0,"hampel_mad_scale":1.4826,"hampel_min_periods":3,
            "future_context_ns":10000000,"preceding_context_ns":18333334,"segment_gap_ns":1000000000,
            "difference_boundary":"missing-first","transform_casts":"f64-hampel-difference-square-log1p-to-f32",
            "tensor_layout":"batch,time,980-signals,980-validity,4-presence"})).unwrap()
    }
    #[test]
    fn differences_missingness_normalization_and_edges() {
        let mut magnitude: Vec<_> = (0..7)
            .flat_map(|row| std::iter::repeat_n(row as f64, SIGNALS))
            .collect();
        magnitude[2 * SIGNALS + 245] = f64::NAN;
        let snapshot = Snapshot {
            generation: 4,
            first_round: 0,
            magnitude,
            presence: vec![[true; 4]; 7],
            capture_ns: vec![[None; 4]; 7],
        };
        let times: Vec<_> = (0..7).map(|i| i as f64 / 120.0).collect();
        let normalizer = Normalizer::new(vec![0.0; SIGNALS], vec![1.0; SIGNALS]).unwrap();
        let prepared = prepare(
            &snapshot,
            &times,
            0..7,
            SegmentEdges {
                start: true,
                end: true,
            },
            &contract(),
            &normalizer,
        )
        .unwrap();
        assert_eq!(prepared.generation, 4);
        assert_eq!(prepared.model_input.len(), 7 * 1964);
        assert!(prepared.transformed[..SIGNALS].iter().all(|v| v.is_nan()));
        assert_eq!(prepared.transformed[SIGNALS], 2.0f64.ln() as f32);
        assert!(prepared.transformed[2 * SIGNALS + 245].is_nan());
        assert!(prepared.transformed[3 * SIGNALS + 245].is_nan());
        assert_eq!(prepared.model_input[980], 0.0);
        assert_eq!(prepared.model_input[1960], 1.0);
        assert!(
            prepare(
                &snapshot,
                &times,
                0..7,
                SegmentEdges {
                    start: false,
                    end: false
                },
                &contract(),
                &normalizer
            )
            .is_err()
        );
        assert!(
            prepare(
                &snapshot,
                &times,
                3..7,
                SegmentEdges {
                    start: false,
                    end: false
                },
                &contract(),
                &normalizer
            )
            .is_err()
        );
    }
    #[test]
    fn finalization_context_and_publication_deadline_are_separate() {
        let timing =
            crate::stream::WindowTiming::new(0, 2_000_000_000, 100_000_000, 900_000_000).unwrap();
        let prepared = || Prepared {
            generation: 2,
            frames: 240,
            filtered: vec![],
            replacements: vec![],
            transformed: vec![],
            model_input: vec![0.0; 240 * 1964],
            coverage: [0.8; 4],
        };
        assert!(
            prepared()
                .into_job("cnn-2s".into(), &timing, 2_999_999_999, 250_000_000)
                .is_err()
        );
        let job = prepared()
            .into_job("cnn-2s".into(), &timing, 3_000_000_000, 250_000_000)
            .unwrap();
        assert_eq!(job.end_ns, 2_000_000_000);
        assert_eq!(job.finalized_ns, 3_000_000_000);
        assert_eq!(job.deadline_ns, 3_500_000_000);
        assert!(
            prepared()
                .into_job("cnn-2s".into(), &timing, 3_500_000_001, 250_000_000)
                .is_err()
        );
    }
}
