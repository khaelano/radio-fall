//! Linux serial ownership shared by native headless consumers.
use crate::framing::{Decoder, Frame, encode};
use std::{
    fs::{File, OpenOptions},
    io::{self, Read, Write},
    os::fd::AsRawFd,
    path::Path,
};

/// Exclusive serial connection. Timeout-bounded reads retain native framing state.
pub struct Serial {
    file: File,
    decoder: Decoder,
}

impl Serial {
    /// Open raw 115200 baud USB serial without changing firmware configuration.
    pub fn open(path: &Path) -> io::Result<Self> {
        let file = OpenOptions::new().read(true).write(true).open(path)?;
        let fd = file.as_raw_fd();
        // SAFETY: the owned descriptor remains valid, and termios storage is initialized.
        unsafe {
            if libc::ioctl(fd, libc::TIOCEXCL) < 0 {
                return Err(io::Error::last_os_error());
            }
            let mut settings: libc::termios = std::mem::zeroed();
            if libc::tcgetattr(fd, &mut settings) < 0 {
                return Err(io::Error::last_os_error());
            }
            libc::cfmakeraw(&mut settings);
            settings.c_cflag |= libc::CLOCAL | libc::CREAD;
            settings.c_cflag &= !libc::CRTSCTS;
            settings.c_cc[libc::VMIN] = 0;
            settings.c_cc[libc::VTIME] = 2;
            if libc::cfsetispeed(&mut settings, libc::B115200) < 0
                || libc::cfsetospeed(&mut settings, libc::B115200) < 0
                || libc::tcsetattr(fd, libc::TCSANOW, &settings) < 0
            {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(Self {
            file,
            decoder: Decoder::default(),
        })
    }

    /// Drain at most 4096 bytes and return complete validated frames.
    pub fn read(&mut self) -> io::Result<Vec<Frame>> {
        let mut bytes = [0; 4096];
        let count = self.file.read(&mut bytes)?;
        Ok(self.decoder.feed(&bytes[..count]))
    }

    /// Write one complete CRC-protected control frame or report the I/O failure.
    pub fn write(&mut self, kind: u8, payload: &[u8]) -> io::Result<()> {
        let encoded =
            encode(kind, payload).map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
        self.file.write_all(&encoded)
    }

    /// Return cumulative framing health without exposing packet callbacks.
    pub fn framing_errors(&self) -> (u64, u64) {
        (self.decoder.malformed, self.decoder.oversized)
    }
}

impl Drop for Serial {
    fn drop(&mut self) {
        // SAFETY: the descriptor is still owned and valid during drop.
        unsafe {
            libc::ioctl(self.file.as_raw_fd(), libc::TIOCNXCL);
        }
    }
}
