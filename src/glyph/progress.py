"""Progress / status reporting — the layer that decouples the orchestrator from
its UI so the CLI works now and a TUI can plug in later.

The orchestrator emits coarse-grained events (:class:`ProgressReporter`); a
reporter renders them. :class:`ConsoleReporter` (the one the CLI uses) draws a
page progress bar plus transient spinners/bars for on-demand service loads and
per-engine attempts, so the user always sees that work is happening and roughly
how far along it is — model loads can take minutes.

A future ``TuiReporter`` implements the *same* protocol against Textual widgets
(see the redesign notes in the plan). Keep new events additive: add a default
no-op to :class:`BaseReporter` so existing reporters keep working.

``fraction=None`` is a first-class value meaning "indeterminate" — the UI shows a
spinner / pulsing bar rather than a percentage.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """The event surface the orchestrator emits and a UI consumes."""

    def on_run_start(
        self, source: str, total_pages: int, tiers: list[list[str]]
    ) -> None: ...
    def on_page_start(self, page_no: int, total_pages: int) -> None: ...
    def on_service_starting(self, service: str) -> None: ...
    def on_service_progress(
        self, service: str, fraction: float | None, stage: str
    ) -> None: ...
    def on_service_ready(self, service: str, elapsed: float) -> None: ...
    def on_engine_start(self, page_no: int, engine: str) -> None: ...
    def on_engine_progress(
        self, page_no: int, engine: str, fraction: float | None
    ) -> None: ...
    def on_engine_done(self, page_no: int, engine: str, chars: int) -> None: ...
    def on_reconcile(
        self,
        page_no: int,
        tier: list[str],
        confidence: float,
        accepted: bool,
        next_tier: list[str] | None,
    ) -> None: ...
    def on_page_done(
        self, page_no: int, confidence: float, tier: list[str]
    ) -> None: ...
    def on_run_done(self, pages: int, elapsed: float, out_path: str) -> None: ...
    def on_message(self, level: str, text: str) -> None: ...


class BaseReporter:
    """No-op implementation of every event. Subclass and override what you need.

    Guarantees forward-compatibility: a reporter written today keeps working when
    a new event is added here (it just no-ops it).
    """

    def on_run_start(
        self, source: str, total_pages: int, tiers: list[list[str]]
    ) -> None: ...
    def on_page_start(self, page_no: int, total_pages: int) -> None: ...
    def on_service_starting(self, service: str) -> None: ...
    def on_service_progress(
        self, service: str, fraction: float | None, stage: str
    ) -> None: ...
    def on_service_ready(self, service: str, elapsed: float) -> None: ...
    def on_engine_start(self, page_no: int, engine: str) -> None: ...
    def on_engine_progress(
        self, page_no: int, engine: str, fraction: float | None
    ) -> None: ...
    def on_engine_done(self, page_no: int, engine: str, chars: int) -> None: ...
    def on_reconcile(
        self,
        page_no: int,
        tier: list[str],
        confidence: float,
        accepted: bool,
        next_tier: list[str] | None,
    ) -> None: ...
    def on_page_done(
        self, page_no: int, confidence: float, tier: list[str]
    ) -> None: ...
    def on_run_done(self, pages: int, elapsed: float, out_path: str) -> None: ...
    def on_message(self, level: str, text: str) -> None: ...


def _fmt_secs(seconds: float) -> str:
    """``92.0`` -> ``"01:32"`` (or ``"1:01:32"`` past an hour)."""
    seconds = int(max(0.0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class ConsoleReporter(BaseReporter):
    """Renders events to the terminal with ``rich`` (falls back to plain prints).

    A persistent page bar (``pages 23/64 · elapsed · eta · throughput``) plus
    transient tasks for service startup (spinner + elapsed, or a % bar when the
    service reports one) and per-engine OCR attempts. The escalation decisions are
    printed above the live display so the user sees the ladder climb.
    """

    def __init__(self) -> None:
        self._progress = None  # rich.progress.Progress | None
        self._page_task = None
        self._total_pages = 0
        self._completed = 0  # pages finished this run (drives the bar; != page_no)
        self._service_tasks: dict[str, int] = {}
        self._engine_tasks: dict[tuple[int, str], int] = {}
        try:
            import rich  # noqa: F401

            self._rich = True
        except ImportError:
            self._rich = False

    # -- helpers ----------------------------------------------------------
    def _print(self, text: str) -> None:
        """Print a line, routed through rich's console while the bar is live."""
        if self._progress is not None:
            self._progress.console.print(text)
        else:
            print(text)

    def _page_detail(self, completed: int) -> str:
        task = self._progress.tasks[self._page_task]  # type: ignore[index]
        elapsed = task.elapsed or 0.0
        tput = completed / elapsed if elapsed > 0 else 0.0
        eta = (self._total_pages - completed) / tput if tput > 0 else 0.0
        return (
            f"{completed}/{self._total_pages} · elapsed {_fmt_secs(elapsed)} · "
            f"eta {_fmt_secs(eta)} · {tput:.1f} pg/s"
        )

    # -- events -----------------------------------------------------------
    def on_run_start(
        self, source: str, total_pages: int, tiers: list[list[str]]
    ) -> None:
        self._total_pages = total_pages
        self._completed = 0
        ladder = " → ".join("+".join(t) for t in tiers)
        if not self._rich:
            print(f"📚 {source} — {total_pages} pages · ladder: {ladder}")
            return
        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("{task.fields[detail]}"),
            transient=False,
        )
        self._progress.start()
        self._progress.console.print(f"📚 {source} — ladder: {ladder}")
        self._page_task = self._progress.add_task(
            "pages", total=max(total_pages, 1), detail=f"0/{total_pages}"
        )

    def on_page_start(self, page_no: int, total_pages: int) -> None:
        if self._progress is None:
            return
        self._progress.update(
            self._page_task, detail=self._page_detail(self._completed)
        )

    def on_service_starting(self, service: str) -> None:
        if self._progress is None:
            self._print(f"⏳ starting service: {service}…")
            return
        self._service_tasks[service] = self._progress.add_task(
            service, total=None, detail="starting…"
        )

    def on_service_progress(
        self, service: str, fraction: float | None, stage: str
    ) -> None:
        if self._progress is None:
            return
        task_id = self._service_tasks.get(service)
        if task_id is None:
            return
        if fraction is None:
            task = self._progress.tasks[task_id]
            self._progress.update(
                task_id, total=None, detail=f"{stage}… {_fmt_secs(task.elapsed or 0.0)}"
            )
        else:
            self._progress.update(
                task_id,
                total=100,
                completed=int(fraction * 100),
                detail=f"{stage} {int(fraction * 100)}%",
            )

    def on_service_ready(self, service: str, elapsed: float) -> None:
        if self._progress is None:
            self._print(f"✅ {service} ready ({_fmt_secs(elapsed)})")
            return
        task_id = self._service_tasks.pop(service, None)
        if task_id is not None:
            self._progress.remove_task(task_id)
        self._print(f"✅ {service} ready ({_fmt_secs(elapsed)})")

    def on_engine_start(self, page_no: int, engine: str) -> None:
        if self._progress is None:
            return
        self._engine_tasks[(page_no, engine)] = self._progress.add_task(
            f"page {page_no}: {engine}", total=None, detail="ocr…"
        )

    def on_engine_progress(
        self, page_no: int, engine: str, fraction: float | None
    ) -> None:
        if self._progress is None:
            return
        task_id = self._engine_tasks.get((page_no, engine))
        if task_id is None or fraction is None:
            return
        self._progress.update(task_id, total=100, completed=int(fraction * 100))

    def on_engine_done(self, page_no: int, engine: str, chars: int) -> None:
        if self._progress is None:
            return
        task_id = self._engine_tasks.pop((page_no, engine), None)
        if task_id is not None:
            self._progress.remove_task(task_id)

    def on_reconcile(
        self,
        page_no: int,
        tier: list[str],
        confidence: float,
        accepted: bool,
        next_tier: list[str] | None,
    ) -> None:
        label = "+".join(tier)
        # page_no is the real PDF page (may be a subset); the bar carries overall
        # progress, so the log just names the page.
        head = f"page {page_no}: {label} → confidence {confidence:.2f}"
        if accepted:
            self._print(f"{head} [green]✓[/green]" if self._rich else f"{head} ✓")
        elif next_tier is not None:
            nxt = "+".join(next_tier)
            tail = f"— escalating to {nxt}"
            self._print(
                f"{head} [yellow]{tail}[/yellow]" if self._rich else f"{head} {tail}"
            )
        else:
            self._print(f"{head} (last tier, keeping best result)")

    def on_page_done(self, page_no: int, confidence: float, tier: list[str]) -> None:
        self._completed += 1
        if self._progress is None:
            return
        self._progress.update(
            self._page_task,
            completed=self._completed,
            detail=self._page_detail(self._completed),
        )

    def on_run_done(self, pages: int, elapsed: float, out_path: str) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
        print(f"\n✅ {pages} pages in {_fmt_secs(elapsed)} → {out_path}")

    def on_message(self, level: str, text: str) -> None:
        if self._rich and self._progress is not None:
            color = {"error": "red", "warn": "yellow"}.get(level, "dim")
            self._print(f"[{color}]{text}[/{color}]")
        else:
            self._print(text)
