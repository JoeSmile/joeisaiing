#!/usr/bin/env python3
"""Migrate Hexo posts from blog-source-code to Hugo flat markdown files."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

HEXO_POSTS = Path("/Users/guowei/Desktop/github/blog-source-code/source/_posts")
HUGO_POSTS = Path("/Users/guowei/Desktop/github/joeisaiing/content/posts")
HUGO_STATIC = Path("/Users/guowei/Desktop/github/joeisaiing/static")


def parse_list_field(meta: dict[str, str], block: str, field: str) -> list[str]:
    if field in block:
        items = re.findall(rf"^{field}:\s*\n((?:\s*-\s*.+\n)+)", block, re.MULTILINE)
        if items:
            return [
                item.strip().lstrip("- ").strip().strip("'\"")
                for item in items[0].splitlines()
                if item.strip().startswith("-")
            ]
    value = meta.get(field, "")
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]
    return [value.strip("'\"")]


def read_meta_block(text: str) -> tuple[dict[str, str], list[str], list[str], str]:
    if not text.startswith("---"):
        return {}, [], [], text

    parts = text.split("---", 2)
    block = parts[1]
    body = parts[2].lstrip("\n") if len(parts) > 2 else ""

    meta: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("- "):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()

    tags = parse_list_field(meta, block, "tags")
    categories = parse_list_field(meta, block, "category")
    if not categories and "categories" in meta:
        categories = parse_list_field(meta, block, "categories")

    return meta, tags, categories, body


def normalize_date(raw: str) -> str:
    value = raw.strip("'\"")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except ValueError:
            continue
    if "T" in value:
        return value if "+" in value else value + "+08:00"
    return value.replace(" ", "T") + "+08:00"


def build_hugo_frontmatter(slug: str, meta: dict[str, str], tags: list[str], categories: list[str]) -> str:
    title = meta.get("title", "Untitled").strip("'\"")
    date = normalize_date(meta.get("date", "2019-01-01 00:00:00"))

    lines = ["---", f'title: "{title}"', f"date: {date}", f'slug: "{slug}"', f'url: "/{slug}.html"']

    if categories:
        lines.append("categories:")
        lines.extend(f'  - "{cat}"' for cat in categories)

    if tags:
        lines.append("tags:")
        lines.extend(f'  - "{tag}"' for tag in tags)

    if "thumbnail" in meta:
        lines.append(f'featuredImage: "{meta["thumbnail"]}"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def migrate_post(md_file: Path) -> None:
    slug = md_file.stem
    text = md_file.read_text(encoding="utf-8")
    meta, tags, categories, body = read_meta_block(text)

    asset_dir = md_file.parent / slug
    if asset_dir.is_dir():
        target = HUGO_STATIC / slug
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(asset_dir, target)

    frontmatter = build_hugo_frontmatter(slug, meta, tags, categories)
    (HUGO_POSTS / f"{slug}.md").write_text(frontmatter + "\n" + body, encoding="utf-8")
    print(f"migrated: {slug}")


def main() -> None:
    HUGO_POSTS.mkdir(parents=True, exist_ok=True)

    for path in HUGO_POSTS.glob("*/"):
        if path.is_dir():
            shutil.rmtree(path)

    for md_file in HUGO_POSTS.glob("*.md"):
        if md_file.stem != "hugo-migration":
            md_file.unlink()

    for md_file in sorted(HEXO_POSTS.glob("*.md")):
        migrate_post(md_file)


if __name__ == "__main__":
    main()
