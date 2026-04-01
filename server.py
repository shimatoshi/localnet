"""localnet — ローカルインターネット Flask API"""

import os
import re
import json
import time
import queue
import tarfile
import tempfile
import mimetypes
from flask import Flask, request, jsonify, send_from_directory, Response, send_file
from urllib.parse import unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from config import PORT, CACHE_BASE
from catalog_builder import search_catalogs
from jobs import (
    get_job, stop_job, start_crawl_job, start_resume_job, start_build_job,
    start_import_job, get_all_sites,
)

app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


# === 静的ファイル ===

@app.route('/')
def index():
    resp = send_from_directory('static', 'index.html')
    resp.headers['ETag'] = ''
    resp.headers['Last-Modified'] = ''
    return resp


@app.route('/static/<path:path>')
def static_files(path):
    resp = send_from_directory('static', path)
    resp.headers['ETag'] = ''
    resp.headers['Last-Modified'] = ''
    return resp


# === 検索 API ===

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 50))
    if not q:
        return jsonify([])
    results = search_catalogs(q, limit=limit)
    return jsonify(results)


# === カタログ API ===

@app.route('/api/catalog/<domain>')
def api_catalog(domain):
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    catalog_path = os.path.join(CACHE_BASE, domain, 'catalog.json')
    if not os.path.isfile(catalog_path):
        return jsonify({"error": "カタログが見つかりません"}), 404
    return send_file(catalog_path, mimetype='application/json')


# === キャッシュファイル配信 ===

@app.route('/api/cache/<domain>/<path:subpath>')
def api_cache(domain, subpath):
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400

    # URLデコード
    subpath = unquote(subpath)

    base = os.path.join(CACHE_BASE, domain, domain)
    if not os.path.isdir(base):
        base = os.path.join(CACHE_BASE, domain)

    filepath = os.path.realpath(os.path.join(base, subpath))
    if not filepath.startswith(os.path.realpath(base) + os.sep):
        return jsonify({"error": "不正なパスです"}), 400

    if not os.path.isfile(filepath):
        return '', 404

    mime, _ = mimetypes.guess_type(filepath)
    if not mime:
        # ヘッダで判定
        try:
            with open(filepath, 'rb') as f:
                head = f.read(256)
            if head.startswith(b'\x89PNG'):
                mime = 'image/png'
            elif head.startswith(b'\xff\xd8\xff'):
                mime = 'image/jpeg'
            elif head.startswith(b'GIF8'):
                mime = 'image/gif'
            elif head[:4] == b'RIFF' and head[8:12] == b'WEBP':
                mime = 'image/webp'
            elif b'<html' in head.lower() or b'<!doctype' in head.lower():
                mime = 'text/html'
            else:
                mime = 'application/octet-stream'
        except Exception:
            mime = 'application/octet-stream'

    # HTMLファイルのcharset検出
    if mime and mime.startswith('text/html'):
        try:
            with open(filepath, 'rb') as f:
                head = f.read(4096)
            head_lower = head.lower()
            charset = None
            # <meta charset="...">
            m = re.search(rb'<meta\s[^>]*charset=["\']?([a-zA-Z0-9_-]+)', head_lower)
            if m:
                charset = m.group(1).decode('ascii', errors='ignore')
            # <meta http-equiv="content-type" content="text/html; charset=...">
            if not charset:
                m = re.search(rb'content-type[^>]*charset=([a-zA-Z0-9_-]+)', head_lower)
                if m:
                    charset = m.group(1).decode('ascii', errors='ignore')
            if charset:
                mime = f'text/html; charset={charset}'
        except Exception:
            pass

    return send_file(filepath, mimetype=mime)


# === エクスポート/インポート API ===

@app.route('/api/export/<domain>')
def api_export(domain):
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        return jsonify({"error": "キャッシュが見つかりません"}), 404

    tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    try:
        with tarfile.open(tmp.name, 'w:gz') as tar:
            tar.add(cache_dir, arcname=domain)
        return send_file(
            tmp.name,
            as_attachment=True,
            download_name=f"{domain}.tar.gz",
            mimetype='application/gzip',
        )
    except Exception as e:
        os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


@app.route('/api/import', methods=['POST'])
def api_import():
    if 'file' not in request.files:
        return jsonify({"error": "ファイルが指定されていません"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "ファイル名がありません"}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    try:
        f.save(tmp.name)
        with tarfile.open(tmp.name, 'r:*') as tar:
            members = tar.getnames()
            if not members:
                os.unlink(tmp.name)
                return jsonify({"error": "空のアーカイブです"}), 400
            for m in members:
                if m.startswith('/') or '..' in m:
                    os.unlink(tmp.name)
                    return jsonify({"error": "不正なパスがアーカイブに含まれています"}), 400
            domain = members[0].split('/')[0]
            if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
                os.unlink(tmp.name)
                return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
            tar.extractall(path=CACHE_BASE)

        os.unlink(tmp.name)
        job = start_import_job(domain)
        return jsonify(job.to_dict())
    except tarfile.TarError as e:
        os.unlink(tmp.name)
        return jsonify({"error": f"アーカイブ解凍エラー: {e}"}), 400
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


# === クロール API ===

@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    data = request.get_json(force=True)
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"error": "URLを指定してください"}), 400

    depth = int(data.get('depth', 0))
    if depth < 0:
        depth = 0
    delay = max(0.5, min(float(data.get('delay', 1.0)), 30.0))
    exclude = data.get('exclude', [])
    if isinstance(exclude, str):
        exclude = [p.strip() for p in exclude.split(',') if p.strip()]

    job = start_crawl_job(url, depth, delay, exclude)
    return jsonify(job.to_dict())


@app.route('/api/resume/<domain>', methods=['POST'])
def api_resume(domain):
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_resume_job(domain)
    return jsonify(job.to_dict())


@app.route('/api/build/<domain>', methods=['POST'])
def api_build(domain):
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_build_job(domain)
    return jsonify(job.to_dict())


@app.route('/api/jobs/<job_id>/stop', methods=['POST'])
def api_stop(job_id):
    if stop_job(job_id):
        return jsonify({"ok": True})
    return jsonify({"error": "ジョブが見つからないか停止できません"}), 404


@app.route('/api/jobs/active')
def api_active_jobs():
    from jobs import _jobs, _jobs_lock
    with _jobs_lock:
        active = [j.to_dict() for j in _jobs.values() if j.status == 'running']
    return jsonify(active)


@app.route('/api/sites')
def api_sites():
    return jsonify(get_all_sites())


# === ジョブ API ===

@app.route('/api/jobs/<job_id>/stream')
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


@app.route('/api/jobs/<job_id>')
def api_job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404
    return jsonify(job.to_dict())


if __name__ == '__main__':
    print(f'localnet starting on port {PORT}')
    print(f'ディレクトリ: {BASE_DIR}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
