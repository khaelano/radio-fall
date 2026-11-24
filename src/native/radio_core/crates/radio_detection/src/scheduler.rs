//! Bounded latest-window scheduling, independent of transport and inference.
use std::{collections::BTreeMap, sync::Arc};

/// Immutable prepared input and capture/finalization clocks, all in nanoseconds.
#[derive(Clone, Debug)]
pub struct Job {
    pub model_id: String,
    pub generation: u64,
    pub start_ns: u64,
    pub end_ns: u64,
    pub finalized_ns: u64,
    pub deadline_ns: u64,
    pub coverage: [f32; 4],
    pub frames: usize,
    pub input: Arc<[f32]>,
}

/// Explicit result state: unknown never becomes a non-fall decision.
#[derive(Debug, PartialEq)]
pub enum Outcome {
    Score { logit: f32, sigmoid: f32 },
    Unknown(&'static str),
}

/// One active call and at most one pending job for each selected model.
pub struct Scheduler {
    pending: BTreeMap<String, Option<Job>>,
    active: Option<Job>,
    latest_end: BTreeMap<String, u64>,
    generation: u64,
    minimum_coverage: f32,
    maximum_age_ns: u64,
    pub replacements: u64,
}

impl Scheduler {
    pub fn pending_count(&self) -> usize {
        self.pending.values().filter(|slot| slot.is_some()).count()
    }
    pub fn active_model(&self) -> Option<&str> {
        self.active.as_ref().map(|job| job.model_id.as_str())
    }
    pub fn generation(&self) -> u64 {
        self.generation
    }
    /// Construct explicit operational coverage and freshness policies.
    pub fn new(
        models: Vec<String>,
        minimum_coverage: f32,
        maximum_age_ns: u64,
    ) -> Result<Self, String> {
        if models.is_empty()
            || models.len() > crate::bundle::MAX_MODELS
            || !(0.0..=1.0).contains(&minimum_coverage)
            || maximum_age_ns == 0
        {
            return Err("invalid scheduler configuration".into());
        }
        let count = models.len();
        let pending: BTreeMap<_, _> = models.into_iter().map(|id| (id, None)).collect();
        if pending.len() != count || pending.keys().any(String::is_empty) {
            return Err("model IDs must be unique and nonempty".into());
        }
        Ok(Self {
            pending,
            active: None,
            latest_end: BTreeMap::new(),
            generation: 0,
            minimum_coverage,
            maximum_age_ns,
            replacements: 0,
        })
    }

    /// Invalidate pending and active results together; an active call must still finish.
    pub fn reset(&mut self) -> Result<u64, String> {
        self.generation = self
            .generation
            .checked_add(1)
            .ok_or("generation exhausted")?;
        for slot in self.pending.values_mut() {
            *slot = None;
        }
        self.latest_end.clear();
        Ok(self.generation)
    }

    /// Replace only with a newer immutable window from the current generation.
    pub fn submit(&mut self, job: Job) -> Result<(), String> {
        let slot = self
            .pending
            .get_mut(&job.model_id)
            .ok_or("unselected model")?;
        if job.generation != self.generation {
            return Err("stale generation".into());
        }
        if self
            .latest_end
            .get(&job.model_id)
            .is_some_and(|&end| end >= job.end_ns)
        {
            return Err("superseded window".into());
        }
        if job.start_ns >= job.end_ns
            || job.finalized_ns < job.end_ns
            || job.deadline_ns < job.finalized_ns
            || job.frames == 0
            || job.frames.checked_mul(1964) != Some(job.input.len())
            || job
                .coverage
                .iter()
                .any(|c| !c.is_finite() || !(0.0..=1.0).contains(c))
        {
            return Err("invalid prepared window".into());
        }
        if slot.as_ref().is_some_and(|old| old.end_ns >= job.end_ns)
            || self.active.as_ref().is_some_and(|old| {
                old.generation == job.generation
                    && old.model_id == job.model_id
                    && old.end_ns >= job.end_ns
            })
        {
            return Err("superseded window".into());
        }
        self.latest_end.insert(job.model_id.clone(), job.end_ns);
        if slot.replace(job).is_some() {
            self.replacements = self.replacements.saturating_add(1);
        }
        Ok(())
    }

    /// Take the earliest deadline, breaking ties by model ID. No second call starts.
    pub fn take_next(&mut self) -> Option<Job> {
        if self.active.is_some() {
            return None;
        }
        let id = self
            .pending
            .iter()
            .filter_map(|(id, job)| job.as_ref().map(|j| (j.deadline_ns, id)))
            .min()
            .map(|(_, id)| id.clone())?;
        let job = self.pending.get_mut(&id)?.take()?;
        self.active = Some(job.clone());
        Some(job)
    }

    /// Complete the active call and apply validity at publication time.
    pub fn complete(
        &mut self,
        now_ns: u64,
        logit: Result<f32, String>,
    ) -> Result<(Job, Outcome), String> {
        let job = self.active.take().ok_or("no active inference")?;
        let outcome = if job.generation != self.generation {
            Outcome::Unknown("reset")
        } else if now_ns < job.finalized_ns
            || now_ns.saturating_sub(job.end_ns) > self.maximum_age_ns
            || now_ns > job.deadline_ns
        {
            Outcome::Unknown("stale")
        } else if job.coverage.iter().any(|&c| c < self.minimum_coverage)
            || self
                .pending
                .get(&job.model_id)
                .and_then(Option::as_ref)
                .is_some_and(|newer| {
                    newer.end_ns > job.end_ns
                        && newer.coverage.iter().any(|&c| c < self.minimum_coverage)
                })
        {
            Outcome::Unknown("coverage")
        } else {
            match logit {
                Ok(logit) if logit.is_finite() => Outcome::Score {
                    logit,
                    sigmoid: if logit >= 0.0 {
                        1.0 / (1.0 + (-logit).exp())
                    } else {
                        let e = logit.exp();
                        e / (1.0 + e)
                    },
                },
                _ => Outcome::Unknown("runtime-error"),
            }
        };
        Ok((job, outcome))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn job(model: &str, end: u64) -> Job {
        Job {
            model_id: model.into(),
            generation: 0,
            start_ns: 0,
            end_ns: end,
            finalized_ns: end,
            deadline_ns: end + 100,
            coverage: [1.0; 4],
            frames: 1,
            input: vec![0.0; 1964].into(),
        }
    }
    #[test]
    fn replacement_fairness_and_single_active_call() {
        let mut s = Scheduler::new(vec!["b".into(), "a".into()], 0.7, 1000).unwrap();
        s.submit(job("a", 10)).unwrap();
        s.submit(job("a", 20)).unwrap();
        s.submit(job("b", 10)).unwrap();
        assert_eq!(s.replacements, 1);
        assert_eq!(s.take_next().unwrap().model_id, "b");
        assert!(s.take_next().is_none());
        assert!(matches!(
            s.complete(20, Ok(0.0)).unwrap().1,
            Outcome::Score { sigmoid: 0.5, .. }
        ));
        assert_eq!(s.take_next().unwrap().model_id, "a");
        s.reset().unwrap();
        assert_eq!(
            s.complete(20, Ok(-100.0)).unwrap().1,
            Outcome::Unknown("reset")
        );
    }
    #[test]
    fn delayed_and_invalid_results_are_unknown() {
        let mut s = Scheduler::new(vec!["a".into()], 0.7, 1000).unwrap();
        s.submit(job("a", 10)).unwrap();
        s.take_next();
        assert_eq!(
            s.complete(111, Ok(0.0)).unwrap().1,
            Outcome::Unknown("stale")
        );
        let mut low = job("a", 20);
        low.coverage[1] = 0.69;
        s.submit(low).unwrap();
        s.take_next();
        assert_eq!(
            s.complete(21, Ok(-100.0)).unwrap().1,
            Outcome::Unknown("coverage")
        );
    }
    #[test]
    fn newer_bad_coverage_suppresses_older_inflight_score() {
        let mut scheduler = Scheduler::new(vec!["a".into()], 0.7, 1000).unwrap();
        scheduler.submit(job("a", 10)).unwrap();
        scheduler.take_next();
        let mut newer = job("a", 20);
        newer.coverage[0] = 0.5;
        scheduler.submit(newer).unwrap();
        assert_eq!(
            scheduler.complete(21, Ok(10.0)).unwrap().1,
            Outcome::Unknown("coverage")
        );
    }
}
