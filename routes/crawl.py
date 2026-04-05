"""クロール・ジョブ操作API + SSEストリーミング + WebViewクロール"""

import os
import shutil
import json
import time
import queue
import threading
import base64
from urllib.parse import urlparse, urljoin
from flask import Blueprint, request, jsonify, Response

from config import CACHE_BASE
from utils import is_valid_domain

from jobs import (
    get_job, stop_job, start_crawl_job, start_resume_job,
    start_build_job, start_recrawl_job, get_active_jobs,
)

bp = Blueprint('crawl', __name__)


@bp.route('/api/crawl', methods=['POST'])
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

    job = start_crawl_job(url, depth, delay, exclude)
    return jsonify(job.to_dict())


@bp.route('/api/resume/<domain>', methods=['POST'])
def api_resume(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_resume_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/recrawl/<domain>', methods=['POST'])
def api_recrawl(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_recrawl_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/build/<domain>', methods=['POST'])
def api_build(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_build_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/delete/<domain>', methods=['POST'])
def api_delete(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        return jsonify({"error": "キャッシュが見つかりません"}), 404
    shutil.rmtree(cache_dir)
    return jsonify({"ok": True})


@bp.route('/api/jobs/<job_id>/stop', methods=['POST'])
def api_stop(job_id):
    if stop_job(job_id):
        return jsonify({"ok": True})
    return jsonify({"error": "ジョブが見つからないか停止できません"}), 404


@bp.route('/api/jobs/active')
def api_active_jobs():
    return jsonify(get_active_jobs())


@bp.route('/api/jobs/<job_id>/stream')
def api_stream(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404

    def generate():
        max_duration = 86400
        start_time = time.time()
        while time.time() - start_time < max_duration:
            try:
                msg = job.log_queue.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get('type') in ('done', 'error'):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                if job.status in ('done', 'error'):
                    break
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト（24時間）'})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@bp.route('/api/jobs/<job_id>')
def api_job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404
    return jsonify(job.to_dict())


# === WebViewクロール（APK用、Cloudflare TLS対策） ===

_wv_session = {
    'active': False, 'queue': [], 'visited': set(), 'job': None,
    'domain': None, 'max_depth': 0, 'exclude': [], 'page_count': 0,
    'pending': False, 'current_depth': 0, 'lock': threading.Lock(),
}


@bp.route('/api/webview-crawl/next')
def api_wv_next():
    with _wv_session['lock']:
        if not _wv_session['active']:
            return jsonify({"url": None, "done": False})
        while _wv_session['queue']:
            url, depth = _wv_session['queue'].pop(0)
            url = url.split('#')[0]
            if url in _wv_session['visited']:
                continue
            if _wv_session['max_depth'] > 0 and depth > _wv_session['max_depth']:
                continue
            domain = _wv_session['domain']
            if urlparse(url).netloc != domain:
                continue
            _wv_session['visited'].add(url)
            _wv_session['pending'] = True
            _wv_session['current_depth'] = depth
            return jsonify({"url": url, "depth": depth, "done": False})
        if _wv_session['pending']:
            return jsonify({"url": None, "done": False})
        if _wv_session['page_count'] == 0:
            return jsonify({"url": None, "done": False})
        job = _wv_session['job']
        _wv_session['active'] = False
    if job and job.status == 'running':
        job.log(f"取得完了: {_wv_session['page_count']} ページ")
        job.log("--- カタログ生成中 ---")
        threading.Thread(target=lambda: _wv_finish(job), daemon=True).start()
    return jsonify({"url": None, "done": True})


def _wv_finish(job):
    try:
        from catalog_builder import build_catalog
        build_catalog(job.domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)


@bp.route('/api/webview-crawl/result', methods=['POST'])
def api_wv_result():
    data = request.get_json(silent=True)
    if not data:
        try:
            data = json.loads(request.get_data(as_text=True))
        except Exception:
            pass
    if not data or not data.get('url'):
        with _wv_session['lock']:
            _wv_session['pending'] = False
        return jsonify({"error": "no url"}), 400

    page_url = data['url']
    error = data.get('error', '')
    html = data.get('html', '')
    html_b64 = data.get('html_b64', '')
    if html_b64 and not html:
        html = base64.b64decode(html_b64).decode('utf-8', errors='replace')

    with _wv_session['lock']:
        if not _wv_session['active']:
            return jsonify({"ok": False})
        domain = _wv_session['domain']
        job = _wv_session['job']
        _wv_session['pending'] = False

    if error:
        if job:
            job.log(f"ERR {page_url[:60]}: {error}")
        return jsonify({"ok": True, "skipped": True})

    if not domain or not html:
        return jsonify({"ok": False})

    # ファイル保存（生HTML。リソースのインライン化はWebViewのTLS制約上不可）
    parsed = urlparse(page_url)
    path = parsed.path.lstrip('/')
    if not path or path.endswith('/'):
        path += 'index.html'
    if not os.path.splitext(path)[1]:
        path += '.html'
    filepath = os.path.join(CACHE_BASE, domain, domain, path)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    with _wv_session['lock']:
        _wv_session['page_count'] += 1
        count = _wv_session['page_count']

    if job:
        display = page_url[:75] + '...' if len(page_url) > 75 else page_url
        job.log(f"[{count}] {display}")

    # リンク抽出
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            abs_url = urljoin(page_url, href).split('#')[0]
            if urlparse(abs_url).netloc == domain:
                with _wv_session['lock']:
                    if abs_url not in _wv_session['visited']:
                        next_depth = _wv_session.get('current_depth', 0) + 1
                        _wv_session['queue'].append((abs_url, next_depth))
    except Exception:
        pass

    return jsonify({"ok": True, "count": count})


@bp.route('/api/webview-crawl/stop', methods=['POST'])
def api_wv_stop():
    with _wv_session['lock']:
        job = _wv_session['job']
        _wv_session['active'] = False
        _wv_session['queue'] = []
        _wv_session['pending'] = False
    if job and job.status == 'running':
        job.log("--- 停止: カタログ生成中 ---")
        threading.Thread(target=lambda: _wv_finish(job), daemon=True).start()
    return jsonify({"ok": True})


def start_webview_crawl(job, url, depth, exclude):
    """WebView方式でクロール開始（jobs.pyから呼ばれる）"""
    domain = urlparse(url).netloc
    with _wv_session['lock']:
        _wv_session['active'] = True
        _wv_session['queue'] = [(url, 0)]
        _wv_session['visited'] = set()
        _wv_session['job'] = job
        _wv_session['domain'] = domain
        _wv_session['max_depth'] = depth
        _wv_session['exclude'] = exclude if isinstance(exclude, list) else []
        _wv_session['page_count'] = 0
        _wv_session['pending'] = False
    job._wv_session = _wv_session
    os.makedirs(os.path.join(CACHE_BASE, domain, domain), exist_ok=True)
