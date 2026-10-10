"""Standalone JSON-lines worker for the frozen XTF composite runtime.

This file intentionally uses only the Python standard library before importing the
external frozen runtime, so it can execute under the detector's isolated venv without
installing the XRay web package into that environment.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_CLOSURE_SHA256 = "85fbf6abb0f800fa4fbcb88fe5930987d50794e2776128d8b6731db9c486d3fa"
EXPECTED_RUNTIME_SCRIPT_SHA256 = (
    "057b008d3a4bef67ded868ee237b74a1d35660ec92cce0d039fb4db388ec549f"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def load_runtime(root: Path) -> Any:
    closure = root / "xtf-composite-v1-closure.json"
    script = root / "xtf-composite-v1" / "xtf_composite.py"
    if sha256(closure) != EXPECTED_CLOSURE_SHA256:
        raise RuntimeError("composite closure hash mismatch")
    if sha256(script) != EXPECTED_RUNTIME_SCRIPT_SHA256:
        raise RuntimeError("composite runtime script hash mismatch")

    spec = importlib.util.spec_from_file_location("_xray_frozen_xtf_composite_v1", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to create frozen runtime module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if Path(module.ROOT).resolve() != root:
        raise RuntimeError("configured root differs from frozen runtime embedded root")
    return module.XTFCompositeV1(load_encoder=True)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: composite_worker.py ROOT", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).expanduser().resolve()
    try:
        runtime = load_runtime(root)
    except Exception as exc:
        emit({"status": "error", "error": str(exc)})
        return 1

    emit({"status": "ready", "closure_sha256": EXPECTED_CLOSURE_SHA256})
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            request_id = str(request["id"])
            command = request.get("command")
            if command == "ping":
                emit({"id": request_id, "ok": True, "result": {"pong": True}})
                continue
            if command != "classify":
                raise ValueError("unsupported command")
            text = request.get("text")
            if not isinstance(text, str):
                raise ValueError("text must be a string")
            result = runtime.classify(text)
            emit({"id": request_id, "ok": True, "result": result})
        except Exception as exc:
            response_id = (
                str(request.get("id", ""))
                if "request" in locals()
                else ""
            )
            emit({"id": response_id, "ok": False, "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
