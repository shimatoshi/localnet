"""localnet — ローカルインターネット Flask API"""

import os
import json
import time
import queue
from flask import Flask, request, jsonify, send_from_directory, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

from config import PORT, DATASETS_DIR
from jobs import (
    get_job, start_crawl_job, start_build_job,
    get_all_sites, get_all_datasets,
)

app = Flask(__name__, static_folder='static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# === 静的ファイル ===

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


# === データセット API ===

@app.route('/api/datasets')
def api_datasets():
    return jsonify(get_all_datasets())


@app.route('/api/datasets/<name>/download')
def api_dataset_download(name):
    os.makedirs(DATASETS_DIR, exist_ok=True)
    filename = f"{name}.sqlite" if not name.endswith('.sqlite') else name
    filepath = os.path.realpath(os.path.join(DATASETS_DIR, filename))
    if not filepath.startswith(os.path.realpath(DATASETS_DIR) + os.sep):
        return jsonify({"error": "不正なパスです"}), 400
    if os.path.exists(filepath):
        return send_from_directory(
            DATASETS_DIR, filename,
            as_attachment=True,
            mimetype='application/x-sqlite3',
        )
    return jsonify({"error": "データセットが見つかりません"}), 404


# === クロール API ===

@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    data = request.get_json(force=True)
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"error": "URLを指定してください"}), 400

    depth = max(0, min(int(data.get('depth', 2)), 10))
    delay = max(0.5, min(float(data.get('delay', 1.0)), 30.0))
    daily_limit = max(100, min(int(data.get('daily_limit', 5000)), 50000))
    exclude = data.get('exclude', [])
    if isinstance(exclude, str):
        exclude = [p.strip() for p in exclude.split(',') if p.strip()]
    auto_build = bool(data.get('auto_build', True))

    job = start_crawl_job(url, depth, delay, daily_limit, exclude, auto_build)
    return jsonify(job.to_dict())


@app.route('/api/build/<domain>', methods=['POST'])
def api_build(domain):
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_build_job(domain)
    return jsonify(job.to_dict())


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
        max_duration = 3600
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
            yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト（1時間）'})}\n\n"

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
    os.makedirs(DATASETS_DIR, exist_ok=True)
    print(f'localnet starting on port {PORT}')
    print(f'ディレクトリ: {BASE_DIR}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
