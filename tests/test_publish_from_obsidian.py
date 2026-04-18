from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from publish_from_obsidian import source_markdown_files, stage_and_commit_content, sync_posts


def write_markdown(path: Path, title: str, date: str = "2026-04-18T09:00:00-05:00", draft: bool = False) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            ---
            title: "{title}"
            date: {date}
            draft: {"true" if draft else "false"}
            tags: []
            ---

            Body for {title}.
            """
        ),
        encoding="utf-8",
    )


class PublishFromObsidianTests(unittest.TestCase):
    def test_source_markdown_files_retries_until_markdown_files_appear(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "source"
            source.mkdir(parents=True)
            delayed = source / "delayed.md"

            call_count = {"value": 0}

            def fake_scan_once(path: Path) -> list[Path]:
                self.assertEqual(path, source)
                call_count["value"] += 1
                if call_count["value"] < 3:
                    return []
                return [delayed]

            with mock.patch("publish_from_obsidian.source_markdown_files_once", side_effect=fake_scan_once):
                with mock.patch("publish_from_obsidian.time.sleep") as sleep_mock:
                    files = source_markdown_files(source, attempts=4, retry_delay_seconds=1)

            self.assertEqual(files, [delayed])
            self.assertEqual(call_count["value"], 3)
            self.assertEqual(sleep_mock.call_count, 2)

    def test_sync_copies_publishable_posts_and_skips_template_and_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source"
            content = root / "content" / "posts"
            source.mkdir(parents=True)
            content.mkdir(parents=True)
            (content / "_index.md").write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")

            write_markdown(source / "published.md", title="Published")
            write_markdown(source / "draft.md", title="Draft", draft=True)
            (source / "template.md").write_text("template", encoding="utf-8")
            (source / "broken.md").write_text("---\ntitle: \"Broken\"\ndraft: false\n---\n", encoding="utf-8")

            result = sync_posts(source, content)

            self.assertTrue((content / "published.md").exists())
            self.assertFalse((content / "draft.md").exists())
            self.assertFalse((content / "template.md").exists())
            self.assertEqual(result.published, ["published.md"])
            self.assertEqual(len(result.skipped), 1)
            self.assertIn("broken.md: missing date", result.skipped[0])

    def test_sync_removes_stale_and_legacy_nested_content(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source"
            content = root / "content" / "posts"
            legacy_dir = content / "2008"
            source.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            (content / "_index.md").write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")
            (content / "stale.md").write_text("stale", encoding="utf-8")
            (legacy_dir / "old.md").write_text("old", encoding="utf-8")
            write_markdown(source / "fresh.md", title="Fresh")

            result = sync_posts(source, content)

            self.assertTrue((content / "fresh.md").exists())
            self.assertFalse((content / "stale.md").exists())
            self.assertFalse((legacy_dir / "old.md").exists())
            self.assertFalse(legacy_dir.exists())
            self.assertIn("stale.md", result.removed)
            self.assertIn("2008/old.md", result.removed)

    def test_sync_refuses_to_clear_existing_content_when_no_publishable_posts_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source"
            content = root / "content" / "posts"
            source.mkdir(parents=True)
            content.mkdir(parents=True)
            (content / "_index.md").write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")
            (content / "published.md").write_text("published", encoding="utf-8")
            write_markdown(source / "draft.md", title="Draft", draft=True)

            with self.assertRaisesRegex(RuntimeError, "Refusing to sync zero publishable posts"):
                sync_posts(source, content)

            self.assertTrue((content / "published.md").exists())

    def test_stage_and_commit_content_only_commits_content_posts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            content = repo / "content" / "posts"
            content.mkdir(parents=True)
            (content / "_index.md").write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")

            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tester"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)

            (content / "post.md").write_text("published", encoding="utf-8")
            (repo / "README.md").write_text("local note", encoding="utf-8")

            committed = stage_and_commit_content(repo, content, "Publish blog updates")

            self.assertTrue(committed)
            log = subprocess.run(
                ["git", "-C", str(repo), "log", "--oneline", "-1"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Publish blog updates", log.stdout)
            status = subprocess.run(
                ["git", "-C", str(repo), "status", "--short"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("?? README.md", status.stdout)

    def test_stage_and_commit_content_returns_false_when_content_posts_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = Path(tempdir) / "repo"
            content = repo / "content" / "posts"
            content.mkdir(parents=True)
            (content / "_index.md").write_text("---\ntitle: \"博客\"\n---\n", encoding="utf-8")

            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tester"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)

            (repo / "README.md").write_text("local note", encoding="utf-8")

            committed = stage_and_commit_content(repo, content, "Publish blog updates")

            self.assertFalse(committed)
            log = subprocess.run(
                ["git", "-C", str(repo), "log", "--oneline", "-1"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("init", log.stdout)
            status = subprocess.run(
                ["git", "-C", str(repo), "status", "--short"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("?? README.md", status.stdout)


if __name__ == "__main__":
    unittest.main()
