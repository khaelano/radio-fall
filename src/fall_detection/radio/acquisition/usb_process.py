"""Isolate POSIX USB reads from GUI pauses while preserving arrival timestamps."""

from __future__ import annotations

from collections import deque
import os
import selectors
import struct
import subprocess
import sys
import time

from .usb_buffer import UsbReadChunk

_HEADER = struct.Struct("!QI")
_MAX_READ = 4096


class UsbReadProcess:
    """Drain an inherited serial descriptor without depending on the GUI's GIL.

    The parent retains writes and serial configuration. The child owns reads;
    its bounded FIFO and pipe preserve byte order and original read-completion
    timestamps. Call ``request_stop`` before joining the consuming thread, then
    ``close`` to release the process and descriptors on every exit.
    """

    def __init__(self, fd: int, *, maximum_age_ns: int = 200_000_000) -> None:
        self._read_fd, child_write = os.pipe()
        child_control, self._control_fd = os.pipe()
        self._stopping = False
        self._closed = False
        self._process = None
        try:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    __name__,
                    str(fd),
                    str(child_write),
                    str(child_control),
                    str(maximum_age_ns),
                ],
                pass_fds=(fd, child_write, child_control),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except BaseException:
            self.close()
            raise
        finally:
            os.close(child_write)
            os.close(child_control)
        try:
            import select

            if (
                not select.select([self._read_fd], [], [], 2)[0]
                or os.read(self._read_fd, 1) != b"R"
            ):
                raise RuntimeError("gateway USB read process did not start")
        except BaseException:
            self.close()
            raise

    def _read_exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            data = os.read(self._read_fd, size - len(result))
            if not data:
                if result:
                    raise OSError("gateway USB read process stream truncated")
                return b""
            result.extend(data)
        return bytes(result)

    def read_chunk(self) -> UsbReadChunk | None:
        """Receive one completed read, or EOF after an explicitly requested stop."""
        header = self._read_exact(_HEADER.size)
        if not header:
            assert self._process is not None
            self._process.wait(timeout=2)
            if self._stopping and self._process.returncode == 0:
                return None
            detail = self._process.stderr.read(1024).decode(errors="replace").strip()
            raise OSError(detail or "gateway USB read process exited unexpectedly")
        arrival, size = _HEADER.unpack(header)
        if not 0 < size <= _MAX_READ:
            raise ValueError("invalid gateway USB read process chunk")
        payload = self._read_exact(size)
        if len(payload) != size:
            raise OSError("gateway USB read process payload truncated")
        return UsbReadChunk(payload, arrival)

    def request_stop(self) -> None:
        """Stop new USB reads and finish forwarding already owned bytes."""
        if not self._stopping:
            self._stopping = True
            os.close(self._control_fd)

    def close(self) -> None:
        """Bound process shutdown, including when the consumer failed."""
        if self._closed:
            return
        self._closed = True
        self.request_stop()
        os.close(self._read_fd)
        if self._process is not None:
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            if self._process.stderr is not None:
                self._process.stderr.close()


def _pump(fd: int, output: int, control: int, maximum_age_ns: int) -> None:
    """Read USB promptly; bounded nonblocking IPC absorbs short parent pauses."""
    pending: deque[tuple[int, bytes]] = deque()
    queued_bytes, offset = 0, 0
    staging = bytearray()
    flush_at = 0
    stopping = False
    output_registered = False
    os.set_blocking(output, False)
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ, "usb")
        selector.register(control, selectors.EVENT_READ, "stop")
        os.write(output, b"R")
        while not stopping or staging or pending:
            now = time.monotonic_ns()
            if staging and (stopping or len(staging) == _MAX_READ or now >= flush_at):
                data = bytes(staging)
                if len(pending) >= 256 or queued_bytes + len(data) > 256 * 1024:
                    raise BufferError("gateway USB read process buffer overflow")
                pending.append((now, _HEADER.pack(now, len(data)) + data))
                queued_bytes += len(data)
                staging.clear()
            if pending and now - pending[0][0] > maximum_age_ns:
                raise TimeoutError("gateway USB read process buffer age exceeded")
            if pending and not output_registered:
                selector.register(output, selectors.EVENT_WRITE, "output")
                output_registered = True
            elif not pending and output_registered:
                selector.unregister(output)
                output_registered = False
            if stopping and not pending:
                break
            timeout = 0.005
            if staging:
                timeout = max(0, min(timeout, (flush_at - now) / 1e9))
            for key, _mask in selector.select(timeout):
                if key.data == "stop":
                    stopping = True
                    selector.unregister(control)
                    selector.unregister(fd)
                elif key.data == "usb" and not stopping:
                    try:
                        data = os.read(fd, _MAX_READ - len(staging))
                    except BlockingIOError:
                        continue
                    if not data:
                        raise OSError("gateway USB disconnected")
                    if not staging:
                        flush_at = time.monotonic_ns() + 5_000_000
                    staging.extend(data)
                    # Flush a full chunk before another read can request zero bytes.
                    if len(staging) == _MAX_READ:
                        break
                elif key.data == "output" and pending:
                    try:
                        count = os.write(output, pending[0][1][offset:])
                    except BlockingIOError:
                        continue
                    offset += count
                    if offset == len(pending[0][1]):
                        _, frame = pending.popleft()
                        queued_bytes -= len(frame) - _HEADER.size
                        offset = 0


def _main() -> int:
    try:
        _pump(*(int(value) for value in sys.argv[1:]))
    except (OSError, ValueError, BufferError, TimeoutError) as exc:
        print(f"gateway USB read process: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
