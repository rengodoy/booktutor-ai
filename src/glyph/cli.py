"""Command-line interface: OCR a PDF into a Markdown file (``extract``)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from glyph.config import Settings


def _check_files_exist(paths: list[str]) -> bool:
    missing = [p for p in paths if not os.path.exists(p)]
    for p in missing:
        print(f"❌ File not found: {p}", file=sys.stderr)
    return not missing


def cmd_tui(args: argparse.Namespace, settings: Settings) -> int:
    from glyph.tui.app import GlyphApp

    GlyphApp().run()
    return 0


def cmd_extract(args: argparse.Namespace, settings: Settings) -> int:
    if not _check_files_exist([args.source]):
        return 1
    from glyph.loaders import make_loader

    loader = make_loader(settings, args.source)
    text = loader.load()

    out = Path(args.output) if args.output else Path(args.source).with_suffix(".md")
    out.write_text(text, encoding="utf-8")
    print(f"\n✅ Extracted markdown -> {out}  ({len(text):,} chars)")
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
