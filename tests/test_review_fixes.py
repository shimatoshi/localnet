"""コードレビュー修正のテスト — #3, #5, #6, #7, #12, #13"""

import sys
import os
import json
import tarfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import catalog_builder
import pytest


@pytest.fixture
def client(tmp_path):
    """テスト用Flaskクライアント（隔離されたCACHE_BASE）"""
    import server as server_mod
    import jobs as jobs_mod
    import routes.cache as cache_mod
    import routes.transfer as transfer_mod

    test_cache = str(tmp_path / "cache")
    os.makedirs(test_cache, exist_ok=True)

    originals = {
        'config': config.CACHE_BASE,
        'catalog_builder': catalog_builder.CACHE_BASE,
        'server': getattr(server_mod, 'CACHE_BASE', None),
        'jobs': jobs_mod.CACHE_BASE,
        'cache_route': cache_mod.CACHE_BASE,
        'transfer_route': transfer_mod.CACHE_BASE,
    }

    config.CACHE_BASE = test_cache
    catalog_builder.CACHE_BASE = test_cache
    if hasattr(server_mod, 'CACHE_BASE'):
        server_mod.CACHE_BASE = test_cache
    jobs_mod.CACHE_BASE = test_cache
    cache_mod.CACHE_BASE = test_cache
    transfer_mod.CACHE_BASE = test_cache

    with catalog_builder._catalog_lock:
        catalog_builder._catalog_cache.clear()
        catalog_builder._catalog_mtime.clear()

    server_mod.app.config['TESTING'] = True

    with server_mod.app.test_client() as c:
        yield c

    config.CACHE_BASE = originals['config']
    catalog_builder.CACHE_BASE = originals['catalog_builder']
    if originals['server'] is not None:
        server_mod.CACHE_BASE = originals['server']
    jobs_mod.CACHE_BASE = originals['jobs']
    cache_mod.CACHE_BASE = originals['cache_route']
    transfer_mod.CACHE_BASE = originals['transfer_route']
    with catalog_builder._catalog_lock:
        catalog_builder._catalog_cache.clear()
        catalog_builder._catalog_mtime.clear()


# === #3: get_active_jobs public API ===

class TestGetActiveJobs:
    def setup_method(self):
        from jobs import _jobs, _jobs_lock
        with _jobs_lock:
            _jobs.clear()

    def teardown_method(self):
        from jobs import _jobs, _jobs_lock
        with _jobs_lock:
            _jobs.clear()

    def test_get_active_jobs_empty(self):
        from jobs import get_active_jobs
        assert get_active_jobs() == []

    def test_get_active_jobs_returns_running(self):
        from jobs import Job, _jobs, _jobs_lock, get_active_jobs
        job = Job()
        job.status = 'running'
        job.domain = 'test.com'
        with _jobs_lock:
            _jobs[job.id] = job
        result = get_active_jobs()
        assert len(result) == 1
        assert result[0]['job_id'] == job.id
        assert result[0]['status'] == 'running'

    def test_get_active_jobs_excludes_done(self):
        from jobs import Job, _jobs, _jobs_lock, get_active_jobs
        job = Job()
        job.status = 'done'
        with _jobs_lock:
            _jobs[job.id] = job
        assert get_active_jobs() == []

    def test_get_active_jobs_excludes_pending(self):
        from jobs import Job, _jobs, _jobs_lock, get_active_jobs
        job = Job()
        job.status = 'pending'
        with _jobs_lock:
            _jobs[job.id] = job
        assert get_active_jobs() == []

    def test_api_active_jobs_endpoint(self, client):
        """routes/crawl.py がget_active_jobsを使ってることを確認"""
        resp = client.get('/api/jobs/active')
        assert resp.status_code == 200
        assert resp.get_json() == []


# === #5: tarfile filter互換 ===

class TestImportFilterCompat:
    def test_import_valid_tar(self, client, tmp_path):
        """tar.gzインポートがfilter='data'有無にかかわらず動作する"""
        domain = "import-test.com"
        site_dir = tmp_path / domain
        site_dir.mkdir()
        (site_dir / "index.html").write_text("<html><title>Test</title></html>")

        tar_path = str(tmp_path / "test.tar.gz")
        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(str(site_dir), arcname=domain)

        with open(tar_path, 'rb') as f:
            resp = client.post(
                '/api/import',
                data={'file': (f, 'test.tar.gz')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'job_id' in data
        assert data.get('domain') == domain

    def test_import_rejects_path_traversal(self, client, tmp_path):
        """パストラバーサルを含むtar.gzを拒否"""
        tar_path = str(tmp_path / "evil.tar.gz")
        evil_dir = tmp_path / "evil_src"
        evil_dir.mkdir()
        (evil_dir / "safe.txt").write_text("safe")

        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(str(evil_dir / "safe.txt"), arcname="../etc/passwd")

        with open(tar_path, 'rb') as f:
            resp = client.post(
                '/api/import',
                data={'file': (f, 'evil.tar.gz')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400
        assert 'error' in resp.get_json()


# === #12: cache.py パストラバーサル ===

class TestCachePathTraversal:
    def test_rejects_dotdot(self, client, tmp_path):
        domain = "safe.com"
        site_dir = os.path.join(config.CACHE_BASE, domain)
        os.makedirs(site_dir, exist_ok=True)
        with open(os.path.join(site_dir, "page.html"), "w") as f:
            f.write("<html>safe</html>")

        resp = client.get(f'/api/cache/{domain}/../../../etc/passwd')
        assert resp.status_code in (400, 404)

    def test_serves_valid_file(self, client, tmp_path):
        domain = "serve.com"
        site_dir = os.path.join(config.CACHE_BASE, domain)
        os.makedirs(site_dir, exist_ok=True)
        with open(os.path.join(site_dir, "page.html"), "w") as f:
            f.write("<html><title>Hello</title></html>")

        resp = client.get(f'/api/cache/{domain}/page.html')
        assert resp.status_code == 200
        assert b'Hello' in resp.data

    def test_serves_query_param_filename(self, client, tmp_path):
        """wgetがクエリパラメータ込みで保存したファイルを配信できる"""
        domain = "qp.com"
        css_dir = os.path.join(config.CACHE_BASE, domain, "_static")
        os.makedirs(css_dir, exist_ok=True)
        # wgetが保存するファイル名: classic.css?v=abc123.css
        with open(os.path.join(css_dir, "style.css?v=abc123.css"), "w") as f:
            f.write("body { color: red; }")

        # ブラウザからはクエリパラメータなしでリクエストが来る
        resp = client.get(f'/api/cache/{domain}/_static/style.css')
        assert resp.status_code == 200
        assert b'color: red' in resp.data

    def test_exact_match_takes_priority(self, client, tmp_path):
        """クエリパラメータなしのファイルが存在する場合はそちらを優先"""
        domain = "exact.com"
        css_dir = os.path.join(config.CACHE_BASE, domain, "css")
        os.makedirs(css_dir, exist_ok=True)
        with open(os.path.join(css_dir, "main.css"), "w") as f:
            f.write("body { exact: true; }")
        with open(os.path.join(css_dir, "main.css?v=old.css"), "w") as f:
            f.write("body { old: true; }")

        resp = client.get(f'/api/cache/{domain}/css/main.css')
        assert resp.status_code == 200
        assert b'exact: true' in resp.data


# === #13: DATASETS_DIR削除確認 ===

class TestDeadCodeRemoval:
    def test_datasets_dir_not_in_config(self):
        """DATASETS_DIRがconfig.pyからエクスポートされていない"""
        assert not hasattr(config, 'DATASETS_DIR')


# === routes/crawl.py が _jobs をインポートしていないことの確認 ===

class TestNoPrivateImports:
    def test_crawl_route_no_private_jobs_import(self):
        """routes/crawl.pyが_jobsや_jobs_lockを直接インポートしていない"""
        import routes.crawl as crawl_mod
        assert not hasattr(crawl_mod, '_jobs'), "routes/crawl.py should not import _jobs"
        assert not hasattr(crawl_mod, '_jobs_lock'), "routes/crawl.py should not import _jobs_lock"
