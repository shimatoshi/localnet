"""localnet — ローカルインターネット Flask API"""

import os
import time
import subprocess
from flask import Flask, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    _VERSION = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'], cwd=BASE_DIR,
    ).decode().strip()
except Exception:
    _VERSION = str(int(time.time()))

from config import PORT

# --- App ---

FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend', 'dist')

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Blueprint登録
from routes.search import bp as search_bp
from routes.cache import bp as cache_bp
from routes.crawl import bp as crawl_bp
from routes.transfer import bp as transfer_bp
from routes.sites import bp as sites_bp
from routes.datasets import bp as datasets_bp

app.register_blueprint(search_bp)
app.register_blueprint(cache_bp)
app.register_blueprint(crawl_bp)
app.register_blueprint(transfer_bp)
app.register_blueprint(sites_bp)
app.register_blueprint(datasets_bp)


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# === バージョン ===

@app.route('/api/version')
@app.route('/api/version/<path:_>')
def api_version(_=None):
    return jsonify({"version": _VERSION})


# === SPA配信 ===

@app.route('/assets/<path:path>')
def serve_assets(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), path)


@app.route('/sw.js')
def serve_sw():
    resp = send_from_directory(FRONTEND_DIR, 'sw.js')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    filepath = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(filepath):
        resp = send_from_directory(FRONTEND_DIR, path)
        if path == 'index.html':
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    resp = send_from_directory(FRONTEND_DIR, 'index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


if __name__ == '__main__':
    print(f'localnet starting on port {PORT}')
    print(f'ディレクトリ: {BASE_DIR}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
