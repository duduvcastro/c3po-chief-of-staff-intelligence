from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.maintenance_gate import Drain, MaintenanceBusy, admit


@pytest.fixture
def gate(tmp_path):
    for name in ("admission.lock", "work.lock"):
        path = tmp_path / name
        path.touch(mode=0o644)
    return tmp_path


def test_admission_closes_before_old_work_finishes_and_remains_closed(gate):
    old = admit(gate)
    with Drain(gate) as drain:
        assert not drain.try_drained()
        with pytest.raises(MaintenanceBusy):
            admit(gate)
        old.close()
        assert drain.try_drained()
        with pytest.raises(MaintenanceBusy):
            admit(gate)
        with pytest.raises(MaintenanceBusy):
            Drain(gate)
    with admit(gate):
        pass


def test_background_completion_is_required_after_request_returns(gate):
    request = admit(gate)
    background = request.retain()
    request.close()
    request.close()  # Double close must not prematurely release the child.
    with Drain(gate) as drain:
        assert not drain.try_drained()
        background.close()
        assert drain.try_drained()
    with pytest.raises(RuntimeError):
        request.retain()


def test_timeout_or_exception_reopens_admission_without_killing_job(gate):
    with admit(gate) as old:
        with pytest.raises(TimeoutError):
            with Drain(gate) as drain:
                assert not drain.try_drained()
                raise TimeoutError("bounded wait exhausted")
        with admit(gate):
            pass
        child = old.retain()
        child.close()


def test_barrier_is_visible_to_another_process(gate):
    code = '''
import sys
from pathlib import Path
from app.maintenance_gate import admit, MaintenanceBusy
try:
    with admit(Path(sys.argv[1])):
        pass
except MaintenanceBusy:
    sys.exit(23)
'''
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    def probe():
        return subprocess.run([sys.executable, "-c", code, str(gate)], env=environment,
                              capture_output=True, timeout=10).returncode
    assert probe() == 0
    with admit(gate):
        with Drain(gate) as drain:
            assert not drain.try_drained()
            assert probe() == 23
    assert probe() == 0


@pytest.mark.parametrize("kind", ["missing", "symlink", "hardlink", "writable", "directory"])
def test_invalid_barrier_fails_closed(gate, kind):
    work = gate / "work.lock"
    work.unlink()
    other = gate / "other"
    other.touch(mode=0o644)
    if kind == "symlink":
        work.symlink_to(other)
    elif kind == "hardlink":
        os.link(other, work)
    elif kind == "writable":
        work.touch()
        work.chmod(0o666)
    elif kind == "directory":
        work.mkdir()
    for operation in (admit, Drain):
        with pytest.raises((OSError, ValueError)):
            operation(gate)


def test_application_never_changes_lock_bytes_or_identity(gate):
    files = list(gate.iterdir())
    before = [(p.stat().st_ino, p.read_bytes(), p.stat().st_mode) for p in files]
    with admit(gate):
        pass
    with Drain(gate) as drain:
        assert drain.try_drained()
    assert before == [(p.stat().st_ino, p.read_bytes(), p.stat().st_mode) for p in files]


def test_timed_out_future_retains_work_until_actual_completion(gate, monkeypatch):
    from app.maintenance_gate import MaintenanceExecutor, job
    from threading import Event
    from concurrent.futures import TimeoutError
    monkeypatch.setenv("C3PO_MAINTENANCE_GATE_DIR", str(gate))
    release, started = Event(), Event()
    def operation():
        started.set()
        release.wait(5)
    pool = MaintenanceExecutor(max_workers=1)
    try:
        with job() as admitted:
            assert admitted
            future = pool.submit(operation)
            assert started.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.001)
        with Drain(gate) as drain:
            assert not drain.try_drained()
            with job() as admitted:
                assert not admitted
            release.set()
            future.result(timeout=2)
            pool.shutdown(wait=True)
            assert drain.try_drained()
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_asgi_keeps_background_work_and_refuses_new_requests(gate, monkeypatch):
    import asyncio
    from app.maintenance_gate import MaintenanceMiddleware
    monkeypatch.setenv("C3PO_MAINTENANCE_GATE_DIR", str(gate))
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def application(scope, receive, send):
            started.set()
            await finish.wait()  # Models Starlette's awaited background task.
        middleware = MaintenanceMiddleware(application)
        async def send(message):
            messages.append(message)
        messages = []
        task = asyncio.create_task(middleware({"type": "http"}, None, send))
        await started.wait()
        with Drain(gate) as drain:
            assert not drain.try_drained()
            await middleware({"type": "http"}, None, send)
            assert messages[0]["status"] == 503
            finish.set()
            await task
            assert drain.try_drained()
    asyncio.run(scenario())


def test_raw_queue_retains_work_until_buffer_is_flushed(gate, tmp_path, monkeypatch):
    from app.microstructure_capture import AppendOnlyRawStreamCapture
    from datetime import datetime, timezone
    import time
    monkeypatch.setenv("C3PO_MAINTENANCE_GATE_DIR", str(gate))
    capture = AppendOnlyRawStreamCapture(tmp_path / "raw", minimum_free_bytes=0, flush_every=1000)
    capture.start()
    try:
        assert capture.record("trade", '{"s":"TEST","p":1}', received_at=datetime.now(timezone.utc))
        with Drain(gate) as drain:
            assert not capture.record("trade", '{}', received_at=datetime.now(timezone.utc))
            deadline = time.monotonic() + 3
            while not drain.try_drained() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert drain.try_drained()
            assert capture.stats().written == 1
            assert any(p.stat().st_size > 0 for p in (tmp_path / "raw").rglob("*.ndjson"))
    finally:
        capture.stop()


def test_async_context_copied_at_startup_does_not_bypass_later_maintenance(gate, monkeypatch):
    import asyncio
    from app.maintenance_gate import job
    monkeypatch.setenv("C3PO_MAINTENANCE_GATE_DIR", str(gate))
    async def scenario():
        wake = asyncio.Event()
        async def background():
            await wake.wait()
            with job() as admitted:
                return admitted
        with job():
            task = asyncio.create_task(background())
        with Drain(gate) as drain:
            assert drain.try_drained()
            wake.set()
            assert await task is False
    asyncio.run(scenario())


def test_webhook_rejects_during_drain_without_appending(gate, tmp_path, monkeypatch):
    import importlib.util
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    import app.maintenance_gate as protocol
    monkeypatch.setenv("C3PO_MAINTENANCE_GATE_DIR", str(gate))
    monkeypatch.setitem(sys.modules, "maintenance_gate", protocol)
    file = Path(__file__).resolve().parents[3] / "work/pluggy_webhook.py"
    spec = importlib.util.spec_from_file_location("test_webhook_maintenance", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TOKEN = "test-only"
    module.EVENT_LOG = tmp_path / "events.jsonl"
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.PluggyWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def post():
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/pluggy/webhook",
            data=b'{"event":"test"}', headers={"X-Webhook-Token": "test-only"})
        return urllib.request.urlopen(request, timeout=2).status
    try:
        assert post() == 204
        before = module.EVENT_LOG.read_bytes()
        with Drain(gate) as drain:
            assert drain.try_drained()
            with pytest.raises(urllib.error.HTTPError) as error:
                post()
            assert error.value.code == 503
            assert module.EVENT_LOG.read_bytes() == before
        assert post() == 204
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_raw_burst_uses_bounded_descriptors_and_retains_backlog_until_flush(tmp_path):
    import subprocess
    import sys
    import textwrap
    script = textwrap.dedent('''
        import os, resource, sys, time
        from pathlib import Path
        from datetime import datetime, timezone
        from app.microstructure_capture import AppendOnlyRawStreamCapture
        from app.maintenance_gate import Drain
        root=Path(sys.argv[1]); gate=root/'gate'; gate.mkdir()
        for name in ('admission.lock','work.lock'): (gate/name).touch(mode=0o644)
        os.environ['C3PO_MAINTENANCE_GATE_DIR']=str(gate)
        capture=AppendOnlyRawStreamCapture(root/'raw', minimum_free_bytes=0, queue_size=5000)
        old=resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE,(min(128,old[0]),old[1]))
        try:
            for _ in range(3000):
                assert capture.record('trade','{}',received_at=datetime.now(timezone.utc))
            with Drain(gate) as drain:
                assert not drain.try_drained()
                assert not capture.record('trade','{}',received_at=datetime.now(timezone.utc))
                capture.start()
                deadline=time.monotonic()+10
                while not drain.try_drained() and time.monotonic()<deadline: time.sleep(.01)
                assert drain.try_drained()
                assert capture.stats().written==3000
                assert sum(len(p.read_text().splitlines()) for p in (root/'raw').rglob('*.ndjson'))==3000
            capture.stop()
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE,old)
    ''')
    import os
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_marker_removed_during_admission_read_is_already_reconciled(gate,monkeypatch):
    marker=gate/'reboot.pending'
    marker.write_text('12345678-1234-1234-1234-123456789012')
    original=Path.read_text
    def removed(path,*args,**kwargs):
        if path==marker:
            path.unlink()
            raise FileNotFoundError(str(path))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',removed)
    with admit(gate):
        pass
