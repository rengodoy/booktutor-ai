"""On-demand lifecycle for the OCR engine services (docker compose).

The orchestrator runs locally and talks to the OCR engines over HTTP. Heavy
engines (docling, deepseek2) are containers it spins up the first time the ladder
needs them and **stops at the end — but only the ones it started**, so a service
the user pre-started is reused and left running.

Stdlib only (``subprocess``/``urllib``) — this module stays importable in the
thin local install with no extra deps.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from glyph.progress import BaseReporter, ProgressReporter


class ServiceError(RuntimeError):
    """A required engine service is unavailable (won't start / no docker)."""


class ServiceManager:
    """Brings engine services up on demand and tears down what it started.

    One PDF at a time: ``ensure()`` is called per page but short-circuits once a
    service is up (``_started``) or known-bad (``_failed``), so it's cheap to call
    in the page loop. ``up -d`` on a running service is a no-op.
    """

    def __init__(
        self,
        *,
        compose_file: str,
        project_name: str | None = None,
        poll_interval: float = 2.0,
        autostart: bool = True,
        reporter: ProgressReporter | None = None,
    ) -> None:
        self.compose_file = compose_file
        self.project_name = project_name
        self.poll_interval = poll_interval
        self.autostart = autostart
        self.reporter: ProgressReporter = reporter or BaseReporter()
        self._started: set[str] = set()  # services WE brought up (only these stop)
        self._failed: set[str] = set()  # won't-start -> skip for the rest of the run

    # -- docker compose ----------------------------------------------------
    def _compose(self, *args: str) -> list[str]:
        cmd = ["docker", "compose", "-f", self.compose_file]
        if self.project_name:
            cmd += ["-p", self.project_name]
        return [*cmd, *args]

    # -- health / status ---------------------------------------------------
    def _health_ok(self, base_url: str) -> bool:
        try:
            with urllib.request.urlopen(
                f"{base_url.rstrip('/')}/health", timeout=3
            ) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def _status(self, base_url: str) -> dict | None:
        try:
            with urllib.request.urlopen(
                f"{base_url.rstrip('/')}/status", timeout=3
            ) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, ValueError):
            return None

    # -- lifecycle ---------------------------------------------------------
    def ensure(self, service: str, base_url: str, *, timeout: float) -> None:
        """Guarantee ``service`` is healthy at ``base_url`` (start it if needed).

        Raises :class:`ServiceError` if it's already known-bad, can't be started,
        or never becomes healthy within ``timeout``. The caller degrades that to
        an empty OCR candidate.
        """
        if service in self._started:
            return
        if service in self._failed:
            raise ServiceError(f"{service} previously failed to start")
        # Health-probe BEFORE `up` so a user-pre-started service is reused and NOT
        # tracked (we'd never stop someone else's service).
        if self._health_ok(base_url):
            return
        if not self.autostart:
            raise ServiceError(
                f"{service} is not running and autostart is off "
                f"(start it: docker compose up -d {service})"
            )
        if shutil.which("docker") is None:
            raise ServiceError("docker not found; start engine services manually")

        self.reporter.on_service_starting(service)
        try:
            proc = subprocess.run(
                self._compose("up", "-d", service),
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:  # docker vanished between which() and run()
            self._failed.add(service)
            raise ServiceError(
                "docker not found; start engine services manually"
            ) from exc
        if proc.returncode != 0:
            self._failed.add(service)
            raise ServiceError(
                f"`docker compose up -d {service}` failed: {proc.stderr.strip()}"
            )

        start = time.monotonic()
        while True:
            if self._health_ok(base_url):
                self._started.add(service)
                self.reporter.on_service_ready(service, time.monotonic() - start)
                return
            if time.monotonic() - start > timeout:
                self._failed.add(service)
                raise ServiceError(
                    f"{service} did not become healthy within {timeout:.0f}s"
                )
            status = self._status(base_url)
            if status is not None:
                frac = status.get("progress")
                stage = status.get("stage", "loading")
                self.reporter.on_service_progress(
                    service, frac if isinstance(frac, (int, float)) else None, stage
                )
            else:
                self.reporter.on_service_progress(service, None, "starting")
            time.sleep(self.poll_interval)

    def stop_all(self) -> None:
        """Stop only the services this manager started. Best-effort, never raises."""
        if not self._started:
            return
        services = sorted(self._started)
        self._started.clear()
        if shutil.which("docker") is None:
            return
        try:
            subprocess.run(
                self._compose("stop", *services),
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, OSError):
            pass
        self.reporter.on_message("info", f"stopped services: {', '.join(services)}")
