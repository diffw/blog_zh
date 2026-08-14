from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import posixpath
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


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
KNOWN_WORDPRESS_ID = "1055"
KNOWN_WORDPRESS_REDIRECT = "/blog/2020/07/买了把有点贵的人体工学椅-herman-miller-aeron/"
KNOWN_WORDPRESS_PAGE_ID = "1371"
KNOWN_WORDPRESS_PAGE_REDIRECT = "/about/"
KNOWN_WORDPRESS_ATTACHMENT_ID = "775"
KNOWN_WORDPRESS_ATTACHMENT_REDIRECT = "/blog/2019/02/读书笔记富能仁传/"
TOP_LEVEL_PAGE_PATHS = ("/about/", "/links/", "/now/", "/projects/")
INTERNAL_HOSTS = {"diff.im", "www.diff.im"}
NON_HTML_LINK_EXTENSIONS = (
    ".avif",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
    ".zip",
)


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


class CanonicalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return

        attrs_map = {key: value or "" for key, value in attrs}
        if attrs_map.get("rel") == "canonical" and attrs_map.get("href"):
            self.href = attrs_map["href"]


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

    def canonical_href_for_page(self, page: Path) -> str | None:
        parser = CanonicalLinkParser()
        parser.feed(page.read_text(encoding="utf-8"))
        return parser.href

    def site_relative_href(self, href: str) -> str:
        path = normalize_href(href)
        if self.base_path and path.startswith(f"{self.base_path}/"):
            return path[len(self.base_path) :]
        if self.base_path and path == f"{self.base_path}/":
            return "/"
        return path

    def internal_html_target_for_href(self, source_page: Path, href: str) -> Path | None:
        href = href.strip()
        if not href or href.startswith(("#", "?")):
            return None

        parsed = urlparse(href)
        scheme = parsed.scheme.lower()
        if scheme in {"mailto", "tel", "javascript", "data"}:
            return None
        if scheme and scheme not in {"http", "https"}:
            return None
        if parsed.netloc and parsed.netloc not in INTERNAL_HOSTS:
            return None

        path = unquote(parsed.path)
        if not path or path.endswith(NON_HTML_LINK_EXTENSIONS):
            return None

        if path.startswith("/"):
            site_path = posixpath.normpath(path)
        else:
            source_parent = source_page.parent.relative_to(self.output_dir).as_posix()
            source_dir = "/" if source_parent == "." else f"/{source_parent}"
            site_path = posixpath.normpath(posixpath.join(source_dir, path))

        if not site_path.startswith("/"):
            site_path = f"/{site_path}"
        if site_path == "/":
            return self.output_dir / "index.html"
        if site_path.endswith(".html"):
            return self.output_dir / site_path.lstrip("/")
        return self.output_dir / site_path.lstrip("/") / "index.html"

    def rss_item_links(self, rss_path: str) -> list[str]:
        tree = ET.parse(self.output_dir / rss_path)
        return [
            link.text or ""
            for link in tree.findall("./channel/item/link")
        ]

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

    def test_homepage_shows_projects_before_recent_posts(self) -> None:
        projects_idx = self.homepage_html.index("我的项目")
        posts_idx = self.homepage_html.index("最近文章")

        self.assertLess(projects_idx, posts_idx)
        self.assertIn("RXlingo", self.homepage_html)
        self.assertIn("把刷 X，变成学英语。", self.homepage_html)
        self.assertIn("https://rxlingo.com/", self.homepage_html)
        self.assertLess(self.homepage_html.index("RXlingo"), self.homepage_html.index("VibeCap - Screenshot for AI"))
        self.assertIn("VibeCap - Screenshot for AI", self.homepage_html)
        self.assertIn("Bible 2460 - Verse Clock", self.homepage_html)
        self.assertIn("截图、标注，然后直接粘贴到 AI。", self.homepage_html)
        self.assertIn("每一分钟，都有一句经文。", self.homepage_html)

    def test_projects_page_uses_app_project_list(self) -> None:
        projects_html = self.rendered_page_for_href("/projects/").read_text(encoding="utf-8")

        self.assertIn('class="project-list"', projects_html)
        self.assertIn("RXlingo", projects_html)
        self.assertIn("把刷 X，变成学英语。", projects_html)
        self.assertIn("https://rxlingo.com/", projects_html)
        self.assertLess(projects_html.index("RXlingo"), projects_html.index("VibeCap - Screenshot for AI"))
        self.assertIn("VibeCap - Screenshot for AI", projects_html)
        self.assertIn("Bible 2460 - Verse Clock", projects_html)
        self.assertIn("https://vibecap.dev/", projects_html)
        self.assertIn("https://bible2460.com/", projects_html)

    def test_rxlingo_localizes_on_english_pages(self) -> None:
        english_homepage_html = (self.output_dir / "en" / "index.html").read_text(encoding="utf-8")
        english_projects_html = self.rendered_page_for_href("/en/projects/").read_text(encoding="utf-8")

        for page_html in (english_homepage_html, english_projects_html):
            self.assertIn("RXlingo", page_html)
            self.assertIn("Learn English on X", page_html)
            self.assertIn("https://rxlingo.com/", page_html)
            self.assertNotIn("把刷 X，变成学英语。", page_html)

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

    def test_legacy_posts_redirect_targets_resolve(self) -> None:
        legacy_pages = sorted((self.output_dir / "posts").rglob("index.html"))
        self.assertTrue(legacy_pages, "Legacy /posts/ redirects should be rendered.")

        failures: list[str] = []
        for legacy_page in legacy_pages:
            canonical_href = self.canonical_href_for_page(legacy_page)
            if not canonical_href:
                failures.append(f"{legacy_page.relative_to(self.output_dir)} is missing a canonical redirect target")
                continue

            target = self.internal_html_target_for_href(legacy_page, canonical_href)
            if target is None:
                failures.append(f"{legacy_page.relative_to(self.output_dir)} points outside the site: {canonical_href}")
                continue

            if not target.exists():
                failures.append(
                    f"{legacy_page.relative_to(self.output_dir)} -> {canonical_href} -> {target.relative_to(self.output_dir)}"
                )

        self.assertFalse(
            failures,
            "Legacy /posts/ redirects point at missing pages:\n" + "\n".join(failures[:30]),
        )

    def test_recent_changed_article_aliases_resolve(self) -> None:
        aliases = [
            "/en/blog/2026/06/why-keep-kids-piano-lessons-without-talent/",
            "/blog/2026/04/ai时代再谈设计师-35-岁职业危机/",
            "/posts/2026/04/ai时代再谈设计师-35-岁职业危机/",
            "/blog/2016/08/淫乱/",
            "/posts/2016/08/淫乱/",
        ]

        failures: list[str] = []
        for alias in aliases:
            alias_page = self.rendered_page_for_href(alias)
            if not alias_page.exists():
                failures.append(f"{alias} did not render an alias page")
                continue

            canonical_href = self.canonical_href_for_page(alias_page)
            if not canonical_href:
                failures.append(f"{alias} is missing a canonical target")
                continue

            target = self.internal_html_target_for_href(alias_page, canonical_href)
            if target is None or not target.exists():
                failures.append(f"{alias} -> {canonical_href} did not resolve to a rendered page")

        self.assertFalse(
            failures,
            "Changed article aliases should resolve to existing article pages:\n" + "\n".join(failures),
        )

    def test_ga_404_legacy_path_redirects_resolve(self) -> None:
        with (ROOT / "data" / "legacy-path-redirects.csv").open("r", encoding="utf-8", newline="") as handle:
            redirects = list(csv.DictReader(handle))

        self.assertTrue(redirects, "GA-discovered legacy 404 redirects should be recorded.")

        failures: list[str] = []
        for row in redirects:
            legacy_path = row["legacy_path"]
            target_path = row["target_path"]
            legacy_page = self.rendered_page_for_href(legacy_path)
            if not legacy_page.exists():
                failures.append(f"{legacy_path} did not render a static redirect page")
                continue

            canonical_href = self.canonical_href_for_page(legacy_page)
            if not canonical_href:
                failures.append(f"{legacy_path} is missing a canonical target")
                continue

            canonical_path = normalize_href(unquote(urlparse(canonical_href).path))
            expected_path = normalize_href(target_path)
            if canonical_path != expected_path:
                failures.append(f"{legacy_path} -> {canonical_path}, expected {expected_path}")
                continue

            target = self.rendered_page_for_href(target_path)
            if not target.exists():
                failures.append(f"{legacy_path} target does not exist: {target_path}")

        self.assertFalse(
            failures,
            "GA-discovered legacy 404 redirects should resolve to existing pages:\n" + "\n".join(failures),
        )

    def test_google_analytics_is_present_on_every_rendered_html_page(self) -> None:
        html_pages = sorted(self.output_dir.rglob("*.html"))
        self.assertTrue(html_pages, "Rendered site should contain HTML pages.")

        for html_page in html_pages:
            html = html_page.read_text(encoding="utf-8")
            if '<meta http-equiv="refresh"' in html:
                continue

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

    def test_custom_404_page_tracks_page_not_found_event(self) -> None:
        not_found_page = self.output_dir / "404.html"
        self.assertTrue(not_found_page.exists(), "GitHub Pages should receive a custom 404.html page.")

        html = not_found_page.read_text(encoding="utf-8")

        self.assertIn("页面不存在 / Page not found", html)
        self.assertIn(GOOGLE_ANALYTICS_SRC, html)
        self.assertIn(f"gtag('config', '{GOOGLE_ANALYTICS_ID}')", html)
        self.assertIn("gtag('event', 'page_not_found'", html)
        self.assertIn("document.addEventListener('DOMContentLoaded', adaptLanguageLinks)", html)
        self.assertIn("['/blog/', '/en/blog/', 'Blog']", html)
        self.assertIn("missing_path: path", html)
        self.assertIn("missing_url: window.location.href", html)
        self.assertIn("missing_path_bucket: bucketForPath()", html)
        self.assertIn("missing_extension: extensionForPath()", html)
        self.assertIn("not_found_reason: reasonFor404()", html)
        self.assertIn("page_referrer: referrer", html)
        self.assertIn("referrer_host: referrerHost", html)
        self.assertIn("referrer_path: referrerPath", html)
        self.assertIn("requested_lang: isEnglishPath ? 'en' : 'zh'", html)
        self.assertIn("referrer_type: referrerType", html)
        self.assertIn("legacy_query_type: queryTypeFor404()", html)
        self.assertIn("lang_pref_state: langPrefState()", html)
        self.assertIn("language_auto_redirect_candidate", html)
        self.assertIn("direct_404_template", html)
        self.assertIn("legacy_wordpress_query", html)
        self.assertIn('<meta name="robots" content="noindex,follow">', html)
        self.assertNotIn("https://diff.im/404.html", (self.output_dir / "sitemap.xml").read_text(encoding="utf-8"))

    def test_rendered_pages_include_canonical_links(self) -> None:
        html_pages = sorted(self.output_dir.rglob("*.html"))
        self.assertTrue(html_pages, "Rendered site should contain HTML pages.")

        for html_page in html_pages:
            html = html_page.read_text(encoding="utf-8")
            self.assertRegex(
                html,
                r'<link rel="canonical" href="https://diff\.im/.+?"|<link rel="canonical" href="https://diff\.im/">',
                f"Canonical link is missing from {html_page.relative_to(self.output_dir)}",
            )

    def test_generated_internal_links_resolve_to_html_pages(self) -> None:
        failures: list[str] = []
        html_pages = sorted(self.output_dir.rglob("*.html"))

        for html_page in html_pages:
            relative_page = html_page.relative_to(self.output_dir)
            if relative_page.parts and relative_page.parts[0] == "posts":
                continue

            parser = AnchorParser()
            parser.feed(html_page.read_text(encoding="utf-8"))
            for anchor in parser.anchors:
                href = anchor["href"]
                target = self.internal_html_target_for_href(html_page, href)
                if target and not target.exists():
                    failures.append(
                        f"{relative_page}: {href} -> {target.relative_to(self.output_dir)}"
                    )

        self.assertFalse(
            failures,
            "Rendered generated pages contain internal links that do not resolve:\n"
            + "\n".join(failures[:30]),
        )

    def test_post_pages_include_description_and_social_metadata(self) -> None:
        post_pages = sorted(self.output_dir.glob("blog/*/*/*/index.html"))
        self.assertTrue(post_pages, "Rendered site should include at least one post page.")

        html = post_pages[0].read_text(encoding="utf-8")
        self.assertIn('<meta name="description" content="', html)
        self.assertIn('<meta property="og:type" content="article">', html)
        self.assertIn('<meta name="twitter:card" content="summary">', html)
        self.assertIn('"@type":"BlogPosting"', html)
        self.assertNotIn("0001-01-01T00:00:00Z", html)

    def test_multilingual_pages_include_x_default_and_author_schema(self) -> None:
        html = (self.output_dir / "en" / "blog" / "2026" / "05" / "choose-money-or-passion" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('hreflang="zh-CN"', html)
        self.assertIn('hreflang="en"', html)
        self.assertIn('hreflang="x-default"', html)
        self.assertIn('"@id":"https://diff.im/en/about/#person"', html)
        self.assertIn('"url":"https://diff.im/en/about/"', html)

    def test_language_auto_redirect_uses_translated_permalink(self) -> None:
        zh_html = (
            self.output_dir
            / "blog"
            / "2026"
            / "04"
            / "北美买房经验分享"
            / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('var enTarget = "/en/blog/2026/04/homebuying-tips-from-four-houses/";', zh_html)
        self.assertNotIn("'/en' +", zh_html)
        self.assertIn("gtag('event', 'language_auto_redirect'", zh_html)
        self.assertIn("redirect_to: enTarget", zh_html)
        self.assertIn("redirect_has_translation: 'true'", zh_html)
        self.assertIn("language_auto_redirect_skipped", zh_html)
        self.assertIn("redirect_reason: 'missing_en_translation'", zh_html)

    def test_taxonomy_pages_are_noindex_and_excluded_from_sitemaps(self) -> None:
        zh_tag_html = (self.output_dir / "tags" / "life" / "index.html").read_text(encoding="utf-8")
        en_tag_html = (self.output_dir / "en" / "tags" / "life" / "index.html").read_text(encoding="utf-8")
        zh_sitemap = (self.output_dir / "zh-cn" / "sitemap.xml").read_text(encoding="utf-8")
        en_sitemap = (self.output_dir / "en" / "sitemap.xml").read_text(encoding="utf-8")

        self.assertIn('<meta name="robots" content="noindex,follow">', zh_tag_html)
        self.assertIn('<meta name="robots" content="noindex,follow">', en_tag_html)
        self.assertNotIn("/tags/", zh_sitemap)
        self.assertNotIn("/tags/", en_sitemap)
        self.assertNotIn("/categories/", zh_sitemap)
        self.assertNotIn("/categories/", en_sitemap)
        self.assertIn('hreflang="x-default"', zh_sitemap)
        self.assertIn('hreflang="x-default"', en_sitemap)

    def test_seo_title_override_keeps_article_heading(self) -> None:
        html = (
            self.output_dir
            / "en"
            / "blog"
            / "2026"
            / "05"
            / "one-person-company-non-developer-week-6"
            / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("<title>One-Person Company, Week 6</title>", html)
        self.assertIn("<h1>One-Person Company Practice &amp; The Indie Developer Who Can&#39;t Code - Week 6</h1>", html)

    def test_blog_archive_embeds_legacy_wordpress_query_redirect_map(self) -> None:
        archive_html = self.rendered_page_for_href("/blog/").read_text(encoding="utf-8")
        self.assertIn("window.location.pathname !== '/blog/'", archive_html)
        self.assertIn('legacyPostId = params.get("p")', archive_html)
        self.assertIn('legacyPageId = params.get("page_id")', archive_html)
        self.assertIn('legacyAttachmentId = params.get("attachment_id")', archive_html)
        self.assertIn(f'"{KNOWN_WORDPRESS_ID}":"{KNOWN_WORDPRESS_REDIRECT}"', archive_html)
        self.assertIn(f'"{KNOWN_WORDPRESS_PAGE_ID}":"{KNOWN_WORDPRESS_PAGE_REDIRECT}"', archive_html)
        self.assertIn(f'"{KNOWN_WORDPRESS_ATTACHMENT_ID}":"{KNOWN_WORDPRESS_ATTACHMENT_REDIRECT}"', archive_html)

    def test_wordpress_query_redirect_targets_resolve(self) -> None:
        map_files = [
            ROOT / "data" / "wordpress_id_map.json",
            ROOT / "data" / "wordpress_page_id_map.json",
            ROOT / "data" / "wordpress_attachment_id_map.json",
        ]

        failures: list[str] = []
        for map_file in map_files:
            redirects = json.loads(map_file.read_text(encoding="utf-8"))
            self.assertIsInstance(redirects, dict)
            for legacy_id, target_path in redirects.items():
                target = self.rendered_page_for_href(str(target_path))
                if not target.exists():
                    failures.append(f"{map_file.name}:{legacy_id} -> {target_path}")

        self.assertFalse(
            failures,
            "WordPress query redirect maps point at missing pages:\n" + "\n".join(failures[:40]),
        )

    def test_wordpress_post_csv_and_json_redirect_maps_match(self) -> None:
        with (ROOT / "data" / "wordpress-url-map.csv").open("r", encoding="utf-8", newline="") as handle:
            csv_map = {
                row["wordpress_id"]: row["new_url"]
                for row in csv.DictReader(handle)
                if row.get("wordpress_id") and row.get("new_url")
            }

        json_map = json.loads((ROOT / "data" / "wordpress_id_map.json").read_text(encoding="utf-8"))

        self.assertEqual(csv_map, json_map)

    def test_rss_feeds_only_expose_language_specific_blog_posts(self) -> None:
        zh_home_links = self.rss_item_links("index.xml")
        zh_blog_links = self.rss_item_links("blog/index.xml")
        en_home_links = self.rss_item_links("en/index.xml")
        en_blog_links = self.rss_item_links("en/blog/index.xml")

        self.assertGreater(len(zh_home_links), 0)
        self.assertGreater(len(en_home_links), 0)
        self.assertEqual(zh_home_links, zh_blog_links)
        self.assertEqual(en_home_links, en_blog_links)
        self.assertTrue(all(link.startswith("https://diff.im/blog/") for link in zh_home_links))
        self.assertTrue(all(link.startswith("https://diff.im/en/blog/") for link in en_home_links))

        all_feed_links = zh_home_links + zh_blog_links + en_home_links + en_blog_links
        for page_path in TOP_LEVEL_PAGE_PATHS:
            self.assertNotIn(f"https://diff.im{page_path}", all_feed_links)
            self.assertNotIn(f"https://diff.im/en{page_path}", all_feed_links)

    def test_pages_advertise_language_specific_blog_rss(self) -> None:
        zh_home = (self.output_dir / "index.html").read_text(encoding="utf-8")
        en_home = (self.output_dir / "en" / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="https://diff.im/blog/index.xml"', zh_home)
        self.assertIn('title="Diff客旅日志 Blog RSS"', zh_home)
        self.assertNotIn('href="https://diff.im/index.xml"', zh_home)

        self.assertIn('href="https://diff.im/en/blog/index.xml"', en_home)
        self.assertIn("Diff&#39;s Pilgrimage Notes Blog RSS", en_home)
        self.assertNotIn('href="https://diff.im/en/index.xml"', en_home)

    def test_robots_txt_mentions_sitemap(self) -> None:
        robots_txt = (self.output_dir / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("User-agent: *", robots_txt)
        self.assertIn("Sitemap: https://diff.im/sitemap.xml", robots_txt)


if __name__ == "__main__":
    unittest.main()
