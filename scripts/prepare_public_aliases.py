#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate static /posts redirect pages that point to canonical /blog URLs."
    )
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Repository root used when rendering Hugo",
    )
    parser.add_argument(
        "--static-dir",
        default=Path(__file__).resolve().parents[1] / "static",
        type=Path,
        help="Static directory where legacy /posts redirects should be written",
    )
    parser.add_argument(
        "--site-url",
        default="https://diff.im",
        help="Public site origin used in redirect targets",
    )
    return parser.parse_args()


def build_redirect_html(target_url: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>Redirecting...</title>
    <meta http-equiv="refresh" content="0; url={target_url}">
    <link rel="canonical" href="{target_url}">
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WRGQE6EWMX"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', 'G-WRGQE6EWMX');
    </script>
    <script>
      location.replace({target_url!r});
    </script>
  </head>
  <body>
    <p>Redirecting to <a href="{target_url}">{target_url}</a>.</p>
  </body>
</html>
"""


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.expanduser().resolve()
    static_dir = args.static_dir.expanduser().resolve()
    legacy_posts_dir = static_dir / "posts"
    site_url = args.site_url.rstrip("/")

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        subprocess.run(
            ["hugo", "--quiet", "--destination", str(output_dir)],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        canonical_blog_dir = output_dir / "blog"

        if not canonical_blog_dir.exists():
            raise RuntimeError(f"Canonical blog output does not exist: {canonical_blog_dir}")

        if legacy_posts_dir.exists():
            shutil.rmtree(legacy_posts_dir)
        legacy_posts_dir.mkdir(parents=True, exist_ok=True)

        redirect_count = 0
        for canonical_page in canonical_blog_dir.rglob("index.html"):
            rel_dir = canonical_page.relative_to(canonical_blog_dir).parent
            redirect_dir = legacy_posts_dir / rel_dir
            redirect_dir.mkdir(parents=True, exist_ok=True)

            blog_path = "/blog/"
            if rel_dir != Path("."):
                blog_path = f"/blog/{rel_dir.as_posix().strip('/')}/"
            target_url = f"{site_url}{blog_path}"

            (redirect_dir / "index.html").write_text(build_redirect_html(target_url), encoding="utf-8")
            redirect_count += 1

    print(f"Generated {redirect_count} legacy redirect pages under {legacy_posts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
