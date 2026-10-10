"""Optional process-isolated client for the frozen XTF composite runtime."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import uuid4

COMPOSITE_ID = "xtf-composite-v1"
_LOG = logging.getLogger(__name__)
MAX_IPC_RESPONSE_BYTES = 64 * 1024
MAX_IPC_REQUEST_BYTES = 32 * 1024 * 1024
_READ_CHUNK = 4096
_CLEANUP_RESERVE_SECONDS = 0.5
EXPECTED_CLOSURE_SHA256 = "85fbf6abb0f800fa4fbcb88fe5930987d50794e2776128d8b6731db9c486d3fa"
EXPECTED_FREEZE_SHA256 = "23a67a9adb85ffef3199d6e2f332a77683a7c2ca3eb3a41ad8ae14de1ad2d20f"
EXPECTED_RUNTIME_MANIFEST_SHA256 = (
    "bd079d2867a1bdc90a53260759336a34f7fbeba550dc9e4fceef22004cfcd902"
)
EXPECTED_RUNTIME_SCRIPT_SHA256 = (
    "057b008d3a4bef67ded868ee237b74a1d35660ec92cce0d039fb4db388ec549f"
)
EXPECTED_SELFTEST_SHA256 = "38bd99660f3df1a6984e485dbced30359b3816ff6a6a23d75f7896b311ada21b"
EXPECTED_AI_RUNTIME_SHA256 = "eb89527a4d8a866f0987a866f827857555eab874cf28244e3c796577adad6b55"
EXPECTED_AI_RUNTIME_MANIFEST_SHA256 = (
    "dc13db59df8dea4128b880cab0870760f80c1fe3d3598e9329c88e685f4b3d13"
)


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


class CompositeClassifier(Protocol):
    def classify(self, text: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CompositeLoadResult:
    classifier: CompositeClassifier | None
    status: str
    reason: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FrozenCompositeWorkerClient:
    """One persistent, byte-bounded, deadline-aware worker. Never auto-restart.

    _synthetic_command is only for fixture tests; the production loader uses
    the fixed hash-verified runtime command.
    """

    def __init__(
        self,
        root: Path,
        *,
        timeout_seconds: int,
        _synthetic_command: Sequence[str] | None = None,
    ) -> None:
        self.root = root
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = threading.Event()
        self._frames: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=2)
        self._outbound: queue.Queue[
            tuple[bytes, queue.Queue[BaseException | None]] | None
        ] = queue.Queue(maxsize=1)
        self._stderr_digest = hashlib.sha256()
        self._stderr_bytes = 0
        worker = Path(__file__).with_name("composite_worker.py")
        python_wrapper = root / "human-likely-v2-runtime" / "python"
        if _synthetic_command is None and not python_wrapper.is_file():
            raise RuntimeError("Frozen runtime Python wrapper is missing")
        command = (
            [str(python_wrapper), str(worker), str(root)]
            if _synthetic_command is None
            else list(_synthetic_command)
        )
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        try:
            if (
                self._process.stdin is None
                or self._process.stdout is None
                or self._process.stderr is None
            ):
                raise RuntimeError("Failed to create composite worker pipes")
            # os.read/os.write work with anonymous subprocess pipes on Windows.
            for name, target in (
                ("stdout", self._read_stdout),
                ("stderr", self._drain_stderr),
                ("stdin", self._write_stdin),
            ):
                threading.Thread(
                    target=target, name="xtf-composite-" + name, daemon=True
                ).start()
            hello = self._read_json_line(time.monotonic() + self.timeout_seconds)
            if hello.get("status") != "ready":
                raise RuntimeError("Composite worker failed its initial readiness handshake")
            if hello.get("closure_sha256") != EXPECTED_CLOSURE_SHA256:
                raise RuntimeError("Worker closure identity mismatch")
        except BaseException:
            self.close()
            raise

    def _publish_frame(self, frame: bytes | BaseException) -> None:
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            self._closed.set()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        pending = bytearray()
        try:
            while not self._closed.is_set():
                chunk = os.read(self._process.stdout.fileno(), _READ_CHUNK)
                if not chunk:
                    self._publish_frame(
                        RuntimeError(
                            "Incomplete composite IPC response" if pending
                            else "Composite worker closed stdout"
                        )
                    )
                    return
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if len(line) > MAX_IPC_RESPONSE_BYTES:
                        self._publish_frame(
                            RuntimeError("Composite IPC response exceeds size limit")
                        )
                        return
                    self._publish_frame(bytes(line))
                if len(pending) > MAX_IPC_RESPONSE_BYTES:
                    self._publish_frame(
                        RuntimeError("Composite IPC response exceeds size limit")
                    )
                    return
        except (OSError, ValueError) as exc:
            self._publish_frame(
                RuntimeError(f"Composite IPC read failed: {type(exc).__name__}")
            )

    def _drain_stderr(self) -> None:
        assert self._process.stderr is not None
        try:
            while not self._closed.is_set():
                chunk = os.read(self._process.stderr.fileno(), _READ_CHUNK)
                if not chunk:
                    return
                # Constant memory; no private text is kept or logged.
                self._stderr_bytes += len(chunk)
                self._stderr_digest.update(chunk)
        except (OSError, ValueError):
            return

    def _write_stdin(self) -> None:
        assert self._process.stdin is not None
        fd = self._process.stdin.fileno()
        while not self._closed.is_set():
            try:
                item = self._outbound.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                return
            data, ack = item
            try:
                offset = 0
                while offset < len(data):
                    n = os.write(fd, data[offset : offset + _READ_CHUNK])
                    if n <= 0:
                        raise BrokenPipeError("Composite worker stdin closed")
                    offset += n
                ack.put_nowait(None)
            except (OSError, ValueError) as exc:
                ack.put_nowait(
                    RuntimeError(f"Composite IPC write failed: {type(exc).__name__}")
                )
                return

    def _read_json_line(self, deadline: float) -> dict[str, Any]:
        try:
            frame = self._frames.get(timeout=_remaining(deadline))
        except queue.Empty as exc:
            raise TimeoutError("Composite worker response timed out") from exc
        if isinstance(frame, BaseException):
            raise frame
        try:
            decoded = json.loads(frame.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError("Composite worker returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("Composite worker returned a non-object response")
        return decoded

    def _exchange(
        self,
        command: str,
        *,
        timeout_seconds: int,
        text: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        io_deadline = deadline - min(_CLEANUP_RESERVE_SECONDS, timeout_seconds / 4)
        acquired = self._lock.acquire(timeout=_remaining(io_deadline))
        if not acquired:
            raise TimeoutError("Composite worker busy (lock acquisition timed out)")
        try:
            if self._closed.is_set() or self._process.poll() is not None:
                raise RuntimeError("Composite worker is not running")
            request_id = uuid4().hex
            request: dict[str, Any] = {"id": request_id, "command": command}
            if text is not None:
                request["text"] = text
            payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
            if len(payload) > MAX_IPC_REQUEST_BYTES:
                raise ValueError("Composite IPC request exceeds size limit")
            ack: queue.Queue[BaseException | None] = queue.Queue(maxsize=1)
            self._outbound.put((payload, ack), timeout=_remaining(io_deadline))
            try:
                write_result = ack.get(timeout=_remaining(io_deadline))
            except queue.Empty as exc:
                raise TimeoutError("Composite worker write timed out") from exc
            if write_result is not None:
                raise write_result
            response = self._read_json_line(io_deadline)
            if response.get("id") != request_id:
                raise RuntimeError("Composite worker response ID mismatch")
            if response.get("ok") is not True:
                raise RuntimeError("Composite worker rejected request")
            result = response.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Composite worker returned an invalid result")
            return result
        except (OSError, RuntimeError, TimeoutError, ValueError, queue.Full) as exc:
            # Uncertain IPC state is permanently poisoned; no recovery/retry.
            self.close(deadline=deadline)
            _LOG.warning(
                "Composite worker IPC failure type=%s stderr_bytes=%d stderr_sha256=%s",
                type(exc).__name__, self._stderr_bytes, self._stderr_digest.hexdigest(),
            )
            raise
        finally:
            self._lock.release()

    def classify(self, text: str) -> dict[str, Any]:
        return self._exchange("classify", timeout_seconds=self.timeout_seconds, text=text)

    def health(self) -> bool:
        try:
            result = self._exchange(
                "ping", timeout_seconds=min(3, self.timeout_seconds)
            )
        except (OSError, RuntimeError, TimeoutError, ValueError, queue.Full):
            return False
        return result.get("pong") is True

    def operational_status(self) -> str:
        """Return ok/busy/error without pinging over an active inference.

        A live worker holding its request lock is busy, not broken.
        An idle worker receives the original bounded liveness ping.
        """
        if self._closed.is_set() or self._process.poll() is not None:
            return "error"
        if self._lock.locked():
            return "busy"
        if self.health():
            return "ok"
        # An inference may acquire the lock between the first check and
        # the health ping. Do not reinterpret that race as worker failure.
        if (
            self._lock.locked()
            and not self._closed.is_set()
            and self._process.poll() is None
        ):
            return "busy"
        return "error"

    def close(self, *, deadline: float | None = None) -> None:
        with self._close_lock:
            process = getattr(self, "_process", None)
            if process is None:
                return
            self._closed.set()
            if process.poll() is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    grace = 0.4 if deadline is None else min(0.4, _remaining(deadline))
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(
                            timeout=0.2 if deadline is None else _remaining(deadline)
                        )
                    except subprocess.TimeoutExpired:
                        pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass


def load_frozen_composite(
    root: Path | None,
    *,
    timeout_seconds: int = 60,
) -> CompositeLoadResult:
    """Verify and start the exact frozen runtime when configured."""

    if root is None:
        return CompositeLoadResult(None, "not_configured", None)

    root = root.expanduser().resolve()
    runtime_dir = root / COMPOSITE_ID
    artifacts = {
        root / "xtf-composite-v1-closure.json": EXPECTED_CLOSURE_SHA256,
        root / "xtf-composite-v1-freeze.json": EXPECTED_FREEZE_SHA256,
        runtime_dir / "composite-runtime-manifest.json": EXPECTED_RUNTIME_MANIFEST_SHA256,
        runtime_dir / "xtf_composite.py": EXPECTED_RUNTIME_SCRIPT_SHA256,
        runtime_dir / "selftest-report.json": EXPECTED_SELFTEST_SHA256,
        runtime_dir / "ai-likely-v26-runtime.npz": EXPECTED_AI_RUNTIME_SHA256,
        runtime_dir / "ai-likely-v26-runtime-manifest.json": (
            EXPECTED_AI_RUNTIME_MANIFEST_SHA256
        ),
    }

    try:
        for path, expected in artifacts.items():
            if not path.is_file():
                raise RuntimeError(f"Missing frozen composite artifact: {path.name}")
            if _sha256(path) != expected:
                raise RuntimeError(f"Frozen composite hash mismatch: {path.name}")

        closure = json.loads((root / "xtf-composite-v1-closure.json").read_text(encoding="utf-8"))
        if closure.get("status") != "COMPOSITE_FROZEN_PASS":
            raise RuntimeError("Composite closure is not COMPOSITE_FROZEN_PASS")
        if closure.get("composite_state") != "XTF_COMPOSITE_V1_FROZEN":
            raise RuntimeError("Composite state is not XTF_COMPOSITE_V1_FROZEN")

        client = FrozenCompositeWorkerClient(root, timeout_seconds=timeout_seconds)
        return CompositeLoadResult(client, "ok", None)
    except Exception as exc:
        return CompositeLoadResult(
            None, "error", f"Frozen composite unavailable: {type(exc).__name__}"
        )
