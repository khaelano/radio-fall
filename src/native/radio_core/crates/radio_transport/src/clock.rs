//! Bounded low-delay clock fit matching acquisition/clock_sync.py.
use std::collections::VecDeque;

/// Linux monotonic clock shared with Python monotonic timestamps, in microseconds.
#[cfg(target_os = "linux")]
pub fn monotonic_us() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: initialized writable timespec; CLOCK_MONOTONIC is supported on Linux.
    let result = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    assert_eq!(result, 0, "CLOCK_MONOTONIC unavailable");
    ts.tv_sec as u64 * 1_000_000 + ts.tv_nsec as u64 / 1000
}

/// Four timestamps in microseconds; t1/t4 belong to the reference clock.
#[derive(Clone, Copy)]
pub struct Sample {
    pub boot: u32,
    pub t1: u64,
    pub t2: u64,
    pub t3: u64,
    pub t4: u64,
}

impl Sample {
    /// Decode the existing 72-byte CSYS v1 exchange without changing units.
    pub fn decode(bytes: &[u8]) -> Result<Self, String> {
        use crate::wire::{u16be, u32be, u64be};
        if bytes.len() != 72
            || &bytes[..4] != b"CSYS"
            || bytes[4] != 1
            || bytes[5] != 0
            || u16be(bytes, 6) != 72
            || u32be(bytes, 20) != 0
            || u16be(bytes, 70) != 0
        {
            return Err("invalid clock exchange payload".into());
        }
        let sample = Self {
            boot: u32be(bytes, 16),
            t1: u64be(bytes, 24),
            t2: u64be(bytes, 32),
            t3: u64be(bytes, 40),
            t4: u64be(bytes, 48),
        };
        sample.rtt()?;
        Ok(sample)
    }
    fn rtt(self) -> Result<u64, String> {
        self.t4
            .checked_sub(self.t1)
            .and_then(|v| {
                self.t3
                    .checked_sub(self.t2)
                    .and_then(|turn| v.checked_sub(turn))
            })
            .ok_or("invalid clock exchange ordering or turnaround".into())
    }
    fn midpoint(self) -> f64 {
        (self.t1 as f64 + self.t4 as f64) / 2.0
    }
    fn offset(self) -> f64 {
        ((self.t2 as i128 - self.t1 as i128) + (self.t3 as i128 - self.t4 as i128)) as f64 / 2.0
    }
}

/// Affine receiver-to-reference estimate and measured delay uncertainty.
#[derive(Debug, Clone)]
pub struct Estimate {
    pub boot: u32,
    pub reference_us: f64,
    pub offset_us: f64,
    pub drift_ppm: f64,
    pub uncertainty_us: f64,
    pub sample_count: usize,
    pub minimum_rtt_us: u64,
}

impl Estimate {
    /// Map receiver time without confusing USB delivery time with capture time.
    pub fn map(&self, receiver_us: f64) -> Result<f64, String> {
        let slope = self.drift_ppm / 1_000_000.0;
        let value = (receiver_us - self.offset_us + slope * self.reference_us) / (1.0 + slope);
        if !receiver_us.is_finite() || !value.is_finite() || slope <= -1.0 {
            return Err("invalid clock map".into());
        }
        Ok(value)
    }
}

/// Small bounded sample ledger; reboot/backward reference clocks reset it.
pub struct Estimator {
    samples: VecDeque<Sample>,
    capacity: usize,
    minimum_span_us: u64,
    pub generation: u64,
}

impl Estimator {
    /// Retain preflight sample evidence for deterministic native replay.
    pub fn samples(&self) -> impl Iterator<Item = &Sample> {
        self.samples.iter()
    }
    /// Configure sample capacity and the minimum baseline for a drift estimate.
    pub fn new(capacity: usize, minimum_span_us: u64) -> Result<Self, String> {
        if !(2..=4096).contains(&capacity) {
            return Err("clock capacity must be 2..4096".into());
        }
        Ok(Self {
            samples: VecDeque::new(),
            capacity,
            minimum_span_us,
            generation: 0,
        })
    }

    /// Validate and add an exchange, then fit low-delay samples in arrival order.
    pub fn add(&mut self, sample: Sample) -> Result<Estimate, String> {
        sample.rtt()?;
        if self
            .samples
            .back()
            .is_some_and(|old| old.boot != sample.boot || sample.t4 < old.t4)
        {
            self.generation = self
                .generation
                .checked_add(1)
                .ok_or("clock generation exhausted")?;
            self.samples.clear();
        }
        if self.samples.len() == self.capacity {
            self.samples.pop_front();
        }
        self.samples.push_back(sample);
        let minimum_rtt_us = self.samples.iter().map(|s| s.rtt().unwrap()).min().unwrap();
        let ceiling = minimum_rtt_us.saturating_add(250.max(minimum_rtt_us / 4));
        let selected: Vec<_> = self
            .samples
            .iter()
            .filter(|s| s.rtt().unwrap() <= ceiling)
            .collect();
        let reference_us = selected.last().unwrap().midpoint();
        let count = selected.len() as f64;
        let xs: Vec<_> = selected
            .iter()
            .map(|s| s.midpoint() - reference_us)
            .collect();
        let offsets: Vec<_> = selected.iter().map(|s| s.offset()).collect();
        let mean_x = xs.iter().sum::<f64>() / count;
        let mean_offset = offsets.iter().sum::<f64>() / count;
        let mut slope = 0.0;
        if selected.len() >= 3
            && reference_us - selected[0].midpoint() >= self.minimum_span_us as f64
        {
            let denominator = xs.iter().map(|x| (x - mean_x).powi(2)).sum::<f64>();
            if denominator > 0.0 {
                slope = xs
                    .iter()
                    .zip(&offsets)
                    .map(|(x, o)| (x - mean_x) * (o - mean_offset))
                    .sum::<f64>()
                    / denominator;
            }
        }
        let offset_us = mean_offset - slope * mean_x;
        let rms = (xs
            .iter()
            .zip(&offsets)
            .map(|(x, o)| (o - (offset_us + slope * x)).powi(2))
            .sum::<f64>()
            / count)
            .sqrt();
        Ok(Estimate {
            boot: sample.boot,
            reference_us,
            offset_us,
            drift_ppm: slope * 1_000_000.0,
            uncertainty_us: minimum_rtt_us as f64 / 2.0 + rms,
            sample_count: selected.len(),
            minimum_rtt_us,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matches_python_affine_fixture() {
        let mut estimator = Estimator::new(32, 1_000_000).unwrap();
        let mut fit = None;
        for i in 0..5 {
            let t = i * 1_000_000;
            fit = Some(
                estimator
                    .add(Sample {
                        boot: 7,
                        t1: t,
                        t2: t + 150 + i * 10,
                        t3: t + 160 + i * 10,
                        t4: t + 110,
                    })
                    .unwrap(),
            );
        }
        let fit = fit.unwrap();
        // Verified with the current Python ClockSyncEstimator on identical exchanges.
        assert_eq!(fit.reference_us, 4000055.0);
        assert_eq!(fit.offset_us, 140.0);
        assert_eq!(fit.drift_ppm, 10.0);
        assert_eq!(fit.uncertainty_us, 50.0);
        assert!((fit.map(4000200.0).unwrap() - 4000059.99995).abs() < 1e-8);
    }
    #[test]
    fn offset_delay_floor_and_reboot() {
        let mut estimator = Estimator::new(32, 1_000_000).unwrap();
        for time in [1000, 2000, 3000] {
            let fit = estimator
                .add(Sample {
                    boot: 1,
                    t1: time,
                    t2: time + 150,
                    t3: time + 160,
                    t4: time + 110,
                })
                .unwrap();
            assert_eq!(fit.offset_us, 100.0);
            assert_eq!(fit.minimum_rtt_us, 100);
            assert_eq!(fit.map(time as f64 + 100.0).unwrap(), time as f64);
        }
        let fit = estimator
            .add(Sample {
                boot: 2,
                t1: 1,
                t2: 151,
                t3: 161,
                t4: 111,
            })
            .unwrap();
        assert_eq!(fit.sample_count, 1);
        assert_eq!(estimator.generation, 1);
        assert!(
            estimator
                .add(Sample {
                    boot: 2,
                    t1: 10,
                    t2: 100,
                    t3: 200,
                    t4: 20
                })
                .is_err()
        );
    }
}
