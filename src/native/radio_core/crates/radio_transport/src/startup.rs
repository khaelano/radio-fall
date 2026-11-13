//! Native preflight and configuration ordering for the current relay transport.
use crate::{
    acquisition::FrameIo,
    clock::{Estimate, Estimator},
    control::Controller,
    wire::{mac, u32be, u64be},
};
use std::time::Duration;

/// Verified preflight evidence; configuration does not itself authorize scores.
pub struct Configured {
    pub run: u64,
    pub gateway_boot: u64,
    pub transmitter_boot: u32,
    pub reference_drops: u32,
    pub clock: Estimate,
    pub estimator: Estimator,
    pub gateway_mac: String,
    pub transmitter_mac: String,
    pub receivers: [String; 4],
    pub fingerprint: String,
}

/// Validate the existing CGCF v7 wire configuration without inventing defaults.
pub fn validate_config(bytes: &[u8]) -> Result<(), String> {
    if bytes.len() != 108
        || &bytes[..4] != b"CGCF"
        || bytes[4] != 7
        || bytes[5] != 4
        || u64be(bytes, 8) == 0
        || crc32fast::hash(&bytes[..104]) != u32be(bytes, 104)
    {
        return Err("invalid four-receiver CGCF v7 configuration".into());
    }
    let identities: std::collections::BTreeSet<_> =
        (0..4).map(|i| &bytes[44 + i * 6..50 + i * 6]).collect();
    if identities.len() != 4 || identities.iter().any(|mac| mac.iter().all(|&b| b == 0)) {
        return Err("receiver identities must be distinct and nonzero".into());
    }
    if !bytes[68..100].iter().all(u8::is_ascii_hexdigit) {
        return Err("invalid profile/transport fingerprint".into());
    }
    Ok(())
}

/// Copy an operational configuration with a fresh nonzero acquisition run.
pub fn with_run(config: &[u8], run: u64) -> Result<Vec<u8>, String> {
    validate_config(config)?;
    if run == 0 {
        return Err("acquisition run must be nonzero".into());
    }
    let mut bytes = config.to_vec();
    bytes[8..16].copy_from_slice(&run.to_be_bytes());
    let crc = crc32fast::hash(&bytes[..104]);
    bytes[104..108].copy_from_slice(&crc.to_be_bytes());
    Ok(bytes)
}

/// Bring the gateway to an idle, relay-ready state before configuring a run.
///
/// A gateway still configured for an earlier run is stopped. After a failed
/// run (`recovering`), a faulted relay epoch is restarted when the firmware
/// supports it. The call then waits a bounded time for relay readiness.
pub fn prepare<T: FrameIo>(
    controller: &mut Controller<T>,
    gateway_mac: &str,
    recovering: bool,
    ready_timeout: Duration,
) -> Result<(), String> {
    let mut status = controller.discover(false, Duration::from_secs(2))?;
    if status["role"] != "gateway" || status["target"] != "esp32c6" || status["mac"] != gateway_mac
    {
        return Err("gateway preflight identity mismatch".into());
    }
    if status["configured"] == true {
        let previous = status["run_id"]
            .as_str()
            .and_then(|value| value.parse::<u64>().ok())
            .or_else(|| status["run_id"].as_u64())
            .ok_or("configured gateway lacks its run identity")?;
        let mut stop = b"CGSP".to_vec();
        stop.extend_from_slice(&previous.to_be_bytes());
        controller.command(false, &stop, Duration::from_secs(2))?;
    }
    let faulted = status["relay_fault"] == true;
    if recovering && faulted {
        if status["relay_recovery_version"] != 1 {
            return Err("gateway firmware lacks automatic relay recovery".into());
        }
        controller.recover_relay(Duration::from_secs(2))?;
    }
    let deadline = std::time::Instant::now() + ready_timeout;
    while status["relay_ready"] != true || status["relay_fault"] == true {
        if std::time::Instant::now() >= deadline {
            return Err("wireless reference handshake timed out".into());
        }
        std::thread::sleep(Duration::from_millis(200));
        status = controller.discover(false, Duration::from_secs(2))?;
    }
    Ok(())
}

/// Discover identities, fit the reference, then configure gateway and transmitter.
/// The caller supplies an already validated operational configuration. No CGGO
/// command is sent; receiver evidence and sensing activation remain separate.
pub fn configure<T: FrameIo>(
    controller: &mut Controller<T>,
    config: &[u8],
    clock_us: impl Fn() -> u64,
) -> Result<Configured, String> {
    validate_config(config)?;
    let gateway_mac = mac(&config[32..38]);
    let transmitter_mac = mac(&config[38..44]);
    let fingerprint = std::str::from_utf8(&config[68..84])
        .map_err(|e| e.to_string())?
        .to_owned();
    let gateway = controller.discover(false, Duration::from_secs(2))?;
    if gateway["mac"] != gateway_mac
        || gateway["role"] != "gateway"
        || gateway["target"] != "esp32c6"
        || gateway["protocol_version"] != 3
        || gateway["ready"] != true
        || gateway["relay_ready"] != true
        || gateway["relay_paired"] != true
        || gateway["relay_transport"] != "espnow_uart"
        || gateway["transport_config_max_version"]
            .as_u64()
            .unwrap_or(0)
            < 7
    {
        return Err("gateway preflight identity/capability mismatch".into());
    }
    if gateway["configured"] != false {
        return Err("gateway already configured; explicit run shutdown required".into());
    }
    let transmitter = controller.discover(true, Duration::from_secs(2))?;
    if transmitter["mac"] != transmitter_mac
        || transmitter["role"] != "transmitter"
        || transmitter["target"] != "esp32c5"
        || transmitter["protocol_version"] != 3
        || transmitter["ready"] != true
        || transmitter["profile_fingerprint"] != fingerprint
        || transmitter["sensing_phy"] != "he20"
        || transmitter["sensing_version"] != 4
        || transmitter["transport_config_max_version"]
            .as_u64()
            .unwrap_or(0)
            < 7
    {
        return Err("transmitter preflight identity/profile/capability mismatch".into());
    }
    let mut estimator = Estimator::new(32, 10_000_000)?;
    let mut evidence = None;
    for id in 0..8 {
        let (sample, drops) = controller.sync(id, &clock_us)?;
        if evidence
            .as_ref()
            .is_some_and(|(old_boot, old_drops, _)| *old_boot != sample.boot || *old_drops != drops)
        {
            return Err("transmitter reboot or reference log loss during preflight".into());
        }
        evidence = Some((sample.boot, drops, estimator.add(sample)?));
    }
    let (transmitter_boot, reference_drops, clock) = evidence.unwrap();
    let run = u64be(config, 8);
    let gateway_boot = gateway["boot_id"].as_u64().ok_or("missing gateway boot")?;
    let mut bind = b"CGTB".to_vec();
    bind.extend_from_slice(&run.to_be_bytes());
    bind.extend_from_slice(&transmitter_boot.to_be_bytes());
    let configured = (|| {
        controller.command(false, config, Duration::from_secs(2))?;
        controller.command(false, &bind, Duration::from_secs(2))?;
        controller.command(true, config, Duration::from_secs(2))
    })();
    if let Err(error) = configured {
        let cleanup = controller.stop_run(run);
        return Err(match cleanup {
            Ok(()) => error,
            Err(cleanup) => format!("{error}; stop writes failed: {cleanup}"),
        });
    }
    Ok(Configured {
        run,
        gateway_boot,
        transmitter_boot,
        reference_drops,
        clock,
        estimator,
        gateway_mac,
        transmitter_mac,
        receivers: std::array::from_fn(|i| mac(&config[44 + i * 6..50 + i * 6])),
        fingerprint,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_configuration_is_rejected_before_io() {
        for bytes in [vec![], vec![0; 107], vec![0; 108], vec![0; 109]] {
            assert!(validate_config(&bytes).is_err());
        }
    }
}
