//! Live-session validation and journal-before-ACK application acceptance.
use crate::{journal::Journal, wire::Batch};
use std::{collections::BTreeMap, sync::Arc};

/// Preflight-verified run identities. Receiver order belongs to deployment metadata.
pub struct Identities {
    pub run: u64,
    pub transmitter_boot: u32,
    pub transmitter_mac: String,
    pub fingerprint: String,
    pub receivers: BTreeMap<String, u32>,
}

/// Complete validated batch and optional application acknowledgement payload.
pub struct Accepted {
    pub batch: Arc<Batch>,
    pub fresh: bool,
    pub acknowledgement: Option<Vec<u8>>,
}

/// Own run identity checks and accepted raw journal; errors require a new run.
pub struct Acceptor {
    identities: Identities,
    journal: Journal,
    acknowledgements: bool,
    failed: bool,
    receiver_boots_verified: bool,
}

impl Acceptor {
    /// Persist native control/reference evidence before using it for acceptance.
    pub fn event(
        &mut self,
        kind: &str,
        now_ns: u64,
        value: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let result = self.journal.event(kind, now_ns, value);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    /// Persist one finalized availability bin; a storage failure latches.
    pub fn bin(&mut self, row: &serde_json::Value) -> Result<(), Box<dyn std::error::Error>> {
        let result = self.journal.bin(row);
        if result.is_err() {
            self.failed = true;
        }
        result
    }

    /// Directory of the run journal owned by this acceptor.
    pub fn journal_directory(&self) -> &std::path::Path {
        self.journal.directory()
    }

    /// Construct only after gateway/reference/receiver preflight has completed.
    pub fn new(
        identities: Identities,
        journal: Journal,
        acknowledgements: bool,
    ) -> Result<Self, String> {
        if identities.run == 0
            || identities.transmitter_mac.is_empty()
            || identities.fingerprint.is_empty()
            || identities.receivers.len() != 4
        {
            return Err("incomplete acquisition identities".into());
        }
        Ok(Self {
            identities,
            journal,
            acknowledgements,
            failed: false,
            receiver_boots_verified: true,
        })
    }

    /// Await current-run receiver status; placeholder boot values are never accepted.
    pub fn awaiting_receivers(
        identities: Identities,
        journal: Journal,
        acknowledgements: bool,
    ) -> Result<Self, String> {
        let mut acceptor = Self::new(identities, journal, acknowledgements)?;
        acceptor.receiver_boots_verified = false;
        Ok(acceptor)
    }

    /// Bind once from the receiver ledger, then reject every boot identity change.
    pub fn verify_receiver_boots(&mut self, boots: BTreeMap<String, u32>) -> Result<(), String> {
        if self.failed || !self.identities.receivers.keys().eq(boots.keys()) {
            return Err("verified receiver set differs from configured inventory".into());
        }
        if self.receiver_boots_verified {
            if boots != self.identities.receivers {
                self.failed = true;
                return Err("receiver boot changed after verification".into());
            }
        } else {
            self.identities.receivers = boots;
            self.receiver_boots_verified = true;
        }
        Ok(())
    }

    /// Journal and pass each new batch to a native sink before releasing its ACK.
    /// An old run is ignored. Any other validation/storage/sink failure latches.
    pub fn accept(
        &mut self,
        bytes: &[u8],
        arrival_ns: u64,
        sink: impl FnOnce(&Batch) -> Result<(), String>,
    ) -> Result<Option<Accepted>, Box<dyn std::error::Error>> {
        if self.failed {
            return Err("acquisition failed; restart required".into());
        }
        if !self.receiver_boots_verified {
            return Err("receiver boot evidence unavailable".into());
        }
        let result = self.accept_inner(bytes, arrival_ns, sink);
        if result.is_err() {
            self.failed = true;
        }
        result
    }

    fn accept_inner(
        &mut self,
        bytes: &[u8],
        arrival_ns: u64,
        sink: impl FnOnce(&Batch) -> Result<(), String>,
    ) -> Result<Option<Accepted>, Box<dyn std::error::Error>> {
        let batch = Batch::decode(bytes)?;
        if batch.run != self.identities.run {
            return Ok(None);
        }
        if batch.tx_boot != self.identities.transmitter_boot
            || self.identities.receivers.get(&batch.mac) != Some(&batch.rx_boot)
        {
            return Err("acquisition identity/boot mismatch".into());
        }
        if batch.records.iter().any(|r| {
            r.fingerprint != self.identities.fingerprint
                || r.transmitter != self.identities.transmitter_mac
        }) {
            return Err("acquisition transmitter/profile mismatch".into());
        }
        let fresh = self.journal.accept(bytes, arrival_ns)?;
        if fresh {
            sink(&batch)?;
        }
        let acknowledgement = if self.acknowledgements {
            let mut ack = Vec::with_capacity(34);
            ack.extend_from_slice(b"CGAK");
            ack.extend_from_slice(&batch.run.to_be_bytes());
            ack.extend_from_slice(&batch.tx_boot.to_be_bytes());
            ack.extend_from_slice(&batch.rx_boot.to_be_bytes());
            ack.extend_from_slice(&batch.id.to_be_bytes());
            ack.extend_from_slice(&bytes[28..34]);
            ack.extend_from_slice(&crc32fast::hash(&ack).to_be_bytes());
            Some(ack)
        } else {
            None
        };
        Ok(Some(Accepted {
            batch,
            fresh,
            acknowledgement,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (Vec<u8>, Acceptor) {
        let bytes = std::fs::read(std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()).unwrap();
        let batch = Batch::decode(&bytes).unwrap();
        let mut receivers = BTreeMap::from([(batch.mac.clone(), batch.rx_boot)]);
        for id in 1..=3 {
            receivers.insert(format!("00:00:00:00:00:{id:02x}"), 1);
        }
        let identities = Identities {
            run: batch.run,
            transmitter_boot: batch.tx_boot,
            transmitter_mac: batch.records[0].transmitter.clone(),
            fingerprint: batch.records[0].fingerprint.clone(),
            receivers,
        };
        let root = std::env::temp_dir().join(format!(
            "radio-acceptance-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let journal =
            Journal::create(&root, batch.run, serde_json::json!({"source":"test"})).unwrap();
        (bytes, Acceptor::new(identities, journal, true).unwrap())
    }
    #[test]
    #[ignore = "requires RADIO_JOURNAL_FIXTURE and matching .ack file"]
    fn native_sink_acceptance_and_python_ack_parity() {
        let (bytes, mut acceptor) = fixture();
        let mut calls = 0;
        let result = acceptor
            .accept(&bytes, 10, |_| {
                calls += 1;
                Ok(())
            })
            .unwrap()
            .unwrap();
        assert!(result.fresh);
        let expected = std::fs::read(format!(
            "{}.ack",
            std::env::var("RADIO_JOURNAL_FIXTURE").unwrap()
        ))
        .unwrap();
        assert_eq!(result.acknowledgement.unwrap(), expected);
        assert!(
            !acceptor
                .accept(&bytes, 11, |_| {
                    calls += 1;
                    Ok(())
                })
                .unwrap()
                .unwrap()
                .fresh
        );
        assert_eq!(calls, 1);
        let (bytes, mut failing) = fixture();
        assert!(
            failing
                .accept(&bytes, 10, |_| Err("sink failed".into()))
                .is_err()
        );
        assert!(failing.accept(&bytes, 11, |_| Ok(())).is_err());
        let (bytes, mut waiting) = fixture();
        let boots = waiting.identities.receivers.clone();
        waiting.receiver_boots_verified = false;
        waiting
            .identities
            .receivers
            .values_mut()
            .for_each(|boot| *boot = 0);
        assert!(
            waiting
                .accept(&bytes, 12, |_| panic!(
                    "sink must not run before receiver verification"
                ))
                .is_err()
        );
        waiting.verify_receiver_boots(boots.clone()).unwrap();
        assert!(
            waiting
                .accept(&bytes, 13, |_| Ok(()))
                .unwrap()
                .unwrap()
                .fresh
        );
        let mut rebooted = boots;
        *rebooted.values_mut().next().unwrap() ^= 1;
        assert!(waiting.verify_receiver_boots(rebooted).is_err());
        assert!(waiting.accept(&bytes, 14, |_| Ok(())).is_err());
    }
}
