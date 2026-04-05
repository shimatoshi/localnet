"""localnet — ローカルインターネット Flask API"""

import os
import time
import subprocess
from flask import Flask, request, jsonify, send_from_directory, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    _VERSION = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'], cwd=BASE_DIR,
    ).decode().strip()
except Exception:
    _VERSION = str(int(time.time()))

from config import PORT, CACHE_BASE
from utils import is_valid_domain
from catalog_builder import search_catalogs, search_images
from jobs import get_all_sites

# --- App ---

FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend', 'dist')

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Blueprint登録
from routes.cache import bp as cache_bp
from routes.crawl import bp as crawl_bp
from routes.transfer import bp as transfer_bp
from routes.sites import bp as sites_bp

app.register_blueprint(cache_bp)
app.register_blueprint(crawl_bp)
app.register_blueprint(transfer_bp)
app.register_blueprint(sites_bp)


@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# === 軽量API ===

@app.route('/assets/<path:path>')
def serve_assets(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), path)


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
    catalog_path = os.path.join(CACHE_BASE, domain, 'catalog.json')
    if not os.path.isfile(catalog_path):
        return jsonify({"error": "カタログが見つかりません"}), 404
    return send_file(catalog_path, mimetype='application/json')


@app.route('/api/sites')
def api_sites():
    return jsonify(get_all_sites())


@app.route('/api/sites/versions')
def api_sites_versions():
    versions = {}
    if os.path.isdir(CACHE_BASE):
        for name in os.listdir(CACHE_BASE):
            catalog = os.path.join(CACHE_BASE, name, 'catalog.json')
            if os.path.isfile(catalog):
                versions[name] = int(os.path.getmtime(catalog))
    return jsonify(versions)


# === SPA フォールバック ===

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    filepath = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(filepath):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, 'index.html')


if __name__ == '__main__':
    print(f'localnet starting on port {PORT}')
    print(f'ディレクトリ: {BASE_DIR}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
