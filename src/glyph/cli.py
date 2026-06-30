"""Command-line interface: OCR a PDF into a Markdown file (``extract``)."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
from pathlib import Path

from glyph.config import Settings


def _check_files_exist(paths: list[str]) -> bool:
    missing = [p for p in paths if not os.path.exists(p)]
    for p in missing:
        print(f"❌ File not found: {p}", file=sys.stderr)
    return not missing


def _parse_pages(spec: str) -> list[int]:
    """``"51-60"`` / ``"5"`` / ``"1-3,7,10-12"`` -> sorted unique 1-indexed pages."""
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
            if start < 1 or end < start:
                raise ValueError(f"bad page range: {part!r}")
            pages.update(range(start, end + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"bad page number: {part!r}")
            pages.add(n)
    if not pages:
        raise ValueError("no pages selected")
    return sorted(pages)


def cmd_tui(args: argparse.Namespace, settings: Settings) -> int:
    try:
        from glyph.tui.app import GlyphApp
    except ImportError:
        print(
            "The TUI needs the optional 'tui' group: uv sync --group tui",
            file=sys.stderr,
        )
        return 1
    GlyphApp().run()
    return 0


def cmd_extract(args: argparse.Namespace, settings: Settings) -> int:
    if not _check_files_exist([args.source]):
        return 1
    pages: list[int] | None = None
    if args.pages:
        try:
            pages = _parse_pages(args.pages)
        except ValueError as exc:
            print(f"❌ invalid --pages {args.pages!r}: {exc}", file=sys.stderr)
            return 1
    if args.no_escalate:
        settings = settings.model_copy(update={"merge_escalate": False})
    from glyph.loaders import make_loader
    from glyph.progress import ConsoleReporter
    from glyph.services import ServiceManager

    reporter = ConsoleReporter()
    services = ServiceManager(
        compose_file=settings.compose_file_path,
        project_name=settings.compose_project_name or None,
        poll_interval=settings.health_poll_interval,
        autostart=settings.service_autostart and not args.no_autostart,
        reporter=reporter,
    )

    # Guarantee the on-demand services we started are torn down — on normal exit,
    # on an unhandled error, and on Ctrl-C / SIGTERM.
    if not args.keep_up:
        atexit.register(services.stop_all)

        def _handle_signal(*_):
            services.stop_all()
            sys.exit(130)

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _handle_signal)

    if args.output:
        out = Path(args.output)
    elif pages:
        # Don't clobber a full-document .md with a partial run.
        tag = args.pages.replace(",", "_").replace(" ", "")
        src = Path(args.source)
        out = src.with_name(f"{src.stem}.pages-{tag}.md")
    else:
        out = Path(args.source).with_suffix(".md")
    loader = make_loader(settings, args.source, services, reporter, pages=pages)
    try:
        text = loader.load(out_path=str(out))
    finally:
        if settings.service_stop_on_exit and not args.keep_up:
            services.stop_all()

    out.write_text(text, encoding="utf-8")
    print(f"📝 wrote {out}  ({len(text):,} chars)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph",
        description="OCR a PDF into a Markdown file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="OCR a PDF into a markdown file.")
    p_extract.add_argument("source", help="Path to the PDF to OCR.")
    p_extract.add_argument(
        "-o", "--output", help="Output markdown path (default: <source>.md)."
    )
    p_extract.add_argument(
        "--pages",
        metavar="SPEC",
        help="Only these 1-indexed pages, e.g. '51-60', '5', '1-3,7,10-12' "
        "(default <source>.pages-<spec>.md to avoid clobbering the full doc).",
    )
    p_extract.add_argument(
        "--keep-up",
        action="store_true",
        help="Don't stop the engine services at the end (reuse on the next run).",
    )
    p_extract.add_argument(
        "--no-autostart",
        action="store_true",
        help="Assume engine services are already running; don't spin them up.",
    )
    p_extract.add_argument(
        "--no-escalate",
        action="store_true",
        help="Run only the first MERGE_TIERS tier and accept its result "
        "(no escalation, ignores MERGE_MIN_CONFIDENCE).",
    )
    p_extract.set_defaults(func=cmd_extract)

    p_tui = sub.add_parser("tui", help="Launch the glyph TUI.")
    p_tui.set_defaults(func=cmd_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings()
    return args.func(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
