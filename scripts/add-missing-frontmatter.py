#!/usr/bin/env python3
"""Add Hugo frontmatter to posts that start with a markdown H1 instead of ---."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "content" / "posts"


def iter_post_files() -> list[Path]:
    return sorted(POSTS.rglob("*.md"))

POST_META: dict[str, dict[str, object]] = {
    "langchain1.x-retrievers.md": {
        "date": "2026-06-17T10:00:00+08:00",
        "tags": ["RAG", "LangChain", "Retriever"],
    },
    "route-query.md": {
        "date": "2026-06-17T14:00:00+08:00",
        "tags": ["RAG", "Query路由", "Adaptive-RAG"],
    },
    "RRF-vs-MMR.md": {
        "date": "2026-06-18T10:00:00+08:00",
        "tags": ["RAG", "RRF", "MMR"],
    },
    "ReRank.md": {
        "date": "2026-06-18T14:00:00+08:00",
        "tags": ["RAG", "ReRank", "检索优化"],
    },
    "MultiVectorRetriever.md": {
        "date": "2026-06-19T10:00:00+08:00",
        "tags": ["RAG", "LangChain", "MultiVector"],
    },
    "RAPTOR.md": {
        "date": "2026-06-19T12:00:00+08:00",
        "tags": ["RAG", "RAPTOR", "分层RAG"],
    },
    "self-rag.md": {
        "date": "2026-06-19T16:00:00+08:00",
        "tags": ["RAG", "Self-RAG", "MemoryOS"],
    },
    "file-loaders.md": {
        "date": "2026-06-20T10:00:00+08:00",
        "tags": ["RAG", "LangChain", "DocumentLoader"],
    },
    "pdf-loaders.md": {
        "date": "2026-06-20T12:00:00+08:00",
        "tags": ["RAG", "DocumentLoader", "PDF"],
    },
    "pdf-loader-optimize.md": {
        "date": "2026-06-20T14:00:00+08:00",
        "tags": ["RAG", "PDF", "文档解析"],
    },
    "excel-word-loaders.md": {
        "date": "2026-06-20T16:00:00+08:00",
        "tags": ["RAG", "DocumentLoader", "Office"],
    },
}


def build_frontmatter(title: str, slug: str, date: str, tags: list[str]) -> str:
    lines = [
        "---",
        f'title: "{title}"',
        f"date: {date}",
        f'slug: "{slug}"',
        f'url: "/{slug}.html"',
        "categories:",
        '  - "AI 工程"',
        "tags:",
    ]
    for tag in tags:
        lines.append(f'  - "{tag}"')
    lines.extend(["draft: false", "---", ""])
    return "\n".join(lines)


def main() -> None:
    updated = 0
    for filename, meta in POST_META.items():
        matches = [p for p in iter_post_files() if p.name == filename]
        if not matches:
            print(f"skip missing: {filename}")
            continue
        path = matches[0]
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            print(f"skip has frontmatter: {filename}")
            continue
        lines = text.splitlines()
        if not lines or not lines[0].startswith("# "):
            print(f"skip no H1: {filename}")
            continue
        title = lines[0][2:].strip()
        slug = Path(filename).stem
        body = "\n".join(lines[1:]).lstrip("\n")
        frontmatter = build_frontmatter(
            title, slug, str(meta["date"]), list(meta["tags"])
        )
        path.write_text(f"{frontmatter}{body}\n", encoding="utf-8")
        updated += 1
        print(f"updated: {filename}")
    print(f"done, updated {updated} files")


if __name__ == "__main__":
    main()
