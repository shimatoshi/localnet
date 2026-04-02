"""catalog_builder.py のテスト"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import catalog_builder


class TestBuildCatalog:
    def setup_method(self):
        self._orig_cache_base = config.CACHE_BASE
        self.tmpdir = tempfile.mkdtemp()
        config.CACHE_BASE = self.tmpdir
        catalog_builder.CACHE_BASE = self.tmpdir

    def teardown_method(self):
        config.CACHE_BASE = self._orig_cache_base
        catalog_builder.CACHE_BASE = self._orig_cache_base
        # Clean up catalog cache
        with catalog_builder._catalog_lock:
            catalog_builder._catalog_cache.clear()
            catalog_builder._catalog_mtime.clear()

    def _make_site(self, domain, files):
        """Helper: create domain/domain/ structure with files dict {relpath: content_bytes}"""
        base = os.path.join(self.tmpdir, domain, domain)
        os.makedirs(base, exist_ok=True)
        for relpath, content in files.items():
            fpath = os.path.join(base, relpath)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'wb') as f:
                f.write(content)

    def test_build_basic(self):
        self._make_site("example.com", {
            "index.html": b"<html><head><title>Example</title></head><body>Hello</body></html>",
            "about.html": b"<html><head><title>About</title></head><body>About</body></html>",
        })
        catalog_path = catalog_builder.build_catalog("example.com")
        assert os.path.isfile(catalog_path)
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        assert len(catalog) == 2
        titles = {e['title'] for e in catalog}
        assert "Example" in titles
        assert "About" in titles

    def test_build_ignores_non_html(self):
        self._make_site("test.org", {
            "index.html": b"<html><head><title>Home</title></head></html>",
            "style.css": b"body { color: red; }",
            "image.png": b'\x89PNG\r\n\x1a\n\x00\x00',
        })
        catalog_path = catalog_builder.build_catalog("test.org")
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        assert len(catalog) == 1
        assert catalog[0]['title'] == "Home"

    def test_build_empty_site(self):
        domain = "empty.com"
        os.makedirs(os.path.join(self.tmpdir, domain, domain), exist_ok=True)
        catalog_path = catalog_builder.build_catalog(domain)
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        assert catalog == []

    def test_build_title_fallback_to_path(self):
        """HTML without <title> should fall back to path"""
        self._make_site("notitle.com", {
            "page.html": b"<html><body>No title here</body></html>",
        })
        catalog_path = catalog_builder.build_catalog("notitle.com")
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        assert len(catalog) == 1
        assert catalog[0]['title'] == "page.html"


class TestSearchCatalogs:
    def setup_method(self):
        self._orig_cache_base = config.CACHE_BASE
        self.tmpdir = tempfile.mkdtemp()
        config.CACHE_BASE = self.tmpdir
        catalog_builder.CACHE_BASE = self.tmpdir
        with catalog_builder._catalog_lock:
            catalog_builder._catalog_cache.clear()
            catalog_builder._catalog_mtime.clear()

    def teardown_method(self):
        config.CACHE_BASE = self._orig_cache_base
        catalog_builder.CACHE_BASE = self._orig_cache_base
        with catalog_builder._catalog_lock:
            catalog_builder._catalog_cache.clear()
            catalog_builder._catalog_mtime.clear()

    def _write_catalog(self, domain, entries):
        ddir = os.path.join(self.tmpdir, domain)
        os.makedirs(ddir, exist_ok=True)
        with open(os.path.join(ddir, 'catalog.json'), 'w') as f:
            json.dump(entries, f)

    def test_search_by_title(self):
        self._write_catalog("example.com", [
            {"url": "https://example.com/page", "title": "Hello World", "path": "page.html"},
            {"url": "https://example.com/other", "title": "Other Page", "path": "other.html"},
        ])
        results = catalog_builder.search_catalogs("hello")
        assert len(results) == 1
        assert results[0]['title'] == "Hello World"
        assert results[0]['domain'] == "example.com"

    def test_search_by_path(self):
        self._write_catalog("test.org", [
            {"url": "https://test.org/docs/api", "title": "API Docs", "path": "docs/api.html"},
        ])
        results = catalog_builder.search_catalogs("docs/api")
        assert len(results) == 1

    def test_search_no_match(self):
        self._write_catalog("test.org", [
            {"url": "https://test.org/page", "title": "Page", "path": "page.html"},
        ])
        results = catalog_builder.search_catalogs("nonexistent")
        assert results == []

    def test_search_limit(self):
        entries = [
            {"url": f"https://test.org/p{i}", "title": f"Page {i}", "path": f"p{i}.html"}
            for i in range(100)
        ]
        self._write_catalog("test.org", entries)
        results = catalog_builder.search_catalogs("Page", limit=5)
        assert len(results) == 5

    def test_search_empty_cache_base(self):
        # Point to nonexistent directory
        catalog_builder.CACHE_BASE = os.path.join(self.tmpdir, "nonexistent")
        results = catalog_builder.search_catalogs("anything")
        assert results == []
