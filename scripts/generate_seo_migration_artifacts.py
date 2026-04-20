#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


WP_NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

PAGE_ROUTE_OVERRIDES = {
    "about": "/about/",
    "links": "/links/",
}

LEGACY_PATTERNS = {
    "wangwangwang": re.compile(r"https?://(?:www\.)?wangwangwang\.org[^)\s\]\">]*"),
    "handhard": re.compile(r"https?://(?:www\.)?handhard\.com[^)\s\]\">]*"),
    "wp_uploads": re.compile(r"https?://diff\.im(?:/blog)?/wp-content/uploads/[^)\s\]\">]*"),
}


@dataclass
class PageRecord:
    wordpress_id: str
    title: str
    slug: str
    old_url: str


@dataclass
class AttachmentRecord:
    wordpress_id: str
    old_url: str
    attachment_url: str
    parent_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SEO migration artifacts from a WordPress export.")
    parser.add_argument("--xml", required=True, help="Path to the WordPress XML export")
    parser.add_argument("--post-map-csv", required=True, help="Path to wordpress-url-map.csv")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--page-map-json", default="data/wordpress_page_id_map.json")
    parser.add_argument("--attachment-map-json", default="data/wordpress_attachment_id_map.json")
    parser.add_argument("--report", default="docs/seo-migration-audit.md")
    return parser.parse_args()


def load_post_map(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            post_id = (row.get("wordpress_id") or "").strip()
            new_url = (row.get("new_url") or "").strip()
            if post_id and new_url:
                rows[post_id] = new_url
    return rows


def load_wordpress_records(xml_path: Path) -> tuple[list[PageRecord], list[AttachmentRecord]]:
    root = ET.parse(xml_path).getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Invalid WordPress export: missing channel node")

    pages: list[PageRecord] = []
    attachments: list[AttachmentRecord] = []

    for item in channel.findall("item"):
        post_type = item.findtext("wp:post_type", namespaces=WP_NS)
        status = item.findtext("wp:status", namespaces=WP_NS)

        if post_type == "page" and status == "publish":
            pages.append(
                PageRecord(
                    wordpress_id=item.findtext("wp:post_id", namespaces=WP_NS) or "",
                    title=item.findtext("title") or "",
                    slug=item.findtext("wp:post_name", namespaces=WP_NS) or "",
                    old_url=item.findtext("link") or "",
                )
            )
            continue

        if post_type == "attachment" and status == "inherit":
            attachments.append(
                AttachmentRecord(
                    wordpress_id=item.findtext("wp:post_id", namespaces=WP_NS) or "",
                    old_url=item.findtext("link") or "",
                    attachment_url=item.findtext("wp:attachment_url", namespaces=WP_NS) or "",
                    parent_id=item.findtext("wp:post_parent", namespaces=WP_NS) or "",
                )
            )

    return pages, attachments


def scan_legacy_links(content_root: Path) -> dict[str, list[dict[str, object]]]:
    findings: dict[str, list[dict[str, object]]] = {name: [] for name in LEGACY_PATTERNS}
    for path in sorted(content_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in LEGACY_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                findings[name].append(
                    {
                        "file": str(path.relative_to(content_root.parent)),
                        "count": len(matches),
                        "examples": matches[:3],
                    }
                )
    return findings


def write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def write_report(
    path: Path,
    page_map: dict[str, str],
    unmapped_pages: list[PageRecord],
    attachments: list[AttachmentRecord],
    attachment_map: dict[str, str],
    orphan_attachments: list[AttachmentRecord],
    legacy_link_findings: dict[str, list[dict[str, object]]],
) -> None:
    attachment_extensions = Counter()
    for attachment in attachments:
        suffix = Path(attachment.attachment_url).suffix.lower().lstrip(".") or "unknown"
        attachment_extensions[suffix] += 1

    lines = [
        "# SEO Migration Audit",
        "",
        "## Snapshot",
        "",
        f"- WordPress pages found: `{len(page_map) + len(unmapped_pages)}`",
        f"- WordPress pages mapped to current Hugo routes: `{len(page_map)}`",
        f"- WordPress attachment pages found: `{len(attachments)}`",
        f"- WordPress attachment pages mapped to parent posts: `{len(attachment_map)}`",
        f"- Attachment pages still unresolved: `{len(orphan_attachments)}`",
        "",
        "## WordPress Page Routes",
        "",
    ]

    for wordpress_id, target in sorted(page_map.items()):
        lines.append(f"- `?page_id={wordpress_id}` -> `{target}`")

    if unmapped_pages:
        lines.extend(["", "## Unmapped Pages", ""])
        for page in unmapped_pages:
            lines.append(f"- `?page_id={page.wordpress_id}` `{page.title}` (`slug: {page.slug}`) has no Hugo route yet.")

    lines.extend(
        [
            "",
            "## Attachment Notes",
            "",
            f"- Attachment file types in export: `{dict(attachment_extensions.most_common())}`",
            "- Mapped attachment pages redirect to the parent post rather than to missing old media pages.",
        ]
    )

    if orphan_attachments:
        lines.extend(["", "### Unresolved Attachment Pages", ""])
        for attachment in orphan_attachments[:10]:
            lines.append(
                f"- `?attachment_id={attachment.wordpress_id}` parent=`{attachment.parent_id or '0'}` file=`{attachment.attachment_url}`"
            )
        if len(orphan_attachments) > 10:
            lines.append(f"- ... and `{len(orphan_attachments) - 10}` more unresolved attachment pages.")

    lines.extend(["", "## Hardcoded Legacy Links In Content", ""])
    for name, entries in legacy_link_findings.items():
        total = sum(int(entry["count"]) for entry in entries)
        lines.append(f"- `{name}`: `{total}` matches across `{len(entries)}` files")
        for entry in entries[:5]:
            example_list = ", ".join(f"`{example}`" for example in entry["examples"])
            lines.append(f"  - `{entry['file']}` x{entry['count']}: {example_list}")
        if len(entries) > 5:
            lines.append(f"  - ... and `{len(entries) - 5}` more files")

    lines.extend(
        [
            "",
            "## Recommended Next Actions",
            "",
            "- Add server-side `301/308` redirects for `?p=ID`, `?page_id=ID`, and the mapped `?attachment_id=ID` URLs at the edge layer if Linode or Cloudflare is still available.",
            "- Restore the missing `wp-content/uploads` tree under the Hugo site or move those images into the repository and rewrite post bodies to the new asset URLs.",
            "- Review the unresolved `Idea` page and decide whether it needs a Hugo destination or a deliberate `410`/redirect strategy.",
            "- Use Google Search Console to resubmit the sitemap and inspect a sample of old `?p=ID` URLs after the server-side redirects are in place.",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.expanduser().resolve()
    xml_path = Path(args.xml).expanduser().resolve()
    post_map_csv = Path(args.post_map_csv).expanduser().resolve()
    page_map_path = repo_root / args.page_map_json
    attachment_map_path = repo_root / args.attachment_map_json
    report_path = repo_root / args.report

    post_map = load_post_map(post_map_csv)
    pages, attachments = load_wordpress_records(xml_path)

    page_map = {
        page.wordpress_id: PAGE_ROUTE_OVERRIDES[page.slug]
        for page in pages
        if page.slug in PAGE_ROUTE_OVERRIDES
    }
    unmapped_pages = [page for page in pages if page.slug not in PAGE_ROUTE_OVERRIDES]

    attachment_map: dict[str, str] = {}
    orphan_attachments: list[AttachmentRecord] = []
    for attachment in attachments:
        target = post_map.get(attachment.parent_id)
        if target:
            attachment_map[attachment.wordpress_id] = target
        else:
            orphan_attachments.append(attachment)

    legacy_link_findings = scan_legacy_links(repo_root / "content")

    write_json(page_map_path, page_map)
    write_json(attachment_map_path, attachment_map)
    write_report(report_path, page_map, unmapped_pages, attachments, attachment_map, orphan_attachments, legacy_link_findings)

    print(f"Wrote {page_map_path.relative_to(repo_root)} with {len(page_map)} entries")
    print(f"Wrote {attachment_map_path.relative_to(repo_root)} with {len(attachment_map)} entries")
    print(f"Wrote {report_path.relative_to(repo_root)}")
    if unmapped_pages:
        print("Unmapped pages:")
        for page in unmapped_pages:
            print(f"  - {page.wordpress_id} {page.slug} {page.title}")
    if orphan_attachments:
        print(f"Unresolved attachments: {len(orphan_attachments)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
