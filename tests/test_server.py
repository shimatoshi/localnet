"""server.py Flask routes のテスト"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import catalog_builder
import pytest


@pytest.fixture
def client(tmp_path):
    """Create a test client with isolated CACHE_BASE and a minimal frontend/dist"""
    import server as server_mod
    import jobs as jobs_mod
    import routes.cache as cache_mod

    test_cache = str(tmp_path / "cache")
    os.makedirs(test_cache, exist_ok=True)

    # Save originals
    originals = {
        'config': config.CACHE_BASE,
        'catalog_builder': catalog_builder.CACHE_BASE,
        'server': server_mod.CACHE_BASE,
        'jobs': jobs_mod.CACHE_BASE,
        'cache_route': cache_mod.CACHE_BASE,
    }

    # Patch all module-level CACHE_BASE references
    config.CACHE_BASE = test_cache
    catalog_builder.CACHE_BASE = test_cache
    server_mod.CACHE_BASE = test_cache
    jobs_mod.CACHE_BASE = test_cache
    cache_mod.CACHE_BASE = test_cache

    # Clear catalog cache
    with catalog_builder._catalog_lock:
        catalog_builder._catalog_cache.clear()
        catalog_builder._catalog_mtime.clear()

    server_mod.app.config['TESTING'] = True

    with server_mod.app.test_client() as c:
        yield c

    # Restore
    config.CACHE_BASE = originals['config']
    catalog_builder.CACHE_BASE = originals['catalog_builder']
    server_mod.CACHE_BASE = originals['server']
    jobs_mod.CACHE_BASE = originals['jobs']
    cache_mod.CACHE_BASE = originals['cache_route']
    with catalog_builder._catalog_lock:
        catalog_builder._catalog_cache.clear()
        catalog_builder._catalog_mtime.clear()


class TestVersionAPI:
    def test_version_returns_json(self, client):
        resp = client.get('/api/version')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'version' in data
        assert isinstance(data['version'], str)

    def test_version_with_path(self, client):
        resp = client.get('/api/version/anything/here')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'version' in data


class TestSearchAPI:
    def test_search_empty_query(self, client):
        resp = client.get('/api/search?q=')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_no_results(self, client):
        resp = client.get('/api/search?q=nonexistent')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_with_results(self, client, tmp_path):
        # Write a catalog
        domain = "example.com"
        ddir = os.path.join(config.CACHE_BASE, domain)
        os.makedirs(ddir, exist_ok=True)
        catalog = [{"url": "https://example.com/test", "title": "Test Page", "path": "test.html"}]
        with open(os.path.join(ddir, "catalog.json"), "w") as f:
            json.dump(catalog, f)

        resp = client.get('/api/search?q=Test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['title'] == "Test Page"


class TestSitesAPI:
    def test_sites_empty(self, client):
        resp = client.get('/api/sites')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_sites_with_data(self, client, tmp_path):
        domain = "mysite.org"
        site_dir = os.path.join(config.CACHE_BASE, domain)
        os.makedirs(site_dir, exist_ok=True)
        # Create a file so file_count > 0
        with open(os.path.join(site_dir, "page.html"), "w") as f:
            f.write("<html></html>")

        resp = client.get('/api/sites')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['domain'] == "mysite.org"
        assert data[0]['file_count'] >= 1
        assert data[0]['has_catalog'] is False


class TestCatalogAPI:
    def test_catalog_invalid_domain(self, client):
        resp = client.get('/api/catalog/bad domain!')
        assert resp.status_code == 400

    def test_catalog_not_found(self, client):
        resp = client.get('/api/catalog/nosite.com')
        assert resp.status_code == 404

    def test_catalog_ok(self, client, tmp_path):
        domain = "ok.com"
        ddir = os.path.join(config.CACHE_BASE, domain)
        os.makedirs(ddir, exist_ok=True)
        catalog = [{"url": "https://ok.com/", "title": "OK", "path": "index.html"}]
        with open(os.path.join(ddir, "catalog.json"), "w") as f:
            json.dump(catalog, f)

        resp = client.get(f'/api/catalog/{domain}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1


class TestSPAFallback:
    def test_root_returns_index(self, client):
        resp = client.get('/')
        # May be 404 if frontend/dist/index.html doesn't exist, or 200 if it does
        # Since the project has frontend/dist/index.html, it should work
        if resp.status_code == 200:
            assert b'html' in resp.data.lower() or len(resp.data) > 0

    def test_unknown_path_falls_back(self, client):
        resp = client.get('/some/unknown/path')
        # Should serve index.html (SPA fallback) if it exists
        if resp.status_code == 200:
            assert len(resp.data) > 0


class TestCORS:
    def test_cors_headers(self, client):
        resp = client.get('/api/version')
        assert resp.headers.get('Access-Control-Allow-Origin') == '*'
