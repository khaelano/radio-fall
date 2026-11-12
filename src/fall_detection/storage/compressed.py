"""Logical access to independently framed Zstandard recording files."""

import io
from contextlib import contextmanager
from pathlib import Path


class _Decoded(io.RawIOBase):
    def __init__(self, source):
        import zstandard as zstd

        self.source = source
        self.decoder = zstd.ZstdDecompressor().decompressobj()
        self.buffer = bytearray()
        self.offset = 0
        self.finished = False
        self.complete = True  # Empty streams have no admitted data.

    def readable(self):
        return True

    def readinto(self, target):
        import zstandard as zstd

        while self.offset == len(self.buffer) and not self.finished:
            self.buffer.clear()
            self.offset = 0
            data = self.source.read(65536)
            if not data:
                if not self.complete:
                    raise OSError("Truncated Zstandard recording frame")
                self.finished = True
                break
            while data:
                if self.decoder.eof:
                    self.decoder = zstd.ZstdDecompressor().decompressobj()
                self.buffer.extend(self.decoder.decompress(data))
                self.complete = self.decoder.eof
                data = self.decoder.unused_data
        count = min(len(target), len(self.buffer) - self.offset)
        target[:count] = self.buffer[self.offset : self.offset + count]
        self.offset += count
        return count


@contextmanager
def decoded_stream(source):
    """Decode complete concatenated frames, rejecting a truncated final frame."""
    with io.BufferedReader(_Decoded(source)) as stream:
        yield stream


def physical_path(path: Path) -> Path:
    """Resolve a logical recording path to its existing disk representation."""
    return path if path.exists() else Path(str(path) + ".zst")


@contextmanager
def open_binary(path: Path):
    """Read plain files or all concatenated Zstandard frames."""
    path = physical_path(path)
    with path.open("rb") as stream:
        if path.suffix == ".zst":
            with decoded_stream(stream) as decoded:
                yield decoded
        else:
            yield stream


def read_bytes(path: Path) -> bytes:
    """Read logical bytes, independent of disk compression."""
    with open_binary(path) as stream:
        return stream.read()


def read_text(path: Path) -> str:
    """Read a UTF-8 logical recording."""
    return read_bytes(path).decode("utf-8")
