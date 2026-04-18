#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from markdownify import markdownify as md


NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "wp": "http://wordpress.org/export/1.2/",
}

GUTENBERG_COMMENT_RE = re.compile(r"<!--\s*/?wp:[\s\S]*?-->")
MULTI_BLANK_RE = re.compile(r"\n{3,}")


@dataclass
class PostRecord:
    post_id: str
    title: str
    slug: str
    author: str
    source_url: str
    source_guid: str
    publish_dt: datetime
    modified_dt: datetime | None
    tags: list[str]
    body_markdown: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a WordPress XML export into Hugo content.")
    parser.add_argument("--xml", required=True, help="Path to the WordPress XML export.")
    parser.add_argument("--output", required=True, help="Hugo content output directory, e.g. content/posts.")
    parser.add_argument(
        "--mapping-output",
        required=True,
        help="CSV file path for old URL to new URL mappings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional number of posts to import for testing.",
    )
    parser.add_argument(
        "--set-file-times",
        action="store_true",
        help="Set macOS creation time to publish date and modified time to now.",
    )
    return parser.parse_args()


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def decode_slug(value: str, fallback: str) -> str:
    slug = urllib.parse.unquote(clean_text(value))
    slug = html.unescape(slug)
    slug = slug.strip("/")
    return slug or fallback


def sanitize_filename(title: str) -> str:
    sanitized = title.strip()
    replacements = {
        "/": "／",
        ":": "：",
        "*": "＊",
        "?": "？",
        '"': "'",
        "<": "〈",
        ">": "〉",
        "|": "｜",
    }
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized or "untitled"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def extract_tags(item: ET.Element) -> list[str]:
    tags: list[str] = []
    for category in item.findall("category"):
        if category.attrib.get("domain") != "post_tag":
            continue
        value = clean_text(category.text)
        if value and value not in tags:
            tags.append(value)
    return tags


def html_to_markdown(raw_html: str) -> str:
    content = GUTENBERG_COMMENT_RE.sub("", raw_html).strip()
    if not content:
        return ""

    soup = BeautifulSoup(content, "html.parser")

    # Strip script/style noise from old exports before conversion.
    for tag in soup(["script", "style"]):
        tag.decompose()

    markdown = md(
        str(soup),
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    )
    markdown = markdown.replace("\xa0", " ")
    markdown = MULTI_BLANK_RE.sub("\n\n", markdown).strip()
    return markdown


def frontmatter_lines(post: PostRecord) -> list[str]:
    lines = [
        "---",
        f"title: {yaml_quote(post.title)}",
        f"date: {post.publish_dt.isoformat()}",
    ]
    if post.modified_dt:
        lines.append(f"lastmod: {post.modified_dt.isoformat()}")
    lines.extend(
        [
            "draft: false",
            f"slug: {yaml_quote(post.slug)}",
        ]
    )
    if post.tags:
        lines.append("tags:")
        lines.extend(f"  - {yaml_quote(tag)}" for tag in post.tags)
    lines.extend(
        [
            f"author: {yaml_quote(post.author or 'diff')}",
            "params:",
            f"  wordpress_id: {yaml_quote(post.post_id)}",
            f"  source_url: {yaml_quote(post.source_url)}",
            f"  source_guid: {yaml_quote(post.source_guid)}",
            "---",
            "",
        ]
    )
    return lines


def build_post(item: ET.Element) -> PostRecord | None:
    post_type = clean_text(item.findtext("wp:post_type", namespaces=NS))
    status = clean_text(item.findtext("wp:status", namespaces=NS))
    title = clean_text(item.findtext("title"))

    if post_type != "post" or status != "publish" or not title:
        return None

    publish_raw = clean_text(item.findtext("pubDate"))
    source_url = clean_text(item.findtext("link"))
    source_guid = clean_text(item.findtext("guid"))
    author = clean_text(item.findtext("dc:creator", namespaces=NS))
    post_id = clean_text(item.findtext("wp:post_id", namespaces=NS))
    post_name = clean_text(item.findtext("wp:post_name", namespaces=NS))
    modified_gmt_raw = clean_text(item.findtext("wp:post_modified_gmt", namespaces=NS))
    modified_local_raw = clean_text(item.findtext("wp:post_modified", namespaces=NS))
    raw_html = item.findtext("content:encoded", default="", namespaces=NS) or ""

    body_markdown = html_to_markdown(raw_html)
    if not body_markdown:
        return None

    publish_dt = parsedate_to_datetime(publish_raw)
    modified_dt = None
    if modified_gmt_raw and modified_gmt_raw != "0000-00-00 00:00:00":
        modified_dt = datetime.strptime(modified_gmt_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif modified_local_raw and modified_local_raw != "0000-00-00 00:00:00":
        modified_dt = datetime.strptime(modified_local_raw, "%Y-%m-%d %H:%M:%S").astimezone()

    fallback_slug = sanitize_filename(title)
    slug = decode_slug(post_name, fallback_slug)
    tags = extract_tags(item)

    return PostRecord(
        post_id=post_id,
        title=title,
        slug=slug,
        author=author or "diff",
        source_url=source_url,
        source_guid=source_guid,
        publish_dt=publish_dt,
        modified_dt=modified_dt,
        tags=tags,
        body_markdown=body_markdown,
    )


def iter_posts(xml_path: Path) -> Iterable[PostRecord]:
    root = ET.parse(xml_path).getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Invalid WordPress XML: missing channel element")

    for item in channel.findall("item"):
        post = build_post(item)
        if post:
            yield post


def write_post(post: PostRecord, output_dir: Path, set_file_times: bool) -> tuple[Path, str]:
    year_dir = output_dir / f"{post.publish_dt.year:04d}"
    year_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{post.publish_dt:%Y-%m-%d}-{sanitize_filename(post.title)}.md"
    filepath = year_dir / filename

    content = "\n".join(frontmatter_lines(post)) + post.body_markdown.rstrip() + "\n"
    filepath.write_text(content, encoding="utf-8")

    if set_file_times:
        set_macos_file_times(filepath, post.publish_dt, datetime.now().astimezone())

    rel_url = f"/blog/{post.publish_dt:%Y/%m}/{post.slug}/"
    return filepath, rel_url


def set_macos_file_times(filepath: Path, created_at: datetime, modified_at: datetime) -> None:
    setfile = Path("/usr/bin/SetFile")
    if not setfile.exists():
        return

    local_created = created_at.astimezone()
    local_modified = modified_at.astimezone()

    subprocess.run(
        [str(setfile), "-d", local_created.strftime("%m/%d/%Y %H:%M:%S"), str(filepath)],
        check=True,
    )
    subprocess.run(
        [str(setfile), "-m", local_modified.strftime("%m/%d/%Y %H:%M:%S"), str(filepath)],
        check=True,
    )


def write_mapping(mapping_path: Path, rows: list[dict[str, str]]) -> None:
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with mapping_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["wordpress_id", "old_url", "new_url", "title", "source_guid"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()

    xml_path = Path(args.xml).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    mapping_path = Path(args.mapping_output).expanduser().resolve()

    posts = list(iter_posts(xml_path))
    if args.limit:
        posts = posts[: args.limit]

    mapping_rows: list[dict[str, str]] = []
    for post in posts:
        filepath, rel_url = write_post(post, output_dir, args.set_file_times)
        mapping_rows.append(
            {
                "wordpress_id": post.post_id,
                "old_url": post.source_url,
                "new_url": rel_url,
                "title": post.title,
                "source_guid": post.source_guid,
            }
        )
        print(f"Wrote {filepath}")

    write_mapping(mapping_path, mapping_rows)
    print(f"Wrote mapping file: {mapping_path}")
    print(f"Imported {len(mapping_rows)} posts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
