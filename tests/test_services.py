import pytest

from glyph import services as services_mod
from glyph.services import ServiceError, ServiceManager


class _FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def recorder(monkeypatch):
    """Record docker invocations; pretend docker exists. Returns the calls list."""
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        return _FakeProc()

    monkeypatch.setattr(services_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(services_mod.shutil, "which", lambda _: "/usr/bin/docker")
    return calls


def _mgr(**over) -> ServiceManager:
    opts = dict(compose_file="/abs/docker-compose.yaml", poll_interval=0.001)
    opts.update(over)
    return ServiceManager(**opts)


def test_compose_command_has_file_and_project():
    mgr = _mgr(project_name="glyphtest")
    cmd = mgr._compose("up", "-d", "docling")
    assert cmd[:4] == ["docker", "compose", "-f", "/abs/docker-compose.yaml"]
    assert "-p" in cmd and "glyphtest" in cmd
    assert cmd[-3:] == ["up", "-d", "docling"]


def test_ensure_starts_and_tracks(recorder, monkeypatch):
    mgr = _mgr()
    # unhealthy before `up`, healthy after.
    health = iter([False, True])
    monkeypatch.setattr(mgr, "_health_ok", lambda _u: next(health))
    monkeypatch.setattr(mgr, "_status", lambda _u: None)

    mgr.ensure("docling", "http://x:8002", timeout=5)

    assert "docling" in mgr._started
    assert any("up" in c for c in recorder)


def test_ensure_reuses_prestarted_without_tracking(recorder, monkeypatch):
    mgr = _mgr()
    monkeypatch.setattr(mgr, "_health_ok", lambda _u: True)  # already running

    mgr.ensure("docling", "http://x:8002", timeout=5)

    assert "docling" not in mgr._started  # we didn't start it -> we won't stop it
    assert recorder == []  # no `docker compose up`


def test_ensure_raises_when_docker_missing(monkeypatch):
    monkeypatch.setattr(services_mod.shutil, "which", lambda _: None)
    mgr = _mgr()
    monkeypatch.setattr(mgr, "_health_ok", lambda _u: False)
    with pytest.raises(ServiceError, match="docker not found"):
        mgr.ensure("docling", "http://x:8002", timeout=5)


def test_ensure_times_out_and_marks_failed(recorder, monkeypatch):
    mgr = _mgr()
    monkeypatch.setattr(mgr, "_health_ok", lambda _u: False)  # never healthy
    monkeypatch.setattr(mgr, "_status", lambda _u: None)
    clock = iter([0.0, 100.0, 200.0])
    monkeypatch.setattr(services_mod.time, "monotonic", lambda: next(clock))

    with pytest.raises(ServiceError, match="did not become healthy"):
        mgr.ensure("docling", "http://x:8002", timeout=1)
    assert "docling" in mgr._failed

    # A second ensure for a failed service raises without retrying docker.
    with pytest.raises(ServiceError, match="previously failed"):
        mgr.ensure("docling", "http://x:8002", timeout=1)


def test_ensure_skips_up_when_autostart_off(monkeypatch):
    mgr = _mgr(autostart=False)
    monkeypatch.setattr(mgr, "_health_ok", lambda _u: False)
    with pytest.raises(ServiceError, match="autostart is off"):
        mgr.ensure("docling", "http://x:8002", timeout=5)


def test_stop_all_stops_only_started(recorder):
    mgr = _mgr()
    mgr._started = {"docling", "deepseek2"}
    mgr.stop_all()
    assert mgr._started == set()
    stop_cmd = recorder[-1]
    assert "stop" in stop_cmd
    assert "docling" in stop_cmd and "deepseek2" in stop_cmd


def test_stop_all_noop_when_nothing_started(recorder):
    mgr = _mgr()
    mgr.stop_all()
    assert recorder == []  # nothing we started -> no docker call
