"""localnet Flask server — APK版
ルートの分割モジュールをimportして組み立てるだけのブートストラップ。
ビジネスロジックは各モジュールに委譲する。"""

import os
import sys
import time

from flask import Flask, request, jsonify, send_from_directory, send_file


def create_app(base_dir, port):
    # 環境変数でモジュール群にbase_dirを伝達
    os.environ['LOCALNET_BASE'] = base_dir
    os.environ['LOCALNET_PORT'] = str(port)

    # モジュールパス設定（APK内のPythonソース群を参照可能にする）
    src_dir = os.path.dirname(os.path.abspath(__file__))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    frontend_dir = os.path.join(base_dir, 'frontend', 'dist')
    os.makedirs(os.path.join(base_dir, 'cache'), exist_ok=True)
    os.makedirs(os.path.join(base_dir, 'sites'), exist_ok=True)
    import_dir = os.environ.get('SHIMANET_IMPORT_DIR', os.path.join(base_dir, 'import'))
    os.makedirs(import_dir, exist_ok=True)

    app = Flask(__name__, static_folder=frontend_dir)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    _VERSION = str(int(time.time()))

    # --- 共有モジュールimport ---
    from config import CACHE_BASE
    from utils import is_valid_domain
    from catalog_builder import search_catalogs, search_images
    from jobs import get_all_sites

    # --- Blueprint登録 ---
    from routes.cache import bp as cache_bp
    from routes.crawl import bp as crawl_bp
    from routes.transfer import bp as transfer_bp
    from routes.sites import bp as sites_bp

    app.register_blueprint(cache_bp)
    app.register_blueprint(crawl_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(sites_bp)

    # --- CORS ---
    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return response

    # --- 軽量API ---
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
        cache_dir = CACHE_BASE
        if os.path.isdir(cache_dir):
            for name in os.listdir(cache_dir):
                catalog = os.path.join(cache_dir, name, 'catalog.json')
                if os.path.isfile(catalog):
                    versions[name] = int(os.path.getmtime(catalog))
        return jsonify(versions)

    # --- SPA フォールバック ---
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_spa(path):
        filepath = os.path.join(frontend_dir, path)
        if path and os.path.isfile(filepath):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, 'index.html')

    return app
