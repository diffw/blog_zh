#!/usr/bin/env python3

from __future__ import annotations

import argparse
import signal
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from publish_from_obsidian import (
    DEFAULT_CONTENT_DIR,
    DEFAULT_SOURCE_DIR,
    REPO_ROOT,
    IGNORED_FILENAMES,
    publish_once,
)


class DebouncePublisher(FileSystemEventHandler):
    def __init__(
        self,
        *,
        source_dir: Path,
        content_dir: Path,
        repo_dir: Path,
        debounce_seconds: int,
        commit_message: str,
        push: bool,
    ) -> None:
        self.source_dir = source_dir
        self.content_dir = content_dir
        self.repo_dir = repo_dir
        self.debounce_seconds = debounce_seconds
        self.commit_message = commit_message
        self.push = push
        self.lock = threading.Lock()
        self.pending = False
        self.last_change_ts = 0.0
        self.publishing = False
        self.shutdown = False

    def _relevant_path(self, event: FileSystemEvent) -> Path | None:
        path = Path(event.src_path)
        if event.is_directory:
            return None
        if path.suffix != ".md":
            return None
        if path.name in IGNORED_FILENAMES or path.name.startswith("."):
            return None
        return path

    def on_any_event(self, event: FileSystemEvent) -> None:
        path = self._relevant_path(event)
        if path is None:
            return

        with self.lock:
            self.pending = True
            self.last_change_ts = time.monotonic()
        print(f"[watch] detected {event.event_type}: {path.name}")

    def loop(self) -> None:
        while not self.shutdown:
            time.sleep(1)
            should_publish = False
            with self.lock:
                idle_for = time.monotonic() - self.last_change_ts
                if self.pending and not self.publishing and idle_for >= self.debounce_seconds:
                    self.pending = False
                    self.publishing = True
                    should_publish = True

            if not should_publish:
                continue

            print(f"[watch] quiet for {self.debounce_seconds}s, publishing...")
            try:
                publish_once(
                    source_dir=self.source_dir,
                    content_dir=self.content_dir,
                    repo_dir=self.repo_dir,
                    commit_message=self.commit_message,
                    push=self.push,
                    dry_run=False,
                    allow_empty=False,
                )
            except Exception as exc:
                print(f"[watch] publish failed: {exc}")
            finally:
                with self.lock:
                    self.publishing = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Obsidian blog files and publish after a debounce window.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--content-dir", default=str(DEFAULT_CONTENT_DIR))
    parser.add_argument("--repo-dir", default=str(REPO_ROOT))
    parser.add_argument("--debounce-seconds", type=int, default=180)
    parser.add_argument("--commit-message", default="Publish blog updates")
    parser.add_argument("--no-push", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dir).expanduser().resolve()
    content_dir = Path(args.content_dir).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()

    handler = DebouncePublisher(
        source_dir=source_dir,
        content_dir=content_dir,
        repo_dir=repo_dir,
        debounce_seconds=args.debounce_seconds,
        commit_message=args.commit_message,
        push=not args.no_push,
    )
    observer = Observer()
    observer.schedule(handler, str(source_dir), recursive=False)
    observer.start()
    print(f"[watch] watching {source_dir}")
    print(f"[watch] debounce window: {args.debounce_seconds}s")

    def request_shutdown(_signum: int, _frame: object) -> None:
        handler.shutdown = True
        observer.stop()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    try:
        handler.loop()
    finally:
        observer.stop()
        observer.join()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
