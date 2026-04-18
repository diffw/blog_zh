#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path(
    "/Users/diffwang/Library/Mobile Documents/iCloud~md~obsidian/Documents/notes/diff-blog"
)
DEFAULT_CONTENT_DIR = REPO_ROOT / "content" / "posts"
IGNORED_FILENAMES = {"template.md"}
FRONT_MATTER_DELIMITER = "---"


@dataclass
class SourcePost:
    source_path: Path
    title: str
    date: str
    draft: bool


@dataclass
class SyncResult:
    copied: list[str]
    removed: list[str]
    skipped: list[str]
    published: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Obsidian blog posts into the Hugo content tree.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Obsidian blog source directory")
    parser.add_argument("--content-dir", default=str(DEFAULT_CONTENT_DIR), help="Hugo content/posts directory")
    parser.add_argument("--repo-dir", default=str(REPO_ROOT), help="Git repository root for commit/push operations")
    parser.add_argument(
        "--commit-message",
        default="Publish blog updates",
        help="Commit message to use when synced content changes",
    )
    parser.add_argument("--no-push", action="store_true", help="Skip git push after committing")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync actions without writing files")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow syncing zero publishable posts and removing existing content/posts files",
    )
    return parser.parse_args()


def split_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith(f"{FRONT_MATTER_DELIMITER}\n"):
        return None, text

    marker = f"\n{FRONT_MATTER_DELIMITER}\n"
    closing_index = text.find(marker, len(FRONT_MATTER_DELIMITER) + 1)
    if closing_index == -1:
        return None, text

    front_matter = text[len(FRONT_MATTER_DELIMITER) + 1 : closing_index]
    body = text[closing_index + len(marker) :]
    return front_matter, body


def extract_scalar(front_matter: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", front_matter)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_source_post(path: Path) -> tuple[SourcePost | None, str | None]:
    text = path.read_text(encoding="utf-8")
    front_matter, _body = split_front_matter(text)
    if front_matter is None:
        return None, f"{path.name}: missing valid YAML front matter"

    title = extract_scalar(front_matter, "title")
    date = extract_scalar(front_matter, "date")
    draft_raw = extract_scalar(front_matter, "draft")

    if not title:
        return None, f"{path.name}: missing title"
    if not date:
        return None, f"{path.name}: missing date"
    if draft_raw is None:
        return None, f"{path.name}: missing draft"

    draft = draft_raw.lower() == "true"
    return SourcePost(source_path=path, title=title, date=date, draft=draft), None


def iter_source_posts(source_dir: Path) -> tuple[list[SourcePost], list[str]]:
    posts: list[SourcePost] = []
    skipped: list[str] = []

    for path in sorted(source_dir.glob("*.md")):
        if path.name in IGNORED_FILENAMES or path.name.startswith("."):
            continue
        post, error = parse_source_post(path)
        if error:
            skipped.append(error)
            continue
        if post and not post.draft:
            posts.append(post)

    return posts, skipped


def source_markdown_files(source_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(source_dir.glob("*.md"))
        if path.name not in IGNORED_FILENAMES and not path.name.startswith(".")
    ]


def ensure_content_index(content_dir: Path) -> None:
    content_dir.mkdir(parents=True, exist_ok=True)
    index_path = content_dir / "_index.md"
    if not index_path.exists():
        index_path.write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")


def remove_stale_entries(content_dir: Path, desired_filenames: set[str], dry_run: bool) -> list[str]:
    removed: list[str] = []

    if not content_dir.exists():
        return removed

    for path in sorted(content_dir.rglob("*"), reverse=True):
        relative = path.relative_to(content_dir)
        if relative == Path("_index.md"):
            continue

        should_remove = False
        if path.is_dir():
            if not any(path.iterdir()):
                should_remove = True
        elif relative.parent != Path("."):
            should_remove = True
        elif path.name not in desired_filenames:
            should_remove = True

        if should_remove:
            removed.append(str(relative))
            if not dry_run:
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()

    return removed


def copy_publishable_posts(posts: list[SourcePost], content_dir: Path, dry_run: bool) -> list[str]:
    copied: list[str] = []
    for post in posts:
        destination = content_dir / post.source_path.name
        current_bytes = destination.read_bytes() if destination.exists() else None
        source_bytes = post.source_path.read_bytes()
        if current_bytes == source_bytes:
            continue
        copied.append(post.source_path.name)
        if not dry_run:
            shutil.copy2(post.source_path, destination)
    return copied


def sync_posts(
    source_dir: Path,
    content_dir: Path,
    dry_run: bool = False,
    allow_empty: bool = False,
) -> SyncResult:
    if not source_dir.exists():
        raise RuntimeError(f"Source directory does not exist: {source_dir}")

    ensure_content_index(content_dir)
    source_files = source_markdown_files(source_dir)
    posts, skipped = iter_source_posts(source_dir)

    if not allow_empty and not posts:
        if source_files:
            raise RuntimeError(
                "Refusing to sync zero publishable posts. "
                "Check front matter or pass --allow-empty if you really want to clear the site."
            )
        existing_posts = [path for path in content_dir.glob("*.md") if path.name != "_index.md"]
        if existing_posts:
            raise RuntimeError(
                "Refusing to clear existing content/posts because no source markdown files were found. "
                "Pass --allow-empty if this is intentional."
            )

    desired = {post.source_path.name for post in posts}
    removed = remove_stale_entries(content_dir, desired, dry_run=dry_run)
    copied = copy_publishable_posts(posts, content_dir, dry_run=dry_run)
    return SyncResult(copied=copied, removed=removed, skipped=skipped, published=sorted(desired))


def run_git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def stage_and_commit_content(repo_dir: Path, content_dir: Path, commit_message: str) -> bool:
    relative_content_dir = content_dir.relative_to(repo_dir)
    add_result = run_git(repo_dir, "add", "-A", "--", str(relative_content_dir))
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or add_result.stdout.strip())

    diff_result = run_git(repo_dir, "diff", "--cached", "--quiet", "--", str(relative_content_dir))
    if diff_result.returncode == 0:
        return False
    if diff_result.returncode not in (0, 1):
        raise RuntimeError(diff_result.stderr.strip() or diff_result.stdout.strip())

    commit_result = run_git(repo_dir, "commit", "-m", commit_message, "--", str(relative_content_dir))
    if commit_result.returncode != 0:
        raise RuntimeError(commit_result.stderr.strip() or commit_result.stdout.strip())
    return True


def push_current_head(repo_dir: Path) -> None:
    push_result = run_git(repo_dir, "push", "origin", "HEAD")
    if push_result.returncode != 0:
        raise RuntimeError(push_result.stderr.strip() or push_result.stdout.strip())


def publish_once(
    source_dir: Path,
    content_dir: Path,
    repo_dir: Path,
    commit_message: str,
    push: bool,
    dry_run: bool,
    allow_empty: bool,
) -> int:
    result = sync_posts(
        source_dir=source_dir,
        content_dir=content_dir,
        dry_run=dry_run,
        allow_empty=allow_empty,
    )

    print(f"Publishable posts: {len(result.published)}")
    print(f"Copied/updated: {len(result.copied)}")
    print(f"Removed: {len(result.removed)}")
    if result.skipped:
        print("Skipped:")
        for item in result.skipped:
            print(f"  - {item}")

    if dry_run:
        return 0

    committed = stage_and_commit_content(repo_dir, content_dir, commit_message)
    if not committed:
        print("No git changes to commit in content/posts.")
        return 0

    print("Committed synced blog content.")
    if push:
        push_current_head(repo_dir)
        print("Pushed current HEAD to origin.")
    return 0


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    content_dir = Path(args.content_dir).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()

    return publish_once(
        source_dir=source_dir,
        content_dir=content_dir,
        repo_dir=repo_dir,
        commit_message=args.commit_message,
        push=not args.no_push,
        dry_run=args.dry_run,
        allow_empty=args.allow_empty,
    )


if __name__ == "__main__":
    sys.exit(main())
