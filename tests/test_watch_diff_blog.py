from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from watch_diff_blog import PUBLISH_SCRIPT, build_publish_command


class WatchDiffBlogTests(unittest.TestCase):
    def test_build_publish_command_uses_current_python_and_publish_script(self) -> None:
        command = build_publish_command(
            source_dir=Path("/tmp/source"),
            content_dir=Path("/tmp/content/posts"),
            repo_dir=Path("/tmp/repo"),
            commit_message="Publish blog updates",
            push=True,
        )

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], str(PUBLISH_SCRIPT))
        self.assertIn("--source-dir", command)
        self.assertIn("/tmp/source", command)
        self.assertIn("--content-dir", command)
        self.assertIn("/tmp/content/posts", command)
        self.assertIn("--repo-dir", command)
        self.assertIn("/tmp/repo", command)
        self.assertIn("--commit-message", command)
        self.assertIn("Publish blog updates", command)
        self.assertNotIn("--no-push", command)

    def test_build_publish_command_adds_no_push_when_push_is_disabled(self) -> None:
        command = build_publish_command(
            source_dir=Path("/tmp/source"),
            content_dir=Path("/tmp/content/posts"),
            repo_dir=Path("/tmp/repo"),
            commit_message="Publish blog updates",
            push=False,
        )

        self.assertIn("--no-push", command)


if __name__ == "__main__":
    unittest.main()
