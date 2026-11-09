use crate::numeric::{self, Phase};
use std::fmt::Write;
use std::sync::{Arc, OnceLock};

pub const MAX_ENVELOPE: usize = 1400;
pub fn u16be(p: &[u8], i: usize) -> u16 {
    u16::from_be_bytes(p[i..i + 2].try_into().unwrap())
}
pub fn u32be(p: &[u8], i: usize) -> u32 {
    u32::from_be_bytes(p[i..i + 4].try_into().unwrap())
}
pub fn u64be(p: &[u8], i: usize) -> u64 {
    u64::from_be_bytes(p[i..i + 8].try_into().unwrap())
}
pub fn mac(p: &[u8]) -> String {
    format!(
        "{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}",
        p[0], p[1], p[2], p[3], p[4], p[5]
    )
}

pub struct Record {
    pub wire: Arc<[u8]>,
    pub sequence: u32,
    pub transport_sequence: u32,
    pub timestamp: u32,
    pub receiver: String,
    pub transmitter: String,
    pub fingerprint: String,
    pub tx_timestamp: u64,
    pub callback: u64,
    pub flags: u8,
    pub rssi: i8,
    pub noise: i8,
    pub fields: [u8; 15],
    pub sig_len: u16,
    pub raw: Arc<[u8]>,
    pub mean_i: f64,
    pub mean_q: f64,
    pub phase: Option<Arc<Phase>>,
    pub csv: OnceLock<String>,
}
impl Record {
    pub fn decode(p: &[u8]) -> Result<Arc<Self>, String> {
        if p.len() < 87 || &p[..4] != b"CSI1" || p[4] != 3 || p[5] & !3 != 0 || u16be(p, 6) != 87 {
            return Err("unsupported live CSI header".into());
        }
        let n = u16be(p, 8) as usize;
        if n == 0 || n > 612 || n % 2 != 0 || n != u16be(p, 53) as usize || p.len() != 87 + n {
            return Err("invalid CSI payload length".into());
        }
        let fingerprint = std::str::from_utf8(&p[71..87])
            .map_err(|_| "invalid fingerprint")?
            .trim_end_matches('\0')
            .to_string();
        if fingerprint.len() != 16 || !fingerprint.bytes().all(|c| c.is_ascii_hexdigit()) {
            return Err("invalid profile fingerprint".into());
        }
        let raw: Arc<[u8]> = p[87..].into();
        let (amplitudes, mut si, mut sq) = numeric::iq(&raw);
        let invalid = p[5] & 1 != 0;
        let skip = if invalid { 2.min(n / 2) } else { 0 };
        for pair in raw[..skip * 2].chunks_exact(2) {
            si -= pair[1] as i8 as i64;
            sq -= pair[0] as i8 as i64;
        }
        let count = n / 2 - skip;
        let mean_i = if count > 0 {
            si as f64 / count as f64
        } else {
            f64::NAN
        };
        let mean_q = if count > 0 {
            sq as f64 / count as f64
        } else {
            f64::NAN
        };
        let fields: [u8; 15] = p[36..51].try_into().unwrap();
        let phase = numeric::phase(&raw, fields[1], fields[3], fields[7], invalid, amplitudes)
            .map(Arc::new);
        let r = Arc::new(Self {
            wire: p.into(),
            sequence: u32be(p, 26),
            transport_sequence: u32be(p, 22),
            timestamp: u32be(p, 30),
            receiver: mac(&p[10..16]),
            transmitter: mac(&p[16..22]),
            fingerprint,
            tx_timestamp: u64be(p, 55),
            callback: u64be(p, 63),
            flags: p[5],
            rssi: p[34] as i8,
            noise: p[35] as i8,
            fields,
            sig_len: u16be(p, 51),
            raw,
            mean_i,
            mean_q,
            phase,
            csv: OnceLock::new(),
        });
        let _ = r.csv.set(r.format_csv());
        Ok(r)
    }
    fn format_csv(&self) -> String {
        let f = &self.fields;
        let mut s = format!(
            "CSI_DATA,{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},\"[",
            self.sequence,
            self.transmitter,
            self.rssi,
            f[0],
            f[1],
            f[2],
            f[3],
            f[4],
            f[5],
            f[6],
            f[7],
            f[8],
            f[9],
            self.noise,
            f[10],
            f[11],
            f[12],
            self.timestamp,
            f[13],
            self.sig_len,
            f[14],
            self.raw.len(),
            u8::from(self.flags & 1 != 0)
        );
        for (i, v) in self.raw.iter().enumerate() {
            if i > 0 {
                s.push(',');
            }
            let _ = write!(s, "{}", *v as i8);
        }
        s.push_str("]\"");
        s
    }
}

#[derive(Clone)]
pub struct Batch {
    pub run: u64,
    pub tx_boot: u32,
    pub rx_boot: u32,
    pub id: u32,
    pub mac: String,
    pub payload: Arc<[u8]>,
    pub stats: [u32; 10],
    pub records: Vec<Arc<Record>>,
}
impl Batch {
    pub fn decode(p: &[u8]) -> Result<Arc<Self>, String> {
        if p.len() <= 44
            || p.len() > MAX_ENVELOPE
            || &p[..4] != b"CGWY"
            || p[4] != 1
            || p[5] != 0
            || u16be(p, 6) != 40
            || u32be(p, 36) != 0
        {
            return Err("invalid gateway envelope header".into());
        }
        if crc32fast::hash(&p[..p.len() - 4]) != u32be(p, p.len() - 4) {
            return Err("gateway envelope CRC mismatch".into());
        }
        let run = u64be(p, 8);
        let (tx_boot, rx_boot, id) = (u32be(p, 16), u32be(p, 20), u32be(p, 24));
        let payload = &p[40..p.len() - 4];
        if run == 0 || payload.len() != u16be(p, 34) as usize || payload.len() < 60 {
            return Err("invalid envelope length/identity".into());
        }
        if &payload[..4] != b"CSIB"
            || payload[4] != 1
            || payload[5] != 0
            || u16be(payload, 6) != 60
            || u32be(payload, 8) != rx_boot
            || u32be(payload, 12) != id
            || u16be(payload, 18) != 0
        {
            return Err("invalid nested batch header/identity".into());
        }
        let count = u16be(payload, 16) as usize;
        if !(1..=4).contains(&count) {
            return Err("invalid record count".into());
        }
        let mut offset = 60;
        let mut records = Vec::with_capacity(count);
        let receiver = mac(&p[28..34]);
        for _ in 0..count {
            if offset + 2 > payload.len() {
                return Err("truncated record length".into());
            }
            let n = u16be(payload, offset) as usize;
            offset += 2;
            if offset + n > payload.len() {
                return Err("truncated record".into());
            }
            let r = Record::decode(&payload[offset..offset + n])?;
            offset += n;
            if r.receiver != receiver {
                return Err("nested receiver identity mismatch".into());
            }
            records.push(r);
        }
        if offset != payload.len() {
            return Err("trailing batch bytes".into());
        }
        let mut stats = [0u32; 10];
        for (i, v) in stats.iter_mut().enumerate() {
            *v = u32be(payload, 20 + 4 * i);
        }
        Ok(Arc::new(Self {
            run,
            tx_boot,
            rx_boot,
            id,
            mac: receiver,
            payload: payload.into(),
            stats,
            records,
        }))
    }
}
