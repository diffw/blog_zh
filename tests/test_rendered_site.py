from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_LABEL_RE = re.compile(r"(archive|all\s*posts?)", re.IGNORECASE)
ARCHIVE_PATH_HINTS = ("/archive", "/archives", "/all-posts")
CHINESE_ARCHIVE_HINTS = ("归档", "全部文章", "所有文章", "文章归档", "查看全部", "更多文章")
EXPECTED_NAV_LINKS = {
    "首页": "/",
    "博客": "/blog/",
    "关于": "/about/",
    "近况": "/now/",
    "项目": "/projects/",
    "链接": "/links/",
}
GOOGLE_ANALYTICS_ID = "G-WRGQE6EWMX"
GOOGLE_ANALYTICS_SRC = f"https://www.googletagmanager.com/gtag/js?id={GOOGLE_ANALYTICS_ID}"
LEGACY_BLOG_PATH = "/posts/"


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_label_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        attrs_map = {key: value or "" for key, value in attrs}
        self._current_href = attrs_map.get("href")
        self._current_label_parts = []
        for key in ("aria-label", "title"):
            if attrs_map.get(key):
                self._current_label_parts.append(attrs_map[key])

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_label_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return

        label = " ".join(part.strip() for part in self._current_label_parts if part.strip())
        self.anchors.append({"href": self._current_href, "label": label})
        self._current_href = None
        self._current_label_parts = []


def normalize_href(href: str) -> str:
    parsed = urlparse(href)
    path = parsed.path or href
    if not path.startswith("/"):
        path = f"/{path.lstrip('./')}"
    if path != "/" and not path.endswith("/") and not path.endswith(".html"):
        path = f"{path}/"
    return path


def is_archive_label(label: str) -> bool:
    return bool(ARCHIVE_LABEL_RE.search(label)) or any(token in label for token in CHINESE_ARCHIVE_HINTS)


def is_archive_href(href: str) -> bool:
    path = normalize_href(href)
    return path.endswith("/blog/") or any(hint in path for hint in ARCHIVE_PATH_HINTS)


class RenderedSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        hugo_bin = shutil.which("hugo")
        if hugo_bin is None:
            raise unittest.SkipTest("hugo is required for rendered site tests")

        cls._tempdir = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls._tempdir.name)
        subprocess.run(
            [hugo_bin, "--quiet", "--destination", str(cls.output_dir)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.base_path = urlparse("https://diffw.github.io/blog_zh/").path.rstrip("/")
        cls.homepage_html = (cls.output_dir / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tempdir.cleanup()

    def find_archive_affordance(self) -> dict[str, str]:
        parser = AnchorParser()
        parser.feed(self.homepage_html)
        candidates = [
            anchor
            for anchor in parser.anchors
            if anchor["href"] and is_archive_href(anchor["href"]) and is_archive_label(anchor["label"])
        ]
        self.assertTrue(
            candidates,
            "Homepage should expose an archive/all-posts link with archive-oriented label text.",
        )
        return candidates[0]

    def parse_homepage_anchors(self) -> list[dict[str, str]]:
        parser = AnchorParser()
        parser.feed(self.homepage_html)
        return parser.anchors

    def rendered_page_for_href(self, href: str) -> Path:
        path = normalize_href(href)
        if self.base_path and path.startswith(f"{self.base_path}/"):
            path = path[len(self.base_path) :]
        elif self.base_path and path == f"{self.base_path}/":
            path = "/"
        if path == "/":
            return self.output_dir / "index.html"
        if path.endswith(".html"):
            return self.output_dir / path.lstrip("/")
        return self.output_dir / path.lstrip("/") / "index.html"

    def site_relative_href(self, href: str) -> str:
        path = normalize_href(href)
        if self.base_path and path.startswith(f"{self.base_path}/"):
            return path[len(self.base_path) :]
        if self.base_path and path == f"{self.base_path}/":
            return "/"
        return path

    def test_homepage_exposes_archive_or_all_posts_affordance(self) -> None:
        affordance = self.find_archive_affordance()
        rendered_page = self.rendered_page_for_href(affordance["href"])

        self.assertTrue(
            rendered_page.exists(),
            f"文章归档入口应当指向一个真实生成的页面: {affordance['href']}",
        )

    def test_homepage_navigation_exposes_expected_top_level_pages(self) -> None:
        anchors = self.parse_homepage_anchors()
        normalized = {anchor["label"]: self.site_relative_href(anchor["href"]) for anchor in anchors if anchor["href"]}

        for label, href in EXPECTED_NAV_LINKS.items():
            self.assertIn(label, normalized, f"顶部导航缺少入口: {label}")
            self.assertEqual(normalized[label], href)

            rendered_page = self.rendered_page_for_href(href)
            self.assertTrue(rendered_page.exists(), f"导航页面未生成: {label} -> {href}")

    def test_archive_or_all_posts_view_groups_posts_by_year(self) -> None:
        affordance = self.find_archive_affordance()
        archive_html = self.rendered_page_for_href(affordance["href"]).read_text(encoding="utf-8")
        years = [int(year) for year in re.findall(r"<h[1-6][^>]*>\s*(\d{4})\s*</h[1-6]>", archive_html)]

        self.assertGreaterEqual(
            len(set(years)),
            2,
            "归档页至少应渲染两个不同的年份标题。",
        )
        self.assertEqual(years, sorted(years, reverse=True), "Year headings should render in descending order.")

    def test_legacy_posts_paths_are_preserved_as_static_aliases(self) -> None:
        archive_page = self.rendered_page_for_href(LEGACY_BLOG_PATH)
        self.assertTrue(archive_page.exists(), "Legacy /posts/ archive path should still resolve after moving canonicals to /blog/.")
        archive_html = archive_page.read_text(encoding="utf-8")
        self.assertIn("https://diff.im/blog/", archive_html)

    def test_google_analytics_is_present_on_every_rendered_html_page(self) -> None:
        html_pages = sorted(self.output_dir.rglob("*.html"))
        self.assertTrue(html_pages, "Rendered site should contain HTML pages.")

        for html_page in html_pages:
            html = html_page.read_text(encoding="utf-8")
            self.assertIn(
                GOOGLE_ANALYTICS_SRC,
                html,
                f"Google Analytics script loader is missing from {html_page.relative_to(self.output_dir)}",
            )
            self.assertIn(
                f"gtag('config', '{GOOGLE_ANALYTICS_ID}')",
                html,
                f"Google Analytics config is missing from {html_page.relative_to(self.output_dir)}",
            )


if __name__ == "__main__":
    unittest.main()
