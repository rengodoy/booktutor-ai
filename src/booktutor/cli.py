"""Command-line interface: ``ingest``, ``chat`` and ``list`` sub-commands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from booktutor import vectorstore as vs
from booktutor.config import Settings
from booktutor.factories import make_embeddings, make_llm
from booktutor.rag import build_rag_chain


def default_collection_name(pdf_paths: list[str]) -> str:
    """Derive a collection name from the first PDF's file stem."""
    return Path(pdf_paths[0]).stem


def _check_files_exist(pdf_paths: list[str]) -> bool:
    missing = [p for p in pdf_paths if not os.path.exists(p)]
    for p in missing:
        print(f"❌ File not found: {p}", file=sys.stderr)
    return not missing


def cmd_ingest(args: argparse.Namespace, settings: Settings) -> int:
    if not _check_files_exist(args.pdfs):
        return 1
    name = args.collection or default_collection_name(args.pdfs)
    embeddings = make_embeddings(settings)
    vs.build_collection(settings, embeddings, name, args.pdfs)
    print(f"\n✨ Done. Chat with it: booktutor chat --collection {name}")
    return 0


def cmd_list(args: argparse.Namespace, settings: Settings) -> int:
    collections = vs.list_collections(settings)
    if not collections:
        print(f"No collections found under {settings.index_dir}/")
        return 0
    print(f"Collections under {settings.index_dir}/:")
    for name in collections:
        print(f"  • {name}")
    return 0


def cmd_chat(args: argparse.Namespace, settings: Settings) -> int:
    embeddings = make_embeddings(settings)
    name = args.collection

    if args.pdfs:
        if not _check_files_exist(args.pdfs):
            return 1
        name = name or default_collection_name(args.pdfs)
        store = vs.get_or_build_collection(settings, embeddings, name, args.pdfs)
    else:
        if not name:
            print(
                "❌ Provide --collection NAME (an existing one) or one or more "
                "PDF paths to build from.",
                file=sys.stderr,
            )
            return 1
        try:
            store = vs.load_collection(settings, embeddings, name)
        except FileNotFoundError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1

    retriever = store.as_retriever(
        search_type="mmr", search_kwargs={"k": settings.retrieval_k}
    )
    llm = make_llm(settings)
    chain = build_rag_chain(llm, retriever, book_name=name)

    print(f"\n📚 Tutoring session for '{name}'. Type 'quit' to exit.")
    chat_history: list = []
    while True:
        try:
            question = input("\n❓ Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            break

        result = chain.invoke({"input": question, "chat_history": chat_history})
        answer = result["answer"]
        print("\n🤖 " + answer)

        if args.show_sources:
            print("\n--- sources ---")
            for i, doc in enumerate(result.get("context", []), 1):
                snippet = doc.page_content[:300].replace("\n", " ")
                print(f"[{i}] {snippet}...")

        chat_history.extend([HumanMessage(question), AIMessage(answer)])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="booktutor",
        description="Turn PDF books into an OpenAI-compatible RAG tutor.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Process PDF(s) into a collection.")
    p_ingest.add_argument("pdfs", nargs="+", help="Path(s) to PDF file(s).")
    p_ingest.add_argument(
        "-c", "--collection", help="Collection name (default: first file's name)."
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_chat = sub.add_parser("chat", help="Ask questions about a collection.")
    p_chat.add_argument(
        "pdfs", nargs="*", help="Optional PDF(s) to build the collection from."
    )
    p_chat.add_argument("-c", "--collection", help="Collection name to chat with.")
    p_chat.add_argument(
        "--show-sources",
        action="store_true",
        help="Print the retrieved context chunks with each answer.",
    )
    p_chat.set_defaults(func=cmd_chat)

    p_list = sub.add_parser("list", help="List available collections.")
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings()
    return args.func(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
