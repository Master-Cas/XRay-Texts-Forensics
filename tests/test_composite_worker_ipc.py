"""Synthetic IPC tests. No model, frozen artifact or consumed blind is opened."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from xray_text_forensics.web.composite import FrozenCompositeWorkerClient

WORKER = r'''
import json, os, sys, time
mode = sys.argv[1]
def put(payload):
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
HELLO = {
    "status": "ready",
    "closure_sha256": (
        "85fbf6abb0f800fa4fbcb88fe5930987d50794e2776128d8b6731db9c486d3fa"
    ),
}
if mode == "silent_hello":
    time.sleep(30)
elif mode == "partial_hello":
    put(b'{"status":"ready"')
    time.sleep(30)
elif mode == "bad_hello":
    put(b'not json\n')
    time.sleep(30)
elif mode == "no_hello":
    sys.exit(2)
elif mode == "wrong_hello":
    put(b'{"status":"ready","closure_sha256":"wrong"}\n')
    time.sleep(30)
else:
    if mode == "stderr_flood":
        os.write(sys.stderr.fileno(), b"x" * 131072)
    put((json.dumps(HELLO) + "\n").encode())
    for line in sys.stdin:
        request = json.loads(line)
        if mode == "slow_reply" and request["command"] == "classify":
            time.sleep(1.2)
        if mode == "silent_reply":
            time.sleep(30)
        if mode == "partial_reply":
            put(b'{"id":"partial"')
            time.sleep(30)
        if mode == "oversized_reply":
            put(b"x" * (72 * 1024) + b"\n")
            time.sleep(30)
        if mode == "invalid_reply":
            put(b'broken json\n')
            time.sleep(30)
        if mode == "die_during_ipc":
            sys.exit(9)
        if mode == "wrong_id":
            put(b'{"id":"wrong","ok":true,"result":{"pong":true}}\n')
            continue
        payload = {
            "id": request["id"], "ok": True,
            "result": {"pong": True, "state": "INCONCLUSIVE"},
        }
        put((json.dumps(payload) + "\n").encode())
'''


def make_worker(tmp_path: Path, mode: str, *, timeout: int = 1) -> FrozenCompositeWorkerClient:
    script = tmp_path / "fake_composite_worker.py"
    script.write_text(WORKER, encoding="utf-8")
    return FrozenCompositeWorkerClient(
        tmp_path,
        timeout_seconds=timeout,
        _synthetic_command=[sys.executable, "-u", str(script), mode],
    )


@pytest.mark.parametrize(
    "mode", ("silent_hello", "partial_hello", "bad_hello", "no_hello", "wrong_hello")
)
def test_initialization_failures_do_not_orphan_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    processes = []
    import xray_text_forensics.web.composite as client_module

    original = client_module.subprocess.Popen

    def track(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(client_module.subprocess, "Popen", track)
    with pytest.raises((RuntimeError, TimeoutError)):
        make_worker(tmp_path, mode)
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_stderr_is_drained_without_storing_sensitive_text(tmp_path: Path) -> None:
    client = make_worker(tmp_path, "stderr_flood")
    assert client.health()
    assert client._stderr_bytes >= 131072
    assert not hasattr(client, "stderr_text")
    client.close()
    assert client._process.poll() is not None


@pytest.mark.parametrize(
    "mode",
    ("silent_reply", "partial_reply", "oversized_reply", "invalid_reply",
     "die_during_ipc", "wrong_id"),
)
def test_corrupt_ipc_fails_closed_without_retry(tmp_path: Path, mode: str) -> None:
    client = make_worker(tmp_path, mode)
    with pytest.raises((RuntimeError, TimeoutError)):
        client.classify("synthetic text")
    assert client._process.poll() is not None
    with pytest.raises(RuntimeError):
        client.classify("second attempt is prohibited")


def test_healthy_worker_and_shutdown(tmp_path: Path) -> None:
    client = make_worker(tmp_path, "normal")
    assert client.health()
    assert client.classify("synthetic")["state"] == "INCONCLUSIVE"
    client.close()
    assert client._process.poll() is not None


def test_lock_timeout_does_not_kill_healthy_worker(tmp_path: Path) -> None:
    client = make_worker(tmp_path, "normal")
    client._lock.acquire()
    try:
        with pytest.raises(TimeoutError):
            client.classify("synthetic")
        assert client._process.poll() is None
    finally:
        client._lock.release()
    assert client.health()
    client.close()


def test_oversized_request_fails_before_ipc_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import xray_text_forensics.web.composite as client_module

    client = make_worker(tmp_path, "normal")
    monkeypatch.setattr(client_module, "MAX_IPC_REQUEST_BYTES", 32)
    with pytest.raises(ValueError):
        client.classify("abcdefgh")
    assert client._process.poll() is not None


def test_worker_busy_is_not_worker_broken(tmp_path: Path) -> None:
    client = make_worker(tmp_path, "slow_reply", timeout=4)
    entered = threading.Event()
    replies: list[dict] = []

    def classify() -> None:
        entered.set()
        replies.append(client.classify("entirely synthetic sample"))

    task = threading.Thread(target=classify, daemon=True)
    task.start()
    assert entered.wait(1)
    deadline = time.monotonic() + 2
    while not client._lock.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert client._lock.locked()
    assert client.operational_status() == "busy"
    assert client._process.poll() is None
    task.join(timeout=3)
    assert not task.is_alive()
    assert len(replies) == 1
    assert client.operational_status() == "ok"
    client.close()
    assert client._process.poll() is not None


def test_dead_worker_not_reported_as_busy(tmp_path: Path) -> None:
    client = make_worker(tmp_path, "normal")
    client._process.kill()
    client._process.wait(timeout=3)
    assert client.operational_status() == "error"
    client.close()
    assert client._process.poll() is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific subprocess pipe test")
def test_windows_synthetic_worker_pipe_cleanup(tmp_path: Path) -> None:
    for mode in ("normal", "stderr_flood", "partial_reply", "die_during_ipc"):
        client = make_worker(tmp_path, mode, timeout=2)
        try:
            if mode in {"normal", "stderr_flood"}:
                assert client.health()
            else:
                with pytest.raises((RuntimeError, TimeoutError)):
                    client.classify("synthetic")
        finally:
            client.close()
        assert client._process.poll() is not None
        assert all(
            stream is None or stream.closed
            for stream in (client._process.stdin, client._process.stdout, client._process.stderr)
        )
