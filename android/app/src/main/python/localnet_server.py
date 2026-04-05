"""localnet Flask server — APK版（モノリシック）"""

import os
import sys
import json
import re
import time
import mimetypes
import threading
import queue
import uuid
import tarfile
import zipfile
import shutil
import tempfile
from urllib.parse import urlparse, unquote, quote

from flask import Flask, request, jsonify, send_from_directory, send_file, make_response, Response
from werkzeug.utils import secure_filename


def create_app(base_dir, port):
    frontend_dir = os.path.join(base_dir, 'frontend', 'dist')
    cache_dir = os.path.join(base_dir, 'cache')
    sites_dir = os.path.join(base_dir, 'sites')
    import_dir = os.environ.get('SHIMANET_IMPORT_DIR', os.path.join(base_dir, 'import'))
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(sites_dir, exist_ok=True)
    os.makedirs(import_dir, exist_ok=True)

    # config モジュールの値を上書き
    os.environ['LOCALNET_BASE'] = base_dir

    app = Flask(__name__, static_folder=frontend_dir)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    _VERSION = str(int(time.time()))

    USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36")

    AD_DOMAINS = [
        'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
        'google-analytics.com', 'googletagmanager.com',
    ]

    # --- ユーティリティ ---
    _DOMAIN_RE = re.compile(r'^[a-zA-Z0-9._-]+$')

    def is_valid_domain(d):
        return bool(d) and _DOMAIN_RE.match(d)

    def detect_charset(raw_head):
        head = raw_head[:4096].lower()
        m = re.search(rb'<meta\s[^>]*charset=["\']?([a-zA-Z0-9_-]+)', head)
        if m:
            return m.group(1).decode('ascii', errors='ignore')
        m = re.search(rb'content-type[^>]*charset=([a-zA-Z0-9_-]+)', head)
        if m:
            return m.group(1).decode('ascii', errors='ignore')
        return None

    def detect_mime_from_bytes(data):
        if len(data) < 4:
            return None
        if data.startswith(b'\x89PNG'):
            return 'image/png'
        if data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if data.startswith(b'GIF8'):
            return 'image/gif'
        if data[:4] == b'RIFF' and len(data) >= 12 and data[8:12] == b'WEBP':
            return 'image/webp'
        head_lower = data[:256].lower()
        if b'<html' in head_lower or b'<!doctype' in head_lower:
            return 'text/html'
        return None

    # --- カタログ ---
    _catalog_cache = {}
    _catalog_mtime = {}
    _catalog_lock = threading.Lock()

    def _is_html(filepath):
        mime, _ = mimetypes.guess_type(filepath)
        if mime and 'html' in mime:
            return True
        try:
            with open(filepath, 'rb') as f:
                head = f.read(256).lower()
            return b'<html' in head or b'<!doctype' in head
        except Exception:
            return False

    def _extract_title(filepath):
        try:
            with open(filepath, 'rb') as f:
                head = f.read(8192)
            charset = detect_charset(head) or 'utf-8'
            html = head.decode(charset, errors='replace')
            m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            if m:
                return re.sub(r'<[^>]+>', '', m.group(1)).strip()
        except Exception:
            pass
        return ''

    def _extract_images(filepath, domain, page_path):
        images = []
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            charset = detect_charset(data[:8192]) or 'utf-8'
            html = data.decode(charset, errors='replace')
            for m in re.finditer(r'<img\s[^>]*?src=["\']([^"\']+)["\'][^>]*?>', html, re.IGNORECASE | re.DOTALL):
                tag = m.group(0)
                src = m.group(1)
                if src.startswith('data:'):
                    continue
                alt = ''
                alt_m = re.search(r'alt=["\']([^"\']*)["\']', tag, re.IGNORECASE)
                if alt_m:
                    alt = alt_m.group(1).strip()
                if src.startswith('http://') or src.startswith('https://'):
                    img_url = src
                elif src.startswith('/'):
                    img_url = f'/api/cache/{domain}{src}'
                else:
                    page_dir = '/'.join(page_path.split('/')[:-1])
                    img_url = f'/api/cache/{domain}/{page_dir}/{src}' if page_dir else f'/api/cache/{domain}/{src}'
                images.append({'src': img_url, 'alt': alt, 'page_path': page_path,
                               'page_url': f'https://{domain}/{quote(page_path, safe="/:@!$&()*+,;=-._~")}'})
        except Exception:
            pass
        return images

    def build_catalog(domain, log=None):
        _log = log or (lambda x: None)
        domain_cache = os.path.join(cache_dir, domain)
        base = os.path.join(domain_cache, domain)
        if not os.path.isdir(base):
            base = domain_cache

        catalog = []
        all_images = []
        for root, _, files in os.walk(base):
            for fname in files:
                filepath = os.path.join(root, fname)
                if not _is_html(filepath):
                    continue
                relpath = os.path.relpath(filepath, base).replace(os.sep, '/')
                title = _extract_title(filepath)
                url = f'https://{domain}/{quote(relpath, safe="/:@!$&()*+,;=-._~")}'
                catalog.append({'url': url, 'title': title or relpath, 'path': relpath})
                images = _extract_images(filepath, domain, relpath)
                all_images.extend(images)

        catalog_path = os.path.join(domain_cache, 'catalog.json')
        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False)
        images_path = os.path.join(domain_cache, 'images.json')
        with open(images_path, 'w', encoding='utf-8') as f:
            json.dump(all_images, f, ensure_ascii=False)
        _log(f"カタログ生成完了: {len(catalog)} ページ, {len(all_images)} 画像")
        return catalog_path

    def load_catalog(domain):
        path = os.path.join(cache_dir, domain, 'catalog.json')
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        with _catalog_lock:
            if domain in _catalog_cache and _catalog_mtime.get(domain) == mtime:
                return _catalog_cache[domain]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with _catalog_lock:
                _catalog_cache[domain] = data
                _catalog_mtime[domain] = mtime
            return data
        except Exception:
            return None

    def load_images(domain):
        path = os.path.join(cache_dir, domain, 'images.json')
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        cache_key = f'img_{domain}'
        with _catalog_lock:
            if cache_key in _catalog_cache and _catalog_mtime.get(cache_key) == mtime:
                return _catalog_cache[cache_key]
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with _catalog_lock:
                _catalog_cache[cache_key] = data
                _catalog_mtime[cache_key] = mtime
            return data
        except Exception:
            return None

    def search_catalogs(q, limit=50):
        q_lower = q.lower()
        results = []
        if not os.path.isdir(cache_dir):
            return results
        for name in sorted(os.listdir(cache_dir)):
            if not os.path.isdir(os.path.join(cache_dir, name)):
                continue
            catalog = load_catalog(name)
            if not catalog:
                continue
            for entry in catalog:
                if q_lower in entry['title'].lower() or q_lower in entry.get('path', '').lower():
                    results.append({
                        'url': entry['url'], 'title': entry['title'],
                        'path': entry['path'], 'domain': name,
                    })
                    if len(results) >= limit:
                        return results
        return results

    def search_images(q, limit=50):
        q_lower = q.lower()
        results = []
        if not os.path.isdir(cache_dir):
            return results
        for name in sorted(os.listdir(cache_dir)):
            if not os.path.isdir(os.path.join(cache_dir, name)):
                continue
            images = load_images(name)
            if not images:
                continue
            for img in images:
                if q_lower in (img.get('alt') or '').lower() or q_lower in img.get('src', '').lower() or q_lower in img.get('page_path', '').lower():
                    results.append({**img, 'domain': name})
                    if len(results) >= limit:
                        return results
        return results

    def get_all_sites():
        sites = []
        if not os.path.isdir(cache_dir):
            return sites
        for name in sorted(os.listdir(cache_dir)):
            site_dir = os.path.join(cache_dir, name)
            if not os.path.isdir(site_dir):
                continue
            file_count = sum(1 for _, _, files in os.walk(site_dir) for f in files)
            catalog_path = os.path.join(site_dir, 'catalog.json')
            has_catalog = os.path.exists(catalog_path)
            page_count = 0
            if has_catalog:
                try:
                    with open(catalog_path, 'r') as f:
                        page_count = len(json.load(f))
                except Exception:
                    pass
            sites.append({"domain": name, "file_count": file_count,
                          "has_catalog": has_catalog, "page_count": page_count})
        return sites

    # --- ジョブ管理 ---
    _jobs = {}
    _jobs_lock = threading.Lock()
    _JOB_TTL = 3600

    class Job:
        def __init__(self):
            self.id = str(uuid.uuid4())[:8]
            self.status = 'pending'
            self.log_queue = queue.Queue(maxsize=1000)
            self.error = None
            self.domain = None
            self._crawler = None
            self._stop_requested = threading.Event()
            self._finished_at = None

        def log(self, message):
            item = {"type": "log", "message": str(message)}
            while self.log_queue.full():
                try: self.log_queue.get_nowait()
                except queue.Empty: break
            try: self.log_queue.put_nowait(item)
            except queue.Full: pass

        def finish(self, **extra):
            self.status = 'done'
            self._finished_at = time.time()
            self.log_queue.put({"type": "done", "domain": self.domain, **extra})

        def fail(self, error):
            self.status = 'error'
            self._finished_at = time.time()
            self.error = str(error)
            self.log_queue.put({"type": "error", "message": self.error})

        def to_dict(self):
            d = {'job_id': self.id, 'status': self.status, 'domain': self.domain,
                 'error': self.error, 'page_count': 0}
            if self._crawler:
                d['page_count'] = self._crawler.page_count
            return d

    def _purge_old_jobs():
        now = time.time()
        expired = [jid for jid, j in _jobs.items()
                   if j._finished_at and now - j._finished_at > _JOB_TTL]
        for jid in expired:
            del _jobs[jid]

    def get_job(job_id):
        with _jobs_lock:
            return _jobs.get(job_id)

    def stop_job(job_id):
        job = get_job(job_id)
        if not job:
            return False
        job._stop_requested.set()
        if job._crawler:
            job._crawler.stop()
        return job.status in ('running', 'pending')

    def _start_job(target, *args):
        job = Job()
        with _jobs_lock:
            _purge_old_jobs()
            _jobs[job.id] = job
        threading.Thread(target=target, args=(job, *args), daemon=True).start()
        return job

    def _run_crawl(job, url, depth, delay, exclude):
        job.status = 'running'
        domain = urlparse(url).netloc
        job.domain = domain
        try:
            from singlefile_crawler import SingleFileCrawler
            crawler = SingleFileCrawler(start_url=url, max_depth=depth, delay=delay,
                                        log=job.log, exclude=exclude)
            job._crawler = crawler
            job.domain = crawler.domain
            job.log(f"クロール開始: {domain}")
            crawler.run()
            if not job._stop_requested.is_set():
                job.log("--- カタログ生成中 ---")
                build_catalog(crawler.domain, log=job.log)
                job.finish()
        except Exception as e:
            if not job._stop_requested.is_set():
                job.fail(e)
        finally:
            job._crawler = None
            if job._stop_requested.is_set() and job.status not in ('done', 'error'):
                job.log("--- 停止: カタログ生成中 ---")
                try:
                    build_catalog(job.domain, log=job.log)
                except Exception:
                    pass
                job.finish()

    def _run_resume(job, domain):
        d_cache = os.path.join(cache_dir, domain)
        if not os.path.isdir(d_cache):
            job.status = 'running'
            job.domain = domain
            job.fail(FileNotFoundError(f'キャッシュなし: {domain}'))
            return
        start_url = f'https://{domain}/'
        job.status = 'running'
        job.domain = domain
        try:
            from singlefile_crawler import SingleFileCrawler
            crawler = SingleFileCrawler(start_url=start_url, max_depth=0, delay=1.0, log=job.log)
            job._crawler = crawler
            job.log(f"クロール再開: {domain}")
            crawler.run(resume=True)
            if not job._stop_requested.is_set():
                job.log("--- カタログ生成中 ---")
                build_catalog(domain, log=job.log)
                job.finish()
        except Exception as e:
            if not job._stop_requested.is_set():
                job.fail(e)
        finally:
            job._crawler = None

    def _run_build(job, domain):
        job.status = 'running'
        job.domain = domain
        try:
            build_catalog(domain, log=job.log)
            job.finish()
        except Exception as e:
            job.fail(e)

    def _run_import(job, domain):
        job.status = 'running'
        job.domain = domain
        try:
            d_cache = os.path.join(cache_dir, domain)
            if not os.path.isdir(d_cache):
                raise FileNotFoundError(f'キャッシュなし: {domain}')
            job.log(f"インポート: {domain}")
            job.log("--- カタログ生成中 ---")
            build_catalog(domain, log=job.log)
            job.finish()
        except Exception as e:
            job.fail(e)

    # --- CORS ---
    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return response

    # --- API ---
    @app.route('/assets/<path:path>')
    def serve_assets(path):
        return send_from_directory(os.path.join(frontend_dir, 'assets'), path)

    @app.route('/api/version')
    @app.route('/api/version/<path:_>')
    def api_version(_=None):
        return jsonify({"version": _VERSION})

    @app.route('/api/search')
    def api_search():
        q = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 50))
        if not q:
            return jsonify([])
        return jsonify(search_catalogs(q, limit=limit))

    @app.route('/api/search/images')
    def api_search_images():
        q = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 50))
        if not q:
            return jsonify([])
        return jsonify(search_images(q, limit=limit))

    @app.route('/api/catalog/<domain>')
    def api_catalog(domain):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        catalog_path = os.path.join(cache_dir, domain, 'catalog.json')
        if not os.path.isfile(catalog_path):
            return jsonify({"error": "カタログが見つかりません"}), 404
        return send_file(catalog_path, mimetype='application/json')

    @app.route('/api/sites')
    def api_sites():
        return jsonify(get_all_sites())

    @app.route('/api/sites/versions')
    def api_sites_versions():
        versions = {}
        if os.path.isdir(cache_dir):
            for name in os.listdir(cache_dir):
                catalog = os.path.join(cache_dir, name, 'catalog.json')
                if os.path.isfile(catalog):
                    versions[name] = int(os.path.getmtime(catalog))
        return jsonify(versions)

    # --- キャッシュ配信 ---
    def _find_file(base, subpath):
        filepath = os.path.realpath(os.path.join(base, subpath))
        real_base = os.path.realpath(base)
        if not filepath.startswith(real_base + os.sep) and filepath != real_base:
            return None
        if os.path.isfile(filepath):
            return filepath
        parent = os.path.dirname(filepath)
        basename = os.path.basename(filepath)
        if os.path.isdir(parent):
            for fname in os.listdir(parent):
                if fname.startswith(basename + '?') or fname.startswith(basename + '%3F'):
                    candidate = os.path.join(parent, fname)
                    if os.path.isfile(candidate):
                        return candidate
        return None

    @app.route('/api/cache/<domain>/<path:subpath>')
    def api_cache(domain, subpath):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        subpath = unquote(subpath)
        base = os.path.join(cache_dir, domain, domain)
        if not os.path.isdir(base):
            base = os.path.join(cache_dir, domain)
        filepath = _find_file(base, subpath)
        if not filepath and not os.path.splitext(subpath)[1]:
            filepath = _find_file(base, subpath.rstrip('/') + '.html')
        if not filepath:
            return '', 404
        mime, _ = mimetypes.guess_type(filepath)
        if not mime:
            try:
                with open(filepath, 'rb') as f:
                    head = f.read(256)
                mime = detect_mime_from_bytes(head) or 'application/octet-stream'
            except Exception:
                mime = 'application/octet-stream'
        if mime and mime.startswith('text/html'):
            try:
                with open(filepath, 'rb') as f:
                    head = f.read(4096)
                charset = detect_charset(head)
                if charset:
                    mime = f'text/html; charset={charset}'
            except Exception:
                pass
        response = make_response(send_file(filepath, mimetype=mime))
        response.headers['Content-Type'] = mime
        return response

    # --- クロール ---
    @app.route('/api/crawl', methods=['POST'])
    def api_crawl():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "リクエストボディが不正です"}), 400
        url = data.get('url', '').strip()
        if not url:
            return jsonify({"error": "URLを指定してください"}), 400
        try:
            depth = int(data.get('depth', 0))
        except (ValueError, TypeError):
            depth = 0
        if depth < 0:
            depth = 0
        try:
            delay = max(0.5, min(float(data.get('delay', 1.0)), 30.0))
        except (ValueError, TypeError):
            delay = 1.0
        exclude = data.get('exclude', [])
        if isinstance(exclude, str):
            exclude = [p.strip() for p in exclude.split(',') if p.strip()]
        job = _start_job(_run_crawl, url, depth, delay, exclude)
        return jsonify(job.to_dict())

    @app.route('/api/resume/<domain>', methods=['POST'])
    def api_resume(domain):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        job = _start_job(_run_resume, domain)
        return jsonify(job.to_dict())

    @app.route('/api/recrawl/<domain>', methods=['POST'])
    def api_recrawl(domain):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        job = _start_job(_run_crawl, f'https://{domain}/', 0, 1.0, [])
        return jsonify(job.to_dict())

    @app.route('/api/build/<domain>', methods=['POST'])
    def api_build(domain):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        job = _start_job(_run_build, domain)
        return jsonify(job.to_dict())

    @app.route('/api/jobs/<job_id>/stop', methods=['POST'])
    def api_stop(job_id):
        if stop_job(job_id):
            return jsonify({"ok": True})
        return jsonify({"error": "ジョブが見つからないか停止できません"}), 404

    @app.route('/api/jobs/active')
    def api_active_jobs():
        with _jobs_lock:
            return jsonify([j.to_dict() for j in _jobs.values() if j.status == 'running'])

    @app.route('/api/jobs/<job_id>/stream')
    def api_stream(job_id):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "ジョブが見つかりません"}), 404
        def generate():
            start_time = time.time()
            while time.time() - start_time < 86400:
                try:
                    msg = job.log_queue.get(timeout=30)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    if msg.get('type') in ('done', 'error'):
                        break
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                    if job.status in ('done', 'error'):
                        break
        return Response(generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.route('/api/jobs/<job_id>')
    def api_job_status(job_id):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "ジョブが見つかりません"}), 404
        return jsonify(job.to_dict())

    # --- エクスポート/インポート ---
    @app.route('/api/export/<domain>')
    def api_export(domain):
        if not is_valid_domain(domain):
            return jsonify({"error": "不正なドメイン名です"}), 400
        d_cache = os.path.join(cache_dir, domain)
        if not os.path.isdir(d_cache):
            return jsonify({"error": "キャッシュが見つかりません"}), 404
        tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
        try:
            with tarfile.open(tmp.name, 'w:gz') as tar:
                tar.add(d_cache, arcname=domain)
            resp = send_file(tmp.name, as_attachment=True,
                             download_name=f"{domain}.tar.gz", mimetype='application/gzip')
            @resp.call_on_close
            def _cleanup():
                try: os.unlink(tmp.name)
                except OSError: pass
            return resp
        except Exception as e:
            os.unlink(tmp.name)
            return jsonify({"error": str(e)}), 500

    def _extract_archive(filepath, dest_dir):
        """zip/tar.gz/tar を dest_dir に展開。トップレベルのフォルダ名を返す"""
        name_lower = filepath.lower()
        if name_lower.endswith('.zip'):
            with zipfile.ZipFile(filepath, 'r') as zf:
                members = zf.namelist()
                if not members:
                    raise ValueError("空のアーカイブです")
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパスがアーカイブに含まれています")
                top = members[0].split('/')[0]
                zf.extractall(dest_dir)
                return top
        else:
            with tarfile.open(filepath, 'r:*') as tar:
                members = tar.getnames()
                if not members:
                    raise ValueError("空のアーカイブです")
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパスがアーカイブに含まれています")
                top = members[0].split('/')[0]
                try:
                    tar.extractall(path=dest_dir, filter='data')
                except TypeError:
                    tar.extractall(path=dest_dir)
                return top

    @app.route('/api/import', methods=['POST'])
    def api_import():
        """zip/tar.gz ファイルをアップロードしてインポート"""
        if 'file' not in request.files:
            return jsonify({"error": "ファイルが指定されていません"}), 400
        f = request.files['file']
        if not f.filename:
            return jsonify({"error": "ファイル名がありません"}), 400
        tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(f.filename)[1], delete=False)
        try:
            f.save(tmp.name)
            domain = _extract_archive(tmp.name, cache_dir)
            os.unlink(tmp.name)
            if not is_valid_domain(domain):
                return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
            job = _start_job(_run_import, domain)
            return jsonify(job.to_dict())
        except (ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return jsonify({"error": str(e)}), 500

    @app.route('/api/import/scan')
    def api_import_scan():
        """インポートフォルダ (/sdcard/ShimaNet/import/) のファイル一覧"""
        files = []
        if os.path.isdir(import_dir):
            for name in sorted(os.listdir(import_dir)):
                lower = name.lower()
                if lower.endswith(('.zip', '.tar.gz', '.tgz', '.tar')):
                    filepath = os.path.join(import_dir, name)
                    size = os.path.getsize(filepath)
                    files.append({"name": name, "size": size, "path": filepath})
        return jsonify({"import_dir": import_dir, "files": files})

    @app.route('/api/import/folder/<filename>', methods=['POST'])
    def api_import_from_folder(filename):
        """インポートフォルダ内の指定ファイルをインポート"""
        filepath = os.path.join(import_dir, filename)
        if not os.path.isfile(filepath):
            return jsonify({"error": f"ファイルが見つかりません: {filename}"}), 404
        try:
            domain = _extract_archive(filepath, cache_dir)
            if not is_valid_domain(domain):
                return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
            job = _start_job(_run_import, domain)
            return jsonify(job.to_dict())
        except (ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/import-local', methods=['POST'])
    def api_import_local():
        name = request.form.get('name', '').strip()
        if not name:
            return jsonify({"error": "データセット名が必要です"}), 400
        dataset_name = re.sub(r'[^\w\-.]', '_', name.strip())
        if not dataset_name:
            dataset_name = 'unnamed'
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "ファイルが指定されていません"}), 400
        d_cache = os.path.join(cache_dir, dataset_name)
        base = os.path.join(d_cache, dataset_name)
        os.makedirs(base, exist_ok=True)
        saved = 0
        for f in files:
            if not f.filename:
                continue
            filename = f.filename.replace('\\', '/')
            parts = filename.split('/')
            if len(parts) > 1:
                filename = '/'.join(parts[1:])
            safe_path = os.path.normpath(filename)
            if safe_path.startswith('..') or safe_path.startswith('/'):
                continue
            dest = os.path.join(base, safe_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.save(dest)
            saved += 1
        if saved == 0:
            return jsonify({"error": "保存できるファイルがありませんでした"}), 400
        job = _start_job(_run_import, dataset_name)
        return jsonify({**job.to_dict(), "saved_files": saved})

    # --- 自作サイト ---
    def _sanitize_site_name(name):
        name = re.sub(r'[^\w\-.]', '_', name.strip().lower())
        return name or 'unnamed'

    @app.route('/api/sites/custom')
    def api_custom_sites():
        result = []
        if not os.path.exists(sites_dir):
            return jsonify(result)
        for name in sorted(os.listdir(sites_dir)):
            site_path = os.path.join(sites_dir, name)
            if not os.path.isdir(site_path):
                continue
            file_count = sum(1 for _, _, files in os.walk(site_path) for f in files)
            catalog_path = os.path.join(site_path, 'catalog.json')
            page_count = 0
            if os.path.exists(catalog_path):
                try:
                    with open(catalog_path, 'r') as f:
                        page_count = len(json.load(f))
                except Exception:
                    pass
            result.append({"name": name, "file_count": file_count, "page_count": page_count})
        return jsonify(result)

    @app.route('/api/sites/custom/create', methods=['POST'])
    def api_create_site():
        name = request.form.get('name', '').strip()
        if not name:
            return jsonify({"error": "サイト名が必要です"}), 400
        site_name = _sanitize_site_name(name)
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "ファイルが指定されていません"}), 400
        site_path = os.path.join(sites_dir, site_name)
        content_dir = os.path.join(site_path, site_name)
        os.makedirs(content_dir, exist_ok=True)
        saved = 0
        for f in files:
            if not f.filename:
                continue
            filename = f.filename.replace('\\', '/')
            parts = filename.split('/')
            if len(parts) > 1:
                filename = '/'.join(parts[1:])
            safe_path = os.path.normpath(filename)
            if safe_path.startswith('..') or safe_path.startswith('/'):
                continue
            dest = os.path.join(content_dir, safe_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.save(dest)
            saved += 1
        if saved == 0:
            return jsonify({"error": "保存できるファイルがありませんでした"}), 400
        # サイトカタログ生成
        catalog = []
        for root, _, files2 in os.walk(content_dir):
            for fname in files2:
                filepath = os.path.join(root, fname)
                if not _is_html(filepath):
                    continue
                relpath = os.path.relpath(filepath, content_dir).replace(os.sep, '/')
                title = _extract_title(filepath)
                url = f'shimanet://{site_name}/{quote(relpath, safe="/:@!$&()*+,;=-._~")}'
                catalog.append({'url': url, 'title': title or relpath, 'path': relpath})
        cat_path = os.path.join(site_path, 'catalog.json')
        with open(cat_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False)
        return jsonify({"name": site_name, "saved_files": saved})

    @app.route('/api/sites/custom/delete/<name>', methods=['POST'])
    def api_delete_site(name):
        import shutil
        site_name = _sanitize_site_name(name)
        site_path = os.path.join(sites_dir, site_name)
        if not os.path.isdir(site_path):
            return jsonify({"error": "サイトが見つかりません"}), 404
        shutil.rmtree(site_path)
        return jsonify({"ok": True})

    @app.route('/api/sites/custom/serve/<name>/<path:path>')
    def api_serve_site(name, path):
        site_name = _sanitize_site_name(name)
        content_dir = os.path.join(sites_dir, site_name, site_name)
        if not os.path.isdir(content_dir):
            content_dir = os.path.join(sites_dir, site_name)
        return send_from_directory(content_dir, path)

    @app.route('/api/sites/custom/catalog/<name>')
    def api_site_catalog(name):
        site_name = _sanitize_site_name(name)
        catalog_path = os.path.join(sites_dir, site_name, 'catalog.json')
        if not os.path.isfile(catalog_path):
            return jsonify([])
        return send_file(catalog_path, mimetype='application/json')

    # --- デバッグ ---
    @app.route('/api/debug/paths')
    def api_debug_paths():
        cache_contents = {}
        if os.path.isdir(cache_dir):
            for name in os.listdir(cache_dir):
                sd = os.path.join(cache_dir, name)
                if os.path.isdir(sd):
                    # 再帰的に最大20ファイル表示
                    file_list = []
                    for root, dirs, files in os.walk(sd):
                        for f in files[:10]:
                            file_list.append(os.path.relpath(os.path.join(root, f), sd))
                        if len(file_list) >= 20:
                            break
                    cache_contents[name] = file_list
        return jsonify({
            "base_dir": base_dir,
            "cache_dir": cache_dir,
            "cache_exists": os.path.isdir(cache_dir),
            "cache_contents": cache_contents,
            "LOCALNET_BASE": os.environ.get('LOCALNET_BASE', 'NOT SET'),
            "python_path": sys.path[:5],
        })

    # --- SPA フォールバック ---
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_spa(path):
        filepath = os.path.join(frontend_dir, path)
        if path and os.path.isfile(filepath):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, 'index.html')

    return app
