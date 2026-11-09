use crate::wire::{u16be, u32be};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

pub const MAX_ENCODED: usize = 1412 + 1412 / 254 + 1;
#[derive(Clone)]
pub struct Frame {
    pub kind: u8,
    pub data: Vec<u8>,
}
fn known(v: u8) -> bool {
    matches!(v,1..=14|20..=29|31)
}
pub fn decode(p: &[u8]) -> Result<Frame, String> {
    if p.is_empty() || p.len() > MAX_ENCODED {
        return Err("invalid COBS length".into());
    }
    let mut raw = Vec::with_capacity(p.len());
    let mut i = 0;
    while i < p.len() {
        let code = p[i] as usize;
        i += 1;
        if code == 0 || i + code - 1 > p.len() {
            return Err("truncated COBS frame".into());
        }
        raw.extend_from_slice(&p[i..i + code - 1]);
        i += code - 1;
        if code != 255 && i < p.len() {
            raw.push(0);
        }
    }
    if raw.len() < 12 || &raw[..4] != b"CSIS" || raw[4] != 1 || !known(raw[5]) {
        return Err("invalid serial frame header".into());
    }
    let n = u16be(&raw, 6) as usize;
    if n > 1400 || raw.len() != 12 + n {
        return Err("invalid serial frame length".into());
    }
    if crc32fast::hash(&raw[..8 + n]) != u32be(&raw, 8 + n) {
        return Err("serial frame CRC mismatch".into());
    }
    Ok(Frame {
        kind: raw[5],
        data: raw[8..8 + n].to_vec(),
    })
}
#[derive(Default)]
pub struct Decoder {
    pub pending: Vec<u8>,
    pub synchronized: bool,
    pub dropping: bool,
    pub malformed: u64,
    pub oversized: u64,
}
impl Decoder {
    pub fn feed(&mut self, data: &[u8]) -> Vec<Frame> {
        let mut frames = Vec::new();
        let mut start = 0;
        for end in memchr::memchr_iter(0, data) {
            self.extend(&data[start..end]);
            start = end + 1;
            if !self.synchronized {
                self.synchronized = true;
                self.pending.clear();
                self.dropping = false;
                continue;
            }
            if self.dropping {
                self.dropping = false;
                self.pending.clear();
                continue;
            }
            if !self.pending.is_empty() {
                match decode(&self.pending) {
                    Ok(f) => frames.push(f),
                    Err(_) => self.malformed += 1,
                };
                self.pending.clear();
            }
        }
        self.extend(&data[start..]);
        frames
    }
    fn extend(&mut self, p: &[u8]) {
        if !self.synchronized || self.dropping {
            return;
        }
        if self.pending.len() + p.len() > MAX_ENCODED {
            self.oversized += 1;
            self.pending.clear();
            self.dropping = true;
            return;
        }
        self.pending.extend_from_slice(p);
    }
}
#[pyclass]
#[derive(Default)]
pub struct FrameDecoder {
    inner: Decoder,
}
#[pymethods]
impl FrameDecoder {
    #[new]
    fn new() -> Self {
        Self::default()
    }
    #[getter]
    fn malformed_frames(&self) -> u64 {
        self.inner.malformed
    }
    #[getter]
    fn oversized_frames(&self) -> u64 {
        self.inner.oversized
    }
    fn feed<'py>(&mut self, py: Python<'py>, data: &[u8]) -> Vec<(u8, Bound<'py, PyBytes>)> {
        let frames = py.detach(|| self.inner.feed(data));
        frames
            .into_iter()
            .map(|f| (f.kind, PyBytes::new(py, &f.data)))
            .collect()
    }
}
#[pyfunction]
pub fn encode_frame<'py>(
    py: Python<'py>,
    kind: u8,
    payload: &[u8],
) -> PyResult<Bound<'py, PyBytes>> {
    if !known(kind) || payload.len() > 1400 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "unknown type or oversized serial payload",
        ));
    }
    let encoded = py.detach(|| {
        let mut raw = Vec::with_capacity(12 + payload.len());
        raw.extend_from_slice(b"CSIS");
        raw.extend_from_slice(&[1, kind]);
        raw.extend_from_slice(&(payload.len() as u16).to_be_bytes());
        raw.extend_from_slice(payload);
        let crc = crc32fast::hash(&raw);
        raw.extend_from_slice(&crc.to_be_bytes());
        let mut out = vec![0, 0];
        let (mut index, mut code) = (1usize, 1u8);
        for b in raw {
            if b == 0 {
                out[index] = code;
                index = out.len();
                out.push(0);
                code = 1;
            } else {
                out.push(b);
                code += 1;
                if code == 255 {
                    out[index] = code;
                    index = out.len();
                    out.push(0);
                    code = 1;
                }
            }
        }
        out[index] = code;
        out.push(0);
        out
    });
    Ok(PyBytes::new(py, &encoded))
}
