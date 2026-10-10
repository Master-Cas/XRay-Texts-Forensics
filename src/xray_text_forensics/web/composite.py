"""Optional process-isolated client for the frozen XTF composite runtime."""

from __future__ import annotations

import hashlib
import json
import select
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Protocol
from uuid import uuid4

COMPOSITE_ID = "xtf-composite-v1"
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
    """Persistent local worker keeping ML dependencies outside the web process."""

    def __init__(
        self,
        root: Path,
        *,
        timeout_seconds: int,
    ) -> None:
        self.root = root
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        worker = Path(__file__).with_name("composite_worker.py")
        python_wrapper = root / "human-likely-v2-runtime" / "python"
        if not python_wrapper.is_file():
            raise RuntimeError("Frozen runtime Python wrapper is missing")
        self._process = subprocess.Popen(
            [str(python_wrapper), str(worker), str(root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise RuntimeError("Failed to create composite worker pipes")
        self._stdin: IO[str] = self._process.stdin
        self._stdout: IO[str] = self._process.stdout
        hello = self._read_json_line(self.timeout_seconds)
        if hello.get("status") != "ready":
            reason = hello.get("error", "worker did not report ready")
            self.close()
            raise RuntimeError(str(reason))
        if hello.get("closure_sha256") != EXPECTED_CLOSURE_SHA256:
            self.close()
            raise RuntimeError("Worker closure identity mismatch")

    def _read_json_line(self, timeout_seconds: int) -> dict[str, Any]:
        ready, _, _ = select.select([self._stdout], [], [], timeout_seconds)
        if not ready:
            raise TimeoutError("Composite worker response timed out")
        line = self._stdout.readline()
        if not line:
            code = self._process.poll()
            raise RuntimeError(f"Composite worker closed its output (exit={code})")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError("Composite worker returned a non-object response")
        return payload

    def _exchange(
        self,
        command: str,
        *,
        timeout_seconds: int,
        text: str | None = None,
    ) -> dict[str, Any]:
        request_id = uuid4().hex
        request: dict[str, Any] = {"id": request_id, "command": command}
        if text is not None:
            request["text"] = text
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError("Composite worker is not running")
            self._stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self._stdin.flush()
            response = self._read_json_line(timeout_seconds)
        if response.get("id") != request_id:
            raise RuntimeError("Composite worker response ID mismatch")
        if response.get("ok") is not True:
            raise RuntimeError(str(response.get("error", "Composite worker failed")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Composite worker returned an invalid result")
        return result

    def classify(self, text: str) -> dict[str, Any]:
        return self._exchange(
            "classify",
            timeout_seconds=self.timeout_seconds,
            text=text,
        )

    def health(self) -> bool:
        try:
            result = self._exchange(
                "ping",
                timeout_seconds=min(3, self.timeout_seconds),
            )
        except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError):
            return False
        return result.get("pong") is True

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        try:
            stdin = getattr(self, "_stdin", None)
            if stdin is not None:
                stdin.close()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def load_frozen_composite(
    root: Path | None,
    *,
    timeout_seconds: int = 60,
) -> CompositeLoadResult:
    """Verify and start the exact frozen runtime when configured."""

    if root is None:
        return CompositeLoadResult(None, "not_configured", "Composite runtime is not configured.")

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
        return CompositeLoadResult(None, "error", f"Frozen composite unavailable: {exc}")
